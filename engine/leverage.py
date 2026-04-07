"""Leveraged ETF scanner — aggressive mode for 3x ETFs.

Scans SQQQ/TQQQ/SPXU/UPRO based on market regime and times
entries using pullback + volume confirmation + news sentiment.
5 checks + AI catalyst scoring + position sizing.
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from engine.config import TTRadeConfig
from engine.market_data import get_daily_bars, compute_sma, compute_atr, average_volume
from engine.market_state import MarketStateResult
from engine.models import MarketState

logger = logging.getLogger(__name__)


# Map regime to which leveraged ETF to trade
LEVERAGE_MAP = {
    MarketState.TREND_DOWN: [
        {"ticker": "SQQQ", "tracks": "QQQ", "direction": "short_market", "leverage": 3},
        {"ticker": "SPXU", "tracks": "SPY", "direction": "short_market", "leverage": 3},
        {"ticker": "SOXS", "tracks": "SOXX", "direction": "short_semis", "leverage": 3},
    ],
    MarketState.TREND_UP: [
        {"ticker": "TQQQ", "tracks": "QQQ", "direction": "long_market", "leverage": 3},
        {"ticker": "UPRO", "tracks": "SPY", "direction": "long_market", "leverage": 3},
        {"ticker": "SOXL", "tracks": "SOXX", "direction": "long_semis", "leverage": 3},
    ],
}


@dataclass
class LeverageSignal:
    ticker: str
    tracks: str
    direction: str
    leverage: int
    price: float
    action: str  # "buy", "hold", "avoid"
    score: float  # 0-100
    entry_price: float | None
    stop_price: float
    target_price: float
    position_size_shares: int
    position_size_dollars: float
    checks: dict  # individual check results
    timestamp: datetime
    news_headlines: list[str] = field(default_factory=list)
    ai_catalyst: dict | None = None  # AI analysis of news impact


def _check_pullback(bars: pd.DataFrame, regime: MarketState, config: TTRadeConfig) -> tuple[bool, float]:
    """Check if the leveraged ETF is pulling back into a buy zone.

    For SQQQ in TREND_DOWN: SQQQ goes UP when market drops, so we want
    SQQQ pulling BACK (dipping) before resuming its uptrend.
    """
    close = bars["Close"]
    sma = compute_sma(close, period=config.ma_period)
    sma_clean = sma.dropna()
    if len(sma_clean) < 2:
        return False, 0.0

    current = float(close.iloc[-1])
    sma_val = float(sma_clean.iloc[-1])
    distance_pct = abs(current - sma_val) / sma_val

    # For inverse ETFs in TREND_DOWN: price should be near or slightly below SMA
    # (pulling back before next leg up)
    # For bull ETFs in TREND_UP: same logic — near SMA on a dip
    in_zone = distance_pct <= config.pullback_zone_pct * 2  # wider zone for leveraged
    return in_zone, distance_pct


def _check_volume(bars: pd.DataFrame, config: TTRadeConfig) -> tuple[bool, float]:
    """Check if volume is confirming the move."""
    avg_vol = average_volume(bars["Volume"], period=config.ma_period)
    current_vol = float(bars["Volume"].iloc[-1])
    ratio = current_vol / avg_vol if avg_vol > 0 else 0
    # Lower bar for leveraged ETFs — 0.8x is fine (they're liquid)
    return ratio >= 0.8, ratio


def _check_trend_strength(bars: pd.DataFrame) -> tuple[bool, float]:
    """Check if the leveraged ETF itself is trending (not chopping)."""
    close = bars["Close"]
    sma5 = compute_sma(close, period=5)
    sma20 = compute_sma(close, period=20)
    sma5_clean = sma5.dropna()
    sma20_clean = sma20.dropna()

    if len(sma5_clean) < 1 or len(sma20_clean) < 1:
        return False, 0.0

    # 5 SMA vs 20 SMA — trending when aligned
    sma5_val = float(sma5_clean.iloc[-1])
    sma20_val = float(sma20_clean.iloc[-1])
    spread_pct = (sma5_val - sma20_val) / sma20_val * 100
    trending = abs(spread_pct) > 0.5  # at least 0.5% separation
    return trending, spread_pct


def _fetch_news_rss(query: str) -> list[str]:
    """Fetch headlines from Google News RSS directly (runs locally, not blocked)."""
    import re
    import requests as _requests
    from urllib.parse import quote

    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = _requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if not resp.ok:
            return []
        xml = resp.text
        titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", xml)
        # Skip first title (feed title), return up to 10
        return [t.strip() for t in titles[1:11] if t.strip()]
    except Exception:
        return []


def _fetch_market_news(tracked_ticker: str) -> list[str]:
    """Fetch ticker-specific + broad market/geopolitical news."""
    queries = [
        f"{tracked_ticker} stock",
        "stock market today",
        "geopolitical risk market",
    ]
    all_headlines = []
    for q in queries:
        all_headlines.extend(_fetch_news_rss(q))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for h in all_headlines:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return unique


def _check_news_sentiment(tracked_ticker: str, direction: str) -> tuple[bool, float, list[str]]:
    """Fetch news for the underlying ticker + broad market and score sentiment.

    Returns (aligned, sentiment_score, headlines) where:
    - aligned: True if news sentiment matches our trade direction
    - sentiment_score: -1.0 (bearish) to +1.0 (bullish)
    - headlines: list of recent headline strings
    """
    # Fetch directly from local machine (not blocked by Google like CF Workers)
    headlines = _fetch_market_news(tracked_ticker)

    if not headlines:
        return True, 0.0, []  # no news = neutral, don't block

    # Simple keyword scoring — fast, no AI needed for this step
    bearish_words = [
        "crash", "plunge", "tumble", "selloff", "sell-off", "fear", "war", "strike",
        "bomb", "attack", "deadline", "threat", "sanctions", "recession", "layoff",
        "downgrade", "decline", "crisis", "collapse", "tank", "dump", "risk",
        "tariff", "retaliation", "escalat", "concern", "warn", "die", "dead",
    ]
    bullish_words = [
        "rally", "surge", "soar", "boom", "deal", "agreement", "peace", "record",
        "upgrade", "beat", "strong", "growth", "gain", "recover", "optimis",
        "breakthrough", "ceasefire", "resolve",
    ]

    bearish_hits = 0
    bullish_hits = 0
    combined = " ".join(headlines).lower()
    for w in bearish_words:
        if w in combined:
            bearish_hits += 1
    for w in bullish_words:
        if w in combined:
            bullish_hits += 1

    total = bearish_hits + bullish_hits
    if total == 0:
        return True, 0.0, headlines

    sentiment = (bullish_hits - bearish_hits) / total  # -1 to +1

    # For short_market direction: bearish news is GOOD (aligned)
    # For long_market direction: bullish news is GOOD (aligned)
    if "short" in direction:
        aligned = sentiment <= 0  # bearish or neutral = good for shorts
    else:
        aligned = sentiment >= 0  # bullish or neutral = good for longs

    return aligned, sentiment, headlines


def _get_ai_catalyst(
    ticker: str, tracks: str, direction: str,
    headlines: list[str], market_state: str, price: float,
) -> dict | None:
    """Ask Claude to analyze news catalyst impact on the leveraged ETF trade."""
    if not headlines:
        return None

    from engine.ai_analyst import analyze_signal

    # Reuse the existing AI endpoint with a tailored prompt
    result = analyze_signal(
        ticker=ticker,
        direction="bearish" if "short" in direction else "bullish",
        signal_score=75.0,
        component_scores={"news_catalyst": "leveraged_etf_scan"},
        market_state=market_state,
        gate_results=[{
            "gate_name": "news_catalyst", "passed": True,
            "measured_value": f"{len(headlines)} headlines", "threshold": "sentiment_aligned",
        }],
        recent_prices=[{"date": "today", "open": price, "high": price, "low": price, "close": price, "volume": 0}],
        news_headlines=headlines,
    )

    if result:
        return {
            "conviction": result.conviction,
            "reasoning": result.reasoning,
            "risk_factors": result.risk_factors,
            "trade_quality": result.trade_quality,
            "summary": result.summary,
        }
    return None


def _check_not_overextended(bars: pd.DataFrame, config: TTRadeConfig) -> tuple[bool, float]:
    """Don't buy if already overextended from SMA."""
    close = bars["Close"]
    sma = compute_sma(close, period=config.ma_period)
    sma_clean = sma.dropna()
    if len(sma_clean) < 1:
        return True, 0.0

    current = float(close.iloc[-1])
    sma_val = float(sma_clean.iloc[-1])
    distance_pct = (current - sma_val) / sma_val

    # Don't chase if >8% above SMA (for leveraged, that's a big move already)
    overextended = abs(distance_pct) > 0.08
    return not overextended, distance_pct


def scan_leverage(
    market_state: MarketStateResult,
    config: TTRadeConfig,
    account_value: float = 1000.0,
) -> list[LeverageSignal]:
    """Scan leveraged ETFs and return signals."""
    if market_state.state == MarketState.CHOP:
        logger.info("CHOP regime — no leveraged ETF trades")
        return []

    candidates = LEVERAGE_MAP.get(market_state.state, [])
    signals = []

    for candidate in candidates:
        ticker = candidate["ticker"]
        try:
            bars = get_daily_bars(ticker, period_days=60)
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", ticker, e)
            continue

        current_price = float(bars["Close"].iloc[-1])
        atr = compute_atr(bars, period=config.atr_period)
        atr_val = float(atr.dropna().iloc[-1]) if len(atr.dropna()) > 0 else current_price * 0.03

        # Run 5 checks (4 technical + news sentiment)
        pullback_ok, pullback_dist = _check_pullback(bars, market_state.state, config)
        volume_ok, vol_ratio = _check_volume(bars, config)
        trend_ok, trend_spread = _check_trend_strength(bars)
        not_extended, extension = _check_not_overextended(bars, config)
        news_ok, sentiment, headlines = _check_news_sentiment(
            candidate["tracks"], candidate["direction"],
        )

        checks = {
            "pullback": {"passed": pullback_ok, "value": f"{pullback_dist:.3f}"},
            "volume": {"passed": volume_ok, "value": f"{vol_ratio:.2f}x"},
            "trend": {"passed": trend_ok, "value": f"{trend_spread:+.2f}%"},
            "not_overextended": {"passed": not_extended, "value": f"{extension:+.2f}"},
            "news_sentiment": {"passed": news_ok, "value": f"{sentiment:+.2f}"},
        }

        passed = sum(1 for c in checks.values() if c["passed"])
        score = (passed / 5) * 100

        # Position sizing — risk 10% of account, stop at 1.5x ATR
        stop_distance = atr_val * 1.5
        stop_price = current_price - stop_distance
        risk_per_share = stop_distance
        max_risk = account_value * 0.10  # 10% of account
        shares = int(max_risk / risk_per_share) if risk_per_share > 0 else 0
        shares = min(shares, int(account_value * 0.50 / current_price))  # max 50% in one position
        position_dollars = shares * current_price

        # Target: 2x risk (2R trade), boost to 3R if strong catalyst
        target_multiplier = 3.0 if (news_ok and abs(sentiment) >= 0.5) else 2.0
        target_price = current_price + (stop_distance * target_multiplier)

        # Action decision — news can upgrade hold→buy
        if passed >= 4 and pullback_ok:
            action = "buy"
        elif passed >= 3 and pullback_ok:
            action = "buy"
        elif passed >= 2:
            action = "hold"
        else:
            action = "avoid"

        # AI catalyst analysis for buy signals with headlines
        ai_catalyst = None
        if action == "buy" and headlines:
            try:
                ai_catalyst = _get_ai_catalyst(
                    ticker, candidate["tracks"], candidate["direction"],
                    headlines, market_state.state.value, current_price,
                )
                if ai_catalyst:
                    logger.info("AI catalyst for %s: conviction=%s quality=%s",
                                ticker, ai_catalyst["conviction"], ai_catalyst["trade_quality"])
                    # AI can downgrade if catalyst is misleading
                    if ai_catalyst["trade_quality"] == "PASS":
                        action = "hold"
                        logger.warning("AI downgraded %s from buy to hold (PASS quality)", ticker)
            except Exception as e:
                logger.warning("AI catalyst analysis failed for %s: %s", ticker, e)

        signals.append(LeverageSignal(
            ticker=ticker, tracks=candidate["tracks"],
            direction=candidate["direction"], leverage=candidate["leverage"],
            price=current_price, action=action, score=score,
            entry_price=current_price if action == "buy" else None,
            stop_price=round(stop_price, 2),
            target_price=round(target_price, 2),
            position_size_shares=shares,
            position_size_dollars=round(position_dollars, 2),
            checks=checks, timestamp=datetime.now(),
            news_headlines=headlines, ai_catalyst=ai_catalyst,
        ))

    signals.sort(key=lambda s: (-s.score, s.ticker))
    return signals

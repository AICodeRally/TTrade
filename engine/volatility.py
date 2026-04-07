"""Commodity & volatility scanner — oil, gold, nat gas, VIX.

Scans leveraged instruments across commodity sectors for three strategies:
1. Momentum/Trend — ride directional moves with tight stops
2. Grid — bidirectional capture on range-bound instruments
3. Mean Reversion — fade overextended moves back to SMA

Each instrument gets scored on all three strategies and the best
is recommended. Supports both bull and bear leveraged ETFs per sector.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from engine.config import TTRadeConfig
from engine.market_data import compute_sma, compute_atr

logger = logging.getLogger(__name__)


# Sector → pairs of leveraged instruments (bull + bear)
VOLATILITY_UNIVERSE = {
    "oil": {
        "name": "Crude Oil",
        "bull": {"ticker": "UCO", "desc": "2x Crude Oil Bull", "leverage": 2},
        "bear": {"ticker": "SCO", "desc": "2x Crude Oil Bear", "leverage": 2},
        "underlying": "CL=F",
        "news_query": "oil price crude",
    },
    "gold_miners": {
        "name": "Gold Miners",
        "bull": {"ticker": "JNUG", "desc": "2x Jr Gold Miners Bull", "leverage": 2},
        "bear": {"ticker": "JDST", "desc": "2x Jr Gold Miners Bear", "leverage": 2},
        "underlying": "GDX",
        "news_query": "gold price miners",
    },
    "gold": {
        "name": "Gold",
        "bull": {"ticker": "NUGT", "desc": "2x Gold Miners Bull", "leverage": 2},
        "bear": {"ticker": "DUST", "desc": "2x Gold Miners Bear", "leverage": 2},
        "underlying": "GLD",
        "news_query": "gold price",
    },
    "nat_gas": {
        "name": "Natural Gas",
        "bull": {"ticker": "BOIL", "desc": "2x Natural Gas Bull", "leverage": 2},
        "bear": {"ticker": "KOLD", "desc": "2x Natural Gas Bear", "leverage": 2},
        "underlying": "UNG",
        "news_query": "natural gas price",
    },
    "vix": {
        "name": "VIX / Fear",
        "bull": {"ticker": "UVXY", "desc": "1.5x VIX Futures", "leverage": 1.5},
        "bear": {"ticker": "SVXY", "desc": "0.5x Inverse VIX", "leverage": 0.5},
        "underlying": "^VIX",
        "news_query": "stock market volatility VIX",
    },
    "biotech": {
        "name": "Biotech",
        "bull": {"ticker": "LABU", "desc": "3x Biotech Bull", "leverage": 3},
        "bear": {"ticker": "LABD", "desc": "3x Biotech Bear", "leverage": 3},
        "underlying": "XBI",
        "news_query": "biotech stocks FDA",
    },
    "energy": {
        "name": "Energy Sector",
        "bull": {"ticker": "ERX", "desc": "2x Energy Bull", "leverage": 2},
        "bear": {"ticker": "ERY", "desc": "2x Energy Bear", "leverage": 2},
        "underlying": "XLE",
        "news_query": "energy stocks oil",
    },
}


@dataclass
class StrategyScore:
    name: str           # "momentum", "grid", "mean_reversion"
    score: float        # 0-100
    action: str         # "trade", "watch", "avoid"
    params: dict        # strategy-specific parameters
    est_daily_pnl: float
    est_weekly_pnl: float


@dataclass
class VolatilitySignal:
    sector: str
    sector_name: str
    bull_ticker: str
    bear_ticker: str
    bull_price: float
    bear_price: float
    underlying_ticker: str
    underlying_price: float
    # Volatility metrics
    daily_range_pct: float
    atr_pct: float
    volatility_rank: str    # "extreme", "high", "medium", "low"
    # Trend metrics
    trend: str              # "strong_up", "up", "range", "down", "strong_down"
    trend_strength: float   # 0-100
    rsi: float
    sma20_dist_pct: float
    # Strategy recommendations
    best_strategy: StrategyScore
    all_strategies: list[StrategyScore]
    recommended_ticker: str     # which side to trade (bull or bear)
    recommended_side: str       # "bull" or "bear"
    # Position sizing
    position_size: float
    stop_pct: float
    target_pct: float
    shares: int
    est_win_dollars: float
    est_loss_dollars: float
    # Metadata
    score: float            # overall opportunity score 0-100
    checks: dict
    timestamp: datetime
    news_headlines: list[str] = field(default_factory=list)


def _fetch_bars(ticker: str, period_days: int = 60) -> pd.DataFrame:
    """Fetch daily bars via yfinance."""
    import yfinance as yf
    data = yf.download(ticker, period=f"{period_days}d", interval="1d", progress=False)
    if data.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    return data


def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta).clip(lower=0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_clean = rsi.dropna()
    return float(rsi_clean.iloc[-1]) if len(rsi_clean) > 0 else 50.0


def _analyze_trend(bars: pd.DataFrame) -> tuple[str, float, float]:
    """Analyze trend direction and strength.

    Returns (trend_label, strength_0_100, sma20_distance_pct).
    """
    close = bars["Close"]
    sma5 = compute_sma(close, period=5).dropna()
    sma20 = compute_sma(close, period=20).dropna()
    sma50 = compute_sma(close, period=50).dropna()

    if len(sma20) < 1:
        return "range", 0.0, 0.0

    current = float(close.iloc[-1])
    sma20_val = float(sma20.iloc[-1])
    sma20_dist = (current - sma20_val) / sma20_val * 100

    # Trend strength from SMA alignment
    strength = 0.0
    if len(sma5) >= 1 and len(sma50) >= 1:
        sma5_val = float(sma5.iloc[-1])
        sma50_val = float(sma50.iloc[-1])

        # Price above/below all SMAs = strong trend
        if current > sma5_val > sma20_val > sma50_val:
            strength = min(abs(sma20_dist) * 10, 100)
            trend = "strong_up" if strength > 50 else "up"
        elif current < sma5_val < sma20_val < sma50_val:
            strength = min(abs(sma20_dist) * 10, 100)
            trend = "strong_down" if strength > 50 else "down"
        else:
            strength = max(0, 50 - abs(sma20_dist) * 5)
            trend = "range"
    else:
        trend = "up" if sma20_dist > 2 else "down" if sma20_dist < -2 else "range"
        strength = min(abs(sma20_dist) * 10, 100)

    return trend, strength, sma20_dist


def _analyze_volatility(bars: pd.DataFrame) -> tuple[str, float, float]:
    """Assess volatility level.

    Returns (rank, atr_pct, daily_range_pct).
    """
    close = bars["Close"]
    atr = compute_atr(bars, period=14).dropna()
    if len(atr) < 1:
        return "low", 0.0, 0.0

    current_price = float(close.iloc[-1])
    atr_val = float(atr.iloc[-1])
    atr_pct = atr_val / current_price * 100

    daily_ranges = (bars["High"] - bars["Low"]) / close * 100
    avg_range = float(daily_ranges.tail(14).mean())

    if atr_pct > 8:
        rank = "extreme"
    elif atr_pct > 5:
        rank = "high"
    elif atr_pct > 3:
        rank = "medium"
    else:
        rank = "low"

    return rank, atr_pct, avg_range


def _score_momentum(
    trend: str, strength: float, rsi: float,
    atr_pct: float, daily_range: float, price: float,
    account: float,
) -> StrategyScore:
    """Score momentum/trend-following strategy."""
    score = 0.0
    params = {}

    # Strong trend = high score
    if trend in ("strong_up", "strong_down"):
        score += 40
    elif trend in ("up", "down"):
        score += 25
    else:
        score += 5  # range = bad for momentum

    # RSI confirmation (not overextended)
    if trend in ("strong_up", "up") and 45 < rsi < 70:
        score += 20
        params["rsi_zone"] = "confirmed"
    elif trend in ("strong_down", "down") and 30 < rsi < 55:
        score += 20
        params["rsi_zone"] = "confirmed"
    elif 30 < rsi < 70:
        score += 10
        params["rsi_zone"] = "neutral"
    else:
        params["rsi_zone"] = "overextended"

    # Volatility bonus (more range = more profit potential)
    if daily_range > 6:
        score += 25
    elif daily_range > 4:
        score += 20
    elif daily_range > 2:
        score += 10

    # Trend strength bonus
    score += min(strength / 100 * 15, 15)

    score = min(score, 100)

    # Position sizing: 1.5x ATR stop, 2.5R target
    stop_pct = atr_pct * 1.5
    target_pct = stop_pct * 2.5
    risk_dollars = account * 0.10
    shares = int(risk_dollars / (price * stop_pct / 100)) if stop_pct > 0 else 0
    shares = min(shares, int(account * 0.50 / price))
    est_daily = shares * price * daily_range / 100 * 0.3  # capture ~30% of range
    est_weekly = est_daily * 5

    params.update({
        "stop_pct": round(stop_pct, 1),
        "target_pct": round(target_pct, 1),
        "shares": shares,
        "direction": "bull" if trend in ("strong_up", "up") else "bear",
    })

    action = "trade" if score >= 60 else "watch" if score >= 40 else "avoid"
    return StrategyScore("momentum", round(score), action, params,
                         round(est_daily, 2), round(est_weekly, 2))


def _score_grid(
    trend: str, rsi: float, atr_pct: float,
    daily_range: float, price: float, account: float,
) -> StrategyScore:
    """Score grid trading strategy."""
    score = 0.0
    params = {}

    # Range-bound = best for grid
    if trend == "range":
        score += 35
    elif trend in ("up", "down"):
        score += 15
    else:
        score += 5  # strong trends blow through grids

    # RSI near neutral
    if 40 <= rsi <= 60:
        score += 20
    elif 30 <= rsi <= 70:
        score += 10

    # High volatility = more grid fills
    if daily_range > 6:
        score += 30
    elif daily_range > 4:
        score += 25
    elif daily_range > 2:
        score += 15
    else:
        score += 5

    # Consistent range (not expanding/contracting)
    score += 10  # base points

    score = min(score, 100)

    # Grid parameters
    spacing_pct = max(atr_pct * 0.6, 1.5)
    spacing_pct = min(spacing_pct, 6.0)
    num_levels = 4
    per_level = account / (num_levels * 2)

    profit_per_trip = per_level * spacing_pct / 100
    est_daily_trips = max(daily_range / spacing_pct * 0.8, 0.5)
    est_daily_trips = min(est_daily_trips, 6)
    est_daily = profit_per_trip * est_daily_trips
    est_weekly = est_daily * 5  # equity ETFs = 5 market days

    params.update({
        "spacing_pct": round(spacing_pct, 1),
        "num_levels": num_levels,
        "per_level": round(per_level, 0),
        "profit_per_trip": round(profit_per_trip, 2),
        "est_trips_day": round(est_daily_trips, 1),
    })

    action = "trade" if score >= 60 else "watch" if score >= 40 else "avoid"
    return StrategyScore("grid", round(score), action, params,
                         round(est_daily, 2), round(est_weekly, 2))


def _score_mean_reversion(
    trend: str, rsi: float, sma20_dist: float,
    atr_pct: float, daily_range: float, price: float,
    account: float,
) -> StrategyScore:
    """Score mean-reversion (fade overextended moves)."""
    score = 0.0
    params = {}

    # Overextended = opportunity to fade
    if abs(sma20_dist) > 10:
        score += 35
        params["extension"] = "extreme"
    elif abs(sma20_dist) > 5:
        score += 25
        params["extension"] = "moderate"
    else:
        score += 5
        params["extension"] = "mild"

    # RSI extreme = mean reversion signal
    if rsi > 75 or rsi < 25:
        score += 30
        params["rsi_signal"] = "extreme"
    elif rsi > 65 or rsi < 35:
        score += 15
        params["rsi_signal"] = "moderate"
    else:
        score += 5
        params["rsi_signal"] = "neutral"

    # Volatility (need range to snap back)
    if daily_range > 4:
        score += 20
    elif daily_range > 2:
        score += 10

    # Trend context (mean reversion works best in ranges or trend fades)
    if trend == "range":
        score += 10
    elif trend in ("strong_up", "strong_down"):
        score += 5  # can work but riskier

    score = min(score, 100)

    # Position: trade the opposite side, target SMA
    direction = "bear" if sma20_dist > 0 else "bull"
    stop_pct = atr_pct * 2.0  # wider stop for reversals
    target_pct = abs(sma20_dist) * 0.6  # target 60% reversion to SMA
    target_pct = max(target_pct, atr_pct)

    risk_dollars = account * 0.08  # slightly less risk on reversals
    shares = int(risk_dollars / (price * stop_pct / 100)) if stop_pct > 0 else 0
    shares = min(shares, int(account * 0.40 / price))
    est_daily = shares * price * target_pct / 100 * 0.2  # lower win rate
    est_weekly = est_daily * 5

    params.update({
        "direction": direction,
        "stop_pct": round(stop_pct, 1),
        "target_pct": round(target_pct, 1),
        "shares": shares,
        "reversion_target": "SMA20",
    })

    action = "trade" if score >= 65 else "watch" if score >= 45 else "avoid"
    return StrategyScore("mean_reversion", round(score), action, params,
                         round(est_daily, 2), round(est_weekly, 2))


def _fetch_news(query: str) -> list[str]:
    """Fetch news headlines."""
    import re
    import requests as _requests
    from urllib.parse import quote

    url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
    try:
        resp = _requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if not resp.ok:
            return []
        titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", resp.text)
        return [t.strip() for t in titles[1:8] if t.strip()]
    except Exception:
        return []


def scan_volatility(
    config: TTRadeConfig,
    account_value: float = 1000.0,
    sectors: list[str] | None = None,
) -> list[VolatilitySignal]:
    """Scan commodity/volatility sectors for trading opportunities.

    Returns signals sorted by best opportunity score.
    """
    target_sectors = sectors or list(VOLATILITY_UNIVERSE.keys())
    signals = []

    for sector_key in target_sectors:
        sector = VOLATILITY_UNIVERSE.get(sector_key)
        if not sector:
            continue

        bull_info = sector["bull"]
        bear_info = sector["bear"]

        try:
            bull_bars = _fetch_bars(bull_info["ticker"], period_days=60)
            bear_bars = _fetch_bars(bear_info["ticker"], period_days=60)
        except Exception as e:
            logger.warning("Failed to fetch %s/%s: %s", bull_info["ticker"], bear_info["ticker"], e)
            continue

        # Use bull side for analysis (bear mirrors it)
        bull_price = float(bull_bars["Close"].iloc[-1])
        bear_price = float(bear_bars["Close"].iloc[-1])

        # Get underlying price if possible
        try:
            und_bars = _fetch_bars(sector["underlying"], period_days=60)
            und_price = float(und_bars["Close"].iloc[-1])
        except Exception:
            und_price = 0.0

        # Analyze bull side
        vol_rank, atr_pct, daily_range = _analyze_volatility(bull_bars)
        trend, trend_strength, sma20_dist = _analyze_trend(bull_bars)
        rsi = _compute_rsi(bull_bars["Close"])

        # Also check bear side volatility (use higher)
        bear_vol_rank, bear_atr, bear_range = _analyze_volatility(bear_bars)
        if bear_range > daily_range:
            daily_range = bear_range
            atr_pct = bear_atr

        # Score all three strategies
        momentum = _score_momentum(trend, trend_strength, rsi, atr_pct, daily_range, bull_price, account_value)
        grid = _score_grid(trend, rsi, atr_pct, daily_range, bull_price, account_value)
        mean_rev = _score_mean_reversion(trend, rsi, sma20_dist, atr_pct, daily_range, bull_price, account_value)

        all_strategies = sorted([momentum, grid, mean_rev], key=lambda s: -s.score)
        best = all_strategies[0]

        # Determine which side to trade
        if best.name == "mean_reversion":
            rec_side = best.params.get("direction", "bull")
        elif best.name == "momentum":
            rec_side = best.params.get("direction", "bull")
        else:
            rec_side = "bull"  # grid trades both, but default to bull display

        rec_ticker = bull_info["ticker"] if rec_side == "bull" else bear_info["ticker"]
        rec_price = bull_price if rec_side == "bull" else bear_price

        # Position sizing from best strategy
        if "shares" in best.params:
            shares = best.params["shares"]
            stop_pct = best.params.get("stop_pct", atr_pct * 1.5)
            target_pct = best.params.get("target_pct", stop_pct * 2)
        else:
            stop_pct = atr_pct * 1.5
            target_pct = stop_pct * 2
            risk = account_value * 0.10
            shares = int(risk / (rec_price * stop_pct / 100)) if stop_pct > 0 else 0
            shares = min(shares, int(account_value * 0.50 / rec_price))

        est_win = shares * rec_price * target_pct / 100
        est_loss = shares * rec_price * stop_pct / 100

        # Checks
        checks = {
            "volatility": {"passed": vol_rank in ("high", "extreme"), "value": f"{atr_pct:.1f}% ATR ({vol_rank})"},
            "daily_range": {"passed": daily_range > 3.0, "value": f"{daily_range:.1f}% avg range"},
            "trend_clear": {"passed": trend != "range" or best.name == "grid", "value": f"{trend} ({trend_strength:.0f})"},
            "rsi_zone": {"passed": 25 < rsi < 75, "value": f"RSI {rsi:.0f}"},
            "liquidity": {"passed": True, "value": "leveraged ETF (liquid)"},
        }
        passed = sum(1 for c in checks.values() if c["passed"])
        overall_score = best.score * 0.7 + (passed / 5) * 30  # blend strategy + checks

        # News
        headlines = _fetch_news(sector["news_query"])

        signals.append(VolatilitySignal(
            sector=sector_key,
            sector_name=sector["name"],
            bull_ticker=bull_info["ticker"],
            bear_ticker=bear_info["ticker"],
            bull_price=round(bull_price, 2),
            bear_price=round(bear_price, 2),
            underlying_ticker=sector["underlying"],
            underlying_price=round(und_price, 2),
            daily_range_pct=round(daily_range, 1),
            atr_pct=round(atr_pct, 1),
            volatility_rank=vol_rank,
            trend=trend,
            trend_strength=round(trend_strength, 1),
            rsi=round(rsi, 1),
            sma20_dist_pct=round(sma20_dist, 1),
            best_strategy=best,
            all_strategies=all_strategies,
            recommended_ticker=rec_ticker,
            recommended_side=rec_side,
            position_size=round(shares * rec_price, 2),
            stop_pct=round(stop_pct, 1),
            target_pct=round(target_pct, 1),
            shares=shares,
            est_win_dollars=round(est_win, 2),
            est_loss_dollars=round(est_loss, 2),
            score=round(overall_score),
            checks=checks,
            timestamp=datetime.now(),
            news_headlines=headlines,
        ))

    signals.sort(key=lambda s: (-s.score, s.sector))
    return signals

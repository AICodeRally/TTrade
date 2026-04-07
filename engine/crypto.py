"""Crypto grid/swing scanner — bidirectional Bitcoin trading.

Plays both sides of BTC's volatility using a grid approach:
buy dips, sell rips, repeat. No directional bias needed.

Grid levels are spaced by ATR. Supports BTC-USD and ETH-USD
via Public.com's crypto trading API.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

import pandas as pd

from engine.config import TTRadeConfig
from engine.market_data import compute_sma, compute_atr

logger = logging.getLogger(__name__)

# Crypto universe (Public.com supported tickers)
CRYPTO_TICKERS = [
    {"ticker": "BTC-USD", "name": "Bitcoin", "min_trade": 1.0},   # $1 minimum
    {"ticker": "ETH-USD", "name": "Ethereum", "min_trade": 1.0},
]


@dataclass
class GridLevel:
    price: float
    side: str         # "buy" or "sell"
    status: str       # "pending", "filled", "paired"
    fill_price: float | None = None
    paired_level: float | None = None  # the matching exit level


@dataclass
class CryptoSignal:
    ticker: str
    name: str
    price: float
    trend: str              # "up", "down", "range"
    volatility: str         # "low", "medium", "high"
    atr_pct: float          # ATR as % of price
    daily_range_pct: float  # average daily high-low range
    grid_spacing_pct: float
    grid_levels: list[GridLevel]
    buy_levels: int
    sell_levels: int
    profit_per_round_trip: float
    est_daily_trips: float
    est_daily_profit: float
    est_weekly_profit: float
    position_size: float     # $ per grid level
    total_capital_needed: float
    score: float             # 0-100 opportunity score
    action: str              # "trade", "watch", "avoid"
    checks: dict
    timestamp: datetime
    news_headlines: list[str] = field(default_factory=list)


def _get_crypto_bars(ticker: str, period_days: int = 30) -> pd.DataFrame:
    """Fetch crypto daily bars via yfinance."""
    import yfinance as yf
    data = yf.download(ticker, period=f"{period_days}d", interval="1d", progress=False)
    if data.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    return data


def _get_crypto_intraday(ticker: str) -> pd.DataFrame:
    """Fetch 5-minute bars for intraday volatility analysis."""
    import yfinance as yf
    data = yf.download(ticker, period="5d", interval="5m", progress=False)
    if data.empty:
        raise ValueError(f"No intraday data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    return data


def _check_volatility(bars: pd.DataFrame) -> tuple[str, float, float]:
    """Assess volatility level — grid trading needs sufficient movement.

    Returns (level, atr_pct, daily_range_pct).
    """
    atr = compute_atr(bars, period=14)
    atr_clean = atr.dropna()
    if len(atr_clean) < 1:
        return "low", 0.0, 0.0

    current_price = float(bars["Close"].iloc[-1])
    atr_val = float(atr_clean.iloc[-1])
    atr_pct = atr_val / current_price * 100

    # Average daily range
    daily_ranges = (bars["High"] - bars["Low"]) / bars["Close"] * 100
    avg_range = float(daily_ranges.tail(14).mean())

    if atr_pct > 4.0:
        level = "high"
    elif atr_pct > 2.0:
        level = "medium"
    else:
        level = "low"

    return level, atr_pct, avg_range


def _check_trend(bars: pd.DataFrame) -> tuple[str, float]:
    """Determine if crypto is trending or ranging — grid works best in ranges."""
    close = bars["Close"]
    sma20 = compute_sma(close, period=20)
    sma50 = compute_sma(close, period=50)
    sma20_clean = sma20.dropna()
    sma50_clean = sma50.dropna()

    if len(sma50_clean) < 1:
        return "range", 0.0

    current = float(close.iloc[-1])
    sma20_val = float(sma20_clean.iloc[-1])
    sma50_val = float(sma50_clean.iloc[-1])

    # Distance from 20 SMA as trend strength
    distance_pct = (current - sma20_val) / sma20_val * 100
    sma_spread = (sma20_val - sma50_val) / sma50_val * 100

    if abs(distance_pct) > 5 and abs(sma_spread) > 3:
        trend = "up" if distance_pct > 0 else "down"
    else:
        trend = "range"

    return trend, distance_pct


def _check_mean_reversion(bars: pd.DataFrame) -> tuple[bool, float]:
    """Check RSI for mean-reversion opportunities."""
    close = bars["Close"]
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    rsi_clean = rsi.dropna()

    if len(rsi_clean) < 1:
        return True, 50.0

    rsi_val = float(rsi_clean.iloc[-1])
    # Good for grid: RSI between 35-65 (not overextended)
    in_range = 35 <= rsi_val <= 65
    return in_range, rsi_val


def _check_bollinger_width(bars: pd.DataFrame) -> tuple[bool, float]:
    """Bollinger Band width — wider = more grid opportunities."""
    close = bars["Close"]
    sma20 = compute_sma(close, period=20)
    std20 = close.rolling(window=20).std()
    upper = sma20 + 2 * std20
    lower = sma20 - 2 * std20

    sma_clean = sma20.dropna()
    upper_clean = upper.dropna()
    lower_clean = lower.dropna()

    if len(sma_clean) < 1 or len(upper_clean) < 1:
        return True, 0.0

    width_pct = float((upper_clean.iloc[-1] - lower_clean.iloc[-1]) / sma_clean.iloc[-1] * 100)
    # > 5% band width is good for grid trading
    good_width = width_pct > 5.0
    return good_width, width_pct


def _check_volume_consistency(bars: pd.DataFrame) -> tuple[bool, float]:
    """Check that volume is consistent — low volume = slippage risk."""
    vol = bars["Volume"]
    recent_vol = vol.tail(5).mean()
    avg_vol = vol.tail(20).mean()
    ratio = float(recent_vol / avg_vol) if avg_vol > 0 else 0
    # Consistent volume = ratio near 1.0
    consistent = ratio >= 0.7
    return consistent, ratio


def _calculate_grid(
    current_price: float,
    atr_pct: float,
    account_value: float,
    num_levels: int = 5,
) -> tuple[list[GridLevel], float, float]:
    """Calculate grid levels based on ATR.

    Places buy levels below and sell levels above current price.
    Grid spacing = ATR% * 0.75 (tighter than ATR for more fills).

    Returns (levels, spacing_pct, capital_needed).
    """
    spacing_pct = max(atr_pct * 0.75, 1.0)  # at least 1% spacing
    spacing_pct = min(spacing_pct, 5.0)       # max 5% spacing

    levels = []
    # Buy levels below current price
    for i in range(1, num_levels + 1):
        buy_price = current_price * (1 - spacing_pct * i / 100)
        sell_price = buy_price * (1 + spacing_pct / 100)
        levels.append(GridLevel(
            price=round(buy_price, 2),
            side="buy",
            status="pending",
            paired_level=round(sell_price, 2),
        ))

    # Sell levels above current price (for existing position or DCA sells)
    for i in range(1, num_levels + 1):
        sell_price = current_price * (1 + spacing_pct * i / 100)
        buy_price = sell_price * (1 - spacing_pct / 100)
        levels.append(GridLevel(
            price=round(sell_price, 2),
            side="sell",
            status="pending",
            paired_level=round(buy_price, 2),
        ))

    # Capital needed: $ per level for buy side
    per_level = account_value / (num_levels * 2)  # split across all levels
    capital_needed = per_level * num_levels  # just the buy side

    levels.sort(key=lambda l: l.price)
    return levels, spacing_pct, capital_needed


def _estimate_profitability(
    price: float,
    spacing_pct: float,
    daily_range_pct: float,
    per_level_dollars: float,
) -> tuple[float, float, float, float]:
    """Estimate grid trading profitability.

    Returns (profit_per_trip, est_daily_trips, est_daily_profit, est_weekly_profit).
    """
    # Each round trip captures ~spacing_pct minus fees
    fee_pct = 0.0  # Public.com: zero commission on crypto
    profit_per_trip_pct = spacing_pct - fee_pct
    profit_per_trip = per_level_dollars * profit_per_trip_pct / 100

    # Estimate daily round trips based on daily range vs grid spacing
    # If daily range is 4% and grid spacing is 2%, expect ~2 trips
    est_daily_trips = max(daily_range_pct / spacing_pct, 0.5)
    est_daily_trips = min(est_daily_trips, 8)  # cap at 8

    est_daily_profit = profit_per_trip * est_daily_trips
    est_weekly_profit = est_daily_profit * 7  # crypto trades 24/7

    return profit_per_trip, est_daily_trips, est_daily_profit, est_weekly_profit


def _fetch_crypto_news(ticker: str) -> list[str]:
    """Fetch crypto-specific news."""
    import re
    import requests as _requests
    from urllib.parse import quote

    name = "Bitcoin" if "BTC" in ticker else "Ethereum" if "ETH" in ticker else ticker
    queries = [f"{name} price", "crypto market today"]
    all_headlines = []

    for q in queries:
        url = f"https://news.google.com/rss/search?q={quote(q)}&hl=en-US&gl=US&ceid=US:en"
        try:
            resp = _requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
            if not resp.ok:
                continue
            titles = re.findall(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", resp.text)
            all_headlines.extend(t.strip() for t in titles[1:6] if t.strip())
        except Exception:
            continue

    seen = set()
    unique = []
    for h in all_headlines:
        if h not in seen:
            seen.add(h)
            unique.append(h)
    return unique


def scan_crypto(
    config: TTRadeConfig,
    account_value: float = 1000.0,
) -> list[CryptoSignal]:
    """Scan crypto for grid trading opportunities."""
    signals = []

    for crypto in CRYPTO_TICKERS:
        ticker = crypto["ticker"]
        try:
            bars = _get_crypto_bars(ticker, period_days=60)
        except Exception as e:
            logger.warning("Failed to fetch %s: %s", ticker, e)
            continue

        current_price = float(bars["Close"].iloc[-1])

        # Run checks
        vol_level, atr_pct, daily_range_pct = _check_volatility(bars)
        trend, trend_distance = _check_trend(bars)
        rsi_ok, rsi_val = _check_mean_reversion(bars)
        bb_ok, bb_width = _check_bollinger_width(bars)
        vol_ok, vol_ratio = _check_volume_consistency(bars)

        checks = {
            "volatility": {"passed": vol_level in ("medium", "high"), "value": f"{atr_pct:.1f}% ATR ({vol_level})"},
            "trend_range": {"passed": trend == "range", "value": f"{trend} ({trend_distance:+.1f}%)"},
            "rsi_neutral": {"passed": rsi_ok, "value": f"RSI {rsi_val:.0f}"},
            "bollinger_width": {"passed": bb_ok, "value": f"{bb_width:.1f}% width"},
            "volume": {"passed": vol_ok, "value": f"{vol_ratio:.2f}x avg"},
        }

        passed = sum(1 for c in checks.values() if c["passed"])
        score = (passed / 5) * 100

        # Calculate grid
        num_levels = 5 if account_value >= 500 else 3
        grid_levels, spacing_pct, capital_needed = _calculate_grid(
            current_price, atr_pct, account_value, num_levels,
        )

        per_level = account_value / (num_levels * 2)
        profit_per_trip, est_daily_trips, est_daily, est_weekly = _estimate_profitability(
            current_price, spacing_pct, daily_range_pct, per_level,
        )

        # Action decision
        if passed >= 4 and vol_level in ("medium", "high"):
            action = "trade"
        elif passed >= 3:
            action = "watch"
        else:
            action = "avoid"

        # Boost score if ranging with high volatility (ideal for grid)
        if trend == "range" and vol_level == "high":
            score = min(score + 10, 100)

        # News
        headlines = _fetch_crypto_news(ticker)

        buy_levels = sum(1 for l in grid_levels if l.side == "buy")
        sell_levels = sum(1 for l in grid_levels if l.side == "sell")

        signals.append(CryptoSignal(
            ticker=ticker, name=crypto["name"],
            price=current_price, trend=trend,
            volatility=vol_level, atr_pct=atr_pct,
            daily_range_pct=daily_range_pct,
            grid_spacing_pct=spacing_pct,
            grid_levels=grid_levels,
            buy_levels=buy_levels, sell_levels=sell_levels,
            profit_per_round_trip=round(profit_per_trip, 2),
            est_daily_trips=round(est_daily_trips, 1),
            est_daily_profit=round(est_daily, 2),
            est_weekly_profit=round(est_weekly, 2),
            position_size=round(per_level, 2),
            total_capital_needed=round(capital_needed, 2),
            score=score, action=action,
            checks=checks, timestamp=datetime.now(),
            news_headlines=headlines,
        ))

    signals.sort(key=lambda s: (-s.score, s.ticker))
    return signals

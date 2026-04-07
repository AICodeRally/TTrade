"""Technical analysis toolkit — full TA dashboard for any ticker.

Computes: SMA, EMA, RSI, MACD, Bollinger Bands, OBV, ATR,
Stochastic, VWAP, Fibonacci levels, support/resistance,
and generates a composite signal.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from engine.market_data import compute_sma, compute_atr

logger = logging.getLogger(__name__)


@dataclass
class TAReport:
    ticker: str
    price: float
    # Moving averages
    sma_20: float
    sma_50: float
    sma_200: float
    ema_12: float
    ema_26: float
    ma_signal: str        # "bullish", "bearish", "neutral"
    # RSI
    rsi_14: float
    rsi_signal: str       # "oversold", "overbought", "neutral"
    # MACD
    macd_line: float
    macd_signal_line: float
    macd_histogram: float
    macd_signal: str      # "bullish", "bearish", "neutral"
    # Bollinger Bands
    bb_upper: float
    bb_middle: float
    bb_lower: float
    bb_width_pct: float
    bb_position: str      # "above", "upper", "middle", "lower", "below"
    # Volume
    obv_trend: str        # "rising", "falling", "flat"
    volume_ratio: float   # current vs 20-day avg
    volume_signal: str    # "high", "normal", "low"
    # ATR
    atr_14: float
    atr_pct: float
    volatility: str       # "high", "medium", "low"
    # Stochastic
    stoch_k: float
    stoch_d: float
    stoch_signal: str     # "oversold", "overbought", "neutral"
    # Fibonacci
    fib_levels: dict[str, float]
    nearest_fib: str
    # Support / Resistance
    support: float
    resistance: float
    # Composite
    bull_signals: int
    bear_signals: int
    neutral_signals: int
    composite_signal: str   # "STRONG BUY", "BUY", "NEUTRAL", "SELL", "STRONG SELL"
    composite_score: int    # -100 to +100
    timestamp: datetime


def _compute_ema(close: pd.Series, period: int) -> pd.Series:
    return close.ewm(span=period, adjust=False).mean()


def _compute_rsi(close: pd.Series, period: int = 14) -> float:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta).clip(lower=0).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    rsi_clean = rsi.dropna()
    return float(rsi_clean.iloc[-1]) if len(rsi_clean) > 0 else 50.0


def _compute_macd(close: pd.Series) -> tuple[float, float, float]:
    ema12 = _compute_ema(close, 12)
    ema26 = _compute_ema(close, 26)
    macd_line = ema12 - ema26
    signal_line = _compute_ema(macd_line, 9)
    histogram = macd_line - signal_line

    ml = float(macd_line.iloc[-1])
    sl = float(signal_line.iloc[-1])
    hist = float(histogram.iloc[-1])
    return ml, sl, hist


def _compute_bollinger(close: pd.Series, period: int = 20) -> tuple[float, float, float, float]:
    sma = compute_sma(close, period)
    std = close.rolling(window=period).std()
    upper = sma + 2 * std
    lower = sma - 2 * std

    sma_val = float(sma.dropna().iloc[-1])
    upper_val = float(upper.dropna().iloc[-1])
    lower_val = float(lower.dropna().iloc[-1])
    width_pct = (upper_val - lower_val) / sma_val * 100

    return upper_val, sma_val, lower_val, width_pct


def _compute_obv(close: pd.Series, volume: pd.Series) -> str:
    obv = pd.Series(
        np.where(close > close.shift(), volume,
                 np.where(close < close.shift(), -volume, 0)),
        index=close.index
    ).cumsum()
    obv_sma = compute_sma(obv, period=10).dropna()
    if len(obv_sma) < 2:
        return "flat"
    slope = float(obv_sma.iloc[-1] - obv_sma.iloc[-5]) if len(obv_sma) >= 5 else 0
    if slope > 0:
        return "rising"
    elif slope < 0:
        return "falling"
    return "flat"


def _compute_stochastic(bars: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> tuple[float, float]:
    high = bars["High"].rolling(window=k_period).max()
    low = bars["Low"].rolling(window=k_period).min()
    close = bars["Close"]
    k = ((close - low) / (high - low) * 100)
    d = k.rolling(window=d_period).mean()
    k_val = float(k.dropna().iloc[-1]) if len(k.dropna()) > 0 else 50.0
    d_val = float(d.dropna().iloc[-1]) if len(d.dropna()) > 0 else 50.0
    return k_val, d_val


def _compute_fibonacci(bars: pd.DataFrame, lookback: int = 60) -> dict[str, float]:
    recent = bars.tail(lookback)
    high = float(recent["High"].max())
    low = float(recent["Low"].min())
    diff = high - low
    return {
        "0.0%": round(high, 2),
        "23.6%": round(high - diff * 0.236, 2),
        "38.2%": round(high - diff * 0.382, 2),
        "50.0%": round(high - diff * 0.500, 2),
        "61.8%": round(high - diff * 0.618, 2),
        "78.6%": round(high - diff * 0.786, 2),
        "100.0%": round(low, 2),
    }


def _find_support_resistance(bars: pd.DataFrame, lookback: int = 20) -> tuple[float, float]:
    recent = bars.tail(lookback)
    support = float(recent["Low"].min())
    resistance = float(recent["High"].max())
    return support, resistance


def analyze_ta(ticker: str, period_days: int = 200) -> TAReport:
    """Run full technical analysis on a ticker."""
    import yfinance as yf
    bars = yf.download(ticker, period=f"{period_days}d", interval="1d", progress=False)
    if bars.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(bars.columns, pd.MultiIndex):
        bars.columns = bars.columns.droplevel(1)

    close = bars["Close"]
    volume = bars["Volume"]
    price = float(close.iloc[-1])

    # Moving averages
    sma20 = float(compute_sma(close, 20).dropna().iloc[-1])
    sma50_s = compute_sma(close, 50).dropna()
    sma50 = float(sma50_s.iloc[-1]) if len(sma50_s) > 0 else price
    sma200_s = compute_sma(close, 200).dropna()
    sma200 = float(sma200_s.iloc[-1]) if len(sma200_s) > 0 else price
    ema12 = float(_compute_ema(close, 12).iloc[-1])
    ema26 = float(_compute_ema(close, 26).iloc[-1])

    # MA signal: golden/death cross style
    if price > sma20 > sma50:
        ma_signal = "bullish"
    elif price < sma20 < sma50:
        ma_signal = "bearish"
    else:
        ma_signal = "neutral"

    # RSI
    rsi_val = _compute_rsi(close)
    rsi_signal = "oversold" if rsi_val < 30 else "overbought" if rsi_val > 70 else "neutral"

    # MACD
    macd_l, macd_s, macd_h = _compute_macd(close)
    if macd_l > macd_s and macd_h > 0:
        macd_signal = "bullish"
    elif macd_l < macd_s and macd_h < 0:
        macd_signal = "bearish"
    else:
        macd_signal = "neutral"

    # Bollinger Bands
    bb_upper, bb_middle, bb_lower, bb_width = _compute_bollinger(close)
    if price > bb_upper:
        bb_pos = "above"
    elif price > bb_middle + (bb_upper - bb_middle) * 0.5:
        bb_pos = "upper"
    elif price > bb_middle - (bb_middle - bb_lower) * 0.5:
        bb_pos = "middle"
    elif price > bb_lower:
        bb_pos = "lower"
    else:
        bb_pos = "below"

    # Volume
    obv_trend = _compute_obv(close, volume)
    avg_vol = float(volume.tail(20).mean())
    curr_vol = float(volume.iloc[-1])
    vol_ratio = curr_vol / avg_vol if avg_vol > 0 else 1.0
    vol_signal = "high" if vol_ratio > 1.5 else "low" if vol_ratio < 0.5 else "normal"

    # ATR
    atr = compute_atr(bars, period=14).dropna()
    atr_val = float(atr.iloc[-1]) if len(atr) > 0 else price * 0.02
    atr_pct = atr_val / price * 100
    volatility = "high" if atr_pct > 3 else "medium" if atr_pct > 1.5 else "low"

    # Stochastic
    stoch_k, stoch_d = _compute_stochastic(bars)
    stoch_signal = "oversold" if stoch_k < 20 else "overbought" if stoch_k > 80 else "neutral"

    # Fibonacci
    fib_levels = _compute_fibonacci(bars)
    nearest_fib = min(fib_levels.items(), key=lambda x: abs(x[1] - price))
    nearest_fib_label = f"{nearest_fib[0]} (${nearest_fib[1]:.2f})"

    # Support / Resistance
    support, resistance = _find_support_resistance(bars)

    # Composite signal
    bull = bear = neutral = 0
    for sig in [ma_signal, rsi_signal, macd_signal, stoch_signal]:
        if sig in ("bullish", "oversold"):
            bull += 1
        elif sig in ("bearish", "overbought"):
            bear += 1
        else:
            neutral += 1

    # OBV and volume confirmation
    if obv_trend == "rising" and vol_signal == "high":
        bull += 1
    elif obv_trend == "falling" and vol_signal == "high":
        bear += 1
    else:
        neutral += 1

    # BB position
    if bb_pos in ("below", "lower"):
        bull += 1
    elif bb_pos in ("above", "upper"):
        bear += 1
    else:
        neutral += 1

    total = bull + bear + neutral
    score = int((bull - bear) / total * 100) if total > 0 else 0

    if score >= 50:
        composite = "STRONG BUY"
    elif score >= 20:
        composite = "BUY"
    elif score <= -50:
        composite = "STRONG SELL"
    elif score <= -20:
        composite = "SELL"
    else:
        composite = "NEUTRAL"

    return TAReport(
        ticker=ticker, price=round(price, 2),
        sma_20=round(sma20, 2), sma_50=round(sma50, 2), sma_200=round(sma200, 2),
        ema_12=round(ema12, 2), ema_26=round(ema26, 2), ma_signal=ma_signal,
        rsi_14=round(rsi_val, 1), rsi_signal=rsi_signal,
        macd_line=round(macd_l, 4), macd_signal_line=round(macd_s, 4),
        macd_histogram=round(macd_h, 4), macd_signal=macd_signal,
        bb_upper=round(bb_upper, 2), bb_middle=round(bb_middle, 2),
        bb_lower=round(bb_lower, 2), bb_width_pct=round(bb_width, 2),
        bb_position=bb_pos,
        obv_trend=obv_trend, volume_ratio=round(vol_ratio, 2), volume_signal=vol_signal,
        atr_14=round(atr_val, 2), atr_pct=round(atr_pct, 2), volatility=volatility,
        stoch_k=round(stoch_k, 1), stoch_d=round(stoch_d, 1), stoch_signal=stoch_signal,
        fib_levels=fib_levels, nearest_fib=nearest_fib_label,
        support=round(support, 2), resistance=round(resistance, 2),
        bull_signals=bull, bear_signals=bear, neutral_signals=neutral,
        composite_signal=composite, composite_score=score,
        timestamp=datetime.now(),
    )

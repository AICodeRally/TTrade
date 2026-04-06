"""Market data provider — yfinance wrapper for daily bars."""
import yfinance as yf
import pandas as pd
import numpy as np


def get_daily_bars(ticker: str, period_days: int = 60) -> pd.DataFrame:
    data = yf.download(ticker, period=f"{period_days}d", interval="1d", progress=False)
    if data.empty:
        raise ValueError(f"No data returned for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    return data


def compute_sma(series: pd.Series, period: int = 20) -> pd.Series:
    return series.rolling(window=period).mean()


def compute_atr(bars: pd.DataFrame, period: int = 14) -> pd.Series:
    high = bars["High"]
    low = bars["Low"]
    close = bars["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period).mean()


def compute_slope(sma: pd.Series, lookback: int = 3) -> float:
    recent = sma.dropna()
    if len(recent) < lookback + 1:
        return 0.0
    return float(recent.iloc[-1] - recent.iloc[-1 - lookback])


def average_volume(volume: pd.Series, period: int = 20) -> float:
    recent = volume.tail(period)
    return float(recent.mean())

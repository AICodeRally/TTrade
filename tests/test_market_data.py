import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
import numpy as np
from datetime import date
from engine.market_data import (
    get_daily_bars, compute_sma, compute_atr,
    compute_slope, average_volume
)


@pytest.fixture
def mock_bars():
    """20 days of synthetic OHLCV data with an uptrend."""
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=25)
    base_price = 520.0
    data = {
        "Open": [base_price + i * 0.5 for i in range(25)],
        "High": [base_price + i * 0.5 + 1.0 for i in range(25)],
        "Low": [base_price + i * 0.5 - 0.5 for i in range(25)],
        "Close": [base_price + i * 0.5 + 0.3 for i in range(25)],
        "Volume": [50_000_000 + i * 100_000 for i in range(25)],
    }
    return pd.DataFrame(data, index=dates)


def test_compute_sma(mock_bars):
    sma = compute_sma(mock_bars["Close"], period=20)
    assert len(sma.dropna()) == 6  # 25 - 20 + 1
    assert sma.iloc[-1] > 0


def test_compute_atr(mock_bars):
    atr = compute_atr(mock_bars, period=14)
    assert len(atr.dropna()) > 0
    assert atr.iloc[-1] > 0


def test_compute_slope(mock_bars):
    sma = compute_sma(mock_bars["Close"], period=20)
    slope = compute_slope(sma, lookback=3)
    assert slope > 0


def test_average_volume(mock_bars):
    avg_vol = average_volume(mock_bars["Volume"], period=20)
    assert avg_vol > 0


@patch("engine.market_data.yf.download")
def test_get_daily_bars(mock_download, mock_bars):
    mock_download.return_value = mock_bars
    bars = get_daily_bars("SPY", period_days=25)
    assert len(bars) == 25
    assert "Close" in bars.columns
    mock_download.assert_called_once()

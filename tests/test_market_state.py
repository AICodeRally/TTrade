import pytest
import pandas as pd
from datetime import date
from engine.market_state import evaluate_market_state
from engine.models import MarketState
from engine.config import TTRadeConfig


@pytest.fixture
def config():
    return TTRadeConfig()


@pytest.fixture
def uptrend_bars():
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [500 + i * 1.5 for i in range(30)]
    return pd.DataFrame({
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [50_000_000] * 30,
    }, index=dates)


@pytest.fixture
def downtrend_bars():
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [550 - i * 1.5 for i in range(30)]
    return pd.DataFrame({
        "Open": [c + 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [50_000_000] * 30,
    }, index=dates)


@pytest.fixture
def chop_bars():
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [520 + (1 if i % 2 == 0 else -1) * 0.1 for i in range(30)]
    return pd.DataFrame({
        "Open": [c - 0.05 for c in closes],
        "High": [c + 0.2 for c in closes],
        "Low": [c - 0.2 for c in closes],
        "Close": closes,
        "Volume": [50_000_000] * 30,
    }, index=dates)


def test_trend_up(uptrend_bars, config):
    result = evaluate_market_state(uptrend_bars, config)
    assert result.state == MarketState.TREND_UP
    assert result.slope > 0
    assert result.price_vs_ma == "above"


def test_trend_down(downtrend_bars, config):
    result = evaluate_market_state(downtrend_bars, config)
    assert result.state == MarketState.TREND_DOWN
    assert result.slope < 0
    assert result.price_vs_ma == "below"


def test_chop(chop_bars, config):
    result = evaluate_market_state(chop_bars, config)
    assert result.state == MarketState.CHOP


def test_result_has_all_fields(uptrend_bars, config):
    result = evaluate_market_state(uptrend_bars, config)
    assert hasattr(result, "state")
    assert hasattr(result, "slope")
    assert hasattr(result, "current_price")
    assert hasattr(result, "sma_value")
    assert hasattr(result, "price_vs_ma")

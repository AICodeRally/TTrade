import pytest
import pandas as pd
from datetime import date
from engine.config import TTRadeConfig
from engine.models import MarketState, GateResult
from engine.market_state import MarketStateResult
from engine.gates.regime import check_regime
from engine.gates.alignment import check_alignment
from engine.gates.pullback import check_pullback
from engine.gates.confirmation import check_confirmation


@pytest.fixture
def config():
    return TTRadeConfig()


@pytest.fixture
def trend_up_state():
    return MarketStateResult(
        state=MarketState.TREND_UP, slope=2.5,
        current_price=530.0, sma_value=525.0, price_vs_ma="above",
    )


@pytest.fixture
def chop_state():
    return MarketStateResult(
        state=MarketState.CHOP, slope=0.1,
        current_price=520.0, sma_value=520.5, price_vs_ma="below",
    )


@pytest.fixture
def uptrend_ticker_bars():
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [140 + i * 0.5 for i in range(30)]
    return pd.DataFrame({
        "Open": [c - 0.3 for c in closes],
        "High": [c + 0.5 for c in closes],
        "Low": [c - 0.5 for c in closes],
        "Close": closes,
        "Volume": [30_000_000 + i * 100_000 for i in range(30)],
    }, index=dates)


@pytest.fixture
def pullback_bars():
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [140 + i * 0.5 for i in range(25)]
    closes += [152.0, 151.5, 151.0, 150.8, 151.2]
    return pd.DataFrame({
        "Open": [c - 0.2 for c in closes],
        "High": [c + 0.5 for c in closes],
        "Low": [c - 0.5 for c in closes],
        "Close": closes,
        "Volume": [30_000_000] * 30,
    }, index=dates)


def test_regime_passes_trend_up(trend_up_state, config):
    result = check_regime(trend_up_state, config)
    assert result.passed is True
    assert result.gate_name == "market_regime"


def test_regime_fails_chop(chop_state, config):
    result = check_regime(chop_state, config)
    assert result.passed is False


def test_alignment_passes_bullish(uptrend_ticker_bars, trend_up_state, config):
    result = check_alignment(uptrend_ticker_bars, trend_up_state, config)
    assert result.passed is True
    assert result.gate_name == "ticker_alignment"


def test_alignment_fails_against_regime(uptrend_ticker_bars, config):
    down_state = MarketStateResult(
        state=MarketState.TREND_DOWN, slope=-2.5,
        current_price=520.0, sma_value=525.0, price_vs_ma="below",
    )
    result = check_alignment(uptrend_ticker_bars, down_state, config)
    assert result.passed is False


def test_pullback_quality(pullback_bars, config):
    result = check_pullback(pullback_bars, "bullish", config)
    assert result.gate_name == "pullback_setup"


def test_confirmation_bullish(pullback_bars, config):
    result = check_confirmation(pullback_bars, "bullish", config)
    assert result.gate_name == "confirmation"

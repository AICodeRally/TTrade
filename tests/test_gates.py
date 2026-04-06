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


from engine.gates.earnings import check_earnings
from engine.gates.price_stability import check_price_stability
from engine.gates.options_volatility import check_options_volatility


def test_earnings_clear(config):
    result = check_earnings("AAPL", days_to_earnings=30, config=config)
    assert result.passed is True
    assert result.gate_name == "earnings_event"


def test_earnings_blackout(config):
    result = check_earnings("AAPL", days_to_earnings=3, config=config)
    assert result.passed is False


def test_earnings_unknown_passes(config):
    result = check_earnings("AAPL", days_to_earnings=None, config=config)
    assert result.passed is True


def test_price_stability_normal(uptrend_ticker_bars, config):
    result = check_price_stability(uptrend_ticker_bars, config)
    assert result.gate_name == "price_stability"
    assert result.passed is True


def test_price_stability_spike(config):
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [140 + i * 0.5 for i in range(25)]
    closes += [160, 145, 165, 140, 170]
    bars = pd.DataFrame({
        "Open": closes,
        "High": [c + 0.5 for c in closes[:25]] + [c + 15 for c in closes[25:]],
        "Low": [c - 0.5 for c in closes[:25]] + [c - 15 for c in closes[25:]],
        "Close": closes,
        "Volume": [30_000_000] * 30,
    }, index=dates)
    result = check_price_stability(bars, config)
    assert result.passed is False


def test_iv_rank_low_passes(config):
    result = check_options_volatility(iv_rank=30.0, config=config)
    assert result.passed is True
    assert result.gate_name == "options_volatility"


def test_iv_rank_medium_reduces(config):
    result = check_options_volatility(iv_rank=60.0, config=config)
    assert result.passed is True


def test_iv_rank_high_fails(config):
    result = check_options_volatility(iv_rank=80.0, config=config)
    assert result.passed is False


from engine.gates.liquidity import check_liquidity
from engine.gates.position_construction import check_position_construction
from engine.gates.cooldown_exposure import check_cooldown_exposure
from datetime import datetime, timedelta


def test_liquidity_good(config):
    option_data = {"open_interest": 500, "bid": 5.10, "ask": 5.25}
    result = check_liquidity(option_data, config)
    assert result.passed is True
    assert result.gate_name == "liquidity"


def test_liquidity_wide_spread(config):
    option_data = {"open_interest": 500, "bid": 5.00, "ask": 5.50}
    result = check_liquidity(option_data, config)
    assert result.passed is False


def test_liquidity_low_oi(config):
    option_data = {"open_interest": 20, "bid": 5.10, "ask": 5.15}
    result = check_liquidity(option_data, config)
    assert result.passed is False


def test_position_construction_valid(config):
    spread_params = {"net_debit": 72.0, "max_loss": 72.0, "max_gain": 428.0, "spread_width": 5.0}
    result = check_position_construction(spread_params, config)
    assert result.passed is True
    assert result.gate_name == "position_construction"


def test_position_construction_debit_too_high(config):
    spread_params = {"net_debit": 150.0, "max_loss": 150.0, "max_gain": 350.0, "spread_width": 5.0}
    result = check_position_construction(spread_params, config)
    assert result.passed is False


def test_position_construction_bad_rr(config):
    spread_params = {"net_debit": 80.0, "max_loss": 80.0, "max_gain": 80.0, "spread_width": 5.0}
    result = check_position_construction(spread_params, config)
    assert result.passed is False


def test_cooldown_no_recent_fills(config):
    result = check_cooldown_exposure(
        last_fill_time=None, fills_today=0, open_positions=[],
        new_ticker="AAPL", new_direction="bullish", config=config,
    )
    assert result.passed is True
    assert result.gate_name == "cooldown_exposure"


def test_cooldown_too_recent(config):
    recent = datetime.now() - timedelta(hours=2)
    result = check_cooldown_exposure(
        last_fill_time=recent, fills_today=0, open_positions=[],
        new_ticker="AAPL", new_direction="bullish", config=config,
    )
    assert result.passed is False


def test_cooldown_max_daily_trades(config):
    result = check_cooldown_exposure(
        last_fill_time=None, fills_today=1, open_positions=[],
        new_ticker="AAPL", new_direction="bullish", config=config,
    )
    assert result.passed is False


def test_exposure_bucket_conflict(config):
    open_positions = [{"ticker": "MSFT", "direction": "bullish"}]
    result = check_cooldown_exposure(
        last_fill_time=None, fills_today=0, open_positions=open_positions,
        new_ticker="AAPL", new_direction="bullish", config=config,
    )
    assert result.passed is False


def test_exposure_different_bucket_ok(config):
    open_positions = [{"ticker": "SPY", "direction": "bullish"}]
    result = check_cooldown_exposure(
        last_fill_time=None, fills_today=0, open_positions=open_positions,
        new_ticker="AAPL", new_direction="bullish", config=config,
    )
    assert result.passed is True

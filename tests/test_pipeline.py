import pytest
from unittest.mock import patch, MagicMock
import pandas as pd
from datetime import date
from engine.pipeline import run_pipeline, determine_direction
from engine.config import TTRadeConfig
from engine.models import MarketState
from engine.market_state import MarketStateResult


@pytest.fixture
def config():
    return TTRadeConfig()


@pytest.fixture
def trend_up_state():
    return MarketStateResult(state=MarketState.TREND_UP, slope=2.5,
                             current_price=530.0, sma_value=525.0, price_vs_ma="above")


@pytest.fixture
def chop_state():
    return MarketStateResult(state=MarketState.CHOP, slope=0.1,
                             current_price=520.0, sma_value=520.5, price_vs_ma="below")


def test_determine_direction_trend_up():
    assert determine_direction(MarketState.TREND_UP) == "bullish"


def test_determine_direction_trend_down():
    assert determine_direction(MarketState.TREND_DOWN) == "bearish"


def test_determine_direction_chop():
    assert determine_direction(MarketState.CHOP) is None


def test_pipeline_chop_rejects(chop_state, config):
    result = run_pipeline(
        ticker="SPY", ticker_bars=pd.DataFrame(), market_state=chop_state,
        option_data={}, open_positions=[], last_fill_time=None,
        fills_today=0, days_to_earnings=None, config=config,
    )
    assert result.all_gates_passed is False
    assert result.action_taken == "reject"
    assert result.gate_results[0].gate_name == "market_regime"
    assert result.gate_results[0].passed is False


def test_pipeline_scores_when_all_gates_pass(trend_up_state, config):
    """When all 10 gates pass, the scoring engine must be called and produce a real score."""
    from unittest.mock import patch
    from engine.models import GateResult

    gate_result = GateResult(gate_name="test", passed=True, measured_value=1.0,
                             threshold=0.5, config_version="1.1.0")

    # Build bars with a clear uptrend for scoring to work with
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [500 + i * 1.5 for i in range(30)]
    bars = pd.DataFrame({
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [50_000_000 + i * 500_000 for i in range(30)],
    }, index=dates)

    option_data = {
        "iv_rank": 40.0, "bid_ask_pct": 0.05, "avg_oi": 500,
        "spread_params": {"net_debit": 75, "max_loss": 75, "max_gain": 175, "spread_width": 5},
    }

    # Mock all 10 gates to pass
    with patch("engine.pipeline.check_regime", return_value=gate_result), \
         patch("engine.pipeline.check_alignment", return_value=gate_result), \
         patch("engine.pipeline.check_pullback", return_value=gate_result), \
         patch("engine.pipeline.check_confirmation", return_value=gate_result), \
         patch("engine.pipeline.check_earnings", return_value=gate_result), \
         patch("engine.pipeline.check_price_stability", return_value=gate_result), \
         patch("engine.pipeline.check_options_volatility", return_value=gate_result), \
         patch("engine.pipeline.check_liquidity", return_value=gate_result), \
         patch("engine.pipeline.check_position_construction", return_value=gate_result), \
         patch("engine.pipeline.check_cooldown_exposure", return_value=gate_result):

        result = run_pipeline(
            ticker="AAPL", ticker_bars=bars, market_state=trend_up_state,
            option_data=option_data, open_positions=[], last_fill_time=None,
            fills_today=0, days_to_earnings=20, config=config,
        )

    assert result.all_gates_passed is True
    assert result.signal_score is not None
    assert result.signal_score > 0.0, "Score must not be hardcoded to 0"
    assert result.component_scores is not None
    assert "regime" in result.component_scores
    assert "total" in result.component_scores
    assert result.action_taken in ("execute", "alert", "log")

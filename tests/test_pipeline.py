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

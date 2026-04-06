"""End-to-end integration tests for the TTrade pipeline."""
import pytest
import pandas as pd
from datetime import date, datetime
from engine.config import TTRadeConfig
from engine.models import MarketState
from engine.market_state import evaluate_market_state
from engine.pipeline import run_pipeline
from engine.scoring import ScoreComponents
from engine.reviewer import grade_outcome, grade_setup, auto_tag_failures
from engine.db import init_db, SignalRecord
from sqlmodel import Session, select


@pytest.fixture
def config():
    return TTRadeConfig()


@pytest.fixture
def uptrend_spy_bars():
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [500 + i * 1.5 for i in range(30)]
    return pd.DataFrame({
        "Open": [c - 0.5 for c in closes],
        "High": [c + 1.0 for c in closes],
        "Low": [c - 1.0 for c in closes],
        "Close": closes,
        "Volume": [50_000_000 + i * 100_000 for i in range(30)],
    }, index=dates)


def test_full_pipeline_chop_rejection(config):
    dates = pd.bdate_range(end=date(2026, 4, 3), periods=30)
    closes = [520 + (0.1 if i % 2 == 0 else -0.1) for i in range(30)]
    chop_bars = pd.DataFrame({
        "Open": [c - 0.05 for c in closes],
        "High": [c + 0.2 for c in closes],
        "Low": [c - 0.2 for c in closes],
        "Close": closes,
        "Volume": [50_000_000] * 30,
    }, index=dates)
    market = evaluate_market_state(chop_bars, config)
    assert market.state == MarketState.CHOP
    result = run_pipeline(
        ticker="SPY", ticker_bars=chop_bars, market_state=market,
        option_data={}, open_positions=[], last_fill_time=None,
        fills_today=0, days_to_earnings=None, config=config,
    )
    assert result.all_gates_passed is False
    assert result.action_taken == "reject"


def test_market_state_drives_direction(uptrend_spy_bars, config):
    market = evaluate_market_state(uptrend_spy_bars, config)
    assert market.state == MarketState.TREND_UP
    from engine.pipeline import determine_direction
    direction = determine_direction(market.state)
    assert direction == "bullish"


def test_scoring_bands_are_correct():
    a_score = ScoreComponents(regime=18, alignment=13, pullback=13, confirmation=18, stability=9, structure=8, event=9)
    assert a_score.band == "A"
    assert a_score.total >= 85
    b_score = ScoreComponents(regime=14, alignment=11, pullback=11, confirmation=14, stability=7, structure=7, event=8)
    assert b_score.band == "B"
    junk = ScoreComponents(regime=5, alignment=5, pullback=5, confirmation=5, stability=3, structure=3, event=3)
    assert junk.band == "JUNK"


def test_review_lifecycle():
    assert grade_setup(90.0) == "A"
    assert grade_outcome(0.60, "profit_target") == "A"
    assert grade_setup(90.0) == "A"
    assert grade_outcome(-0.40, "stop_loss") == "F"
    tags = auto_tag_failures(-0.40, "stop_loss", 90.0, mfe=0.10, mae=-0.42)
    assert "market_reversed" in tags


def test_db_round_trip(tmp_path, config):
    engine = init_db(str(tmp_path / "test.db"))
    with Session(engine) as session:
        record = SignalRecord(
            signal_id="sig_int_test", ticker="SPY", direction="bullish",
            timestamp=datetime.now(), market_state="TREND_UP", all_gates_passed=True,
            gate_results_json="[]", signal_score=87.5,
            component_scores_json='{"regime": 17}', action_taken="execute",
            strategy_version="1.1.0", config_hash=config.config_hash,
        )
        session.add(record)
        session.commit()
        result = session.exec(select(SignalRecord).where(SignalRecord.signal_id == "sig_int_test")).one()
        assert result.signal_score == 87.5
        assert result.config_hash == config.config_hash

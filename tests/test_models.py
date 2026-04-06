import pytest
from datetime import datetime, date
from engine.models import (
    GateResult, SignalEvaluation, SpreadLeg, SpreadStructure,
    ExecutionEvent, TradeReview, WeeklyLearningReport,
    MarketState, Direction, ExitReason, ActionTaken
)


def test_gate_result():
    gr = GateResult(
        gate_name="market_regime",
        passed=True,
        measured_value="TREND_UP",
        threshold="!= CHOP",
        config_version="1.1.0",
    )
    assert gr.passed is True
    assert gr.gate_name == "market_regime"


def test_signal_evaluation_all_gates_passed():
    gates = [
        GateResult(gate_name=f"gate_{i}", passed=True,
                   measured_value=1.0, threshold=0.5, config_version="1.1.0")
        for i in range(10)
    ]
    sig = SignalEvaluation(
        id="sig_abc12345",
        ticker="SPY",
        direction="bullish",
        timestamp=datetime.now(),
        market_state="TREND_UP",
        gate_results=gates,
        all_gates_passed=True,
        signal_score=87.5,
        component_scores={"regime": 17, "alignment": 13},
        action_taken="execute",
        strategy_version="1.1.0",
        config_hash="abcd1234abcd1234",
    )
    assert sig.all_gates_passed is True
    assert sig.signal_score == 87.5


def test_signal_evaluation_gates_failed():
    gates = [
        GateResult(gate_name="market_regime", passed=False,
                   measured_value="CHOP", threshold="!= CHOP",
                   config_version="1.1.0")
    ]
    sig = SignalEvaluation(
        id="sig_xyz99999",
        ticker="AAPL",
        direction="bullish",
        timestamp=datetime.now(),
        market_state="CHOP",
        gate_results=gates,
        all_gates_passed=False,
        signal_score=None,
        component_scores=None,
        action_taken="reject",
        strategy_version="1.1.0",
        config_hash="abcd1234abcd1234",
    )
    assert sig.signal_score is None


def test_spread_structure():
    buy_leg = SpreadLeg(
        symbol="SPY260501C00520000",
        side="BUY",
        open_close="OPEN",
        strike=520.0,
        expiry=date(2026, 5, 1),
        option_type="CALL",
    )
    sell_leg = SpreadLeg(
        symbol="SPY260501C00530000",
        side="SELL",
        open_close="OPEN",
        strike=530.0,
        expiry=date(2026, 5, 1),
        option_type="CALL",
    )
    spread = SpreadStructure(
        legs=[buy_leg, sell_leg],
        net_debit=0.72,
        max_loss=72.0,
        max_gain=928.0,
        spread_width=10.0,
        risk_reward_ratio=12.9,
    )
    assert len(spread.legs) == 2
    assert spread.net_debit == 0.72


def test_trade_review_grades():
    review = TradeReview(
        id="rev_abc12345",
        execution_id="exec_abc12345",
        signal_id="sig_abc12345",
        ticker="QQQ",
        direction="bearish",
        signal_score=89.0,
        entry_debit=0.72,
        exit_credit=1.21,
        pnl_pct=0.68,
        pnl_dollars=49.0,
        max_favorable_excursion=0.71,
        max_adverse_excursion=-0.12,
        hold_duration_hours=192.0,
        exit_reason="profit_target",
        setup_grade="A",
        execution_grade="B",
        outcome_grade="A",
        failure_tags=[],
        counterfactuals={
            "held_to_eod": 0.65,
            "wider_stop": 0.68,
        },
        review_notes=None,
        strategy_version="1.1.0",
        config_hash="abcd1234abcd1234",
    )
    assert review.setup_grade == "A"
    assert review.exit_reason == "profit_target"


def test_direction_enum():
    assert Direction.BULLISH == "bullish"
    assert Direction.BEARISH == "bearish"


def test_market_state_enum():
    assert MarketState.TREND_UP == "TREND_UP"
    assert MarketState.CHOP == "CHOP"

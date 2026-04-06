import pytest
from engine.reviewer import grade_outcome, grade_setup, grade_execution, auto_tag_failures


def test_grade_outcome_profit():
    assert grade_outcome(pnl_pct=0.60, exit_reason="profit_target") == "A"

def test_grade_outcome_small_profit():
    assert grade_outcome(pnl_pct=0.15, exit_reason="manual") == "C"

def test_grade_outcome_loss():
    grade = grade_outcome(pnl_pct=-0.40, exit_reason="stop_loss")
    assert grade in ("D", "F")

def test_grade_setup_high_score():
    assert grade_setup(signal_score=90.0) == "A"

def test_grade_setup_medium_score():
    assert grade_setup(signal_score=75.0) == "B"

def test_grade_setup_low_score():
    assert grade_setup(signal_score=55.0) == "C"

def test_grade_execution_good():
    grade = grade_execution(fill_vs_mid_pct=-0.01, entry_timing="on_confirmation", exit_timing="on_rule")
    assert grade in ("A", "B")

def test_auto_tag_failures_stop_loss():
    tags = auto_tag_failures(pnl_pct=-0.40, exit_reason="stop_loss", signal_score=88.0, mfe=0.10, mae=-0.42)
    assert isinstance(tags, list)
    assert len(tags) > 0

def test_auto_tag_no_failures():
    tags = auto_tag_failures(pnl_pct=0.60, exit_reason="profit_target", signal_score=90.0, mfe=0.65, mae=-0.05)
    assert tags == []

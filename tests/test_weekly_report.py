import pytest
from datetime import date
from engine.weekly_report import generate_weekly_report


def test_generate_empty_week():
    report = generate_weekly_report(signals=[], reviews=[], week_start=date(2026, 3, 30), week_end=date(2026, 4, 5))
    assert report.total_signals == 0
    assert report.total_trades == 0
    assert report.win_rate == 0.0


def test_generate_with_trades():
    signals = [
        {"signal_id": "sig_001", "signal_score": 88, "action_taken": "execute", "ticker": "SPY"},
        {"signal_id": "sig_002", "signal_score": 72, "action_taken": "alert", "ticker": "QQQ"},
        {"signal_id": "sig_003", "signal_score": 91, "action_taken": "execute", "ticker": "AAPL"},
    ]
    reviews = [
        {"signal_score": 88, "pnl_pct": 0.55, "pnl_dollars": 40, "ticker": "SPY",
         "exit_reason": "profit_target", "failure_tags": [], "setup_grade": "A", "outcome_grade": "A"},
        {"signal_score": 91, "pnl_pct": -0.38, "pnl_dollars": -30, "ticker": "AAPL",
         "exit_reason": "stop_loss", "failure_tags": ["market_reversed"],
         "setup_grade": "A", "outcome_grade": "F"},
    ]
    report = generate_weekly_report(signals=signals, reviews=reviews, week_start=date(2026, 3, 30), week_end=date(2026, 4, 5))
    assert report.total_signals == 3
    assert report.total_trades == 2
    assert report.win_rate == 0.5
    assert report.total_pnl == 10.0
    assert "SPY" in report.ticker_performance

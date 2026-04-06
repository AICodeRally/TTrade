import pytest
from datetime import datetime
from click.testing import CliRunner
from sqlmodel import Session
from engine.cli import cli
from engine.db import init_db, SignalRecord


def test_cli_version():
    runner = CliRunner()
    result = runner.invoke(cli, ["version"])
    assert result.exit_code == 0
    assert "TTrade v" in result.output


def test_cli_status():
    runner = CliRunner()
    result = runner.invoke(cli, ["status"])
    assert result.exit_code == 0
    assert "TTrade Status" in result.output


def test_cli_approve_missing_id():
    runner = CliRunner()
    result = runner.invoke(cli, ["approve"])
    assert result.exit_code != 0


def test_cli_approve_signal_not_found(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("TTRADE_DB_PATH", db_path)
    init_db(db_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["approve", "sig_nonexistent"])
    assert result.exit_code == 1
    assert "not found" in result.output


def test_cli_approve_rejected_signal(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("TTRADE_DB_PATH", db_path)
    engine = init_db(db_path)
    with Session(engine) as session:
        session.add(SignalRecord(
            signal_id="sig_reject", ticker="SPY", direction="bullish",
            timestamp=datetime.now(), market_state="TREND_UP",
            all_gates_passed=False, gate_results_json="[]",
            action_taken="reject", strategy_version="1.1.0", config_hash="test",
        ))
        session.commit()
    runner = CliRunner()
    result = runner.invoke(cli, ["approve", "sig_reject"])
    assert result.exit_code == 1
    assert "did not pass" in result.output

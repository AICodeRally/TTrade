# tests/test_db.py
import pytest
from datetime import datetime
from sqlmodel import Session, select
from engine.db import (
    SignalRecord, ExecutionRecord, PositionRecord,
    ReviewRecord, CooldownRecord, ConfigRecord,
    init_db
)


def test_init_db_creates_tables(tmp_path):
    db_path = tmp_path / "test.db"
    engine = init_db(str(db_path))
    with Session(engine) as session:
        results = session.exec(select(SignalRecord)).all()
        assert results == []


def test_signal_record_crud(db_session):
    from engine.db import SignalRecord
    record = SignalRecord(
        signal_id="sig_test0001",
        ticker="SPY",
        direction="bullish",
        timestamp=datetime.now(),
        market_state="TREND_UP",
        all_gates_passed=True,
        gate_results_json='[{"gate_name": "regime", "passed": true}]',
        signal_score=87.5,
        component_scores_json='{"regime": 17}',
        action_taken="execute",
        strategy_version="1.1.0",
        config_hash="abcd1234abcd1234",
    )
    db_session.add(record)
    db_session.commit()

    result = db_session.exec(
        select(SignalRecord).where(SignalRecord.signal_id == "sig_test0001")
    ).one()
    assert result.ticker == "SPY"
    assert result.signal_score == 87.5


def test_position_record_crud(db_session):
    from engine.db import PositionRecord
    pos = PositionRecord(
        position_id="pos_test0001",
        signal_id="sig_test0001",
        execution_id="exec_test0001",
        ticker="QQQ",
        direction="bearish",
        entry_debit=0.72,
        spread_json='{"legs": []}',
        status="open",
        opened_at=datetime.now(),
        max_favorable_excursion=0.0,
        max_adverse_excursion=0.0,
    )
    db_session.add(pos)
    db_session.commit()

    result = db_session.exec(
        select(PositionRecord).where(PositionRecord.status == "open")
    ).all()
    assert len(result) == 1
    assert result[0].ticker == "QQQ"


def test_cooldown_record(db_session):
    from engine.db import CooldownRecord
    cd = CooldownRecord(
        last_fill_time=datetime.now(),
        fills_today=1,
        trade_date="2026-04-07",
    )
    db_session.add(cd)
    db_session.commit()

    result = db_session.exec(select(CooldownRecord)).one()
    assert result.fills_today == 1

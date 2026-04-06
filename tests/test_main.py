"""Tests for main orchestrator — market hours, scan cycle, monitor cycle."""
import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from zoneinfo import ZoneInfo

from sqlmodel import Session

from engine.config import TTRadeConfig
from engine.db import init_db, PositionRecord, SignalRecord
from engine.main import is_market_hours, is_trade_hours, run_monitor_cycle

ET = ZoneInfo("America/New_York")


@pytest.fixture
def config():
    return TTRadeConfig()


def test_market_hours_weekday_open(config):
    # Monday 10:00 ET should be market hours
    mock_now = datetime(2026, 4, 6, 10, 0, tzinfo=ET)  # Monday
    with patch("engine.main.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert is_market_hours(config) is True


def test_market_hours_weekend(config):
    # Saturday 10:00 ET should NOT be market hours
    mock_now = datetime(2026, 4, 4, 10, 0, tzinfo=ET)  # Saturday
    with patch("engine.main.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert is_market_hours(config) is False


def test_market_hours_after_close(config):
    # Monday 17:00 ET should NOT be market hours
    mock_now = datetime(2026, 4, 6, 17, 0, tzinfo=ET)  # Monday
    with patch("engine.main.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert is_market_hours(config) is False


def test_trade_hours_before_start(config):
    # Monday 10:00 ET is market hours but NOT trade hours (trade starts 11:00)
    mock_now = datetime(2026, 4, 6, 10, 0, tzinfo=ET)
    with patch("engine.main.datetime") as mock_dt:
        mock_dt.now.return_value = mock_now
        mock_dt.side_effect = lambda *a, **kw: datetime(*a, **kw)
        assert is_trade_hours(config) is False


def test_monitor_exits_on_chop(config, tmp_path):
    """Monitor should close positions when market flips to CHOP."""
    engine = init_db(str(tmp_path / "test.db"))
    with Session(engine) as session:
        session.add(PositionRecord(
            position_id="pos_test1", signal_id="sig_1", execution_id="exec_1",
            ticker="SPY", direction="bullish", entry_debit=0.75,
            spread_json="{}", status="open", opened_at=datetime.now(),
            pnl_pct=-0.10,
        ))
        session.commit()

        # Mock market state as CHOP → thesis_invalid exit
        from engine.market_state import MarketStateResult
        from engine.models import MarketState
        import pandas as pd

        chop_state = MarketStateResult(
            state=MarketState.CHOP, slope=0.1, current_price=520.0,
            sma_value=520.5, price_vs_ma="below",
        )

        with patch("engine.main.get_daily_bars") as mock_bars, \
             patch("engine.main.evaluate_market_state", return_value=chop_state):
            mock_bars.return_value = pd.DataFrame({"Close": [520.0]})
            run_monitor_cycle(config, session)

        # Position should be closed with thesis_invalid
        pos = session.get(PositionRecord, 1)
        assert pos.status == "closed"
        assert pos.exit_reason == "thesis_invalid"

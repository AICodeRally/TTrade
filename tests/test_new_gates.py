"""Tests for gates 11-15: correlation, VIX, earnings calendar, loss breaker, news sentiment."""
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from engine.config import TTRadeConfig
from engine.models import GateResult

ET = ZoneInfo("America/New_York")


@pytest.fixture
def config():
    return TTRadeConfig()


# ── Gate 11: Correlation ──────────────────────────────────────

class TestCorrelationGate:
    def test_non_speculative_passes(self, config):
        from engine.gates.correlation import check_correlation
        result = check_correlation("AAPL", "bullish", [], config)
        assert result.passed is True
        assert result.measured_value == "non-speculative"

    def test_speculative_no_overlap_passes(self, config):
        from engine.gates.correlation import check_correlation
        result = check_correlation("NVDA", "bullish", [], config)
        assert result.passed is True
        assert result.measured_value == "clear"

    def test_speculative_already_open_blocks(self, config):
        from engine.gates.correlation import check_correlation
        positions = [{"ticker": "NVDA", "direction": "bullish"}]
        result = check_correlation("NVDA", "bullish", positions, config)
        assert result.passed is False
        assert "already_open" in result.measured_value

    def test_max_speculative_reached_blocks(self, config):
        from engine.gates.correlation import check_correlation
        # One speculative already open (RKLB), trying to open NVDA
        positions = [{"ticker": "RKLB", "direction": "bullish"}]
        result = check_correlation("NVDA", "bullish", positions, config)
        assert result.passed is False
        assert "spec_open" in result.measured_value

    def test_different_speculative_under_limit_passes(self, config):
        from engine.gates.correlation import check_correlation
        # No speculative positions open, opening RKLB
        result = check_correlation("RKLB", "bearish", [], config)
        assert result.passed is True

    def test_etf_with_spec_open_still_passes(self, config):
        from engine.gates.correlation import check_correlation
        positions = [{"ticker": "NVDA", "direction": "bullish"}]
        result = check_correlation("SPY", "bullish", positions, config)
        assert result.passed is True


# ── Gate 12: VIX Circuit Breaker ──────────────────────────────

class TestVIXCircuitBreaker:
    @patch("engine.gates.vix_circuit_breaker.get_vix_level", return_value=22.5)
    def test_vix_below_threshold_passes(self, mock_vix, config):
        from engine.gates.vix_circuit_breaker import check_vix_circuit_breaker
        result = check_vix_circuit_breaker(config)
        assert result.passed is True
        assert "22.5" in result.measured_value

    @patch("engine.gates.vix_circuit_breaker.get_vix_level", return_value=35.0)
    def test_vix_above_threshold_blocks(self, mock_vix, config):
        from engine.gates.vix_circuit_breaker import check_vix_circuit_breaker
        result = check_vix_circuit_breaker(config)
        assert result.passed is False
        assert "35.0" in result.measured_value

    @patch("engine.gates.vix_circuit_breaker.get_vix_level", return_value=30.0)
    def test_vix_at_threshold_passes(self, mock_vix, config):
        from engine.gates.vix_circuit_breaker import check_vix_circuit_breaker
        result = check_vix_circuit_breaker(config)
        assert result.passed is True  # > not >=

    @patch("engine.gates.vix_circuit_breaker.get_vix_level", return_value=None)
    def test_vix_unavailable_fail_open(self, mock_vix, config):
        from engine.gates.vix_circuit_breaker import check_vix_circuit_breaker
        result = check_vix_circuit_breaker(config)
        assert result.passed is True
        assert "unavailable" in result.measured_value


# ── Gate 13: Earnings Calendar ────────────────────────────────

class TestEarningsCalendar:
    @patch("engine.gates.earnings_calendar.get_days_to_earnings", return_value=30)
    def test_earnings_far_passes(self, mock_earn, config):
        from engine.gates.earnings_calendar import check_earnings_calendar
        result = check_earnings_calendar("AAPL", config)
        assert result.passed is True
        assert "30d" in result.measured_value

    @patch("engine.gates.earnings_calendar.get_days_to_earnings", return_value=3)
    def test_earnings_within_blackout_blocks(self, mock_earn, config):
        from engine.gates.earnings_calendar import check_earnings_calendar
        result = check_earnings_calendar("AAPL", config)
        assert result.passed is False
        assert "3d" in result.measured_value

    @patch("engine.gates.earnings_calendar.get_days_to_earnings", return_value=7)
    def test_earnings_at_blackout_boundary_blocks(self, mock_earn, config):
        from engine.gates.earnings_calendar import check_earnings_calendar
        result = check_earnings_calendar("AAPL", config)
        assert result.passed is False  # <= 7

    @patch("engine.gates.earnings_calendar.get_days_to_earnings", return_value=8)
    def test_earnings_just_outside_blackout_passes(self, mock_earn, config):
        from engine.gates.earnings_calendar import check_earnings_calendar
        result = check_earnings_calendar("AAPL", config)
        assert result.passed is True

    @patch("engine.gates.earnings_calendar.get_days_to_earnings", return_value=None)
    def test_no_earnings_data_passes(self, mock_earn, config):
        from engine.gates.earnings_calendar import check_earnings_calendar
        result = check_earnings_calendar("SPY", config)
        assert result.passed is True
        assert "no_date" in result.measured_value


# ── Gate 14: Loss Circuit Breaker ─────────────────────────────

class TestLossCircuitBreaker:
    def _make_session_with_positions(self, positions_data):
        """Create an in-memory DB session with closed positions."""
        from sqlmodel import Session, SQLModel, create_engine
        from engine.db import PositionRecord
        engine = create_engine("sqlite:///:memory:", echo=False)
        SQLModel.metadata.create_all(engine)
        session = Session(engine)
        for p in positions_data:
            session.add(PositionRecord(**p))
        session.commit()
        return session

    def test_no_losses_passes(self, config):
        from engine.gates.loss_circuit_breaker import check_loss_circuit_breaker
        session = self._make_session_with_positions([])
        result = check_loss_circuit_breaker(session, config)
        assert result.passed is True

    def test_daily_loss_exceeded_blocks(self, config):
        from engine.gates.loss_circuit_breaker import check_loss_circuit_breaker
        # Use ET-aligned naive datetime so "today" matches the gate's perspective
        now_et = datetime.now(ET).replace(tzinfo=None)
        # Ensure closed_at is after today's midnight in ET
        today_noon = now_et.replace(hour=12, minute=0, second=0, microsecond=0)
        session = self._make_session_with_positions([{
            "position_id": "p1", "signal_id": "s1", "execution_id": "e1",
            "ticker": "NVDA", "direction": "bullish", "entry_debit": 100.0,
            "spread_json": "{}", "status": "closed",
            "opened_at": today_noon - timedelta(hours=5),
            "closed_at": today_noon,
            "pnl_dollars": -250.0, "pnl_pct": -0.50,
        }])
        result = check_loss_circuit_breaker(session, config)
        assert result.passed is False
        assert "daily" in result.measured_value

    def test_weekly_loss_exceeded_blocks(self, config):
        from engine.gates.loss_circuit_breaker import check_loss_circuit_breaker
        now = datetime.now()
        session = self._make_session_with_positions([
            {
                "position_id": "p1", "signal_id": "s1", "execution_id": "e1",
                "ticker": "NVDA", "direction": "bullish", "entry_debit": 100.0,
                "spread_json": "{}", "status": "closed",
                "opened_at": now - timedelta(hours=10), "closed_at": now - timedelta(hours=5),
                "pnl_dollars": -150.0, "pnl_pct": -0.30,
            },
            {
                "position_id": "p2", "signal_id": "s2", "execution_id": "e2",
                "ticker": "RKLB", "direction": "bullish", "entry_debit": 100.0,
                "spread_json": "{}", "status": "closed",
                "opened_at": now - timedelta(hours=8), "closed_at": now - timedelta(hours=3),
                "pnl_dollars": -300.0, "pnl_pct": -0.60,
            },
        ])
        result = check_loss_circuit_breaker(session, config)
        assert result.passed is False

    def test_small_losses_pass(self, config):
        from engine.gates.loss_circuit_breaker import check_loss_circuit_breaker
        now = datetime.now()
        session = self._make_session_with_positions([{
            "position_id": "p1", "signal_id": "s1", "execution_id": "e1",
            "ticker": "AAPL", "direction": "bullish", "entry_debit": 75.0,
            "spread_json": "{}", "status": "closed",
            "opened_at": now - timedelta(hours=5), "closed_at": now - timedelta(hours=1),
            "pnl_dollars": -50.0, "pnl_pct": -0.10,
        }])
        result = check_loss_circuit_breaker(session, config)
        assert result.passed is True


# ── Gate 15: News Sentiment ───────────────────────────────────

class TestNewsSentiment:
    @patch("engine.gates.news_sentiment._fetch_and_score_news", return_value=("neutral", 0.0))
    def test_neutral_news_passes(self, mock_news, config):
        from engine.gates.news_sentiment import check_news_sentiment
        with patch("engine.gates.news_sentiment._get_keychain_value", return_value="test-token"):
            result = check_news_sentiment("AAPL", "bullish", config)
        assert result.passed is True

    @patch("engine.gates.news_sentiment._fetch_and_score_news", return_value=("bearish", -0.7))
    def test_bearish_news_blocks_bullish(self, mock_news, config):
        from engine.gates.news_sentiment import check_news_sentiment
        with patch("engine.gates.news_sentiment._get_keychain_value", return_value="test-token"):
            result = check_news_sentiment("AAPL", "bullish", config)
        assert result.passed is False
        assert "bearish" in result.measured_value

    @patch("engine.gates.news_sentiment._fetch_and_score_news", return_value=("bullish", 0.8))
    def test_bullish_news_blocks_bearish(self, mock_news, config):
        from engine.gates.news_sentiment import check_news_sentiment
        with patch("engine.gates.news_sentiment._get_keychain_value", return_value="test-token"):
            result = check_news_sentiment("AAPL", "bearish", config)
        assert result.passed is False
        assert "bullish" in result.measured_value

    @patch("engine.gates.news_sentiment._fetch_and_score_news", return_value=("bullish", 0.6))
    def test_bullish_news_passes_bullish(self, mock_news, config):
        from engine.gates.news_sentiment import check_news_sentiment
        with patch("engine.gates.news_sentiment._get_keychain_value", return_value="test-token"):
            result = check_news_sentiment("AAPL", "bullish", config)
        assert result.passed is True

    def test_no_token_passes(self, config):
        from engine.gates.news_sentiment import check_news_sentiment
        with patch.dict("os.environ", {"TTRADE_DASHBOARD_TOKEN": ""}), \
             patch("engine.gates.news_sentiment._get_keychain_value", return_value=""):
            result = check_news_sentiment("AAPL", "bullish", config)
        assert result.passed is True
        assert "no_token" in result.measured_value

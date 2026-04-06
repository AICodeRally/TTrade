import pytest
from engine.monitor import check_exit_rules, ExitSignal
from engine.config import TTRadeConfig
from engine.models import MarketState


@pytest.fixture
def config():
    return TTRadeConfig()


def test_stop_loss_triggered(config):
    signal = check_exit_rules(pnl_pct=-0.45, current_dte=30, market_state=MarketState.TREND_UP, config=config)
    assert signal is not None
    assert signal.reason == "stop_loss"


def test_profit_target_triggered(config):
    signal = check_exit_rules(pnl_pct=0.65, current_dte=30, market_state=MarketState.TREND_UP, config=config)
    assert signal is not None
    assert signal.reason == "profit_target"


def test_thesis_invalid_chop(config):
    signal = check_exit_rules(pnl_pct=0.10, current_dte=30, market_state=MarketState.CHOP, config=config)
    assert signal is not None
    assert signal.reason == "thesis_invalid"


def test_time_decay_exit(config):
    signal = check_exit_rules(pnl_pct=0.10, current_dte=5, market_state=MarketState.TREND_UP, config=config)
    assert signal is not None
    assert signal.reason == "time_decay"


def test_no_exit_normal(config):
    signal = check_exit_rules(pnl_pct=0.10, current_dte=30, market_state=MarketState.TREND_UP, config=config)
    assert signal is None

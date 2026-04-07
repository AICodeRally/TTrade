import pytest
from engine.config import TTRadeConfig


def test_config_defaults():
    cfg = TTRadeConfig()
    assert cfg.tickers == ("SPY", "QQQ", "AAPL", "MSFT", "NVDA", "VCX", "RKLB")
    assert cfg.ma_period == 20
    assert cfg.stop_loss_pct == -0.40
    assert cfg.profit_target_pct == 0.60
    assert cfg.max_open_positions == 2
    assert cfg.mode == "MANUAL_APPROVAL"


def test_config_is_frozen():
    cfg = TTRadeConfig()
    with pytest.raises(AttributeError):
        cfg.ma_period = 50


def test_config_hash_deterministic():
    cfg1 = TTRadeConfig()
    cfg2 = TTRadeConfig()
    assert cfg1.config_hash == cfg2.config_hash
    assert len(cfg1.config_hash) == 16  # first 16 chars of sha256


def test_config_hash_changes_with_values():
    cfg1 = TTRadeConfig()
    cfg2 = TTRadeConfig(ma_period=50)
    assert cfg1.config_hash != cfg2.config_hash


def test_config_version():
    cfg = TTRadeConfig()
    assert cfg.strategy_version == "1.1.0"

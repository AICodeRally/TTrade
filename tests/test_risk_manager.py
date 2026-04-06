import pytest
from engine.risk_manager import calculate_position_size, select_strikes, get_exposure_bucket
from engine.config import TTRadeConfig


@pytest.fixture
def config():
    return TTRadeConfig()


def test_position_size_normal(config):
    size = calculate_position_size(account_value=1000.0, iv_rank=30.0, config=config)
    assert config.min_debit <= size <= config.max_debit


def test_position_size_high_iv_reduces(config):
    normal = calculate_position_size(1000.0, iv_rank=30.0, config=config)
    reduced = calculate_position_size(1000.0, iv_rank=60.0, config=config)
    assert reduced < normal


def test_exposure_bucket_spy():
    assert get_exposure_bucket("SPY") == "market"


def test_exposure_bucket_aapl():
    assert get_exposure_bucket("AAPL") == "tech"


def test_select_strikes_bullish():
    chain = [
        {"strike": 515, "type": "CALL", "bid": 8.0, "ask": 8.30, "oi": 500},
        {"strike": 520, "type": "CALL", "bid": 5.0, "ask": 5.30, "oi": 800},
        {"strike": 525, "type": "CALL", "bid": 3.0, "ask": 3.20, "oi": 600},
        {"strike": 530, "type": "CALL", "bid": 1.5, "ask": 1.70, "oi": 400},
    ]
    result = select_strikes(chain=chain, direction="bullish", target_debit=75.0, config=TTRadeConfig())
    assert result is not None
    assert result["buy_strike"] < result["sell_strike"]

import pytest
from unittest.mock import patch, MagicMock
from engine.broker import BrokerClient


@patch("engine.broker.subprocess.run")
def test_broker_init_reads_keychain(mock_run):
    mock_run.return_value = MagicMock(stdout="test_api_key_123\n", returncode=0)
    client = BrokerClient(account_id="test_account")
    assert client.api_key == "test_api_key_123"
    assert client.account_id == "test_account"


@patch("engine.broker.subprocess.run")
def test_broker_get_quote(mock_run):
    mock_run.return_value = MagicMock(stdout="test_api_key_123\n", returncode=0)
    client = BrokerClient(account_id="test_account")
    with patch.object(client, "_request", return_value={"quotes": [{"symbol": "SPY", "last": 520.50}]}):
        quote = client.get_quote("SPY")
        assert quote["symbol"] == "SPY"


@patch("engine.broker.subprocess.run")
def test_broker_get_option_chain(mock_run):
    mock_run.return_value = MagicMock(stdout="test_api_key_123\n", returncode=0)
    client = BrokerClient(account_id="test_account")
    chain_data = {"options": [
        {"symbol": "SPY260501C00520000", "strike": 520},
        {"symbol": "SPY260501C00530000", "strike": 530},
    ]}
    with patch.object(client, "_request", return_value=chain_data):
        chain = client.get_option_chain("SPY", "2026-05-01")
        assert len(chain["options"]) == 2


@patch("engine.broker.subprocess.run")
def test_broker_preflight_multileg(mock_run):
    mock_run.return_value = MagicMock(stdout="test_api_key_123\n", returncode=0)
    client = BrokerClient(account_id="test_account")
    with patch.object(client, "_request", return_value={"valid": True}):
        result = client.preflight_multileg(legs=[], limit_price=0.72)
        assert result["valid"] is True


@patch("engine.broker.subprocess.run")
def test_broker_place_order(mock_run):
    mock_run.return_value = MagicMock(stdout="test_api_key_123\n", returncode=0)
    client = BrokerClient(account_id="test_account")
    with patch.object(client, "_request", return_value={"orderId": "uuid-123", "status": "PENDING"}):
        result = client.place_multileg_order(legs=[], limit_price=0.72)
        assert result["orderId"] == "uuid-123"

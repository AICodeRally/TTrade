import pytest
from unittest.mock import patch, MagicMock
from engine.sync import SyncClient


@patch("engine.sync.httpx.Client")
def test_sync_client_init(mock_client_cls):
    client = SyncClient(worker_url="https://ttrade.workers.dev", api_key="test_key")
    assert client.worker_url == "https://ttrade.workers.dev"


@patch("engine.sync.httpx.Client")
def test_sync_signals(mock_client_cls):
    mock_client = MagicMock()
    mock_client_cls.return_value = mock_client
    mock_client.post.return_value = MagicMock(
        status_code=200, json=MagicMock(return_value={"ok": True, "synced": {"signals": 1}})
    )
    client = SyncClient(worker_url="https://ttrade.workers.dev", api_key="test_key")
    result = client.sync_signals([{"signal_id": "sig_test001"}])
    assert result["ok"] is True

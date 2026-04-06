import pytest
from unittest.mock import MagicMock
from engine.executor import prepare_order_legs, submit_order


def test_prepare_order_legs():
    legs = prepare_order_legs(buy_symbol="SPY260501C00520000", sell_symbol="SPY260501C00530000", open_close="OPEN")
    assert len(legs) == 2
    assert legs[0]["side"] == "BUY"
    assert legs[1]["side"] == "SELL"
    assert legs[0]["instrument"]["type"] == "OPTION"


def test_submit_order_calls_preflight_then_place():
    mock_broker = MagicMock()
    mock_broker.preflight_multileg.return_value = {"valid": True}
    mock_broker.place_multileg_order.return_value = {"orderId": "uuid-123", "status": "PENDING"}
    result = submit_order(broker=mock_broker, legs=[{"side": "BUY"}, {"side": "SELL"}], limit_price=0.70)
    mock_broker.preflight_multileg.assert_called_once()
    mock_broker.place_multileg_order.assert_called_once()
    assert result["orderId"] == "uuid-123"


def test_submit_order_preflight_fails():
    mock_broker = MagicMock()
    mock_broker.preflight_multileg.return_value = {"valid": False, "reason": "insufficient funds"}
    with pytest.raises(ValueError, match="Preflight failed"):
        submit_order(broker=mock_broker, legs=[{"side": "BUY"}, {"side": "SELL"}], limit_price=0.70)
    mock_broker.place_multileg_order.assert_not_called()

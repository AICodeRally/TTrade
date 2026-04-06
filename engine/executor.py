"""Order placement — preflight, submit, poll for fill."""
import logging
import time
import uuid
from engine.broker import BrokerClient

logger = logging.getLogger(__name__)


def prepare_order_legs(buy_symbol: str, sell_symbol: str, open_close: str = "OPEN") -> list[dict]:
    return [
        {"instrument": {"symbol": buy_symbol, "type": "OPTION"}, "side": "BUY",
         "openCloseIndicator": open_close, "ratioQuantity": 1},
        {"instrument": {"symbol": sell_symbol, "type": "OPTION"}, "side": "SELL",
         "openCloseIndicator": open_close, "ratioQuantity": 1},
    ]


def submit_order(broker: BrokerClient, legs: list[dict], limit_price: float, mode: str = "MANUAL_APPROVAL") -> dict:
    if mode == "PAPER":
        paper_id = f"PAPER-{uuid.uuid4().hex[:8]}"
        logger.info("PAPER mode — simulating order %s at $%.2f", paper_id, limit_price)
        return {"orderId": paper_id, "status": "PAPER_SIMULATED", "limitPrice": limit_price}
    preflight = broker.preflight_multileg(legs, limit_price)
    if not preflight.get("valid", False):
        raise ValueError(f"Preflight failed: {preflight.get('reason', 'unknown')}")
    logger.info("Preflight passed, placing order at $%.2f", limit_price)
    return broker.place_multileg_order(legs, limit_price)


def poll_for_fill(broker: BrokerClient, order_id: str, poll_interval_sec: int = 30, timeout_min: int = 15) -> dict:
    max_polls = (timeout_min * 60) // poll_interval_sec
    for i in range(max_polls):
        status = broker.get_order(order_id)
        order_status = status.get("status", "UNKNOWN")
        if order_status in ("FILLED", "EXECUTED"):
            logger.info("Order %s filled", order_id)
            return status
        elif order_status in ("REJECTED", "CANCELLED", "EXPIRED"):
            logger.warning("Order %s ended: %s", order_id, order_status)
            return status
        logger.debug("Order %s status: %s (poll %d/%d)", order_id, order_status, i + 1, max_polls)
        time.sleep(poll_interval_sec)
    logger.warning("Order %s timed out after %d min", order_id, timeout_min)
    return {"status": "TIMEOUT", "orderId": order_id}

"""Public.com SDK wrapper with macOS Keychain auth."""
import subprocess
import uuid
import logging
import httpx

logger = logging.getLogger(__name__)
BASE_URL = "https://api.public.com/userapigateway/trading"


def _get_keychain_value(service: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Keychain lookup failed for {service}: {result.stderr}")
    return result.stdout.strip()


class BrokerClient:
    def __init__(self, account_id: str, api_key: str | None = None):
        self.account_id = account_id
        if api_key:
            self.api_key = api_key
        else:
            self.api_key = _get_keychain_value("ttrade-PUBLIC_API_KEY")
        self._client = httpx.Client(
            base_url=f"{BASE_URL}/{account_id}",
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_accounts(self) -> dict:
        return self._request("GET", "/get-accounts")

    def get_portfolio(self) -> dict:
        return self._request("GET", "/get-account-portfolio-v2")

    def get_quote(self, symbol: str) -> dict:
        data = self._request("POST", "/get-quotes", json={"symbols": [symbol]})
        return data["quotes"][0]

    def get_quotes(self, symbols: list[str]) -> list[dict]:
        data = self._request("POST", "/get-quotes", json={"symbols": symbols})
        return data["quotes"]

    def get_option_expirations(self, symbol: str) -> dict:
        return self._request("POST", "/get-option-expirations", json={"symbol": symbol})

    def get_option_chain(self, symbol: str, expiration: str) -> dict:
        return self._request("POST", "/get-option-chain", json={"symbol": symbol, "expiration": expiration})

    def get_option_greeks(self, option_symbol: str) -> dict:
        return self._request("GET", f"/get-option-greeks?symbol={option_symbol}")

    def preflight_multileg(self, legs: list[dict], limit_price: float) -> dict:
        order = self._build_order(legs, limit_price)
        return self._request("POST", "/preflight-multi-leg", json=order)

    def place_multileg_order(self, legs: list[dict], limit_price: float) -> dict:
        order = self._build_order(legs, limit_price)
        logger.info("Placing multileg order: %s", order["orderId"])
        return self._request("POST", "/place-multileg-order", json=order)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/get-order?orderId={order_id}")

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/cancel-order?orderId={order_id}")

    def _build_order(self, legs: list[dict], limit_price: float) -> dict:
        return {
            "orderId": str(uuid.uuid4()),
            "quantity": 1,
            "type": "LIMIT",
            "limitPrice": str(limit_price),
            "expiration": {"timeInForce": "DAY"},
            "legs": legs,
        }

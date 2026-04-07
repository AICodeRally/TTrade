"""Public.com SDK wrapper with macOS Keychain auth."""
import subprocess
import uuid
import logging
import httpx

logger = logging.getLogger(__name__)
API_BASE = "https://api.public.com/userapigateway"
AUTH_URL = "https://api.public.com/userapiauthservice/personal/access-tokens"


def _get_keychain_value(service: str) -> str:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-w"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Keychain lookup failed for {service}: {result.stderr}")
    return result.stdout.strip()


def _get_access_token(secret: str, validity_minutes: int = 60) -> str:
    """Exchange secret key for a temporary access token."""
    resp = httpx.post(AUTH_URL, json={"validityInMinutes": validity_minutes, "secret": secret}, timeout=30.0)
    resp.raise_for_status()
    return resp.json()["accessToken"]


class BrokerClient:
    def __init__(self, account_id: str, api_key: str | None = None):
        self.account_id = account_id
        secret = api_key or _get_keychain_value("ttrade-PUBLIC_API_KEY")
        logger.info("Exchanging secret for access token...")
        access_token = _get_access_token(secret)
        logger.info("Access token obtained.")
        self._client = httpx.Client(
            base_url=API_BASE,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            timeout=30.0,
        )

    def _request(self, method: str, path: str, **kwargs) -> dict:
        resp = self._client.request(method, path, **kwargs)
        resp.raise_for_status()
        return resp.json()

    # ── Account endpoints (/trading/) ──

    def get_accounts(self) -> dict:
        return self._request("GET", "/trading/account")

    def get_portfolio(self) -> dict:
        return self._request("GET", f"/trading/{self.account_id}/portfolio/v2")

    def get_history(self) -> dict:
        return self._request("GET", f"/trading/{self.account_id}/history")

    # ── Market data endpoints (/marketdata/{accountId}/) ──

    def get_quote(self, symbol: str, instrument_type: str = "EQUITY") -> dict:
        data = self._request(
            "POST", f"/marketdata/{self.account_id}/quotes",
            json={"instruments": [{"symbol": symbol, "type": instrument_type}]},
        )
        return data["quotes"][0]

    def get_quotes(self, symbols: list[str], instrument_type: str = "EQUITY") -> list[dict]:
        data = self._request(
            "POST", f"/marketdata/{self.account_id}/quotes",
            json={"instruments": [{"symbol": s, "type": instrument_type} for s in symbols]},
        )
        return data["quotes"]

    def get_option_expirations(self, symbol: str) -> dict:
        return self._request(
            "POST", f"/marketdata/{self.account_id}/option-expirations",
            json={"instrument": {"symbol": symbol, "type": "EQUITY"}},
        )

    def get_option_chain(self, symbol: str, expiration: str) -> dict:
        return self._request(
            "POST", f"/marketdata/{self.account_id}/option-chain",
            json={"instrument": {"symbol": symbol, "type": "EQUITY"}, "expirationDate": expiration},
        )

    def get_option_greeks(self, option_symbol: str) -> dict:
        return self._request("GET", f"/trading/options/greeks?symbol={option_symbol}")

    # ── Order endpoints (/trading/) ──

    def preflight_multileg(self, legs: list[dict], limit_price: float) -> dict:
        order = self._build_order(legs, limit_price)
        return self._request("POST", "/trading/orders/preflight-multi-leg", json=order)

    def place_multileg_order(self, legs: list[dict], limit_price: float) -> dict:
        order = self._build_order(legs, limit_price)
        logger.info("Placing multileg order: %s", order["orderId"])
        return self._request("POST", "/trading/orders/multileg", json=order)

    def get_order(self, order_id: str) -> dict:
        return self._request("GET", f"/trading/orders/{order_id}")

    def cancel_order(self, order_id: str) -> dict:
        return self._request("DELETE", f"/trading/orders/{order_id}")

    def _build_order(self, legs: list[dict], limit_price: float) -> dict:
        return {
            "orderId": str(uuid.uuid4()),
            "quantity": 1,
            "type": "LIMIT",
            "limitPrice": str(limit_price),
            "expiration": {"timeInForce": "DAY"},
            "legs": legs,
        }

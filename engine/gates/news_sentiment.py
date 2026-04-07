"""Gate 15: News sentiment — score recent headlines before entry."""
import logging
import os
import subprocess

import requests

from engine.config import TTRadeConfig
from engine.models import GateResult

logger = logging.getLogger(__name__)


def _get_keychain_value(service_name: str) -> str:
    try:
        result = subprocess.run(
            ["security", "find-generic-password", "-s", service_name, "-w"],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _fetch_and_score_news(ticker: str, direction: str, dashboard_token: str) -> tuple[str, float]:
    """Fetch news from Worker and score sentiment via Worker AI endpoint.

    All AI calls route through the Cloudflare AI Gateway on the Worker side.
    Returns (sentiment, score) where sentiment is bullish/bearish/neutral
    and score is -1.0 to 1.0.
    """
    worker_url = os.environ.get("TTRADE_WORKER_URL", "https://ttrade-worker.aicoderally.workers.dev")

    # Fetch news
    try:
        resp = requests.get(
            f"{worker_url}/market/news/{ticker}",
            headers={"Authorization": f"Bearer {dashboard_token}"},
            timeout=10,
        )
        if not resp.ok or not resp.json().get("articles"):
            return "neutral", 0.0
        headlines = [a["title"] for a in resp.json()["articles"][:5]]
    except Exception:
        return "neutral", 0.0

    if not headlines:
        return "neutral", 0.0

    # Score via Worker AI endpoint (routes through CF AI Gateway)
    try:
        payload = {
            "ticker": ticker,
            "direction": direction,
            "signal_score": 0,
            "component_scores": {},
            "market_state": "unknown",
            "gate_results": [],
            "recent_prices": [],
            "news_headlines": headlines,
        }
        resp = requests.post(
            f"{worker_url}/ai/analyze",
            json=payload,
            headers={"Authorization": f"Bearer {dashboard_token}"},
            timeout=15,
        )
        if resp.ok and resp.json().get("ok"):
            analysis = resp.json()["analysis"]
            conviction = analysis.get("conviction", 50)
            if conviction >= 60:
                return "bullish" if direction == "bullish" else "bearish", conviction / 100.0
            elif conviction <= 30:
                return "bearish" if direction == "bullish" else "bullish", -conviction / 100.0
            return "neutral", 0.0
    except Exception as e:
        logger.debug("News sentiment scoring failed: %s", e)

    return "neutral", 0.0


def check_news_sentiment(ticker: str, direction: str, config: TTRadeConfig) -> GateResult:
    """Block entries when news sentiment is strongly negative for the trade direction."""
    dashboard_token = os.environ.get("TTRADE_DASHBOARD_TOKEN") or _get_keychain_value("ttrade-DASHBOARD_TOKEN")

    if not dashboard_token:
        # No token — pass (can't check news without Worker access)
        return GateResult(
            gate_name="news_sentiment", passed=True,
            measured_value="no_token", threshold="sentiment_check",
            config_version=config.strategy_version,
        )

    sentiment, score = _fetch_and_score_news(ticker, direction, dashboard_token)

    # Block if sentiment is strongly against our direction
    # For bullish trades: block on strongly bearish news (score < -0.5)
    # For bearish trades: block on strongly bullish news (score > 0.5)
    if direction == "bullish" and score < -0.5:
        return GateResult(
            gate_name="news_sentiment", passed=False,
            measured_value=f"{sentiment}({score:.2f})",
            threshold="score>-0.5_for_bullish",
            config_version=config.strategy_version,
        )
    if direction == "bearish" and score > 0.5:
        return GateResult(
            gate_name="news_sentiment", passed=False,
            measured_value=f"{sentiment}({score:.2f})",
            threshold="score<0.5_for_bearish",
            config_version=config.strategy_version,
        )

    return GateResult(
        gate_name="news_sentiment", passed=True,
        measured_value=f"{sentiment}({score:.2f})",
        threshold="no_adverse_sentiment",
        config_version=config.strategy_version,
    )

"""AI Signal Analyst — Claude evaluates setup quality before alerting."""
import logging
import os
from dataclasses import dataclass

import requests

logger = logging.getLogger(__name__)


@dataclass
class AIAnalysis:
    conviction: float
    reasoning: str
    risk_factors: list[str]
    trade_quality: str  # A, B, C, PASS
    summary: str


def analyze_signal(
    ticker: str,
    direction: str,
    signal_score: float,
    component_scores: dict,
    market_state: str,
    gate_results: list[dict],
    recent_prices: list[dict],
    news_headlines: list[str],
) -> AIAnalysis | None:
    """Send signal data to Worker AI endpoint for Claude analysis."""
    worker_url = os.environ.get("TTRADE_WORKER_URL", "https://ttrade-worker.aicoderally.workers.dev")
    dashboard_token = os.environ.get("TTRADE_DASHBOARD_TOKEN", "")

    if not dashboard_token:
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "ttrade-DASHBOARD_TOKEN", "-w"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                dashboard_token = result.stdout.strip()
        except Exception:
            pass

    if not dashboard_token:
        logger.warning("No DASHBOARD_TOKEN — skipping AI analysis")
        return None

    payload = {
        "ticker": ticker,
        "direction": direction,
        "signal_score": signal_score,
        "component_scores": component_scores,
        "market_state": market_state,
        "gate_results": gate_results,
        "recent_prices": recent_prices,
        "news_headlines": news_headlines,
    }

    try:
        resp = requests.post(
            f"{worker_url}/ai/analyze",
            json=payload,
            headers={"Authorization": f"Bearer {dashboard_token}"},
            timeout=30,
        )
        if not resp.ok:
            logger.warning("AI analysis failed: %s %s", resp.status_code, resp.text[:200])
            return None

        data = resp.json()
        if not data.get("ok"):
            logger.warning("AI analysis error: %s", data.get("error", "unknown"))
            return None

        analysis = data["analysis"]
        return AIAnalysis(
            conviction=analysis["conviction"],
            reasoning=analysis["reasoning"],
            risk_factors=analysis.get("risk_factors", []),
            trade_quality=analysis.get("trade_quality", "C"),
            summary=analysis.get("summary", ""),
        )
    except Exception as e:
        logger.warning("AI analysis request failed: %s", e)
        return None


def fetch_news_headlines(ticker: str) -> list[str]:
    """Fetch recent news headlines for a ticker via the Worker."""
    worker_url = os.environ.get("TTRADE_WORKER_URL", "https://ttrade-worker.aicoderally.workers.dev")
    dashboard_token = os.environ.get("TTRADE_DASHBOARD_TOKEN", "")

    if not dashboard_token:
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "ttrade-DASHBOARD_TOKEN", "-w"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                dashboard_token = result.stdout.strip()
        except Exception:
            pass

    if not dashboard_token:
        return []

    try:
        resp = requests.get(
            f"{worker_url}/market/news/{ticker}",
            headers={"Authorization": f"Bearer {dashboard_token}"},
            timeout=10,
        )
        if resp.ok:
            data = resp.json()
            return [a["title"] for a in data.get("articles", [])]
    except Exception:
        pass
    return []

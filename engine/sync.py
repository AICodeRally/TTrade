"""Sync local SQLite to Cloudflare D1 via Worker API."""
import json
import logging
import httpx
from sqlmodel import Session, select
from engine.db import SignalRecord, ExecutionRecord, ReviewRecord

logger = logging.getLogger(__name__)


class SyncClient:
    def __init__(self, worker_url: str, api_key: str):
        self.worker_url = worker_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self.worker_url,
            headers={"X-API-Key": api_key},
            timeout=30.0,
        )

    def sync_signals(self, signals: list[dict]) -> dict:
        resp = self._client.post("/sync", json={"signals": signals})
        resp.raise_for_status()
        return resp.json()

    def sync_executions(self, executions: list[dict]) -> dict:
        resp = self._client.post("/sync", json={"executions": executions})
        resp.raise_for_status()
        return resp.json()

    def sync_reviews(self, reviews: list[dict]) -> dict:
        resp = self._client.post("/sync", json={"reviews": reviews})
        resp.raise_for_status()
        return resp.json()

    def sync_all(self, signals: list, executions: list, reviews: list) -> dict:
        resp = self._client.post("/sync", json={"signals": signals, "executions": executions, "reviews": reviews})
        resp.raise_for_status()
        return resp.json()


def sync_to_cloud(session: Session, sync_client: SyncClient) -> dict:
    unsynced_signals = session.exec(select(SignalRecord).where(SignalRecord.synced == False)).all()
    signal_dicts = []
    for s in unsynced_signals:
        signal_dicts.append({
            "signalId": s.signal_id, "ticker": s.ticker, "direction": s.direction,
            "timestamp": s.timestamp.isoformat(), "marketState": s.market_state,
            "allGatesPassed": s.all_gates_passed, "signalScore": s.signal_score,
            "componentScoresJson": s.component_scores_json, "actionTaken": s.action_taken,
            "strategyVersion": s.strategy_version, "configHash": s.config_hash,
        })
    result = sync_client.sync_all(signals=signal_dicts, executions=[], reviews=[])
    for s in unsynced_signals:
        s.synced = True
        session.add(s)
    session.commit()
    logger.info("Synced %d signals to cloud", len(signal_dicts))
    return result

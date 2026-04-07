"""AI Trade Journal — auto-review closed positions with Claude coaching."""
import json
import logging
import os
import subprocess
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from sqlmodel import Session, select

from engine.config import TTRadeConfig
from engine.db import PositionRecord, SignalRecord
from engine.reviewer import grade_outcome, grade_setup, grade_execution, auto_tag_failures

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def _get_keychain_value(service_name: str) -> str:
    """Read a value from macOS Keychain."""
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


def review_closed_positions(session: Session, config: TTRadeConfig):
    """Find newly closed positions without reviews and generate AI reviews."""
    closed = list(session.exec(
        select(PositionRecord).where(
            PositionRecord.status == "closed",
            PositionRecord.reviewed == False,
        )
    ).all())

    if not closed:
        return

    worker_url = os.environ.get("TTRADE_WORKER_URL", "https://ttrade-worker.aicoderally.workers.dev")
    dashboard_token = os.environ.get("TTRADE_DASHBOARD_TOKEN") or _get_keychain_value("ttrade-DASHBOARD_TOKEN")

    for pos in closed:
        pnl_pct = pos.pnl_pct or 0.0
        pnl_dollars = pos.pnl_dollars or 0.0
        exit_reason = pos.exit_reason or "unknown"
        mfe = pos.max_favorable_excursion or 0.0
        mae = pos.max_adverse_excursion or 0.0

        # Get the original signal for this position
        signal_score = 0.0
        market_state_entry = "unknown"
        if pos.signal_id:
            signal = session.exec(
                select(SignalRecord).where(SignalRecord.signal_id == pos.signal_id)
            ).first()
            if signal:
                signal_score = signal.signal_score or 0.0
                market_state_entry = signal.market_state or "unknown"

        # Compute mechanical grades
        setup_grade = grade_setup(signal_score)
        outcome_grade = grade_outcome(pnl_pct, exit_reason)
        execution_grade = grade_execution(0.03, "on_confirmation", "on_rule")
        failure_tags = auto_tag_failures(pnl_pct, exit_reason, signal_score, mfe, mae)

        # Calculate hold duration
        hold_hours = 0.0
        if pos.opened_at and pos.closed_at:
            try:
                opened = pos.opened_at if isinstance(pos.opened_at, datetime) else datetime.fromisoformat(str(pos.opened_at))
                closed_at = pos.closed_at if isinstance(pos.closed_at, datetime) else datetime.fromisoformat(str(pos.closed_at))
                hold_hours = (closed_at - opened).total_seconds() / 3600
            except Exception:
                pass

        # Call AI review endpoint
        ai_review = None
        if dashboard_token:
            try:
                payload = {
                    "ticker": pos.ticker,
                    "direction": pos.direction,
                    "signal_score": signal_score,
                    "entry_debit": pos.entry_debit or 75.0,
                    "exit_credit": pos.exit_credit or 0.0,
                    "pnl_pct": pnl_pct,
                    "pnl_dollars": pnl_dollars,
                    "hold_duration_hours": hold_hours,
                    "exit_reason": exit_reason,
                    "setup_grade": setup_grade,
                    "execution_grade": execution_grade,
                    "outcome_grade": outcome_grade,
                    "failure_tags": failure_tags,
                    "market_state_at_entry": market_state_entry,
                    "market_state_at_exit": "unknown",
                }
                resp = requests.post(
                    f"{worker_url}/ai/review-trade",
                    json=payload,
                    headers={"Authorization": f"Bearer {dashboard_token}"},
                    timeout=30,
                )
                if resp.ok:
                    data = resp.json()
                    if data.get("ok"):
                        ai_review = data["review"]
                        logger.info("AI Review: %s %s — %s (grade=%s)",
                                    pos.ticker, pos.direction,
                                    ai_review.get("coach_summary", ""),
                                    ai_review.get("adjusted_grade", "?"))
            except Exception as e:
                logger.warning("AI review failed for %s: %s", pos.ticker, e)

        # Sync review to Worker
        sync_key = os.environ.get("TTRADE_SYNC_API_KEY") or _get_keychain_value("ttrade-SYNC_API_KEY")
        if sync_key:
            review_payload = {
                "reviewId": f"rev_{uuid.uuid4().hex[:8]}",
                "signalId": pos.signal_id,
                "ticker": pos.ticker,
                "direction": pos.direction,
                "signalScore": signal_score,
                "entryDebit": pos.entry_debit,
                "exitCredit": pos.exit_credit,
                "pnlPct": pnl_pct,
                "pnlDollars": pnl_dollars,
                "holdDurationHours": hold_hours,
                "exitReason": exit_reason,
                "setupGrade": setup_grade,
                "executionGrade": execution_grade,
                "outcomeGrade": outcome_grade,
                "failureTagsJson": json.dumps(failure_tags),
                "aiReviewJson": json.dumps(ai_review) if ai_review else None,
                "strategyVersion": config.strategy_version,
                "configHash": config.config_hash,
            }
            try:
                resp = requests.post(
                    f"{worker_url}/reviews",
                    json=review_payload,
                    headers={"X-API-Key": sync_key},
                    timeout=15,
                )
                if not resp.ok:
                    logger.warning("Review sync failed: %s", resp.status_code)
            except Exception as e:
                logger.warning("Review sync error: %s", e)

        # Mark position as reviewed
        pos.reviewed = True
        session.add(pos)

    session.commit()
    logger.info("Reviewed %d closed positions", len(closed))

"""Main orchestrator — market hours loop with scan + monitor cycles."""
import json
import logging
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from sqlmodel import Session, select

from engine.config import TTRadeConfig
from engine.db import (
    SignalRecord, PositionRecord, CooldownRecord, init_db,
)
from engine.market_data import get_daily_bars
from engine.market_state import evaluate_market_state
from engine.models import MarketState
from engine.monitor import check_exit_rules
from engine.notifier import format_signal_alert, send_imessage
from engine.pipeline import run_pipeline
from engine.ai_journal import review_closed_positions

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")


def is_market_hours(config: TTRadeConfig) -> bool:
    now = datetime.now(ET)
    current_time = now.strftime("%H:%M")
    return config.market_open_et <= current_time <= config.market_close_et and now.weekday() < 5


def is_trade_hours(config: TTRadeConfig) -> bool:
    now = datetime.now(ET)
    current_time = now.strftime("%H:%M")
    return config.trade_start_et <= current_time <= config.market_close_et and now.weekday() < 5


def _get_cooldown_state(session: Session) -> tuple[datetime | None, int]:
    """Return (last_fill_time, fills_today) from cooldown records."""
    today = datetime.now(ET).strftime("%Y-%m-%d")
    records = list(session.exec(
        select(CooldownRecord).where(CooldownRecord.trade_date == today)
    ).all())
    if records:
        return records[0].last_fill_time, records[0].fills_today
    return None, 0


def _get_open_positions_as_dicts(session: Session) -> list[dict]:
    """Return open positions as dicts for the pipeline."""
    positions = list(session.exec(
        select(PositionRecord).where(PositionRecord.status == "open")
    ).all())
    return [{"ticker": p.ticker, "direction": p.direction} for p in positions]


def run_scan_cycle(config: TTRadeConfig, session: Session):
    """Scan all tickers through the signal pipeline."""
    try:
        spy_bars = get_daily_bars("SPY", period_days=60)
    except Exception as e:
        logger.error("Failed to fetch SPY bars: %s", e)
        return

    market_state = evaluate_market_state(spy_bars, config)
    logger.info("Market state: %s (slope=%.2f, SPY=$%.2f)",
                market_state.state.value, market_state.slope, market_state.current_price)

    last_fill_time, fills_today = _get_cooldown_state(session)
    open_positions = _get_open_positions_as_dicts(session)

    if market_state.state == MarketState.CHOP:
        logger.info("CHOP regime — gate 1 will reject, logging for audit trail")

    for ticker in config.tickers:
        try:
            ticker_bars = spy_bars if ticker == "SPY" else get_daily_bars(ticker, period_days=60)
        except Exception as e:
            logger.warning("Failed to fetch bars for %s: %s", ticker, e)
            continue

        evaluation = run_pipeline(
            ticker=ticker, ticker_bars=ticker_bars, market_state=market_state,
            option_data={
                "iv_rank": 40.0, "bid_ask_pct": 0.05, "avg_oi": 500,
                "spread_params": {"net_debit": 75, "max_loss": 75, "max_gain": 175, "spread_width": 5},
            },
            open_positions=open_positions, last_fill_time=last_fill_time,
            fills_today=fills_today, days_to_earnings=None, config=config,
            session=session,
        )

        # Persist signal
        record = SignalRecord(
            signal_id=evaluation.id, ticker=evaluation.ticker,
            direction=evaluation.direction, timestamp=evaluation.timestamp,
            market_state=evaluation.market_state,
            all_gates_passed=evaluation.all_gates_passed,
            gate_results_json=json.dumps([g.model_dump() for g in evaluation.gate_results]),
            signal_score=evaluation.signal_score,
            component_scores_json=json.dumps(evaluation.component_scores) if evaluation.component_scores else None,
            action_taken=evaluation.action_taken,
            strategy_version=evaluation.strategy_version,
            config_hash=evaluation.config_hash,
            ai_conviction=evaluation.ai_conviction,
            ai_analysis_json=json.dumps(evaluation.ai_analysis) if evaluation.ai_analysis else None,
        )
        session.add(record)
        session.commit()

        if evaluation.action_taken in ("alert", "execute"):
            ai_tag = ""
            if evaluation.ai_conviction is not None:
                quality = evaluation.ai_analysis.get("trade_quality", "?") if evaluation.ai_analysis else "?"
                ai_tag = f" | AI={evaluation.ai_conviction:.0f} ({quality})"
            logger.info("SIGNAL: %s %s — score=%.0f (%s)%s",
                        ticker, evaluation.direction, evaluation.signal_score or 0, evaluation.action_taken, ai_tag)
            phone = os.environ.get("TTRADE_PHONE_NUMBER")
            if phone:
                try:
                    msg = format_signal_alert(
                        ticker=ticker, direction=evaluation.direction,
                        spread_desc=f"{evaluation.direction} vertical",
                        expiry="TBD", dte=45,
                        debit=75.0, max_loss=75, max_gain=175, rr_ratio=2.3,
                        signal_score=evaluation.signal_score or 0,
                        band=evaluation.component_scores.get("band", "?") if evaluation.component_scores else "?",
                        regime=market_state.state.value,
                        confirmation="confirmed", signal_id=evaluation.id,
                    )
                    send_imessage(phone, msg)
                except Exception as e:
                    logger.warning("Notification failed: %s", e)
        elif evaluation.all_gates_passed:
            logger.info("LOGGED: %s %s — score=%.0f (below alert threshold)",
                        ticker, evaluation.direction, evaluation.signal_score or 0)


def _sync_to_d1(session: Session):
    """Push unsynced signals to D1 via the Worker sync endpoint."""
    worker_url = os.environ.get("TTRADE_WORKER_URL", "https://ttrade-worker.aicoderally.workers.dev")
    sync_key = os.environ.get("TTRADE_SYNC_API_KEY", "")
    if not sync_key:
        try:
            import subprocess
            result = subprocess.run(
                ["security", "find-generic-password", "-s", "ttrade-SYNC_API_KEY", "-w"],
                capture_output=True, text=True,
            )
            if result.returncode == 0:
                sync_key = result.stdout.strip()
        except Exception:
            pass
    if not sync_key:
        logger.warning("No SYNC_API_KEY — skipping D1 sync")
        return

    signals = list(session.exec(
        select(SignalRecord).where(SignalRecord.synced == False)
    ).all())
    if not signals:
        return

    # Build gate results from the stored JSON
    all_gates = []
    for s in signals:
        if s.gate_results_json:
            try:
                gates = json.loads(s.gate_results_json)
                for g in gates:
                    all_gates.append({
                        "signalId": s.signal_id,
                        "gateName": g.get("gate_name", ""),
                        "passed": 1 if g.get("passed") else 0,
                        "measuredValue": str(g.get("measured_value", "")),
                        "threshold": str(g.get("threshold", "")),
                        "configVersion": g.get("config_version", ""),
                    })
            except (json.JSONDecodeError, TypeError):
                pass

    payload = {
        "signals": [{
            "signalId": s.signal_id, "ticker": s.ticker, "direction": s.direction,
            "timestamp": s.timestamp.isoformat() if s.timestamp else "",
            "marketState": s.market_state,
            "allGatesPassed": 1 if s.all_gates_passed else 0,
            "signalScore": s.signal_score,
            "componentScoresJson": s.component_scores_json,
            "actionTaken": s.action_taken,
            "strategyVersion": s.strategy_version,
            "configHash": s.config_hash,
            "aiConviction": s.ai_conviction,
            "aiAnalysisJson": s.ai_analysis_json,
        } for s in signals],
        "gates": all_gates,
    }

    try:
        resp = requests.post(
            f"{worker_url}/sync", json=payload,
            headers={"X-API-Key": sync_key}, timeout=30,
        )
        if resp.ok:
            for s in signals:
                s.synced = True
                session.add(s)
            session.commit()
            logger.info("Synced %d signals to D1", len(signals))
        else:
            logger.warning("D1 sync failed: %s %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.warning("D1 sync error: %s", e)


def run_monitor_cycle(config: TTRadeConfig, session: Session):
    """Check exit rules on all open positions."""
    open_positions = list(session.exec(
        select(PositionRecord).where(PositionRecord.status == "open")
    ).all())

    if not open_positions:
        return

    try:
        spy_bars = get_daily_bars("SPY", period_days=30)
        market_state = evaluate_market_state(spy_bars, config)
    except Exception as e:
        logger.error("Monitor: failed to get market state: %s", e)
        return

    for pos in open_positions:
        pnl_pct = pos.pnl_pct or 0.0
        dte = 30  # simplified; real version computes from spread expiry

        exit_signal = check_exit_rules(pnl_pct, dte, market_state.state, config)

        if pnl_pct > pos.max_favorable_excursion:
            pos.max_favorable_excursion = pnl_pct
        if pnl_pct < pos.max_adverse_excursion:
            pos.max_adverse_excursion = pnl_pct

        if exit_signal:
            logger.warning("EXIT: %s %s — %s (%.0f%%)",
                           pos.ticker, pos.direction, exit_signal.reason, pnl_pct * 100)
            pos.status = "closed"
            pos.closed_at = datetime.now(ET)
            pos.exit_reason = exit_signal.reason
            pos.pnl_pct = pnl_pct

        session.add(pos)
    session.commit()

    # Auto-review any newly closed positions
    try:
        review_closed_positions(session, config)
    except Exception as e:
        logger.warning("Auto-review failed: %s", e)


def start_engine(mode_override: str | None = None):
    config = TTRadeConfig(mode=mode_override if mode_override else "MANUAL_APPROVAL")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/app.log", mode="a")],
    )
    logger.info("TTrade engine starting v%s (mode=%s, hash=%s)",
                config.strategy_version, config.mode, config.config_hash)

    db_path = os.environ.get("TTRADE_DB_PATH", "data/ttrade.db")
    db_engine = init_db(db_path)

    logger.info("Scan interval: %d min | Monitor interval: %d min",
                config.scan_interval_min, config.monitor_interval_min)
    logger.info("Waiting for market hours (Eastern Time)...")

    last_scan = 0.0
    last_monitor = 0.0

    while True:
        if not is_market_hours(config):
            time.sleep(60)
            continue

        now = time.time()

        if now - last_scan >= config.scan_interval_min * 60:
            if is_trade_hours(config):
                logger.info("Running scan cycle...")
                with Session(db_engine) as session:
                    run_scan_cycle(config, session)
                    _sync_to_d1(session)
            last_scan = now

        if now - last_monitor >= config.monitor_interval_min * 60:
            logger.info("Running monitor cycle...")
            with Session(db_engine) as session:
                run_monitor_cycle(config, session)
            last_monitor = now

        time.sleep(30)

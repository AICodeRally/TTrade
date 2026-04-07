"""Max loss circuit breaker — kill switch on account drawdown."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from sqlmodel import Session, select
from engine.config import TTRadeConfig
from engine.db import PositionRecord
from engine.models import GateResult

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


def check_loss_circuit_breaker(session: Session, config: TTRadeConfig) -> GateResult:
    """Block all entries if daily or weekly loss limit exceeded."""
    now = datetime.now(ET)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())  # Monday

    # Get all closed positions from this week
    closed = list(session.exec(
        select(PositionRecord).where(
            PositionRecord.status == "closed",
            PositionRecord.closed_at >= week_start.isoformat(),
        )
    ).all())

    daily_pnl = 0.0
    weekly_pnl = 0.0

    for pos in closed:
        pnl = pos.pnl_dollars or 0.0
        weekly_pnl += pnl
        if pos.closed_at and pos.closed_at >= today_start:
            daily_pnl += pnl

    if daily_pnl <= -config.max_daily_loss:
        logger.warning("DAILY LOSS BREAKER: $%.2f (limit -$%.2f)", daily_pnl, config.max_daily_loss)
        return GateResult(
            gate_name="loss_circuit_breaker", passed=False,
            measured_value=f"daily_pnl=${daily_pnl:.0f}",
            threshold=f"max_daily_loss=-${config.max_daily_loss:.0f}",
            config_version=config.strategy_version,
        )

    if weekly_pnl <= -config.max_weekly_loss:
        logger.warning("WEEKLY LOSS BREAKER: $%.2f (limit -$%.2f)", weekly_pnl, config.max_weekly_loss)
        return GateResult(
            gate_name="loss_circuit_breaker", passed=False,
            measured_value=f"weekly_pnl=${weekly_pnl:.0f}",
            threshold=f"max_weekly_loss=-${config.max_weekly_loss:.0f}",
            config_version=config.strategy_version,
        )

    return GateResult(
        gate_name="loss_circuit_breaker", passed=True,
        measured_value=f"daily=${daily_pnl:.0f},weekly=${weekly_pnl:.0f}",
        threshold=f"daily=-${config.max_daily_loss:.0f},weekly=-${config.max_weekly_loss:.0f}",
        config_version=config.strategy_version,
    )

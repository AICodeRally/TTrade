"""Position monitoring — exit rules, MFE/MAE tracking."""
import logging
from dataclasses import dataclass
from engine.config import TTRadeConfig
from engine.models import MarketState

logger = logging.getLogger(__name__)


@dataclass
class ExitSignal:
    reason: str
    pnl_pct: float
    dte: int


def check_exit_rules(pnl_pct: float, current_dte: int, market_state: MarketState, config: TTRadeConfig) -> ExitSignal | None:
    if pnl_pct <= config.stop_loss_pct:
        logger.warning("STOP LOSS triggered: %.1f%%", pnl_pct * 100)
        return ExitSignal(reason="stop_loss", pnl_pct=pnl_pct, dte=current_dte)
    if pnl_pct >= config.profit_target_pct:
        logger.info("PROFIT TARGET hit: %.1f%%", pnl_pct * 100)
        return ExitSignal(reason="profit_target", pnl_pct=pnl_pct, dte=current_dte)
    if market_state == MarketState.CHOP:
        logger.warning("THESIS INVALID: regime flipped to CHOP")
        return ExitSignal(reason="thesis_invalid", pnl_pct=pnl_pct, dte=current_dte)
    if current_dte < config.min_dte_exit:
        logger.warning("TIME DECAY exit: %d DTE remaining", current_dte)
        return ExitSignal(reason="time_decay", pnl_pct=pnl_pct, dte=current_dte)
    return None

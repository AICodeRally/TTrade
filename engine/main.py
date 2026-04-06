"""Main orchestrator — market hours loop."""
import logging
import time
from datetime import datetime
from engine.config import TTRadeConfig

logger = logging.getLogger(__name__)


def is_market_hours(config: TTRadeConfig) -> bool:
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    return config.market_open_et <= current_time <= config.market_close_et


def is_trade_hours(config: TTRadeConfig) -> bool:
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    return config.trade_start_et <= current_time <= config.market_close_et


def start_engine(mode_override: str | None = None):
    config = TTRadeConfig(mode=mode_override if mode_override else "MANUAL_APPROVAL")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), logging.FileHandler("logs/app.log", mode="a")],
    )
    logger.info("TTrade engine starting v%s (mode=%s, hash=%s)",
                config.strategy_version, config.mode, config.config_hash)
    logger.info("Engine initialized. Waiting for market hours...")
    logger.info("Scan interval: %d min | Monitor interval: %d min",
                config.scan_interval_min, config.monitor_interval_min)
    while True:
        if not is_market_hours(config):
            logger.debug("Outside market hours, sleeping 60s...")
            time.sleep(60)
            continue
        logger.info("Running scan cycle...")
        logger.info("Running monitor cycle...")
        time.sleep(config.scan_interval_min * 60)

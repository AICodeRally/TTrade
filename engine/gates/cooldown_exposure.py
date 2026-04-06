"""Gate 10: Cooldown + Exposure Buckets."""
from datetime import datetime, timedelta
from engine.config import TTRadeConfig
from engine.models import GateResult

MARKET_BUCKET = {"SPY", "QQQ"}
TECH_BUCKET = {"AAPL", "MSFT", "NVDA"}


def _get_bucket(ticker: str) -> str:
    if ticker in MARKET_BUCKET:
        return "market"
    if ticker in TECH_BUCKET:
        return "tech"
    return "other"


def check_cooldown_exposure(
    last_fill_time: datetime | None, fills_today: int, open_positions: list[dict],
    new_ticker: str, new_direction: str, config: TTRadeConfig,
) -> GateResult:
    reasons = []
    if fills_today >= config.max_trades_per_day:
        reasons.append(f"max_daily={fills_today}/{config.max_trades_per_day}")
    if last_fill_time:
        elapsed = datetime.now() - last_fill_time
        cooldown = timedelta(hours=config.cooldown_hours)
        if elapsed < cooldown:
            remaining = cooldown - elapsed
            reasons.append(f"cooldown={remaining.seconds // 60}min remaining")
    if len(open_positions) >= config.max_open_positions:
        reasons.append(f"max_open={len(open_positions)}/{config.max_open_positions}")
    new_bucket = _get_bucket(new_ticker)
    for pos in open_positions:
        pos_bucket = _get_bucket(pos["ticker"])
        if pos_bucket == new_bucket and pos["direction"] == new_direction:
            reasons.append(f"bucket_conflict={new_bucket}_{new_direction}")
            break
    passed = len(reasons) == 0
    return GateResult(gate_name="cooldown_exposure", passed=passed,
                      measured_value=", ".join(reasons) if reasons else "clear",
                      threshold=f"daily<={config.max_trades_per_day}, cooldown={config.cooldown_hours}h, open<={config.max_open_positions}",
                      config_version=config.strategy_version)

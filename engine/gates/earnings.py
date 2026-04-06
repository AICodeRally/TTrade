"""Gate 5: Earnings/Event Risk — no earnings within blackout window."""
from engine.config import TTRadeConfig
from engine.models import GateResult


def check_earnings(ticker: str, days_to_earnings: int | None, config: TTRadeConfig) -> GateResult:
    if days_to_earnings is None:
        return GateResult(gate_name="earnings_event", passed=True, measured_value="unknown",
                          threshold=f">{config.earnings_blackout_days} days", config_version=config.strategy_version)
    passed = days_to_earnings > config.earnings_blackout_days
    return GateResult(gate_name="earnings_event", passed=passed,
                      measured_value=f"{days_to_earnings} days",
                      threshold=f">{config.earnings_blackout_days} days",
                      config_version=config.strategy_version)

"""Gate 9: Position Construction — spread must be buildable within rules."""
from engine.config import TTRadeConfig
from engine.models import GateResult


def check_position_construction(spread_params: dict, config: TTRadeConfig) -> GateResult:
    debit = spread_params["net_debit"]
    max_loss = spread_params["max_loss"]
    max_gain = spread_params["max_gain"]
    debit_ok = config.min_debit <= debit <= config.max_debit
    rr_ratio = max_gain / max_loss if max_loss > 0 else 0
    rr_ok = rr_ratio >= config.min_risk_reward
    passed = debit_ok and rr_ok
    return GateResult(gate_name="position_construction", passed=passed,
                      measured_value=f"debit=${debit:.0f}, R/R={rr_ratio:.1f}:1",
                      threshold=f"debit ${config.min_debit}-${config.max_debit}, R/R>={config.min_risk_reward}",
                      config_version=config.strategy_version)

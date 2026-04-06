"""Gate 7: Options Volatility — IV rank filter."""
from engine.config import TTRadeConfig
from engine.models import GateResult


def check_options_volatility(iv_rank: float, config: TTRadeConfig) -> GateResult:
    if iv_rank > config.iv_rank_skip_threshold:
        passed = False
        note = "skip (IV too high)"
    elif iv_rank > config.iv_rank_reduce_threshold:
        passed = True
        note = "reduce_size (elevated IV)"
    else:
        passed = True
        note = "full_size"
    return GateResult(gate_name="options_volatility", passed=passed,
                      measured_value=f"IV rank={iv_rank:.1f}, action={note}",
                      threshold=f"skip>{config.iv_rank_skip_threshold}, reduce>{config.iv_rank_reduce_threshold}",
                      config_version=config.strategy_version)

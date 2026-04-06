"""Gate 1: Market Regime — SPY state must not be CHOP."""
from engine.config import TTRadeConfig
from engine.market_state import MarketStateResult
from engine.models import GateResult, MarketState


def check_regime(market_state: MarketStateResult, config: TTRadeConfig) -> GateResult:
    passed = market_state.state != MarketState.CHOP
    return GateResult(
        gate_name="market_regime",
        passed=passed,
        measured_value=market_state.state.value,
        threshold="!= CHOP",
        config_version=config.strategy_version,
    )

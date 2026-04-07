"""Gate 12: VIX circuit breaker — block entries when volatility is extreme."""
import logging
from engine.config import TTRadeConfig
from engine.models import GateResult

logger = logging.getLogger(__name__)


def get_vix_level() -> float | None:
    """Fetch current VIX level from yfinance."""
    try:
        import yfinance as yf
        vix = yf.download("^VIX", period="1d", progress=False)
        if vix.empty:
            return None
        return float(vix["Close"].iloc[-1])
    except Exception as e:
        logger.warning("Failed to fetch VIX: %s", e)
        return None


def check_vix_circuit_breaker(config: TTRadeConfig) -> GateResult:
    """Block all entries when VIX > threshold. High vol = wider spreads = bad fills."""
    vix = get_vix_level()
    if vix is None:
        # Can't verify VIX — pass with warning (fail-open to avoid blocking on data issues)
        logger.warning("VIX data unavailable — passing gate with caution")
        return GateResult(gate_name="vix_circuit_breaker", passed=True, measured_value="unavailable", threshold=str(config.vix_max_entry), config_version=config.strategy_version)

    if vix > config.vix_max_entry:
        return GateResult(
            gate_name="vix_circuit_breaker", passed=False,
            measured_value=f"VIX={vix:.1f}",
            threshold=f"max={config.vix_max_entry}",
            config_version=config.strategy_version,
        )

    return GateResult(gate_name="vix_circuit_breaker", passed=True, measured_value=f"VIX={vix:.1f}", threshold=f"max={config.vix_max_entry}", config_version=config.strategy_version)

"""Gate 11: Correlation guard — block overlapping speculative trades."""
from engine.config import TTRadeConfig
from engine.models import GateResult


def check_correlation(
    ticker: str, direction: str, open_positions: list[dict], config: TTRadeConfig,
) -> GateResult:
    """Enforce portfolio rules:
    - Max 1 position per speculative ticker (NVDA, RKLB)
    - Never overlap 2 speculative trades simultaneously
    """
    spec_tickers = set(config.speculative_tickers)

    # If this ticker isn't speculative, pass
    if ticker not in spec_tickers:
        return GateResult(gate_name="correlation", passed=True, measured_value="non-speculative", threshold="speculative_only", config_version=config.strategy_version)

    # Check if this ticker already has an open position
    for pos in open_positions:
        if pos["ticker"] == ticker:
            return GateResult(
                gate_name="correlation", passed=False,
                measured_value=f"already_open:{ticker}",
                threshold="max_1_per_ticker",
                config_version=config.strategy_version,
            )

    # Count open speculative positions
    open_spec = [p for p in open_positions if p["ticker"] in spec_tickers]
    if len(open_spec) >= config.max_speculative_positions:
        blocking = ", ".join(p["ticker"] for p in open_spec)
        return GateResult(
            gate_name="correlation", passed=False,
            measured_value=f"spec_open:{len(open_spec)}({blocking})",
            threshold=f"max={config.max_speculative_positions}",
            config_version=config.strategy_version,
        )

    return GateResult(gate_name="correlation", passed=True, measured_value="clear", threshold="no_overlap", config_version=config.strategy_version)

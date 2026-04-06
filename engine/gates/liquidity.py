"""Gate 8: Liquidity — OI + bid/ask quality check."""
from engine.config import TTRadeConfig
from engine.models import GateResult


def check_liquidity(option_data: dict, config: TTRadeConfig) -> GateResult:
    oi = option_data.get("open_interest", 0)
    bid = option_data.get("bid", 0)
    ask = option_data.get("ask", 0)
    spread_width = ask - bid
    mid = (bid + ask) / 2 if (bid + ask) > 0 else 1.0
    spread_pct = spread_width / mid
    oi_ok = oi >= config.min_open_interest
    spread_ok = spread_width <= config.max_bid_ask_spread
    pct_ok = spread_pct <= config.max_bid_ask_pct
    passed = oi_ok and spread_ok and pct_ok
    return GateResult(gate_name="liquidity", passed=passed,
                      measured_value=f"OI={oi}, spread=${spread_width:.2f} ({spread_pct:.1%})",
                      threshold=f"OI>={config.min_open_interest}, spread<=${config.max_bid_ask_spread}",
                      config_version=config.strategy_version)

"""Gate 4: Confirmation — bar-computable entry signal."""
import pandas as pd
from engine.config import TTRadeConfig
from engine.market_data import average_volume
from engine.models import GateResult


def check_confirmation(ticker_bars: pd.DataFrame, direction: str, config: TTRadeConfig) -> GateResult:
    if len(ticker_bars) < 3:
        return GateResult(gate_name="confirmation", passed=False,
                          measured_value="insufficient bars", threshold=">=3 bars required",
                          config_version=config.strategy_version)

    current = ticker_bars.iloc[-1]
    prior = ticker_bars.iloc[-2]
    avg_vol = average_volume(ticker_bars["Volume"], period=config.ma_period)
    current_vol = float(current["Volume"])
    vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0

    if direction == "bullish":
        higher_low = float(current["Low"]) > float(prior["Low"])
        close_above = float(current["Close"]) > float(prior["High"])
        vol_ok = vol_ratio >= config.min_volume_ratio
        passed = higher_low and close_above and vol_ok
    else:
        lower_high = float(current["High"]) < float(prior["High"])
        close_below = float(current["Close"]) < float(prior["Low"])
        vol_ok = vol_ratio >= config.min_volume_ratio
        passed = lower_high and close_below and vol_ok

    return GateResult(gate_name="confirmation", passed=passed,
                      measured_value=f"vol_ratio={vol_ratio:.2f}",
                      threshold=f"vol>={config.min_volume_ratio}",
                      config_version=config.strategy_version)

"""Gate 6: Price Stability — ATR must not be spiking."""
import pandas as pd
from engine.config import TTRadeConfig
from engine.market_data import compute_atr
from engine.models import GateResult


def check_price_stability(ticker_bars: pd.DataFrame, config: TTRadeConfig) -> GateResult:
    atr = compute_atr(ticker_bars, period=config.atr_period)
    atr_clean = atr.dropna()
    if len(atr_clean) < 2:
        return GateResult(gate_name="price_stability", passed=False,
                          measured_value="insufficient data",
                          threshold=f"ATR ratio < {config.atr_spike_threshold}",
                          config_version=config.strategy_version)
    current_atr = float(atr_clean.iloc[-1])
    avg_window = min(config.atr_avg_period, len(atr_clean))
    avg_atr = float(atr_clean.tail(avg_window).mean())
    ratio = current_atr / avg_atr if avg_atr > 0 else 999.0
    passed = ratio < config.atr_spike_threshold
    return GateResult(gate_name="price_stability", passed=passed,
                      measured_value=f"ATR ratio={ratio:.2f}",
                      threshold=f"< {config.atr_spike_threshold}",
                      config_version=config.strategy_version)

"""Gate 3: Pullback Setup — price must be pulling back toward 20MA."""
import pandas as pd
from engine.config import TTRadeConfig
from engine.market_data import compute_sma
from engine.models import GateResult


def check_pullback(ticker_bars: pd.DataFrame, direction: str, config: TTRadeConfig) -> GateResult:
    sma = compute_sma(ticker_bars["Close"], period=config.ma_period)
    current_price = float(ticker_bars["Close"].iloc[-1])
    sma_value = float(sma.iloc[-1])
    distance_pct = abs(current_price - sma_value) / sma_value

    if direction == "bullish":
        in_zone = current_price >= sma_value and distance_pct <= config.pullback_zone_pct
        recent_high = float(ticker_bars["High"].tail(config.max_bars_from_swing + 5).max())
        bars_from_high = 0
        for i in range(1, min(len(ticker_bars), config.max_bars_from_swing + 5) + 1):
            if float(ticker_bars["High"].iloc[-i]) == recent_high:
                bars_from_high = i - 1
                break
        within_swing = bars_from_high <= config.max_bars_from_swing
    else:
        in_zone = current_price <= sma_value and distance_pct <= config.pullback_zone_pct
        recent_low = float(ticker_bars["Low"].tail(config.max_bars_from_swing + 5).min())
        bars_from_low = 0
        for i in range(1, min(len(ticker_bars), config.max_bars_from_swing + 5) + 1):
            if float(ticker_bars["Low"].iloc[-i]) == recent_low:
                bars_from_low = i - 1
                break
        within_swing = bars_from_low <= config.max_bars_from_swing

    passed = in_zone and within_swing
    return GateResult(
        gate_name="pullback_setup",
        passed=passed,
        measured_value=f"distance={distance_pct:.3f}, in_zone={in_zone}, within_swing={within_swing}",
        threshold=f"zone<={config.pullback_zone_pct}, bars<={config.max_bars_from_swing}",
        config_version=config.strategy_version,
    )

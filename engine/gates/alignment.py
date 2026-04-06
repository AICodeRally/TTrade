"""Gate 2: Ticker Alignment — ticker must agree with market regime."""
import pandas as pd
from engine.config import TTRadeConfig
from engine.market_data import compute_sma, compute_slope
from engine.market_state import MarketStateResult
from engine.models import GateResult, MarketState


def check_alignment(ticker_bars: pd.DataFrame, market_state: MarketStateResult, config: TTRadeConfig) -> GateResult:
    sma = compute_sma(ticker_bars["Close"], period=config.ma_period)
    slope = compute_slope(sma, lookback=config.slope_lookback_days)
    current_price = float(ticker_bars["Close"].iloc[-1])
    sma_value = float(sma.iloc[-1])

    if market_state.state == MarketState.TREND_UP:
        aligned = current_price > sma_value and slope > 0
    elif market_state.state == MarketState.TREND_DOWN:
        aligned = current_price < sma_value and slope < 0
    else:
        aligned = False

    return GateResult(
        gate_name="ticker_alignment",
        passed=aligned,
        measured_value=f"price={'above' if current_price > sma_value else 'below'} MA, slope={slope:.2f}",
        threshold=f"aligned with {market_state.state.value}",
        config_version=config.strategy_version,
    )

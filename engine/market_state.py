"""SPY-driven market state machine."""
from dataclasses import dataclass
import pandas as pd
from engine.config import TTRadeConfig
from engine.market_data import compute_sma, compute_slope
from engine.models import MarketState


@dataclass
class MarketStateResult:
    state: MarketState
    slope: float
    current_price: float
    sma_value: float
    price_vs_ma: str


def evaluate_market_state(spy_bars: pd.DataFrame, config: TTRadeConfig) -> MarketStateResult:
    sma = compute_sma(spy_bars["Close"], period=config.ma_period)
    slope = compute_slope(sma, lookback=config.slope_lookback_days)
    current_price = float(spy_bars["Close"].iloc[-1])
    sma_value = float(sma.iloc[-1])
    price_above = current_price > sma_value
    price_vs_ma = "above" if price_above else "below"

    if price_above and slope > 0:
        state = MarketState.TREND_UP
    elif not price_above and slope < 0:
        state = MarketState.TREND_DOWN
    else:
        state = MarketState.CHOP

    return MarketStateResult(state=state, slope=slope, current_price=current_price,
                             sma_value=sma_value, price_vs_ma=price_vs_ma)

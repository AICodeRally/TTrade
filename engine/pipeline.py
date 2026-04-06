"""Pipeline runner — orchestrates all 10 gates + scoring."""
import uuid
from datetime import datetime
import pandas as pd
from engine.config import TTRadeConfig
from engine.market_data import compute_sma, compute_atr, average_volume
from engine.market_state import MarketStateResult
from engine.models import GateResult, MarketState, SignalEvaluation
from engine.scoring import score_signal
from engine.gates.regime import check_regime
from engine.gates.alignment import check_alignment
from engine.gates.pullback import check_pullback
from engine.gates.confirmation import check_confirmation
from engine.gates.earnings import check_earnings
from engine.gates.price_stability import check_price_stability
from engine.gates.options_volatility import check_options_volatility
from engine.gates.liquidity import check_liquidity
from engine.gates.position_construction import check_position_construction
from engine.gates.cooldown_exposure import check_cooldown_exposure


def determine_direction(state: MarketState) -> str | None:
    if state == MarketState.TREND_UP: return "bullish"
    elif state == MarketState.TREND_DOWN: return "bearish"
    return None


def run_pipeline(
    ticker: str, ticker_bars: pd.DataFrame, market_state: MarketStateResult,
    option_data: dict, open_positions: list[dict], last_fill_time: datetime | None,
    fills_today: int, days_to_earnings: int | None, config: TTRadeConfig,
) -> SignalEvaluation:
    gate_results: list[GateResult] = []
    direction = determine_direction(market_state.state)

    # Gate 1: Regime
    g1 = check_regime(market_state, config)
    gate_results.append(g1)
    if not g1.passed or direction is None:
        return _build_evaluation(ticker, direction or "bullish", market_state, gate_results, False, config)

    # Gate 2: Alignment
    g2 = check_alignment(ticker_bars, market_state, config)
    gate_results.append(g2)
    if not g2.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    # Gate 3: Pullback
    g3 = check_pullback(ticker_bars, direction, config)
    gate_results.append(g3)
    if not g3.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    # Gate 4: Confirmation
    g4 = check_confirmation(ticker_bars, direction, config)
    gate_results.append(g4)
    if not g4.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    # Gate 5: Earnings
    g5 = check_earnings(ticker, days_to_earnings, config)
    gate_results.append(g5)
    if not g5.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    # Gate 6: Price Stability
    g6 = check_price_stability(ticker_bars, config)
    gate_results.append(g6)
    if not g6.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    # Gate 7: Options Volatility
    iv_rank = option_data.get("iv_rank", 0.0)
    g7 = check_options_volatility(iv_rank, config)
    gate_results.append(g7)
    if not g7.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    # Gate 8: Liquidity
    g8 = check_liquidity(option_data, config)
    gate_results.append(g8)
    if not g8.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    # Gate 9: Position Construction
    spread_params = option_data.get("spread_params", {"net_debit": 0, "max_loss": 0, "max_gain": 0, "spread_width": 0})
    g9 = check_position_construction(spread_params, config)
    gate_results.append(g9)
    if not g9.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    # Gate 10: Cooldown/Exposure
    g10 = check_cooldown_exposure(last_fill_time, fills_today, open_positions, ticker, direction, config)
    gate_results.append(g10)
    if not g10.passed:
        return _build_evaluation(ticker, direction, market_state, gate_results, False, config)

    return _build_evaluation(ticker, direction, market_state, gate_results, True, config,
                             ticker_bars=ticker_bars, option_data=option_data,
                             days_to_earnings=days_to_earnings)


def _compute_scoring_inputs(
    ticker_bars: pd.DataFrame, market_state: MarketStateResult,
    option_data: dict, days_to_earnings: int | None, config: TTRadeConfig,
) -> dict:
    """Extract numeric inputs for the 7-dimension scoring engine."""
    close = ticker_bars["Close"]
    sma = compute_sma(close, period=config.ma_period)
    current_price = float(close.iloc[-1])
    sma_value = float(sma.iloc[-1])

    # Regime: slope + consistency (count of last 5 bars on correct side of SMA)
    regime_slope = market_state.slope
    sma_clean = sma.dropna()
    close_aligned = close.loc[sma_clean.index]
    if market_state.state == MarketState.TREND_UP:
        consistency = int(sum(1 for i in range(-min(5, len(sma_clean)), 0)
                              if float(close_aligned.iloc[i]) > float(sma_clean.iloc[i])))
    elif market_state.state == MarketState.TREND_DOWN:
        consistency = int(sum(1 for i in range(-min(5, len(sma_clean)), 0)
                              if float(close_aligned.iloc[i]) < float(sma_clean.iloc[i])))
    else:
        consistency = 0

    # Alignment: relative strength (price/SMA ratio) + MA distance
    relative_strength = current_price / sma_value if sma_value > 0 else 1.0
    ma_distance_pct = abs(current_price - sma_value) / sma_value if sma_value > 0 else 0.0

    # Pullback: distance, bar count, body size ratio
    pullback_distance = ma_distance_pct
    # Count bars from recent swing high/low
    recent_bars = ticker_bars.tail(config.max_bars_from_swing + 5)
    if market_state.state == MarketState.TREND_UP:
        swing_val = float(recent_bars["High"].max())
        pullback_bar_count = 0
        for i in range(1, len(recent_bars) + 1):
            if float(recent_bars["High"].iloc[-i]) == swing_val:
                pullback_bar_count = i - 1
                break
    else:
        swing_val = float(recent_bars["Low"].min())
        pullback_bar_count = 0
        for i in range(1, len(recent_bars) + 1):
            if float(recent_bars["Low"].iloc[-i]) == swing_val:
                pullback_bar_count = i - 1
                break
    bar = ticker_bars.iloc[-1]
    bar_range = float(bar["High"]) - float(bar["Low"])
    body = abs(float(bar["Close"]) - float(bar["Open"]))
    body_size_ratio = body / bar_range if bar_range > 0 else 0.5

    # Confirmation: volume ratio, close strength, body/wick ratio
    avg_vol = average_volume(ticker_bars["Volume"], period=config.ma_period)
    current_vol = float(bar["Volume"])
    volume_ratio = current_vol / avg_vol if avg_vol > 0 else 0.0
    close_strength = (float(bar["Close"]) - float(bar["Low"])) / bar_range if bar_range > 0 else 0.5
    wick = bar_range - body
    body_wick_ratio = body / wick if wick > 0 else 3.0

    # Stability: ATR ratio
    atr = compute_atr(ticker_bars, period=config.atr_period)
    atr_clean = atr.dropna()
    if len(atr_clean) >= 2:
        current_atr = float(atr_clean.iloc[-1])
        avg_window = min(config.atr_avg_period, len(atr_clean))
        avg_atr = float(atr_clean.tail(avg_window).mean())
        atr_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0
    else:
        atr_ratio = 1.0

    # Structure: bid/ask %, open interest, debit fit
    bid_ask_pct = option_data.get("bid_ask_pct", 0.10)
    open_interest = option_data.get("avg_oi", option_data.get("min_oi", 100))
    spread_params = option_data.get("spread_params", {})
    net_debit = spread_params.get("net_debit", 75.0)
    target = (config.min_debit + config.max_debit) / 2
    debit_fit = max(0.0, 1.0 - abs(net_debit - target) / target) if target > 0 else 0.5

    return {
        "regime_slope": regime_slope, "regime_consistency": consistency,
        "relative_strength": relative_strength, "ma_distance_pct": ma_distance_pct,
        "pullback_distance": pullback_distance, "pullback_bar_count": pullback_bar_count,
        "pullback_body_ratio": body_size_ratio,
        "volume_ratio": volume_ratio, "close_strength": close_strength,
        "body_wick_ratio": body_wick_ratio, "atr_ratio": atr_ratio,
        "bid_ask_pct": bid_ask_pct, "open_interest": open_interest,
        "debit_fit": debit_fit, "days_to_earnings": days_to_earnings,
    }


def _build_evaluation(
    ticker: str, direction: str, market_state: MarketStateResult,
    gate_results: list[GateResult], all_passed: bool, config: TTRadeConfig,
    ticker_bars: pd.DataFrame | None = None, option_data: dict | None = None,
    days_to_earnings: int | None = None,
) -> SignalEvaluation:
    signal_score = None
    component_scores = None
    action = "reject"

    if all_passed and ticker_bars is not None and option_data is not None:
        inputs = _compute_scoring_inputs(ticker_bars, market_state, option_data, days_to_earnings, config)
        scores = score_signal(**inputs)
        signal_score = scores.total
        component_scores = scores.to_dict()
        if signal_score >= config.min_score_execute: action = "execute"
        elif signal_score >= config.min_score_alert: action = "alert"
        elif signal_score >= config.min_score_log: action = "log"
    elif all_passed:
        signal_score = 0.0
        action = "log"

    return SignalEvaluation(
        id=f"sig_{uuid.uuid4().hex[:8]}", ticker=ticker, direction=direction,
        timestamp=datetime.now(), market_state=market_state.state.value,
        gate_results=gate_results, all_gates_passed=all_passed,
        signal_score=signal_score, component_scores=component_scores,
        action_taken=action, strategy_version=config.strategy_version,
        config_hash=config.config_hash,
    )

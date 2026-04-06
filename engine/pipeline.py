"""Pipeline runner — orchestrates all 10 gates + scoring."""
import uuid
from datetime import datetime
import pandas as pd
from engine.config import TTRadeConfig
from engine.market_state import MarketStateResult
from engine.models import GateResult, MarketState, SignalEvaluation
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

    return _build_evaluation(ticker, direction, market_state, gate_results, True, config)


def _build_evaluation(
    ticker: str, direction: str, market_state: MarketStateResult,
    gate_results: list[GateResult], all_passed: bool, config: TTRadeConfig,
) -> SignalEvaluation:
    signal_score = None
    component_scores = None
    action = "reject"
    if all_passed:
        signal_score = 0.0
        action = "log"
    if signal_score is not None:
        if signal_score >= config.min_score_execute: action = "execute"
        elif signal_score >= config.min_score_alert: action = "alert"
        elif signal_score >= config.min_score_log: action = "log"
    return SignalEvaluation(
        id=f"sig_{uuid.uuid4().hex[:8]}", ticker=ticker, direction=direction,
        timestamp=datetime.now(), market_state=market_state.state.value,
        gate_results=gate_results, all_gates_passed=all_passed,
        signal_score=signal_score, component_scores=component_scores,
        action_taken=action, strategy_version=config.strategy_version,
        config_hash=config.config_hash,
    )

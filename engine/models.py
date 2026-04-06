"""TTrade data contracts — Pydantic v2 models."""
from datetime import date, datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel


class MarketState(StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    CHOP = "CHOP"


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"


class ActionTaken(StrEnum):
    EXECUTE = "execute"
    ALERT = "alert"
    LOG = "log"
    REJECT = "reject"


class ExitReason(StrEnum):
    PROFIT_TARGET = "profit_target"
    STOP_LOSS = "stop_loss"
    THESIS_INVALID = "thesis_invalid"
    TIME_DECAY = "time_decay"
    MANUAL = "manual"


class GateResult(BaseModel):
    gate_name: str
    passed: bool
    measured_value: float | str
    threshold: float | str
    config_version: str


class SignalEvaluation(BaseModel):
    id: str
    ticker: str
    direction: Literal["bullish", "bearish"]
    timestamp: datetime
    market_state: Literal["TREND_UP", "TREND_DOWN", "CHOP"]
    gate_results: list[GateResult]
    all_gates_passed: bool
    signal_score: float | None
    component_scores: dict | None
    action_taken: Literal["execute", "alert", "log", "reject"]
    strategy_version: str
    config_hash: str


class SpreadLeg(BaseModel):
    symbol: str
    side: Literal["BUY", "SELL"]
    open_close: Literal["OPEN", "CLOSE"]
    strike: float
    expiry: date
    option_type: Literal["CALL", "PUT"]


class SpreadStructure(BaseModel):
    legs: list[SpreadLeg]
    net_debit: float
    max_loss: float
    max_gain: float
    spread_width: float
    risk_reward_ratio: float


class ExecutionEvent(BaseModel):
    id: str
    signal_id: str
    event_type: Literal[
        "order_submitted", "order_accepted", "order_rejected",
        "fill_received", "exit_triggered", "order_expired"
    ]
    order_id: str
    spread: SpreadStructure
    mid_price: float
    limit_price: float
    fill_price: float | None
    timestamp: datetime
    broker_response: dict | None
    local_wal_id: int


class TradeReview(BaseModel):
    id: str
    execution_id: str
    signal_id: str
    ticker: str
    direction: Literal["bullish", "bearish"]
    signal_score: float
    entry_debit: float
    exit_credit: float
    pnl_pct: float
    pnl_dollars: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    hold_duration_hours: float
    exit_reason: Literal[
        "profit_target", "stop_loss", "thesis_invalid",
        "time_decay", "manual"
    ]
    setup_grade: Literal["A", "B", "C", "D", "F"]
    execution_grade: Literal["A", "B", "C", "D", "F"]
    outcome_grade: Literal["A", "B", "C", "D", "F"]
    failure_tags: list[str]
    counterfactuals: dict
    review_notes: str | None
    strategy_version: str
    config_hash: str


class WeeklyLearningReport(BaseModel):
    id: str
    week_start: date
    week_end: date
    total_signals: int
    total_trades: int
    win_rate: float
    total_pnl: float
    score_band_performance: dict
    dimension_correlation: dict
    failure_tag_frequency: dict
    ticker_performance: dict
    threshold_suggestions: list[dict]
    generated_at: datetime

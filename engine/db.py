# engine/db.py
"""Local SQLite database — operational source of truth."""
from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel, create_engine


class SignalRecord(SQLModel, table=True):
    __tablename__ = "signal_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    signal_id: str = Field(index=True, unique=True)
    ticker: str
    direction: str
    timestamp: datetime
    market_state: str
    all_gates_passed: bool
    gate_results_json: str
    signal_score: Optional[float] = None
    component_scores_json: Optional[str] = None
    action_taken: str
    strategy_version: str
    config_hash: str
    synced: bool = False
    ai_conviction: Optional[float] = None
    ai_analysis_json: Optional[str] = None


class ExecutionRecord(SQLModel, table=True):
    __tablename__ = "execution_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    execution_id: str = Field(index=True, unique=True)
    signal_id: str = Field(index=True)
    event_type: str
    order_id: str
    spread_json: str
    mid_price: float
    limit_price: float
    fill_price: Optional[float] = None
    timestamp: datetime
    broker_response_json: Optional[str] = None
    synced: bool = False


class PositionRecord(SQLModel, table=True):
    __tablename__ = "position_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    position_id: str = Field(index=True, unique=True)
    signal_id: str = Field(index=True)
    execution_id: str
    ticker: str
    direction: str
    entry_debit: float
    spread_json: str
    status: str = "open"
    opened_at: datetime
    closed_at: Optional[datetime] = None
    exit_reason: Optional[str] = None
    exit_credit: Optional[float] = None
    pnl_pct: Optional[float] = None
    pnl_dollars: Optional[float] = None
    max_favorable_excursion: float = 0.0
    max_adverse_excursion: float = 0.0
    reviewed: bool = False


class ReviewRecord(SQLModel, table=True):
    __tablename__ = "review_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    review_id: str = Field(index=True, unique=True)
    execution_id: str = Field(index=True)
    signal_id: str
    ticker: str
    direction: str
    signal_score: float
    entry_debit: float
    exit_credit: float
    pnl_pct: float
    pnl_dollars: float
    hold_duration_hours: float
    exit_reason: str
    setup_grade: str
    execution_grade: str
    outcome_grade: str
    failure_tags_json: str = "[]"
    counterfactuals_json: str = "{}"
    review_notes: Optional[str] = None
    strategy_version: str
    config_hash: str
    synced: bool = False


class CooldownRecord(SQLModel, table=True):
    __tablename__ = "cooldown_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    last_fill_time: datetime
    fills_today: int = 0
    trade_date: str


class ConfigRecord(SQLModel, table=True):
    __tablename__ = "config_records"

    id: Optional[int] = Field(default=None, primary_key=True)
    config_hash: str = Field(index=True, unique=True)
    config_json: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(__import__("datetime").timezone.utc))


def init_db(db_path: str = "data/ttrade.db"):
    """Initialize SQLite database and return engine."""
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    SQLModel.metadata.create_all(engine)
    return engine

"""TTrade configuration — frozen dataclass with all thresholds."""
import hashlib
import json
from dataclasses import dataclass, fields


@dataclass(frozen=True)
class TTRadeConfig:
    # Strategy version
    strategy_version: str = "1.1.0"

    # Universe
    tickers: tuple[str, ...] = ("SPY", "QQQ", "AAPL", "MSFT", "NVDA")

    # State machine
    ma_period: int = 20
    slope_lookback_days: int = 3

    # Pullback
    pullback_zone_pct: float = 0.02
    max_bars_from_swing: int = 5

    # Confirmation
    min_volume_ratio: float = 1.0

    # Earnings
    earnings_blackout_days: int = 7

    # Price stability
    atr_period: int = 14
    atr_avg_period: int = 20
    atr_spike_threshold: float = 1.5

    # Options volatility
    iv_rank_reduce_threshold: float = 50.0
    iv_rank_skip_threshold: float = 75.0

    # Liquidity
    min_open_interest: int = 100
    max_bid_ask_spread: float = 0.20
    max_bid_ask_pct: float = 0.15

    # Position construction
    min_debit: float = 50.0
    max_debit: float = 100.0
    min_risk_reward: float = 1.5

    # DTE
    min_dte: int = 30
    max_dte: int = 60

    # Exits
    stop_loss_pct: float = -0.40
    profit_target_pct: float = 0.60
    min_dte_exit: int = 7

    # Cooldown / Exposure
    max_trades_per_day: int = 1
    cooldown_hours: int = 6
    max_open_positions: int = 2

    # Scoring
    min_score_execute: float = 85.0
    min_score_alert: float = 70.0
    min_score_log: float = 55.0

    # Execution
    limit_order_edge: float = 0.02
    fill_poll_interval_sec: int = 30
    fill_timeout_min: int = 15

    # Scan / Monitor
    scan_interval_min: int = 5
    monitor_interval_min: int = 1
    market_open_et: str = "09:30"
    trade_start_et: str = "11:00"
    market_close_et: str = "16:00"

    # Mode
    mode: str = "MANUAL_APPROVAL"

    @property
    def config_hash(self) -> str:
        """Deterministic hash of all config values."""
        values = {f.name: getattr(self, f.name) for f in fields(self)}
        # Convert tuples to lists for JSON serialization
        for k, v in values.items():
            if isinstance(v, tuple):
                values[k] = list(v)
        raw = json.dumps(values, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

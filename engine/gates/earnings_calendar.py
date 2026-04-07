"""Gate 13: Earnings calendar — auto-fetch real earnings dates."""
import logging
from datetime import datetime
from engine.config import TTRadeConfig
from engine.models import GateResult

logger = logging.getLogger(__name__)


def get_days_to_earnings(ticker: str) -> int | None:
    """Fetch next earnings date from yfinance and return days until it."""
    try:
        import yfinance as yf
        tk = yf.Ticker(ticker)
        cal = tk.calendar
        if cal is None or cal.empty:
            return None
        # calendar returns a DataFrame with 'Earnings Date' column(s)
        # or a dict depending on yfinance version
        if hasattr(cal, 'iloc'):
            # DataFrame: first row, first column is the next earnings date
            earnings_date = cal.iloc[0, 0]
            if hasattr(earnings_date, 'date'):
                earnings_date = earnings_date.date()
            elif isinstance(earnings_date, str):
                earnings_date = datetime.strptime(earnings_date, "%Y-%m-%d").date()
            else:
                return None
        elif isinstance(cal, dict):
            dates = cal.get("Earnings Date", [])
            if not dates:
                return None
            earnings_date = dates[0]
            if hasattr(earnings_date, 'date'):
                earnings_date = earnings_date.date()
        else:
            return None

        days = (earnings_date - datetime.now().date()).days
        return days if days >= 0 else None
    except Exception as e:
        logger.debug("Earnings lookup for %s: %s", ticker, e)
        return None


def check_earnings_calendar(ticker: str, config: TTRadeConfig) -> GateResult:
    """Block entries within blackout_days of earnings. Uses live data."""
    days = get_days_to_earnings(ticker)

    if days is None:
        # No earnings data found — pass (many ETFs like SPY/QQQ don't have earnings)
        return GateResult(gate_name="earnings_calendar", passed=True, measured_value="no_date_found", threshold=f"blackout={config.earnings_blackout_days}d", config_version=config.strategy_version)

    if days <= config.earnings_blackout_days:
        return GateResult(
            gate_name="earnings_calendar", passed=False,
            measured_value=f"{days}d_to_earnings",
            threshold=f"blackout={config.earnings_blackout_days}d",
            config_version=config.strategy_version,
        )

    return GateResult(gate_name="earnings_calendar", passed=True, measured_value=f"{days}d_to_earnings", threshold=f"blackout={config.earnings_blackout_days}d", config_version=config.strategy_version)

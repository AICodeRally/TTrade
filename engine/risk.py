"""Portfolio risk analytics — VaR, correlation, drawdown, Monte Carlo.

Answers: "How much can I lose?" and "Are my bets overlapping?"
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from engine.market_data import compute_atr

logger = logging.getLogger(__name__)


@dataclass
class CorrelationPair:
    ticker_a: str
    ticker_b: str
    correlation: float
    risk_level: str  # "high" (>0.7), "medium" (0.4-0.7), "low" (<0.4)


@dataclass
class RiskReport:
    # Portfolio summary
    tickers: list[str]
    total_value: float
    # Value at Risk
    var_95_pct: float       # 95% daily VaR as % of portfolio
    var_95_dollars: float
    var_99_pct: float       # 99% daily VaR
    var_99_dollars: float
    cvar_95_pct: float      # Conditional VaR (Expected Shortfall)
    cvar_95_dollars: float
    # Drawdown
    current_drawdown_pct: float
    max_drawdown_pct: float
    avg_drawdown_pct: float
    drawdown_duration_days: int
    # Volatility
    portfolio_volatility_annual: float
    portfolio_volatility_daily: float
    individual_vols: dict[str, float]
    # Correlation
    high_correlations: list[CorrelationPair]
    correlation_matrix: dict[str, dict[str, float]]
    diversification_ratio: float  # 1.0 = no diversification, higher = better
    # Monte Carlo
    mc_median_30d: float
    mc_5th_pct_30d: float
    mc_95th_pct_30d: float
    mc_prob_loss_30d: float
    mc_prob_double_1y: float
    # Risk scores
    concentration_risk: str   # "high", "medium", "low"
    volatility_risk: str
    correlation_risk: str
    overall_risk_score: int   # 0-100 (higher = riskier)
    timestamp: datetime


def _fetch_returns(tickers: list[str], period_days: int = 252) -> pd.DataFrame:
    """Fetch daily returns for multiple tickers."""
    import yfinance as yf
    data = yf.download(tickers, period=f"{period_days}d", interval="1d", progress=False)
    if data.empty:
        raise ValueError("No data returned")
    close = data["Close"]
    if isinstance(close, pd.Series):
        close = close.to_frame(name=tickers[0])
    returns = close.pct_change().dropna()
    return returns


def analyze_risk(
    tickers: list[str],
    weights: list[float] | None = None,
    portfolio_value: float = 1000.0,
    period_days: int = 252,
    mc_simulations: int = 5000,
) -> RiskReport:
    """Full portfolio risk analysis."""
    if not weights:
        weights = [1.0 / len(tickers)] * len(tickers)
    weights = np.array(weights)

    returns = _fetch_returns(tickers, period_days)
    # Align columns with tickers
    available = [t for t in tickers if t in returns.columns]
    if not available:
        raise ValueError(f"No data for any tickers: {tickers}")
    returns = returns[available]
    weights = weights[:len(available)]
    weights = weights / weights.sum()  # renormalize

    # Portfolio returns
    port_returns = (returns * weights).sum(axis=1)

    # ── Value at Risk ──
    var_95 = float(np.percentile(port_returns, 5))
    var_99 = float(np.percentile(port_returns, 1))
    # Conditional VaR (average of returns below VaR)
    tail = port_returns[port_returns <= var_95]
    cvar_95 = float(tail.mean()) if len(tail) > 0 else var_95

    # ── Volatility ──
    port_vol_daily = float(port_returns.std())
    port_vol_annual = port_vol_daily * np.sqrt(252)
    individual_vols = {t: float(returns[t].std() * np.sqrt(252) * 100) for t in available}

    # ── Drawdown ──
    cumulative = (1 + port_returns).cumprod()
    peak = cumulative.cummax()
    drawdown = (cumulative - peak) / peak
    current_dd = float(drawdown.iloc[-1] * 100)
    max_dd = float(drawdown.min() * 100)
    avg_dd = float(drawdown[drawdown < 0].mean() * 100) if len(drawdown[drawdown < 0]) > 0 else 0

    # Drawdown duration
    in_dd = drawdown < 0
    if in_dd.any():
        dd_groups = (in_dd != in_dd.shift()).cumsum()
        dd_lengths = in_dd.groupby(dd_groups).sum()
        max_dd_duration = int(dd_lengths.max())
    else:
        max_dd_duration = 0

    # ── Correlation ──
    corr_matrix = returns.corr()
    high_corrs = []
    corr_dict = {}
    for t in available:
        corr_dict[t] = {t2: round(float(corr_matrix.loc[t, t2]), 3) for t2 in available}

    for i, t1 in enumerate(available):
        for t2 in available[i + 1:]:
            c = float(corr_matrix.loc[t1, t2])
            level = "high" if abs(c) > 0.7 else "medium" if abs(c) > 0.4 else "low"
            high_corrs.append(CorrelationPair(t1, t2, round(c, 3), level))

    high_corrs.sort(key=lambda x: -abs(x.correlation))

    # Diversification ratio
    weighted_vol = sum(weights[i] * float(returns[t].std()) for i, t in enumerate(available))
    div_ratio = weighted_vol / port_vol_daily if port_vol_daily > 0 else 1.0

    # ── Monte Carlo ──
    mean_ret = float(port_returns.mean())
    std_ret = float(port_returns.std())

    mc_30d = np.zeros(mc_simulations)
    mc_1y = np.zeros(mc_simulations)
    for sim in range(mc_simulations):
        daily_returns = np.random.normal(mean_ret, std_ret, 252)
        cumulative_30d = np.prod(1 + daily_returns[:30])
        cumulative_1y = np.prod(1 + daily_returns)
        mc_30d[sim] = cumulative_30d
        mc_1y[sim] = cumulative_1y

    mc_median_30d = float(np.median(mc_30d) - 1) * 100
    mc_5th_30d = float(np.percentile(mc_30d, 5) - 1) * 100
    mc_95th_30d = float(np.percentile(mc_30d, 95) - 1) * 100
    mc_prob_loss = float(np.mean(mc_30d < 1)) * 100
    mc_prob_double = float(np.mean(mc_1y >= 2)) * 100

    # ── Risk Scores ──
    # Concentration: max weight
    max_weight = float(weights.max())
    concentration = "high" if max_weight > 0.5 else "medium" if max_weight > 0.3 else "low"

    # Volatility
    vol_risk = "high" if port_vol_annual > 0.4 else "medium" if port_vol_annual > 0.2 else "low"

    # Correlation
    high_corr_count = sum(1 for c in high_corrs if c.risk_level == "high")
    corr_risk = "high" if high_corr_count > len(available) * 0.3 else "medium" if high_corr_count > 0 else "low"

    # Overall
    risk_score = 0
    risk_score += {"high": 35, "medium": 20, "low": 5}[concentration]
    risk_score += {"high": 35, "medium": 20, "low": 10}[vol_risk]
    risk_score += {"high": 30, "medium": 15, "low": 5}[corr_risk]

    return RiskReport(
        tickers=available,
        total_value=portfolio_value,
        var_95_pct=round(abs(var_95) * 100, 2),
        var_95_dollars=round(abs(var_95) * portfolio_value, 2),
        var_99_pct=round(abs(var_99) * 100, 2),
        var_99_dollars=round(abs(var_99) * portfolio_value, 2),
        cvar_95_pct=round(abs(cvar_95) * 100, 2),
        cvar_95_dollars=round(abs(cvar_95) * portfolio_value, 2),
        current_drawdown_pct=round(current_dd, 2),
        max_drawdown_pct=round(max_dd, 2),
        avg_drawdown_pct=round(avg_dd, 2),
        drawdown_duration_days=max_dd_duration,
        portfolio_volatility_annual=round(port_vol_annual * 100, 2),
        portfolio_volatility_daily=round(port_vol_daily * 100, 2),
        individual_vols=individual_vols,
        high_correlations=high_corrs,
        correlation_matrix=corr_dict,
        diversification_ratio=round(div_ratio, 2),
        mc_median_30d=round(mc_median_30d, 2),
        mc_5th_pct_30d=round(mc_5th_30d, 2),
        mc_95th_pct_30d=round(mc_95th_30d, 2),
        mc_prob_loss_30d=round(mc_prob_loss, 1),
        mc_prob_double_1y=round(mc_prob_double, 1),
        concentration_risk=concentration,
        volatility_risk=vol_risk,
        correlation_risk=corr_risk,
        overall_risk_score=min(risk_score, 100),
        timestamp=datetime.now(),
    )

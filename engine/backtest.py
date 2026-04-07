"""Backtesting engine — test strategies against historical data.

Supports: momentum, grid, mean-reversion, and leverage strategies.
Calculates Sharpe ratio, max drawdown, win rate, profit factor,
and generates equity curve data.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from engine.market_data import compute_sma, compute_atr

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    entry_date: str
    exit_date: str
    side: str          # "long" or "short"
    entry_price: float
    exit_price: float
    shares: int
    pnl_dollars: float
    pnl_pct: float
    hold_days: int
    exit_reason: str   # "target", "stop", "time", "signal"


@dataclass
class BacktestResult:
    strategy: str
    ticker: str
    period: str
    start_date: str
    end_date: str
    # Performance
    total_return_pct: float
    annualized_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    max_drawdown_dollars: float
    # Trade stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_win_pct: float
    avg_loss_pct: float
    profit_factor: float
    avg_hold_days: float
    # Risk
    best_trade_pct: float
    worst_trade_pct: float
    max_consecutive_wins: int
    max_consecutive_losses: int
    # Equity curve
    equity_curve: list[dict]
    trades: list[Trade]
    # Account
    start_capital: float
    end_capital: float


def _fetch_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Fetch historical data for backtesting."""
    import yfinance as yf
    data = yf.download(ticker, period=period, interval="1d", progress=False)
    if data.empty:
        raise ValueError(f"No data for {ticker}")
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.droplevel(1)
    return data


def _compute_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(window=period).mean()
    loss = (-delta).clip(lower=0).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def backtest_momentum(
    ticker: str,
    period: str = "1y",
    account: float = 1000.0,
    fast_ma: int = 10,
    slow_ma: int = 30,
    stop_atr_mult: float = 1.5,
    target_atr_mult: float = 2.5,
    max_risk_pct: float = 0.10,
) -> BacktestResult:
    """Backtest a momentum/trend-following strategy.

    Entry: fast MA crosses above slow MA (long) or below (short).
    Exit: ATR-based stop or target hit.
    """
    bars = _fetch_history(ticker, period)
    close = bars["Close"]
    sma_fast = compute_sma(close, period=fast_ma)
    sma_slow = compute_sma(close, period=slow_ma)
    atr = compute_atr(bars, period=14)

    capital = account
    trades = []
    equity = [{"date": str(bars.index[0].date()), "equity": capital}]
    position = None  # {"side", "entry", "stop", "target", "shares", "entry_date"}

    for i in range(slow_ma + 1, len(bars)):
        date = str(bars.index[i].date())
        price = float(close.iloc[i])
        atr_val = float(atr.iloc[i]) if not np.isnan(atr.iloc[i]) else price * 0.03
        fast_val = float(sma_fast.iloc[i])
        slow_val = float(sma_slow.iloc[i])
        prev_fast = float(sma_fast.iloc[i - 1])
        prev_slow = float(sma_slow.iloc[i - 1])

        # Check exits first
        if position:
            hit_stop = (position["side"] == "long" and price <= position["stop"]) or \
                       (position["side"] == "short" and price >= position["stop"])
            hit_target = (position["side"] == "long" and price >= position["target"]) or \
                         (position["side"] == "short" and price <= position["target"])

            if hit_stop or hit_target:
                if position["side"] == "long":
                    pnl = (price - position["entry"]) * position["shares"]
                else:
                    pnl = (position["entry"] - price) * position["shares"]
                pnl_pct = pnl / (position["entry"] * position["shares"]) * 100
                capital += pnl
                hold = (bars.index[i] - pd.Timestamp(position["entry_date"])).days

                trades.append(Trade(
                    entry_date=position["entry_date"], exit_date=date,
                    side=position["side"], entry_price=position["entry"],
                    exit_price=price, shares=position["shares"],
                    pnl_dollars=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
                    hold_days=hold,
                    exit_reason="stop" if hit_stop else "target",
                ))
                position = None

        # Check entries (no position)
        if position is None and capital > 50:
            # Bullish crossover
            if prev_fast <= prev_slow and fast_val > slow_val:
                stop_dist = atr_val * stop_atr_mult
                target_dist = atr_val * target_atr_mult
                risk = capital * max_risk_pct
                shares = int(risk / stop_dist) if stop_dist > 0 else 0
                shares = min(shares, int(capital * 0.5 / price))
                if shares > 0:
                    position = {
                        "side": "long", "entry": price,
                        "stop": price - stop_dist,
                        "target": price + target_dist,
                        "shares": shares, "entry_date": date,
                    }

            # Bearish crossover
            elif prev_fast >= prev_slow and fast_val < slow_val:
                stop_dist = atr_val * stop_atr_mult
                target_dist = atr_val * target_atr_mult
                risk = capital * max_risk_pct
                shares = int(risk / stop_dist) if stop_dist > 0 else 0
                shares = min(shares, int(capital * 0.5 / price))
                if shares > 0:
                    position = {
                        "side": "short", "entry": price,
                        "stop": price + stop_dist,
                        "target": price - target_dist,
                        "shares": shares, "entry_date": date,
                    }

        equity.append({"date": date, "equity": round(capital, 2)})

    # Close any open position at market
    if position:
        price = float(close.iloc[-1])
        if position["side"] == "long":
            pnl = (price - position["entry"]) * position["shares"]
        else:
            pnl = (position["entry"] - price) * position["shares"]
        capital += pnl
        trades.append(Trade(
            entry_date=position["entry_date"], exit_date=str(bars.index[-1].date()),
            side=position["side"], entry_price=position["entry"],
            exit_price=price, shares=position["shares"],
            pnl_dollars=round(pnl, 2),
            pnl_pct=round(pnl / (position["entry"] * position["shares"]) * 100, 2),
            hold_days=(bars.index[-1] - pd.Timestamp(position["entry_date"])).days,
            exit_reason="time",
        ))

    return _compile_result("momentum", ticker, period, account, capital, trades, equity)


def backtest_mean_reversion(
    ticker: str,
    period: str = "1y",
    account: float = 1000.0,
    rsi_oversold: float = 30.0,
    rsi_overbought: float = 70.0,
    sma_period: int = 20,
    stop_atr_mult: float = 2.0,
    max_risk_pct: float = 0.08,
) -> BacktestResult:
    """Backtest a mean-reversion strategy.

    Entry: RSI oversold → long, RSI overbought → short.
    Exit: RSI returns to neutral or ATR stop hit.
    """
    bars = _fetch_history(ticker, period)
    close = bars["Close"]
    rsi = _compute_rsi(close, period=14)
    sma = compute_sma(close, period=sma_period)
    atr = compute_atr(bars, period=14)

    capital = account
    trades = []
    equity = [{"date": str(bars.index[0].date()), "equity": capital}]
    position = None

    for i in range(sma_period + 1, len(bars)):
        date = str(bars.index[i].date())
        price = float(close.iloc[i])
        rsi_val = float(rsi.iloc[i]) if not np.isnan(rsi.iloc[i]) else 50.0
        atr_val = float(atr.iloc[i]) if not np.isnan(atr.iloc[i]) else price * 0.03
        sma_val = float(sma.iloc[i]) if not np.isnan(sma.iloc[i]) else price

        if position:
            hit_stop = (position["side"] == "long" and price <= position["stop"]) or \
                       (position["side"] == "short" and price >= position["stop"])
            # Mean reversion exit: RSI returns to neutral or price returns to SMA
            hit_target = (position["side"] == "long" and (rsi_val >= 50 or price >= sma_val)) or \
                         (position["side"] == "short" and (rsi_val <= 50 or price <= sma_val))

            if hit_stop or hit_target:
                if position["side"] == "long":
                    pnl = (price - position["entry"]) * position["shares"]
                else:
                    pnl = (position["entry"] - price) * position["shares"]
                pnl_pct = pnl / (position["entry"] * position["shares"]) * 100
                capital += pnl
                hold = (bars.index[i] - pd.Timestamp(position["entry_date"])).days

                trades.append(Trade(
                    entry_date=position["entry_date"], exit_date=date,
                    side=position["side"], entry_price=position["entry"],
                    exit_price=price, shares=position["shares"],
                    pnl_dollars=round(pnl, 2), pnl_pct=round(pnl_pct, 2),
                    hold_days=hold,
                    exit_reason="stop" if hit_stop else "target",
                ))
                position = None

        if position is None and capital > 50:
            if rsi_val <= rsi_oversold:
                stop_dist = atr_val * stop_atr_mult
                risk = capital * max_risk_pct
                shares = int(risk / stop_dist) if stop_dist > 0 else 0
                shares = min(shares, int(capital * 0.4 / price))
                if shares > 0:
                    position = {
                        "side": "long", "entry": price,
                        "stop": price - stop_dist,
                        "shares": shares, "entry_date": date,
                    }
            elif rsi_val >= rsi_overbought:
                stop_dist = atr_val * stop_atr_mult
                risk = capital * max_risk_pct
                shares = int(risk / stop_dist) if stop_dist > 0 else 0
                shares = min(shares, int(capital * 0.4 / price))
                if shares > 0:
                    position = {
                        "side": "short", "entry": price,
                        "stop": price + stop_dist,
                        "shares": shares, "entry_date": date,
                    }

        equity.append({"date": date, "equity": round(capital, 2)})

    if position:
        price = float(close.iloc[-1])
        pnl = ((price - position["entry"]) if position["side"] == "long"
               else (position["entry"] - price)) * position["shares"]
        capital += pnl
        trades.append(Trade(
            entry_date=position["entry_date"], exit_date=str(bars.index[-1].date()),
            side=position["side"], entry_price=position["entry"],
            exit_price=price, shares=position["shares"],
            pnl_dollars=round(pnl, 2),
            pnl_pct=round(pnl / (position["entry"] * position["shares"]) * 100, 2),
            hold_days=(bars.index[-1] - pd.Timestamp(position["entry_date"])).days,
            exit_reason="time",
        ))

    return _compile_result("mean_reversion", ticker, period, account, capital, trades, equity)


def backtest_grid(
    ticker: str,
    period: str = "1y",
    account: float = 1000.0,
    grid_spacing_pct: float = 3.0,
    num_levels: int = 4,
) -> BacktestResult:
    """Backtest a grid trading strategy.

    Places virtual buy/sell grid around price. When price crosses a level,
    records a fill and creates a paired exit order.
    """
    bars = _fetch_history(ticker, period)
    close = bars["Close"]

    capital = account
    per_level = account / (num_levels * 2)
    trades = []
    equity = [{"date": str(bars.index[0].date()), "equity": capital}]

    # Track open grid fills waiting for exit
    open_fills = []  # {"side", "price", "exit_price", "date"}

    for i in range(1, len(bars)):
        date = str(bars.index[i].date())
        price = float(close.iloc[i])
        prev_price = float(close.iloc[i - 1])

        # Check if price crossed any open fill's exit level
        closed = []
        for j, fill in enumerate(open_fills):
            if fill["side"] == "buy" and price >= fill["exit_price"]:
                pnl = per_level * (fill["exit_price"] - fill["price"]) / fill["price"]
                capital += pnl
                hold = (bars.index[i] - pd.Timestamp(fill["date"])).days
                trades.append(Trade(
                    entry_date=fill["date"], exit_date=date,
                    side="long", entry_price=fill["price"],
                    exit_price=fill["exit_price"], shares=1,
                    pnl_dollars=round(pnl, 2),
                    pnl_pct=round((fill["exit_price"] / fill["price"] - 1) * 100, 2),
                    hold_days=max(hold, 1), exit_reason="target",
                ))
                closed.append(j)
            elif fill["side"] == "sell" and price <= fill["exit_price"]:
                pnl = per_level * (fill["price"] - fill["exit_price"]) / fill["exit_price"]
                capital += pnl
                hold = (bars.index[i] - pd.Timestamp(fill["date"])).days
                trades.append(Trade(
                    entry_date=fill["date"], exit_date=date,
                    side="short", entry_price=fill["price"],
                    exit_price=fill["exit_price"], shares=1,
                    pnl_dollars=round(pnl, 2),
                    pnl_pct=round((fill["price"] / fill["exit_price"] - 1) * 100, 2),
                    hold_days=max(hold, 1), exit_reason="target",
                ))
                closed.append(j)

        for j in sorted(closed, reverse=True):
            open_fills.pop(j)

        # Check for new grid fills (price moved enough from any reference)
        move_pct = abs(price - prev_price) / prev_price * 100
        if move_pct >= grid_spacing_pct * 0.5 and len(open_fills) < num_levels * 2:
            if price < prev_price:  # price dropped → buy fill
                exit_price = price * (1 + grid_spacing_pct / 100)
                open_fills.append({"side": "buy", "price": price, "exit_price": exit_price, "date": date})
            else:  # price rose → sell fill
                exit_price = price * (1 - grid_spacing_pct / 100)
                open_fills.append({"side": "sell", "price": price, "exit_price": exit_price, "date": date})

        equity.append({"date": date, "equity": round(capital, 2)})

    return _compile_result("grid", ticker, period, account, capital, trades, equity)


def _compile_result(
    strategy: str, ticker: str, period: str,
    start_capital: float, end_capital: float,
    trades: list[Trade], equity: list[dict],
) -> BacktestResult:
    """Compile trade list and equity curve into a BacktestResult."""
    total_return = (end_capital - start_capital) / start_capital * 100

    # Annualize
    if equity and len(equity) > 1:
        days = (pd.Timestamp(equity[-1]["date"]) - pd.Timestamp(equity[0]["date"])).days
        years = max(days / 365, 0.01)
        annualized = ((end_capital / start_capital) ** (1 / years) - 1) * 100
    else:
        annualized = 0.0
        days = 0

    # Sharpe & Sortino from equity curve
    if len(equity) > 2:
        equities = [e["equity"] for e in equity]
        returns = pd.Series(equities).pct_change().dropna()
        if len(returns) > 1 and returns.std() > 0:
            sharpe = float(returns.mean() / returns.std() * np.sqrt(252))
            downside = returns[returns < 0]
            sortino = float(returns.mean() / downside.std() * np.sqrt(252)) if len(downside) > 1 and downside.std() > 0 else 0.0
        else:
            sharpe = sortino = 0.0

        # Max drawdown
        eq_series = pd.Series(equities)
        peak = eq_series.cummax()
        drawdown = (eq_series - peak) / peak * 100
        max_dd_pct = float(drawdown.min())
        max_dd_dollars = float((eq_series - peak).min())
    else:
        sharpe = sortino = 0.0
        max_dd_pct = max_dd_dollars = 0.0

    # Trade stats
    wins = [t for t in trades if t.pnl_dollars > 0]
    losses = [t for t in trades if t.pnl_dollars <= 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0
    avg_win = np.mean([t.pnl_pct for t in wins]) if wins else 0
    avg_loss = np.mean([t.pnl_pct for t in losses]) if losses else 0
    gross_profit = sum(t.pnl_dollars for t in wins)
    gross_loss = abs(sum(t.pnl_dollars for t in losses))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf") if gross_profit > 0 else 0
    avg_hold = np.mean([t.hold_days for t in trades]) if trades else 0

    best = max((t.pnl_pct for t in trades), default=0)
    worst = min((t.pnl_pct for t in trades), default=0)

    # Consecutive wins/losses
    max_con_wins = max_con_losses = cur_wins = cur_losses = 0
    for t in trades:
        if t.pnl_dollars > 0:
            cur_wins += 1
            cur_losses = 0
            max_con_wins = max(max_con_wins, cur_wins)
        else:
            cur_losses += 1
            cur_wins = 0
            max_con_losses = max(max_con_losses, cur_losses)

    return BacktestResult(
        strategy=strategy, ticker=ticker, period=period,
        start_date=equity[0]["date"] if equity else "",
        end_date=equity[-1]["date"] if equity else "",
        total_return_pct=round(total_return, 2),
        annualized_return_pct=round(annualized, 2),
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        max_drawdown_pct=round(max_dd_pct, 2),
        max_drawdown_dollars=round(max_dd_dollars, 2),
        total_trades=len(trades),
        winning_trades=len(wins),
        losing_trades=len(losses),
        win_rate=round(win_rate, 1),
        avg_win_pct=round(float(avg_win), 2),
        avg_loss_pct=round(float(avg_loss), 2),
        profit_factor=round(profit_factor, 2),
        avg_hold_days=round(float(avg_hold), 1),
        best_trade_pct=round(best, 2),
        worst_trade_pct=round(worst, 2),
        max_consecutive_wins=max_con_wins,
        max_consecutive_losses=max_con_losses,
        equity_curve=equity,
        trades=trades,
        start_capital=start_capital,
        end_capital=round(end_capital, 2),
    )

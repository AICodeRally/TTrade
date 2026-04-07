"""TTrade CLI — Click-based command interface."""
import json
import logging
import os
import uuid
from datetime import datetime

import click
from sqlmodel import Session, create_engine, select

from engine.config import TTRadeConfig
from engine.db import SignalRecord, ExecutionRecord, PositionRecord, init_db

logger = logging.getLogger(__name__)


def _get_db_engine():
    db_path = os.environ.get("TTRADE_DB_PATH", "data/ttrade.db")
    return init_db(db_path)


@click.group()
def cli():
    """TTrade v1.1 — State-driven options trading engine."""
    pass


@cli.command()
def version():
    """Show TTrade version and config hash."""
    config = TTRadeConfig()
    click.echo(f"TTrade v{config.strategy_version}")
    click.echo(f"Config hash: {config.config_hash}")
    click.echo(f"Mode: {config.mode}")


@cli.command()
def status():
    """Show current engine status."""
    config = TTRadeConfig()
    click.echo("TTrade Status")
    click.echo(f"  Version: {config.strategy_version}")
    click.echo(f"  Mode: {config.mode}")
    click.echo(f"  Tickers: {', '.join(config.tickers)}")
    click.echo(f"  Config hash: {config.config_hash}")

    db_path = os.environ.get("TTRADE_DB_PATH", "data/ttrade.db")
    if os.path.exists(db_path):
        engine = create_engine(f"sqlite:///{db_path}")
        with Session(engine) as session:
            open_positions = session.exec(
                select(PositionRecord).where(PositionRecord.status == "open")
            ).all()
            click.echo(f"  Open positions: {len(open_positions)}")


@cli.command()
@click.argument("signal_id")
def approve(signal_id: str):
    """Approve a pending signal for execution."""
    config = TTRadeConfig()
    engine = _get_db_engine()

    with Session(engine) as session:
        signal = session.exec(
            select(SignalRecord).where(SignalRecord.signal_id == signal_id)
        ).first()

        if signal is None:
            click.echo(f"Signal {signal_id} not found.", err=True)
            raise SystemExit(1)

        if not signal.all_gates_passed:
            click.echo(f"Signal {signal_id} did not pass all gates (action={signal.action_taken}).", err=True)
            raise SystemExit(1)

        if signal.action_taken == "reject":
            click.echo(f"Signal {signal_id} was rejected.", err=True)
            raise SystemExit(1)

        click.echo(f"Signal: {signal.ticker} {signal.direction}")
        click.echo(f"Score: {signal.signal_score} | Action: {signal.action_taken}")
        click.echo(f"Market state: {signal.market_state}")

        from engine.broker import BrokerClient
        from engine.risk_manager import select_strikes, calculate_position_size
        from engine.executor import prepare_order_legs, submit_order

        account_id = os.environ.get("TTRADE_ACCOUNT_ID", "")
        if not account_id:
            click.echo("TTRADE_ACCOUNT_ID not set.", err=True)
            raise SystemExit(1)

        broker = BrokerClient(account_id=account_id)

        # Get fresh option chain with valid DTE
        expirations = broker.get_option_expirations(signal.ticker)
        exp_dates = expirations.get("expirations", [])
        target_exp = None
        for exp in exp_dates:
            dte = (datetime.strptime(exp, "%Y-%m-%d").date() - datetime.now().date()).days
            if config.min_dte <= dte <= config.max_dte:
                target_exp = exp
                break

        if target_exp is None:
            click.echo("No expiration found in DTE range.", err=True)
            raise SystemExit(1)

        chain_data = broker.get_option_chain(signal.ticker, target_exp)
        chain = chain_data.get("options", [])

        iv_rank = 40.0
        target_debit = calculate_position_size(10000.0, iv_rank, config)
        spread = select_strikes(chain, signal.direction, target_debit, config)

        if spread is None:
            click.echo("No suitable spread found.", err=True)
            raise SystemExit(1)

        click.echo(f"Spread: buy {spread['buy_strike']} / sell {spread['sell_strike']}")
        click.echo(f"Debit: ${spread['net_debit']:.2f} | R/R: {spread['risk_reward_ratio']:.1f}:1")

        # Build OCC symbols and submit
        exp_fmt = target_exp.replace("-", "")
        opt_type = "C" if signal.direction == "bullish" else "P"
        buy_sym = f"{signal.ticker}{exp_fmt}{opt_type}{int(spread['buy_strike'] * 1000):08d}"
        sell_sym = f"{signal.ticker}{exp_fmt}{opt_type}{int(spread['sell_strike'] * 1000):08d}"
        legs = prepare_order_legs(buy_sym, sell_sym)
        limit_price = spread["net_debit"] / 100 * (1 - config.limit_order_edge)

        click.echo(f"Submitting order at ${limit_price:.2f}...")
        result = submit_order(broker, legs, limit_price, mode=config.mode)
        order_id = result.get("orderId", "unknown")
        click.echo(f"Order {order_id}: {result.get('status', 'UNKNOWN')}")

        # Record execution and position
        exec_id = f"exec_{uuid.uuid4().hex[:8]}"
        session.add(ExecutionRecord(
            execution_id=exec_id, signal_id=signal_id, event_type="order_submitted",
            order_id=order_id, spread_json=json.dumps(spread),
            mid_price=spread["net_debit"] / 100, limit_price=limit_price,
            fill_price=None, timestamp=datetime.now(),
        ))
        pos_id = f"pos_{uuid.uuid4().hex[:8]}"
        session.add(PositionRecord(
            position_id=pos_id, signal_id=signal_id, execution_id=exec_id,
            ticker=signal.ticker, direction=signal.direction,
            entry_debit=spread["net_debit"] / 100,
            spread_json=json.dumps(spread), status="open", opened_at=datetime.now(),
        ))
        session.commit()
        click.echo(f"Position {pos_id} opened.")


@cli.command()
def scan():
    """Run a single scan cycle now (ignores market hours)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    config = TTRadeConfig()
    engine = _get_db_engine()
    click.echo(f"Running manual scan for: {', '.join(config.tickers)}")
    from engine.main import run_scan_cycle
    with Session(engine) as session:
        run_scan_cycle(config, session)
    # Show results
    with Session(engine) as session:
        signals = session.exec(select(SignalRecord).order_by(SignalRecord.timestamp.desc()).limit(10)).all()
        click.echo(f"\n{len(signals)} signals in DB:")
        for s in signals:
            status = "PASS" if s.all_gates_passed else "FAIL"
            click.echo(f"  {s.ticker:5s} {s.direction:8s} {status:4s} score={s.signal_score or 0:.0f} state={s.market_state} [{s.action_taken}]")


@cli.command()
def sync():
    """Sync local signals to the Cloudflare D1 Worker."""
    import requests
    config = TTRadeConfig()
    engine = _get_db_engine()
    worker_url = os.environ.get("TTRADE_WORKER_URL", "https://ttrade-worker.aicoderally.workers.dev")

    with Session(engine) as session:
        signals = session.exec(select(SignalRecord).where(SignalRecord.synced == False)).all()
        if not signals:
            click.echo("No unsynced signals.")
            return

        # Get sync API key
        sync_key = os.environ.get("TTRADE_SYNC_API_KEY", "")
        if not sync_key:
            try:
                import subprocess
                result = subprocess.run(
                    ["security", "find-generic-password", "-s", "ttrade-SYNC_API_KEY", "-w"],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    sync_key = result.stdout.strip()
            except Exception:
                pass
        if not sync_key:
            click.echo("No SYNC_API_KEY found — set TTRADE_SYNC_API_KEY or add to Keychain", err=True)
            raise SystemExit(1)

        click.echo(f"Syncing {len(signals)} signals to {worker_url}/sync ...")

        # Build gate results from stored JSON
        import json as _json
        all_gates = []
        for s in signals:
            if s.gate_results_json:
                try:
                    gates = _json.loads(s.gate_results_json)
                    for g in gates:
                        all_gates.append({
                            "signalId": s.signal_id,
                            "gateName": g.get("gate_name", ""),
                            "passed": 1 if g.get("passed") else 0,
                            "measuredValue": str(g.get("measured_value", "")),
                            "threshold": str(g.get("threshold", "")),
                            "configVersion": g.get("config_version", ""),
                        })
                except Exception:
                    pass

        payload = {
            "signals": [
                {
                    "signalId": s.signal_id,
                    "ticker": s.ticker,
                    "direction": s.direction,
                    "timestamp": s.timestamp.isoformat(),
                    "marketState": s.market_state,
                    "allGatesPassed": 1 if s.all_gates_passed else 0,
                    "signalScore": s.signal_score,
                    "componentScoresJson": s.component_scores_json,
                    "actionTaken": s.action_taken,
                    "strategyVersion": s.strategy_version,
                    "configHash": s.config_hash,
                    "aiConviction": s.ai_conviction,
                    "aiAnalysisJson": s.ai_analysis_json,
                }
                for s in signals
            ],
            "gates": all_gates,
        }

        resp = requests.post(f"{worker_url}/sync", json=payload,
                             headers={"X-API-Key": sync_key}, timeout=30)
        if resp.ok:
            data = resp.json()
            click.echo(f"Synced: {data}")
            # Mark as synced
            for s in signals:
                s.synced = True
                session.add(s)
            session.commit()
        else:
            click.echo(f"Sync failed: {resp.status_code} {resp.text}", err=True)


@cli.command(name="bt")
@click.argument("ticker")
@click.option("--strategy", type=click.Choice(["momentum", "mean_reversion", "grid", "all"]), default="all")
@click.option("--period", default="1y", help="Backtest period (1y, 2y, 6mo)")
@click.option("--account", default=1000.0, help="Starting capital")
def backtest(ticker: str, strategy: str, period: str, account: float):
    """Backtest a strategy on historical data."""
    from engine.backtest import backtest_momentum, backtest_mean_reversion, backtest_grid

    logging.basicConfig(level=logging.WARNING)
    click.echo(f"Backtesting {ticker} over {period} with ${account:,.0f}")
    click.echo("=" * 65)

    strategies = {
        "momentum": backtest_momentum,
        "mean_reversion": backtest_mean_reversion,
        "grid": backtest_grid,
    }
    if strategy == "all":
        run = list(strategies.items())
    else:
        run = [(strategy, strategies[strategy])]

    for name, func in run:
        click.echo(f"\n{'─'*65}")
        click.echo(f"  {name.upper()}")
        click.echo(f"{'─'*65}")
        try:
            r = func(ticker, period=period, account=account)
        except Exception as e:
            click.echo(f"  Error: {e}")
            continue

        # Performance
        ret_color = "+" if r.total_return_pct >= 0 else ""
        click.echo(f"  Return:      {ret_color}{r.total_return_pct:.1f}%  (${r.start_capital:.0f} → ${r.end_capital:.0f})")
        click.echo(f"  Annualized:  {r.annualized_return_pct:+.1f}%")
        click.echo(f"  Sharpe:      {r.sharpe_ratio:.2f}  |  Sortino: {r.sortino_ratio:.2f}")
        click.echo(f"  Max DD:      {r.max_drawdown_pct:.1f}% (${r.max_drawdown_dollars:.0f})")

        # Trade stats
        click.echo(f"  Trades:      {r.total_trades}  ({r.winning_trades}W / {r.losing_trades}L)")
        click.echo(f"  Win Rate:    {r.win_rate:.0f}%")
        click.echo(f"  Avg Win:     {r.avg_win_pct:+.2f}%  |  Avg Loss: {r.avg_loss_pct:.2f}%")
        click.echo(f"  Profit Factor: {r.profit_factor:.2f}")
        click.echo(f"  Avg Hold:    {r.avg_hold_days:.0f} days")
        click.echo(f"  Best:        {r.best_trade_pct:+.2f}%  |  Worst: {r.worst_trade_pct:.2f}%")
        click.echo(f"  Streaks:     {r.max_consecutive_wins}W / {r.max_consecutive_losses}L")

    click.echo("")


@cli.command(name="risk")
@click.argument("tickers", nargs=-1, required=True)
@click.option("--account", default=1000.0, help="Portfolio value")
def risk_report(tickers: tuple[str], account: float):
    """Portfolio risk analysis (VaR, correlation, Monte Carlo)."""
    from engine.risk import analyze_risk

    logging.basicConfig(level=logging.WARNING)
    ticker_list = list(tickers)
    click.echo(f"Risk Analysis: {', '.join(ticker_list)}")
    click.echo(f"Portfolio: ${account:,.0f}")
    click.echo("=" * 65)

    r = analyze_risk(ticker_list, portfolio_value=account)

    # VaR
    click.echo(f"\n  ── Value at Risk (Daily) ──")
    click.echo(f"  VaR 95%:     -{r.var_95_pct:.2f}%  (${r.var_95_dollars:.0f})")
    click.echo(f"  VaR 99%:     -{r.var_99_pct:.2f}%  (${r.var_99_dollars:.0f})")
    click.echo(f"  CVaR 95%:    -{r.cvar_95_pct:.2f}%  (${r.cvar_95_dollars:.0f})")

    # Drawdown
    click.echo(f"\n  ── Drawdown ──")
    click.echo(f"  Current:     {r.current_drawdown_pct:.1f}%")
    click.echo(f"  Max:         {r.max_drawdown_pct:.1f}%")
    click.echo(f"  Duration:    {r.drawdown_duration_days} days")

    # Volatility
    click.echo(f"\n  ── Volatility ──")
    click.echo(f"  Annual:      {r.portfolio_volatility_annual:.1f}%  ({r.volatility_risk})")
    click.echo(f"  Daily:       {r.portfolio_volatility_daily:.2f}%")
    for t, v in r.individual_vols.items():
        click.echo(f"    {t:8s}   {v:.1f}%")

    # Correlation
    click.echo(f"\n  ── Correlation ──")
    click.echo(f"  Diversification ratio: {r.diversification_ratio:.2f}")
    for pair in r.high_correlations[:5]:
        icon = "⚠" if pair.risk_level == "high" else "·"
        click.echo(f"    {icon} {pair.ticker_a:6s} / {pair.ticker_b:6s}  {pair.correlation:+.3f}  ({pair.risk_level})")

    # Monte Carlo
    click.echo(f"\n  ── Monte Carlo (5000 sims) ──")
    click.echo(f"  30-day median:     {r.mc_median_30d:+.1f}%")
    click.echo(f"  30-day worst 5%:   {r.mc_5th_pct_30d:+.1f}%")
    click.echo(f"  30-day best 5%:    {r.mc_95th_pct_30d:+.1f}%")
    click.echo(f"  Prob of loss (30d): {r.mc_prob_loss_30d:.0f}%")
    click.echo(f"  Prob of 2x (1yr):  {r.mc_prob_double_1y:.1f}%")

    # Risk scores
    click.echo(f"\n  ── Risk Score ──")
    click.echo(f"  Concentration:  {r.concentration_risk}")
    click.echo(f"  Volatility:     {r.volatility_risk}")
    click.echo(f"  Correlation:    {r.correlation_risk}")
    click.echo(f"  Overall:        {r.overall_risk_score}/100")
    click.echo("")


@cli.command(name="ta")
@click.argument("ticker")
def tech_analysis(ticker: str):
    """Full technical analysis for a ticker."""
    from engine.ta import analyze_ta

    logging.basicConfig(level=logging.WARNING)
    click.echo(f"Technical Analysis: {ticker}")
    click.echo("=" * 65)

    r = analyze_ta(ticker)

    # Signal header
    signal_color = {"STRONG BUY": ">>>", "BUY": ">> ", "NEUTRAL": "-- ",
                    "SELL": "<< ", "STRONG SELL": "<<<"}
    click.echo(f"\n  {signal_color.get(r.composite_signal, '   ')} {r.composite_signal}  (score: {r.composite_score:+d})")
    click.echo(f"  {r.ticker} @ ${r.price:,.2f}")
    click.echo(f"  Bull: {r.bull_signals}  |  Bear: {r.bear_signals}  |  Neutral: {r.neutral_signals}")

    # Moving averages
    click.echo(f"\n  ── Moving Averages ({r.ma_signal}) ──")
    for label, val in [("SMA 20", r.sma_20), ("SMA 50", r.sma_50), ("SMA 200", r.sma_200),
                       ("EMA 12", r.ema_12), ("EMA 26", r.ema_26)]:
        dist = (r.price - val) / val * 100
        click.echo(f"  {label:8s}  ${val:>10,.2f}  ({dist:+.1f}%)")

    # RSI
    click.echo(f"\n  ── RSI ({r.rsi_signal}) ──")
    bar_len = int(r.rsi_14 / 2)
    bar = "█" * bar_len + "░" * (50 - bar_len)
    click.echo(f"  RSI 14:  {r.rsi_14:.1f}  [{bar}]")

    # MACD
    click.echo(f"\n  ── MACD ({r.macd_signal}) ──")
    click.echo(f"  Line:      {r.macd_line:+.4f}")
    click.echo(f"  Signal:    {r.macd_signal_line:+.4f}")
    click.echo(f"  Histogram: {r.macd_histogram:+.4f}")

    # Bollinger Bands
    click.echo(f"\n  ── Bollinger Bands (position: {r.bb_position}) ──")
    click.echo(f"  Upper:   ${r.bb_upper:>10,.2f}")
    click.echo(f"  Middle:  ${r.bb_middle:>10,.2f}")
    click.echo(f"  Lower:   ${r.bb_lower:>10,.2f}")
    click.echo(f"  Width:   {r.bb_width_pct:.1f}%")

    # Stochastic
    click.echo(f"\n  ── Stochastic ({r.stoch_signal}) ──")
    click.echo(f"  %K: {r.stoch_k:.1f}  |  %D: {r.stoch_d:.1f}")

    # Volume
    click.echo(f"\n  ── Volume ({r.volume_signal}) ──")
    click.echo(f"  Ratio:   {r.volume_ratio:.2f}x avg  |  OBV: {r.obv_trend}")

    # ATR / Volatility
    click.echo(f"\n  ── Volatility ({r.volatility}) ──")
    click.echo(f"  ATR 14:  ${r.atr_14:.2f}  ({r.atr_pct:.1f}%)")

    # Fibonacci
    click.echo(f"\n  ── Fibonacci (nearest: {r.nearest_fib}) ──")
    for level, val in r.fib_levels.items():
        marker = " ◄" if abs(val - r.price) / r.price < 0.02 else ""
        click.echo(f"  {level:6s}  ${val:>10,.2f}{marker}")

    # Support / Resistance
    click.echo(f"\n  ── Support / Resistance (20-day) ──")
    click.echo(f"  Support:     ${r.support:>10,.2f}  ({(r.price - r.support)/r.price*100:+.1f}%)")
    click.echo(f"  Resistance:  ${r.resistance:>10,.2f}  ({(r.resistance - r.price)/r.price*100:+.1f}%)")
    click.echo("")


@cli.command(name="lev")
@click.option("--account", default=1000.0, help="Account value for position sizing")
def leverage_scan(account: float):
    """Scan leveraged ETFs (SQQQ/TQQQ/SPXU/UPRO) for aggressive entries."""
    from engine.market_data import get_daily_bars
    from engine.market_state import evaluate_market_state
    from engine.leverage import scan_leverage

    logging.basicConfig(level=logging.WARNING)
    config = TTRadeConfig()

    try:
        spy_bars = get_daily_bars("SPY", period_days=60)
    except Exception as e:
        click.echo(f"Failed to fetch SPY: {e}", err=True)
        raise SystemExit(1)

    market_state = evaluate_market_state(spy_bars, config)
    click.echo(f"Market: {market_state.state.value} (slope={market_state.slope:.2f}, SPY=${market_state.current_price:.2f})")
    click.echo(f"Account: ${account:,.0f}")
    click.echo("")

    signals = scan_leverage(market_state, config, account_value=account)

    if not signals:
        click.echo("No leveraged ETF signals (CHOP regime or no candidates).")
        return

    for s in signals:
        icon = {"buy": ">>> BUY", "hold": "... WATCH", "avoid": "  x AVOID"}[s.action]
        click.echo(f"{icon}  {s.ticker} (3x inverse {s.tracks}) @ ${s.price:.2f}")
        click.echo(f"         Score: {s.score:.0f}/100")

        for name, check in s.checks.items():
            mark = "PASS" if check["passed"] else "FAIL"
            click.echo(f"         {name:20s} {mark}  ({check['value']})")

        if s.action == "buy":
            click.echo(f"         ─────────────────────────────────")
            click.echo(f"         Entry:    ${s.price:.2f}")
            click.echo(f"         Stop:     ${s.stop_price:.2f} (-${s.price - s.stop_price:.2f})")
            click.echo(f"         Target:   ${s.target_price:.2f} (+${s.target_price - s.price:.2f})")
            click.echo(f"         Shares:   {s.position_size_shares}")
            click.echo(f"         Size:     ${s.position_size_dollars:.0f} ({s.position_size_dollars/account*100:.0f}% of account)")
            pnl_win = s.position_size_shares * (s.target_price - s.price)
            pnl_loss = s.position_size_shares * (s.stop_price - s.price)
            click.echo(f"         Win:      +${pnl_win:.0f} ({pnl_win/account*100:+.0f}% of account)")
            click.echo(f"         Loss:     -${abs(pnl_loss):.0f} ({pnl_loss/account*100:+.0f}% of account)")

        # News headlines
        if s.news_headlines:
            click.echo(f"         ── News ({len(s.news_headlines)} headlines) ──")
            for h in s.news_headlines[:5]:
                click.echo(f"           - {h[:80]}")

        # AI catalyst
        if s.ai_catalyst:
            ai = s.ai_catalyst
            click.echo(f"         ── AI Catalyst ──")
            click.echo(f"           Conviction: {ai['conviction']:.0f}/100 ({ai['trade_quality']})")
            click.echo(f"           {ai['summary']}")
            if ai['risk_factors']:
                click.echo(f"           Risks: {', '.join(ai['risk_factors'][:3])}")

        click.echo("")


@cli.command()
@click.option("--top", default=10, help="Show top N candidates")
def screen(top: int):
    """Screen broad universe for promising setups."""
    from engine.market_data import get_daily_bars
    from engine.market_state import evaluate_market_state
    from engine.gates.regime import check_regime
    from engine.gates.alignment import check_alignment
    from engine.gates.pullback import check_pullback
    from engine.gates.confirmation import check_confirmation
    from engine.pipeline import determine_direction

    logging.basicConfig(level=logging.WARNING)
    config = TTRadeConfig()

    click.echo(f"Screening {len(config.screen_universe)} tickers...")
    try:
        spy_bars = get_daily_bars("SPY", period_days=60)
    except Exception as e:
        click.echo(f"Failed to fetch SPY: {e}", err=True)
        raise SystemExit(1)

    market_state = evaluate_market_state(spy_bars, config)
    direction = determine_direction(market_state.state)
    click.echo(f"Market: {market_state.state.value} (slope={market_state.slope:.2f}, SPY=${market_state.current_price:.2f})")
    click.echo(f"Direction: {direction or 'NONE (CHOP)'}")
    click.echo("")

    if direction is None:
        click.echo("CHOP regime — no directional setups to screen.")
        return

    results = []
    for ticker in config.screen_universe:
        try:
            bars = spy_bars if ticker == "SPY" else get_daily_bars(ticker, period_days=60)
        except Exception:
            continue

        gates_passed = 0
        gate_detail = []

        g1 = check_regime(market_state, config)
        if g1.passed:
            gates_passed += 1
            gate_detail.append("regime")

            g2 = check_alignment(bars, market_state, config)
            if g2.passed:
                gates_passed += 1
                gate_detail.append("align")

                g3 = check_pullback(bars, direction, config)
                if g3.passed:
                    gates_passed += 1
                    gate_detail.append("pullback")

                    g4 = check_confirmation(bars, direction, config)
                    if g4.passed:
                        gates_passed += 1
                        gate_detail.append("confirm")

        close = float(bars["Close"].iloc[-1])
        results.append((ticker, gates_passed, gate_detail, close))

    results.sort(key=lambda x: (-x[1], x[0]))
    click.echo(f"{'TICKER':6s} {'GATES':5s} {'PRICE':>8s}  PASSED")
    click.echo("-" * 45)
    for ticker, passed, detail, price in results[:top]:
        bar = "█" * passed + "░" * (4 - passed)
        click.echo(f"{ticker:6s} {bar}  ${price:>7.2f}  {', '.join(detail)}")

    # Summary
    by_count = {}
    for _, passed, _, _ in results:
        by_count[passed] = by_count.get(passed, 0) + 1
    click.echo("")
    click.echo(f"Total: {len(results)} screened | " + " | ".join(f"{k}/4: {v}" for k, v in sorted(by_count.items(), reverse=True)))


@cli.command()
@click.option("--account", default=1000.0, help="Account value for position sizing")
def crypto(account: float):
    """Scan crypto (BTC/ETH) for grid trading opportunities."""
    from engine.crypto import scan_crypto

    logging.basicConfig(level=logging.WARNING)
    config = TTRadeConfig()

    click.echo(f"Scanning crypto for grid trading opportunities...")
    click.echo(f"Account: ${account:,.0f}")
    click.echo("")

    signals = scan_crypto(config, account_value=account)

    if not signals:
        click.echo("No crypto data available.")
        return

    for s in signals:
        icon = {"trade": ">>> TRADE", "watch": "... WATCH", "avoid": "  x AVOID"}[s.action]
        click.echo(f"{icon}  {s.name} ({s.ticker}) @ ${s.price:,.2f}")
        click.echo(f"         Score: {s.score:.0f}/100 | Trend: {s.trend} | Volatility: {s.volatility}")
        click.echo("")

        for name, check in s.checks.items():
            mark = "PASS" if check["passed"] else "FAIL"
            click.echo(f"         {name:20s} {mark}  ({check['value']})")

        click.echo("")
        click.echo(f"         ── Grid Setup ──")
        click.echo(f"         Spacing:     {s.grid_spacing_pct:.1f}%")
        click.echo(f"         Buy levels:  {s.buy_levels} below ${s.price:,.0f}")
        click.echo(f"         Sell levels: {s.sell_levels} above ${s.price:,.0f}")
        click.echo(f"         Per level:   ${s.position_size:.0f}")
        click.echo(f"         Capital:     ${s.total_capital_needed:.0f} ({s.total_capital_needed/account*100:.0f}% of account)")

        click.echo("")
        click.echo(f"         ── Grid Levels ──")
        for level in s.grid_levels:
            side_icon = "BUY " if level.side == "buy" else "SELL"
            marker = " <<<" if abs(level.price - s.price) / s.price < s.grid_spacing_pct / 100 else ""
            click.echo(f"           {side_icon} @ ${level.price:>10,.2f}  -> exit @ ${level.paired_level:>10,.2f}{marker}")

        click.echo("")
        click.echo(f"         ── Profit Estimate ──")
        click.echo(f"         Per round trip: ${s.profit_per_round_trip:.2f}")
        click.echo(f"         Est. daily trips: {s.est_daily_trips:.1f}")
        click.echo(f"         Est. daily profit: ${s.est_daily_profit:.2f} ({s.est_daily_profit/account*100:.1f}% of account)")
        click.echo(f"         Est. weekly profit: ${s.est_weekly_profit:.2f} ({s.est_weekly_profit/account*100:.1f}% of account)")

        if s.est_weekly_profit > 0:
            weeks_to_double = account / s.est_weekly_profit
            click.echo(f"         Time to double: ~{weeks_to_double:.0f} weeks")

        if s.news_headlines:
            click.echo(f"         ── News ({len(s.news_headlines)} headlines) ──")
            for h in s.news_headlines[:5]:
                click.echo(f"           - {h[:80]}")

        click.echo("")


@cli.command(name="vol")
@click.option("--account", default=1000.0, help="Account value for position sizing")
@click.option("--sector", default=None, help="Specific sector (oil, gold, gold_miners, nat_gas, vix, biotech, energy)")
def volatility_scan(account: float, sector: str | None):
    """Scan commodities & volatility instruments (oil, gold, VIX, etc.)."""
    from engine.volatility import scan_volatility

    logging.basicConfig(level=logging.WARNING)
    config = TTRadeConfig()

    sectors = [sector] if sector else None
    click.echo("Commodity & Volatility Scanner")
    click.echo(f"Account: ${account:,.0f}")
    click.echo("=" * 65)
    click.echo("")

    signals = scan_volatility(config, account_value=account, sectors=sectors)

    if not signals:
        click.echo("No signals available.")
        return

    for s in signals:
        best = s.best_strategy
        icon = {"trade": ">>>", "watch": "...", "avoid": "  x"}[best.action]
        click.echo(f"{icon} {s.sector_name.upper()} — Score: {s.score:.0f}/100")
        click.echo(f"    Bull: {s.bull_ticker} ${s.bull_price:.2f}  |  Bear: {s.bear_ticker} ${s.bear_price:.2f}")
        if s.underlying_price > 0:
            click.echo(f"    Underlying: {s.underlying_ticker} ${s.underlying_price:.2f}")
        click.echo(f"    Volatility: {s.volatility_rank} ({s.atr_pct:.1f}% ATR, {s.daily_range_pct:.1f}% daily range)")
        click.echo(f"    Trend: {s.trend} (strength {s.trend_strength:.0f}) | RSI: {s.rsi:.0f} | SMA20: {s.sma20_dist_pct:+.1f}%")
        click.echo("")

        # Checks
        for name, check in s.checks.items():
            mark = "PASS" if check["passed"] else "FAIL"
            click.echo(f"    {name:16s} {mark}  ({check['value']})")
        click.echo("")

        # All strategy scores
        click.echo(f"    ── Strategies ──")
        for strat in s.all_strategies:
            star = " ★ BEST" if strat.name == best.name else ""
            click.echo(f"    {strat.name:16s} {strat.score:3.0f}/100  {strat.action:6s}  "
                        f"est ${strat.est_daily_pnl:.2f}/day  ${strat.est_weekly_pnl:.2f}/wk{star}")
        click.echo("")

        # Recommendation
        click.echo(f"    ── Recommendation ──")
        click.echo(f"    Strategy:  {best.name.upper()}")
        click.echo(f"    Trade:     {s.recommended_ticker} ({s.recommended_side.upper()})")
        rec_price = s.bull_price if s.recommended_side == "bull" else s.bear_price
        click.echo(f"    Entry:     ${rec_price:.2f}")
        click.echo(f"    Stop:      ${rec_price * (1 - s.stop_pct/100):.2f} (-{s.stop_pct:.1f}%)")
        click.echo(f"    Target:    ${rec_price * (1 + s.target_pct/100):.2f} (+{s.target_pct:.1f}%)")
        click.echo(f"    Shares:    {s.shares}")
        click.echo(f"    Size:      ${s.position_size:.0f} ({s.position_size/account*100:.0f}% of account)")
        click.echo(f"    Win P&L:   +${s.est_win_dollars:.0f} ({s.est_win_dollars/account*100:+.0f}%)")
        click.echo(f"    Loss P&L:  -${s.est_loss_dollars:.0f} ({s.est_loss_dollars/account*100:-.0f}%)")

        # Strategy-specific params
        if best.name == "grid":
            p = best.params
            click.echo(f"    Grid:      {p['spacing_pct']:.1f}% spacing, {p['num_levels']} levels, ${p['per_level']:.0f}/level")
            click.echo(f"               ~{p['est_trips_day']:.1f} trips/day, ${p['profit_per_trip']:.2f}/trip")

        if best.name == "mean_reversion":
            p = best.params
            click.echo(f"    Revert to: {p['reversion_target']} ({p['extension']} extension)")

        # News
        if s.news_headlines:
            click.echo(f"    ── News ({len(s.news_headlines)} headlines) ──")
            for h in s.news_headlines[:4]:
                click.echo(f"      - {h[:78]}")

        click.echo("")
        click.echo(f"    ⚠  DRY RUN — no orders placed")
        click.echo("")
        click.echo("=" * 65)
        click.echo("")


@cli.command(name="grid")
@click.option("--account", default=1000.0, help="Account value for position sizing")
@click.option("--ticker", default=None, help="Specific crypto (BTC-USD or ETH-USD)")
@click.option("--save", is_flag=True, help="Save grid plan to database")
def grid_plan(account: float, ticker: str | None, save: bool):
    """Preview crypto grid trading orders (DRY RUN — no real trades)."""
    from engine.crypto import scan_crypto, CRYPTO_TICKERS
    from engine.grid_executor import plan_grid, execute_grid, format_grid_plan

    logging.basicConfig(level=logging.WARNING)
    config = TTRadeConfig()

    click.echo("Crypto Grid Planner (DRY RUN)")
    click.echo(f"Account: ${account:,.0f}")
    click.echo("=" * 60)
    click.echo("")

    signals = scan_crypto(config, account_value=account)

    if ticker:
        signals = [s for s in signals if s.ticker == ticker]

    if not signals:
        click.echo("No crypto signals available.")
        return

    for signal in signals:
        plan = plan_grid(signal, mode="DRY_RUN")
        click.echo(format_grid_plan(plan))

        if save:
            db_engine = _get_db_engine()
            result = execute_grid(plan, db_engine=db_engine)
            click.echo(f"\n  Saved to database: {result['grid_id']}")

        click.echo("")
        click.echo("=" * 60)
        click.echo("")


@cli.command()
@click.option("--paper", is_flag=True, help="Run in paper trading mode")
def run(paper: bool):
    """Start the trading engine."""
    click.echo("Starting TTrade engine...")
    from engine.main import start_engine
    start_engine(mode_override="PAPER" if paper else None)

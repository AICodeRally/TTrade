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
@click.option("--paper", is_flag=True, help="Run in paper trading mode")
def run(paper: bool):
    """Start the trading engine."""
    click.echo("Starting TTrade engine...")
    from engine.main import start_engine
    start_engine(mode_override="PAPER" if paper else None)

"""TTrade CLI — Click-based command interface."""
import click
from engine.config import TTRadeConfig


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


@cli.command()
@click.argument("signal_id")
def approve(signal_id: str):
    """Approve a pending signal for execution."""
    click.echo(f"Approving signal: {signal_id}")
    click.echo(f"Signal {signal_id} approved for execution.")


@cli.command()
@click.option("--paper", is_flag=True, help="Run in paper trading mode")
def run(paper: bool):
    """Start the trading engine."""
    click.echo("Starting TTrade engine...")
    from engine.main import start_engine
    start_engine(mode_override="PAPER" if paper else None)

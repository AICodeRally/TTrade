"""Grid trading executor — manages grid order lifecycle.

Modes:
  DRY_RUN  — calculates and logs all orders, no broker calls (default)
  PAPER    — simulates fills at grid prices
  LIVE     — places real orders via broker (requires explicit approval)

The grid executor:
1. Calculates grid levels from current price + ATR
2. Places buy limit orders below price, sell limits above
3. When a buy fills, spawns a paired sell one grid up (and vice versa)
4. Tracks all state in SQLite grid_orders table
"""
import json
import logging
import uuid
from datetime import datetime

from engine.crypto import scan_crypto, CryptoSignal
from engine.config import TTRadeConfig

logger = logging.getLogger(__name__)


def _generate_grid_id() -> str:
    return f"grid_{datetime.now().strftime('%Y%m%d_%H%M')}_{uuid.uuid4().hex[:6]}"


def plan_grid(signal: CryptoSignal, mode: str = "DRY_RUN") -> dict:
    """Plan a grid for a crypto signal. Returns the full order plan.

    This is the core function — it calculates exactly what orders
    would be placed without touching the broker.
    """
    grid_id = _generate_grid_id()
    orders = []

    for level in signal.grid_levels:
        order = {
            "grid_id": grid_id,
            "ticker": signal.ticker,
            "side": level.side,
            "level_price": round(level.price, 2),
            "exit_price": round(level.paired_level, 2) if level.paired_level else None,
            "notional_amount": signal.position_size,
            "status": "planned",
        }

        # Calculate expected P&L per round trip
        if level.paired_level:
            if level.side == "buy":
                order["expected_pnl"] = round(
                    signal.position_size * (level.paired_level - level.price) / level.price, 2
                )
            else:
                order["expected_pnl"] = round(
                    signal.position_size * (level.price - level.paired_level) / level.paired_level, 2
                )
        else:
            order["expected_pnl"] = 0.0

        orders.append(order)

    # Summary stats
    buy_orders = [o for o in orders if o["side"] == "buy"]
    sell_orders = [o for o in orders if o["side"] == "sell"]
    total_buy_capital = sum(o["notional_amount"] for o in buy_orders)
    total_expected_pnl = sum(o["expected_pnl"] for o in orders)

    return {
        "grid_id": grid_id,
        "ticker": signal.ticker,
        "name": signal.name,
        "mode": mode,
        "price": signal.price,
        "grid_spacing_pct": signal.grid_spacing_pct,
        "orders": orders,
        "summary": {
            "buy_levels": len(buy_orders),
            "sell_levels": len(sell_orders),
            "total_orders": len(orders),
            "capital_needed": round(total_buy_capital, 2),
            "per_level": signal.position_size,
            "expected_pnl_per_cycle": round(total_expected_pnl, 2),
            "est_daily_profit": signal.est_daily_profit,
            "est_weekly_profit": signal.est_weekly_profit,
        },
        "checks": {name: check for name, check in signal.checks.items()},
        "timestamp": datetime.now().isoformat(),
    }


def save_grid_plan(plan: dict, db_engine) -> str:
    """Save a grid plan to the database (DRY_RUN — no broker orders)."""
    from sqlmodel import Session
    from engine.db import GridOrderRecord

    with Session(db_engine) as session:
        for order in plan["orders"]:
            record = GridOrderRecord(
                grid_id=plan["grid_id"],
                ticker=order["ticker"],
                side=order["side"],
                level_price=order["level_price"],
                exit_price=order["exit_price"] or 0.0,
                notional_amount=order["notional_amount"],
                status="dry_run",
            )
            session.add(record)
        session.commit()

    logger.info("Saved grid plan %s: %d orders for %s",
                plan["grid_id"], len(plan["orders"]), plan["ticker"])
    return plan["grid_id"]


def execute_grid(plan: dict, broker=None, db_engine=None) -> dict:
    """Execute a grid plan.

    DRY_RUN:  just saves to DB and returns the plan
    PAPER:    simulates immediate fills at grid prices
    LIVE:     places real limit orders via broker (NOT YET IMPLEMENTED)
    """
    mode = plan["mode"]
    results = {"grid_id": plan["grid_id"], "mode": mode, "orders": []}

    if mode == "LIVE":
        raise NotImplementedError(
            "LIVE mode is not enabled. Grid trading is in review mode. "
            "Use DRY_RUN to preview or PAPER to simulate."
        )

    for order in plan["orders"]:
        result = {
            **order,
            "order_id": f"{mode}-{uuid.uuid4().hex[:8]}",
        }

        if mode == "PAPER":
            # Simulate fill at the grid price
            result["status"] = "paper_filled"
            result["fill_price"] = order["level_price"]
            result["filled_at"] = datetime.now().isoformat()
        else:
            # DRY_RUN — just mark as planned
            result["status"] = "dry_run"

        results["orders"].append(result)

    # Save to DB if engine provided
    if db_engine:
        save_grid_plan(plan, db_engine)

    results["summary"] = plan["summary"]
    return results


def format_grid_plan(plan: dict) -> str:
    """Format a grid plan for CLI display."""
    lines = []
    lines.append(f"Grid Plan: {plan['grid_id']}")
    lines.append(f"Mode: {plan['mode']}")
    lines.append(f"{plan['name']} ({plan['ticker']}) @ ${plan['price']:,.2f}")
    lines.append(f"Grid spacing: {plan['grid_spacing_pct']:.1f}%")
    lines.append("")

    # Checks
    lines.append("Checks:")
    for name, check in plan["checks"].items():
        mark = "PASS" if check["passed"] else "FAIL"
        lines.append(f"  {name:20s} {mark}  ({check['value']})")
    lines.append("")

    # Orders
    lines.append("Orders:")
    lines.append(f"  {'SIDE':5s} {'LEVEL':>12s}    {'EXIT':>12s}    {'SIZE':>8s}  {'P&L':>8s}")
    lines.append(f"  {'─'*55}")
    for o in plan["orders"]:
        side = o["side"].upper()
        exit_str = f"${o['exit_price']:>10,.2f}" if o["exit_price"] else "          -"
        pnl_str = f"+${o['expected_pnl']:.2f}" if o["expected_pnl"] > 0 else f"${o['expected_pnl']:.2f}"
        lines.append(
            f"  {side:5s} ${o['level_price']:>10,.2f}  → {exit_str}    ${o['notional_amount']:>6.0f}  {pnl_str:>8s}"
        )
    lines.append("")

    # Summary
    s = plan["summary"]
    lines.append("Summary:")
    lines.append(f"  Buy levels:        {s['buy_levels']}")
    lines.append(f"  Sell levels:       {s['sell_levels']}")
    lines.append(f"  Capital needed:    ${s['capital_needed']:,.0f}")
    lines.append(f"  Per level:         ${s['per_level']:,.0f}")
    lines.append(f"  P&L per cycle:     ${s['expected_pnl_per_cycle']:.2f}")
    lines.append(f"  Est. daily:        ${s['est_daily_profit']:.2f}")
    lines.append(f"  Est. weekly:       ${s['est_weekly_profit']:.2f}")
    if s['est_weekly_profit'] > 0:
        weeks = 1000 / s['est_weekly_profit']
        lines.append(f"  Time to double:    ~{weeks:.0f} weeks")
    lines.append("")
    lines.append(f"  ⚠  MODE: {plan['mode']} — no real orders placed")

    return "\n".join(lines)

"""Weekly learning report generator."""
import uuid
from collections import defaultdict
from datetime import date, datetime
from engine.models import WeeklyLearningReport


def generate_weekly_report(signals: list[dict], reviews: list[dict], week_start: date, week_end: date) -> WeeklyLearningReport:
    total_signals = len(signals)
    total_trades = len(reviews)
    wins = sum(1 for r in reviews if r.get("pnl_pct", 0) > 0)
    win_rate = wins / total_trades if total_trades > 0 else 0.0
    total_pnl = sum(r.get("pnl_dollars", 0) for r in reviews)

    bands = {"A": [], "B": [], "C": [], "JUNK": []}
    for r in reviews:
        score = r.get("signal_score", 0)
        if score >= 85: bands["A"].append(r)
        elif score >= 70: bands["B"].append(r)
        elif score >= 55: bands["C"].append(r)
        else: bands["JUNK"].append(r)

    score_band_performance = {}
    for band, trades in bands.items():
        if trades:
            band_wins = sum(1 for t in trades if t.get("pnl_pct", 0) > 0)
            score_band_performance[band] = {
                "count": len(trades),
                "win_rate": band_wins / len(trades),
                "avg_pnl": sum(t.get("pnl_dollars", 0) for t in trades) / len(trades),
            }

    failure_tags: dict[str, int] = defaultdict(int)
    for r in reviews:
        for tag in r.get("failure_tags", []):
            failure_tags[tag] += 1

    ticker_perf: dict[str, dict] = defaultdict(lambda: {"count": 0, "pnl": 0.0})
    for r in reviews:
        ticker = r.get("ticker", "unknown")
        ticker_perf[ticker]["count"] += 1
        ticker_perf[ticker]["pnl"] += r.get("pnl_dollars", 0)

    return WeeklyLearningReport(
        id=f"rpt_{uuid.uuid4().hex[:8]}", week_start=week_start, week_end=week_end,
        total_signals=total_signals, total_trades=total_trades, win_rate=win_rate,
        total_pnl=total_pnl, score_band_performance=score_band_performance,
        dimension_correlation={}, failure_tag_frequency=dict(failure_tags),
        ticker_performance=dict(ticker_perf), threshold_suggestions=[],
        generated_at=datetime.now(),
    )

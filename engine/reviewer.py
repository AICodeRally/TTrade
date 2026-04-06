"""Post-trade review — grading + failure taxonomy."""
import logging

logger = logging.getLogger(__name__)


def grade_outcome(pnl_pct: float, exit_reason: str) -> str:
    if pnl_pct >= 0.50: return "A"
    elif pnl_pct >= 0.25: return "B"
    elif pnl_pct >= 0.0: return "C"
    elif pnl_pct >= -0.20: return "D"
    return "F"


def grade_setup(signal_score: float) -> str:
    if signal_score >= 85: return "A"
    elif signal_score >= 70: return "B"
    elif signal_score >= 55: return "C"
    elif signal_score >= 40: return "D"
    return "F"


def grade_execution(fill_vs_mid_pct: float, entry_timing: str, exit_timing: str) -> str:
    score = 0
    if abs(fill_vs_mid_pct) <= 0.02: score += 40
    elif abs(fill_vs_mid_pct) <= 0.05: score += 30
    else: score += 15
    if entry_timing == "on_confirmation": score += 30
    elif entry_timing == "early": score += 15
    else: score += 10
    if exit_timing == "on_rule": score += 30
    elif exit_timing == "early": score += 15
    else: score += 10
    if score >= 85: return "A"
    elif score >= 70: return "B"
    elif score >= 55: return "C"
    elif score >= 40: return "D"
    return "F"


def auto_tag_failures(pnl_pct: float, exit_reason: str, signal_score: float, mfe: float, mae: float) -> list[str]:
    tags = []
    if pnl_pct >= 0.50: return []
    if signal_score >= 85 and pnl_pct < -0.20: tags.append("score_too_high")
    if mfe > 0.30 and pnl_pct < 0: tags.append("profit_taken_too_early")
    if exit_reason == "stop_loss" and mae < -0.50: tags.append("held_past_rule")
    if exit_reason == "thesis_invalid": tags.append("market_reversed")
    if exit_reason == "stop_loss" and signal_score >= 85: tags.append("market_reversed")
    return tags

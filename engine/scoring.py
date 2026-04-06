"""7-dimension scoring engine (0-100)."""
from dataclasses import dataclass
import math


@dataclass
class ScoreComponents:
    regime: float       # 0-20
    alignment: float    # 0-15
    pullback: float     # 0-15
    confirmation: float # 0-20
    stability: float    # 0-10
    structure: float    # 0-10
    event: float        # 0-10

    @property
    def total(self) -> float:
        return (self.regime + self.alignment + self.pullback +
                self.confirmation + self.stability + self.structure + self.event)

    @property
    def band(self) -> str:
        t = self.total
        if t >= 85: return "A"
        elif t >= 70: return "B"
        elif t >= 55: return "C"
        return "JUNK"

    def to_dict(self) -> dict:
        return {
            "regime": self.regime, "alignment": self.alignment,
            "pullback": self.pullback, "confirmation": self.confirmation,
            "stability": self.stability, "structure": self.structure,
            "event": self.event, "total": self.total, "band": self.band,
        }


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _lerp(value: float, in_lo: float, in_hi: float, out_lo: float, out_hi: float) -> float:
    if in_hi == in_lo: return out_hi
    t = (value - in_lo) / (in_hi - in_lo)
    t = max(0.0, min(1.0, t))
    return out_lo + t * (out_hi - out_lo)


def score_regime(slope: float, consistency: int) -> float:
    slope_score = _lerp(abs(slope), 0, 5.0, 0, 12)
    consistency_score = _lerp(consistency, 0, 5, 0, 8)
    return _clamp(slope_score + consistency_score, 0, 20)


def score_alignment(relative_strength: float, ma_distance_pct: float) -> float:
    rs_score = _lerp(relative_strength, 0.95, 1.1, 3, 10)
    dist_score = _lerp(ma_distance_pct, 0, 0.03, 0, 5)
    return _clamp(rs_score + dist_score, 0, 15)


def score_pullback(distance_from_ma: float, pullback_bars: int, body_size_ratio: float) -> float:
    dist_score = _lerp(distance_from_ma, 0.02, 0, 0, 6)
    bars_score = 5.0 if 3 <= pullback_bars <= 5 else _lerp(abs(pullback_bars - 4), 0, 4, 5, 0)
    body_score = _lerp(body_size_ratio, 1.0, 0.2, 0, 4)
    return _clamp(dist_score + bars_score + body_score, 0, 15)


def score_confirmation(volume_ratio: float, close_strength: float, body_wick_ratio: float) -> float:
    vol_score = _lerp(volume_ratio, 0.8, 2.0, 0, 8)
    close_score = _lerp(close_strength, 0, 1.0, 0, 7)
    bw_score = _lerp(body_wick_ratio, 0.3, 3.0, 0, 5)
    return _clamp(vol_score + close_score + bw_score, 0, 20)


def score_stability(atr_ratio: float) -> float:
    return _clamp(_lerp(atr_ratio, 1.5, 1.0, 0, 10), 0, 10)


def score_structure(bid_ask_pct: float, open_interest: int, debit_fit: float) -> float:
    spread_score = _lerp(bid_ask_pct, 0.15, 0.02, 0, 4)
    oi_score = _lerp(math.log10(max(open_interest, 1)), 2, 4, 0, 3)
    fit_score = _lerp(debit_fit, 0, 1.0, 0, 3)
    return _clamp(spread_score + oi_score + fit_score, 0, 10)


def score_event(days_to_earnings: int | None) -> float:
    if days_to_earnings is None: return 7.0
    return _clamp(_lerp(days_to_earnings, 7, 30, 0, 10), 0, 10)


def score_signal(
    regime_slope: float, regime_consistency: int,
    relative_strength: float, ma_distance_pct: float,
    pullback_distance: float, pullback_bar_count: int, pullback_body_ratio: float,
    volume_ratio: float, close_strength: float, body_wick_ratio: float,
    atr_ratio: float, bid_ask_pct: float, open_interest: int, debit_fit: float,
    days_to_earnings: int | None,
) -> ScoreComponents:
    return ScoreComponents(
        regime=score_regime(regime_slope, regime_consistency),
        alignment=score_alignment(relative_strength, ma_distance_pct),
        pullback=score_pullback(pullback_distance, pullback_bar_count, pullback_body_ratio),
        confirmation=score_confirmation(volume_ratio, close_strength, body_wick_ratio),
        stability=score_stability(atr_ratio),
        structure=score_structure(bid_ask_pct, open_interest, debit_fit),
        event=score_event(days_to_earnings),
    )

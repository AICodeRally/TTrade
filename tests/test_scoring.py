import pytest
from engine.scoring import score_signal, ScoreComponents


def test_score_components_sum():
    sc = ScoreComponents(regime=17.0, alignment=13.0, pullback=12.0,
                         confirmation=18.0, stability=8.0, structure=9.0, event=10.0)
    assert sc.total == 87.0


def test_score_components_max():
    sc = ScoreComponents(regime=20.0, alignment=15.0, pullback=15.0,
                         confirmation=20.0, stability=10.0, structure=10.0, event=10.0)
    assert sc.total == 100.0


def test_score_signal_a_band():
    components = ScoreComponents(regime=18.0, alignment=13.0, pullback=13.0,
                                  confirmation=18.0, stability=9.0, structure=8.0, event=9.0)
    assert components.total >= 85.0
    assert components.band == "A"


def test_score_signal_b_band():
    components = ScoreComponents(regime=14.0, alignment=11.0, pullback=11.0,
                                  confirmation=14.0, stability=7.0, structure=7.0, event=8.0)
    total = components.total
    assert 70.0 <= total < 85.0
    assert components.band == "B"


def test_score_signal_c_band():
    components = ScoreComponents(regime=10.0, alignment=8.0, pullback=8.0,
                                  confirmation=12.0, stability=6.0, structure=6.0, event=7.0)
    total = components.total
    assert 55.0 <= total < 70.0
    assert components.band == "C"


def test_score_signal_junk():
    components = ScoreComponents(regime=5.0, alignment=5.0, pullback=5.0,
                                  confirmation=5.0, stability=3.0, structure=3.0, event=3.0)
    assert components.total < 55.0
    assert components.band == "JUNK"


def test_score_regime_dimension():
    from engine.scoring import score_regime
    score = score_regime(slope=3.5, consistency=5)
    assert 15.0 <= score <= 20.0


def test_score_confirmation_dimension():
    from engine.scoring import score_confirmation
    score = score_confirmation(volume_ratio=1.8, close_strength=0.9, body_wick_ratio=3.0)
    assert 15.0 <= score <= 20.0

from __future__ import annotations

from game.constants.thresholds import SCORE_SWING_THRESHOLD
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "score_swing" for s in emit_triggers(facts))


def test_fires_above_threshold():
    assert triggered(make_facts(score_delta=SCORE_SWING_THRESHOLD + 0.1))


def test_fires_negative_above_threshold():
    assert triggered(make_facts(score_delta=-(SCORE_SWING_THRESHOLD + 0.1)))


def test_no_fire_at_threshold():
    assert not triggered(make_facts(score_delta=SCORE_SWING_THRESHOLD))


def test_no_fire_below_threshold():
    assert not triggered(make_facts(score_delta=SCORE_SWING_THRESHOLD - 0.5))


def test_no_fire_at_zero():
    assert not triggered(make_facts(score_delta=0.0))

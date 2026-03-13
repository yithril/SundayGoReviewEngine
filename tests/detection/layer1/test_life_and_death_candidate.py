from __future__ import annotations

from game.constants.thresholds import SCORE_SWING_THRESHOLD
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "life_and_death_candidate" for s in emit_triggers(facts))


def test_fires_with_score_swing_and_weak_group():
    assert triggered(make_facts(
        score_delta=SCORE_SWING_THRESHOLD + 0.1,
        self_liberties=2,
        stones_captured=0,
    ))


def test_fires_with_negative_score_swing():
    assert triggered(make_facts(
        score_delta=-(SCORE_SWING_THRESHOLD + 0.1),
        self_liberties=1,
        stones_captured=0,
    ))


def test_no_fire_score_swing_not_large_enough():
    assert not triggered(make_facts(
        score_delta=SCORE_SWING_THRESHOLD,
        self_liberties=2,
        stones_captured=0,
    ))


def test_no_fire_no_weak_group():
    assert not triggered(make_facts(
        score_delta=SCORE_SWING_THRESHOLD + 0.1,
        self_liberties=4,
        stones_captured=0,
    ))


def test_no_fire_capture_present():
    # stones_captured > 0 suppresses weak_group_candidate
    assert not triggered(make_facts(
        score_delta=SCORE_SWING_THRESHOLD + 0.1,
        self_liberties=1,
        stones_captured=1,
    ))


def test_stub_default_does_not_fire():
    assert not triggered(make_facts())

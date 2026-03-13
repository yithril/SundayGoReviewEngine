from __future__ import annotations

from game.constants.thresholds import TENUKI_DISTANCE
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "tenuki_after_forcing" for s in emit_triggers(facts))


def test_fires_when_far_away_and_urgent():
    assert triggered(make_facts(
        distance_to_prev=TENUKI_DISTANCE + 1,
        urgent_local_existed=True,
    ))


def test_no_fire_not_far_enough():
    assert not triggered(make_facts(
        distance_to_prev=TENUKI_DISTANCE,
        urgent_local_existed=True,
    ))


def test_no_fire_no_urgent_issue():
    assert not triggered(make_facts(
        distance_to_prev=TENUKI_DISTANCE + 1,
        urgent_local_existed=False,
    ))


def test_stub_default_does_not_fire():
    assert not triggered(make_facts())

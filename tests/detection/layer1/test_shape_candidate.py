from __future__ import annotations

from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "shape_candidate" for s in emit_triggers(facts))


def test_fires_with_high_rank_and_nearby_friendlies():
    assert triggered(make_facts(policy_rank=4, adjacent_friendly=2))


def test_fires_with_very_high_rank_and_many_friendlies():
    assert triggered(make_facts(policy_rank=10, adjacent_friendly=3))


def test_no_fire_rank_too_low():
    # policy_rank must be > 3
    assert not triggered(make_facts(policy_rank=3, adjacent_friendly=2))


def test_no_fire_not_enough_friendlies():
    assert not triggered(make_facts(policy_rank=5, adjacent_friendly=1))


def test_stub_default_does_not_fire():
    assert not triggered(make_facts())

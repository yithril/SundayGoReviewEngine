from __future__ import annotations

from game.constants.thresholds import POLICY_RANK_THRESHOLD
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "policy_mismatch" for s in emit_triggers(facts))


def test_fires_above_threshold():
    assert triggered(make_facts(policy_rank=POLICY_RANK_THRESHOLD + 1))


def test_no_fire_at_threshold():
    assert not triggered(make_facts(policy_rank=POLICY_RANK_THRESHOLD))


def test_no_fire_below_threshold():
    assert not triggered(make_facts(policy_rank=POLICY_RANK_THRESHOLD - 1))


def test_no_fire_at_zero():
    assert not triggered(make_facts(policy_rank=0))

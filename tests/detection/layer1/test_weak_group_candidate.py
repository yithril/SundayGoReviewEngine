from __future__ import annotations

from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "weak_group_candidate" for s in emit_triggers(facts))


def test_fires_with_two_liberties_no_capture():
    assert triggered(make_facts(self_liberties=2, stones_captured=0))


def test_fires_with_one_liberty_no_capture():
    assert triggered(make_facts(self_liberties=1, stones_captured=0))


def test_no_fire_with_three_liberties():
    assert not triggered(make_facts(self_liberties=3, stones_captured=0))


def test_no_fire_when_captured_stones():
    # If we just captured stones the self_liberties count is unreliable;
    # the capture trigger is more appropriate
    assert not triggered(make_facts(self_liberties=1, stones_captured=1))


def test_no_fire_zero_liberties():
    # Zero liberties means the group was captured — not a candidate
    assert not triggered(make_facts(self_liberties=0, stones_captured=0))


def test_stub_default_does_not_fire():
    assert not triggered(make_facts())

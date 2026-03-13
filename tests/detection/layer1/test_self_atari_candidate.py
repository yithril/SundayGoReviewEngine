from __future__ import annotations

from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "self_atari_candidate" for s in emit_triggers(facts))


def test_fires_when_self_has_one_liberty():
    assert triggered(make_facts(self_liberties=1))


def test_no_fire_with_two_liberties():
    assert not triggered(make_facts(self_liberties=2))


def test_no_fire_with_zero_liberties():
    assert not triggered(make_facts(self_liberties=0))


def test_stub_default_does_not_fire():
    assert not triggered(make_facts())

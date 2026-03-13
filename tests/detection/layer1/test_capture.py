from __future__ import annotations

from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "capture" for s in emit_triggers(facts))


def test_fires_when_stones_captured():
    assert triggered(make_facts(stones_captured=1))


def test_fires_for_multiple_captures():
    assert triggered(make_facts(stones_captured=5))


def test_no_fire_when_no_capture():
    assert not triggered(make_facts(stones_captured=0))


def test_stub_default_does_not_fire():
    # Board state is stubbed to 0 — no spurious fires
    assert not triggered(make_facts())

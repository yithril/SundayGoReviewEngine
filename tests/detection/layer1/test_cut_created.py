from __future__ import annotations

from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "cut_created" for s in emit_triggers(facts))


def test_fires_when_cut():
    assert triggered(make_facts(cut_groups=True))


def test_no_fire_when_not_cut():
    assert not triggered(make_facts(cut_groups=False))


def test_stub_default_does_not_fire():
    assert not triggered(make_facts())

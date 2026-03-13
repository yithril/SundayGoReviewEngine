from __future__ import annotations

from game.constants.thresholds import WINRATE_SWING_THRESHOLD
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "local_fight" for s in emit_triggers(facts))


def test_fires_with_adjacent_enemies_and_winrate_swing():
    assert triggered(make_facts(
        adjacent_enemy=2,
        winrate_delta=WINRATE_SWING_THRESHOLD + 0.01,
    ))


def test_fires_with_negative_winrate_swing():
    assert triggered(make_facts(
        adjacent_enemy=2,
        winrate_delta=-(WINRATE_SWING_THRESHOLD + 0.01),
    ))


def test_no_fire_too_few_enemies():
    assert not triggered(make_facts(
        adjacent_enemy=1,
        winrate_delta=WINRATE_SWING_THRESHOLD + 0.01,
    ))


def test_no_fire_winrate_swing_too_small():
    assert not triggered(make_facts(
        adjacent_enemy=2,
        winrate_delta=WINRATE_SWING_THRESHOLD,
    ))


def test_stub_default_does_not_fire():
    assert not triggered(make_facts())

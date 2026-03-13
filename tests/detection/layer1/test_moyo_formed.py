from __future__ import annotations

from game.constants.phases import GamePhase
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(
        s.trigger_type == "moyo_formation"
        for s in emit_triggers(facts)
    )


def test_fires_when_all_rule_inputs_match():
    assert triggered(
        make_facts(
            dmoyo=3,
            own_here=0.30,
            adjacent_friendly=1,
            adjacent_enemy=0,
            move_sector_9="right",
        )
    )


def test_no_fire_when_dmoyo_too_large():
    assert not triggered(
        make_facts(
            dmoyo=4,
            own_here=0.90,
            adjacent_friendly=2,
            adjacent_enemy=0,
            move_sector_9="center",
        )
    )


def test_no_fire_when_own_here_too_low():
    assert not triggered(
        make_facts(
            dmoyo=2,
            own_here=0.29,
            adjacent_friendly=1,
            adjacent_enemy=0,
            move_sector_9="top",
        )
    )


def test_no_fire_when_adjacent_enemy_present():
    assert not triggered(
        make_facts(
            dmoyo=1,
            own_here=0.80,
            adjacent_friendly=2,
            adjacent_enemy=1,
            move_sector_9="left",
        )
    )


def test_no_fire_in_corner_sector():
    assert not triggered(
        make_facts(
            dmoyo=0,
            own_here=0.90,
            adjacent_friendly=3,
            adjacent_enemy=0,
            move_sector_9="lower_right",
        )
    )


def test_stub_default_does_not_fire():
    assert not triggered(make_facts())


def test_no_fire_in_disallowed_phase():
    assert not triggered(
        make_facts(
            dmoyo=0,
            own_here=0.90,
            adjacent_friendly=3,
            adjacent_enemy=0,
            move_sector_9="top",
            game_phase=GamePhase.LATE_ENDGAME,
        )
    )

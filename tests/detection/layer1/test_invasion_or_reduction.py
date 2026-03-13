from __future__ import annotations

from game.constants.phases import GamePhase
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def invasion_triggered(facts):
    return any(s.trigger_type == "invasion" for s in emit_triggers(facts))


def reduction_triggered(facts):
    return any(s.trigger_type == "reduction" for s in emit_triggers(facts))


def test_invasion_fires_when_dmoyo_own_here_and_side_match():
    assert invasion_triggered(make_facts(dmoyo=10, own_here=0.20, move_sector_9="top"))


def test_invasion_fires_when_center_move_matches():
    assert invasion_triggered(make_facts(dmoyo=12, own_here=0.05, move_sector_9="center"))


def test_invasion_does_not_fire_when_dmoyo_in_reduction_band():
    assert not invasion_triggered(make_facts(dmoyo=9, own_here=0.10, move_sector_9="left"))


def test_reduction_fires_in_middle_dmoyo_band():
    assert reduction_triggered(make_facts(dmoyo=7, own_here=0.30, move_sector_9="right"))


def test_reduction_does_not_fire_at_invasion_threshold():
    assert not reduction_triggered(make_facts(dmoyo=10, own_here=0.10, move_sector_9="left"))


def test_reduction_does_not_fire_in_corner_sector():
    assert not reduction_triggered(make_facts(dmoyo=6, own_here=0.10, move_sector_9="upper_left"))


def test_reduction_and_invasion_are_separate():
    facts = make_facts(dmoyo=7, own_here=0.10, move_sector_9="bottom")
    assert reduction_triggered(facts)
    assert not invasion_triggered(facts)


def test_stub_default_does_not_fire_either():
    facts = make_facts()
    assert not invasion_triggered(facts)
    assert not reduction_triggered(facts)


def test_invasion_does_not_fire_in_disallowed_phase():
    assert not invasion_triggered(
        make_facts(
            dmoyo=12,
            own_here=0.05,
            move_sector_9="center",
            game_phase=GamePhase.OPENING_1,
        )
    )


def test_reduction_does_not_fire_in_disallowed_phase():
    assert not reduction_triggered(
        make_facts(
            dmoyo=7,
            own_here=0.10,
            move_sector_9="left",
            game_phase=GamePhase.EARLY_ENDGAME,
        )
    )

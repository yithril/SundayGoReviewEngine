from __future__ import annotations

from game.constants.phases import GamePhase
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "good_direction_of_play" for s in emit_triggers(facts))


def test_fires_on_preferred_zone():
    assert triggered(
        make_facts(
            move_sector_9="upper_left",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.60,
        )
    )


def test_fires_on_adjacent_preferred_zone():
    assert triggered(
        make_facts(
            move_sector_9="top",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.60,
        )
    )


def test_no_fire_on_opposite_zone():
    assert not triggered(
        make_facts(
            move_sector_9="lower_right",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.60,
        )
    )


def test_no_fire_in_disallowed_phase():
    assert not triggered(
        make_facts(
            move_sector_9="upper_left",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.80,
            game_phase=GamePhase.OPENING_1,
        )
    )


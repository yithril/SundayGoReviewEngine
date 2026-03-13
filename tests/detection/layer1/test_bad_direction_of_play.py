from __future__ import annotations

from game.constants.phases import GamePhase
from detection.layer1.triggers import emit_triggers
from tests.detection.layer1.conftest import make_facts


def triggered(facts):
    return any(s.trigger_type == "bad_direction_of_play" for s in emit_triggers(facts))


def test_fires_on_strict_opposite_zone():
    assert triggered(
        make_facts(
            move_sector_9="lower_right",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.60,
        )
    )


def test_fires_on_adjacent_opposite_zone():
    assert triggered(
        make_facts(
            move_sector_9="right",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.55,
        )
    )


def test_no_fire_on_non_opposite_zone():
    assert not triggered(
        make_facts(
            move_sector_9="top",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.60,
        )
    )


def test_no_fire_when_top3_prior_sum_is_too_low():
    assert not triggered(
        make_facts(
            move_sector_9="lower_right",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.10,
        )
    )


def test_no_fire_in_disallowed_phase():
    assert not triggered(
        make_facts(
            move_sector_9="lower_right",
            preferred_move_sector_9="upper_left",
            preferred_top3_prior_sum=0.60,
            game_phase=GamePhase.LATE_ENDGAME,
        )
    )


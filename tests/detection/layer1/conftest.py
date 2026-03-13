from __future__ import annotations

"""
tests/detection/layer1/conftest.py
-----------------------------------
Shared fixtures and factory helpers for Layer 1 trigger tests.

make_facts(**overrides) returns a safe all-zero/False MoveFacts so each
test only needs to set the fields it cares about.
"""

import pytest

from game.constants.phases import GamePhase
from detection.types import MoveFacts


def make_facts(**overrides) -> MoveFacts:
    """Return a MoveFacts with safe defaults; override any field by name."""
    defaults = dict(
        move_index=10,
        move="D4",
        player_color="B",
        game_phase=GamePhase.EARLY_MIDDLE,
        score_delta=0.0,
        winrate_delta=0.0,
        policy_rank=0,
        policy_prob=0.18,
        best_pv_length=0,
        preferred_top3_prior_sum=0.0,
        entered_influence=False,
        moyo_cell_count=0,
        own_here=0.5,
        dmoyo=0,
        distance_to_prev=0.0,
        move_sector_9="center",
        preferred_move_sector_9="center",
        stones_captured=0,
        self_liberties=0,
        enemy_liberties_nearby=0,
        adjacent_friendly=0,
        adjacent_enemy=0,
        connected_groups=False,
        cut_groups=False,
        nearby_friendly=0,
        played_group_id=0,
        friendly_group_ids_adjacent_pre=(),
        enemy_group_ids_adjacent_pre=(),
        groups_created=(),
        groups_captured=(),
        groups_merged_into={},
        played_group_liberties_post=0,
        adjacent_enemy_liberties_post={},
        alive_group_liberties={},
        alive_group_zone_9={},
        captured_groups=(),
        max_captured_group_size=0,
        alive_group_ownership_mean={},
        urgent_local_existed=False,
    )
    defaults.update(overrides)
    return MoveFacts(**defaults)

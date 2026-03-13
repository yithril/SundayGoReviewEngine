from __future__ import annotations

from detection.layer1.zones import (
    classify_sector_9,
    is_opposite_or_adjacent_opposite,
    preferred_sector_topk_weighted,
)


def test_preferred_sector_top3_weighted_tie_returns_valid_sector_and_mass():
    move_infos = [
        {"move": "D16", "prior": 0.30},  # upper_left
        {"move": "Q4", "prior": 0.30},   # lower_right
        {"move": "K10", "prior": 0.10},  # center
    ]
    sector, mass = preferred_sector_topk_weighted(move_infos, board_size=19, top_k=3)
    assert sector in {"upper_left", "lower_right"}
    assert abs(mass - 0.70) < 1e-9


def test_opposite_or_adjacent_opposite_mapping_examples():
    assert is_opposite_or_adjacent_opposite("lower_right", "upper_left")
    assert is_opposite_or_adjacent_opposite("right", "upper_left")
    assert not is_opposite_or_adjacent_opposite("top", "upper_left")


def test_classify_sector_9_basics():
    assert classify_sector_9((0, 18), 19) == "upper_left"
    assert classify_sector_9((9, 9), 19) == "center"
    assert classify_sector_9((18, 0), 19) == "lower_right"


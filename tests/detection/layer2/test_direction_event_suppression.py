from __future__ import annotations

from detection.layer2.pipeline import run_layer2
from detection.types import HotspotCandidate


def _game_with_moves(total: int, move: str = "D4") -> dict:
    moves = []
    for i in range(1, total + 1):
        color = "B" if i % 2 == 1 else "W"
        moves.append([color, move])
    return {"moves": moves, "board_size": 19}


def _hotspot(center: int, trigger: str, local_fight: bool = True) -> HotspotCandidate:
    triggers = [trigger]
    if local_fight:
        triggers.append("local_fight")
    return HotspotCandidate(
        center_move_index=center,
        move_indices=[center],
        trigger_types=triggers,  # type: ignore[arg-type]
        max_winrate_delta=0.0,
        max_score_delta=0.0,
    )


def test_good_direction_suppressed_within_local_window():
    game = _game_with_moves(80, move="D4")
    hotspots = [
        _hotspot(41, "good_direction_of_play", local_fight=True),
        _hotspot(45, "good_direction_of_play", local_fight=True),
    ]
    events = run_layer2(hotspots, game, katago_responses={})
    good = [e for e in events if e.event_type == "good_direction_shift"]
    assert len(good) == 1
    assert good[0].center_move_index == 41


def test_bad_direction_suppressed_within_local_window():
    game = _game_with_moves(80, move="D4")
    hotspots = [
        _hotspot(41, "bad_direction_of_play", local_fight=True),
        _hotspot(49, "bad_direction_of_play", local_fight=True),
    ]
    events = run_layer2(hotspots, game, katago_responses={})
    bad = [e for e in events if e.event_type == "bad_direction_shift"]
    assert len(bad) == 1
    assert bad[0].center_move_index == 41


def test_direction_refires_after_zone_shift():
    game = _game_with_moves(100, move="D4")
    game["moves"][54][1] = "Q16"  # move 55 in a different zone
    hotspots = [
        _hotspot(41, "good_direction_of_play", local_fight=True),
        _hotspot(45, "good_direction_of_play", local_fight=True),  # suppressed
        _hotspot(55, "good_direction_of_play", local_fight=True),  # kept: zone changed
    ]
    events = run_layer2(hotspots, game, katago_responses={})
    good = [e for e in events if e.event_type == "good_direction_shift"]
    assert [e.center_move_index for e in good] == [41, 55]


from __future__ import annotations

from detection.layer1.board_tracker import BoardTracker
from detection.layer1.facts import collect_facts
from detection.layer1.hotspots import merge_hotspots
from detection.layer1.triggers import emit_triggers


def _capture_sequence_moves() -> list[list[str]]:
    return [
        ["B", "D4"],
        ["W", "E4"],
        ["B", "E3"],
        ["W", "pass"],
        ["B", "E5"],
        ["W", "pass"],
        ["B", "F4"],
    ]


def test_capture_payload_propagates_snapshot_to_hotspot():
    moves = _capture_sequence_moves()
    tracker = BoardTracker(board_size=9)

    snapshot = None
    for idx, (color, move) in enumerate(moves, 1):
        snapshot = tracker.step(move, color, move_index=idx)
    assert snapshot is not None
    assert snapshot.captured_group_sizes

    facts = collect_facts(
        move_index=len(moves),
        moves=moves,
        katago_responses={},
        player_color="B",
        board_size=9,
        prev_signals=[],
        prev_moyo_cell_count=0,
        snapshot=snapshot,
    )
    assert facts.max_captured_group_size == 1
    assert len(facts.captured_groups) == 1

    signals = emit_triggers(facts)
    capture = [s for s in signals if s.trigger_type == "capture"]
    assert len(capture) == 1
    assert capture[0].max_captured_group_size == 1
    assert len(capture[0].captured_groups) == 1

    hotspot = merge_hotspots(signals)[0]
    assert hotspot.max_captured_group_size == 1
    assert len(hotspot.captured_groups) == 1


def test_collect_facts_plumbs_alive_group_ownership_mean():
    moves = [["B", "D4"]]
    tracker = BoardTracker(board_size=9)
    snapshot = tracker.step("D4", "B", move_index=1)

    ownership = [0.0] * 81
    ownership[5 * 9 + 3] = 0.8  # D4 in top-row indexing for 9x9
    facts = collect_facts(
        move_index=1,
        moves=moves,
        katago_responses={1: {"ownership": ownership}},
        player_color="B",
        board_size=9,
        prev_signals=[],
        prev_moyo_cell_count=0,
        snapshot=snapshot,
    )

    assert facts.alive_group_ownership_mean
    only_mean = next(iter(facts.alive_group_ownership_mean.values()))
    assert only_mean == 0.8

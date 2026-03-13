from __future__ import annotations

from detection.layer1.board_tracker import BoardTracker


def test_creates_group_id_on_first_stone() -> None:
    tracker = BoardTracker(9)
    snapshot = tracker.step("E5", "B")

    assert snapshot.played_group_id > 0
    assert snapshot.groups_created == (snapshot.played_group_id,)
    assert snapshot.alive_group_liberties[snapshot.played_group_id] == 4


def test_merge_retires_source_groups() -> None:
    tracker = BoardTracker(9)

    left = tracker.step("D5", "B")
    right = tracker.step("F5", "B")
    merged = tracker.step("E5", "B")

    assert left.played_group_id != right.played_group_id
    assert merged.played_group_id in merged.groups_merged_into

    merged_sources = merged.groups_merged_into[merged.played_group_id]
    assert set(merged_sources) == {left.played_group_id, right.played_group_id} - {merged.played_group_id}
    retired_ids = {left.played_group_id, right.played_group_id} - {merged.played_group_id}
    for retired_id in retired_ids:
        assert retired_id not in merged.alive_group_liberties
    assert merged.played_group_id in merged.alive_group_liberties


def test_capture_marks_group_dead() -> None:
    tracker = BoardTracker(9)

    white = tracker.step("E5", "W")
    tracker.step("D5", "B")
    tracker.step("F5", "B")
    tracker.step("E6", "B")
    capture = tracker.step("E4", "B")

    assert white.played_group_id in capture.groups_captured
    assert white.played_group_id not in capture.alive_group_liberties


def test_reformation_after_capture_gets_new_id() -> None:
    tracker = BoardTracker(9)

    first = tracker.step("E5", "W")
    second = tracker.step("E6", "W")
    original_id = second.played_group_id

    tracker.step("D5", "B")
    tracker.step("F5", "B")
    tracker.step("D6", "B")
    tracker.step("F6", "B")
    tracker.step("E7", "B")
    capture = tracker.step("E4", "B")

    assert original_id in capture.groups_captured

    reform = tracker.step("E5", "W")
    assert reform.groups_created
    assert reform.played_group_id != original_id
    assert reform.played_group_id in reform.alive_group_liberties
    assert original_id not in reform.alive_group_liberties
    assert first.played_group_id == original_id


def test_liberty_tracking_stays_consistent() -> None:
    tracker = BoardTracker(9)

    first = tracker.step("D5", "B")
    join = tracker.step("E5", "B")
    pressure = tracker.step("D4", "W")

    assert first.played_group_liberties_post == first.alive_group_liberties[first.played_group_id]
    assert join.played_group_liberties_post == join.alive_group_liberties[join.played_group_id]
    assert join.alive_group_liberties[join.played_group_id] == 6

    black_group_id = join.played_group_id
    assert black_group_id in pressure.adjacent_enemy_liberties_post
    assert (
        pressure.adjacent_enemy_liberties_post[black_group_id]
        == pressure.alive_group_liberties[black_group_id]
    )

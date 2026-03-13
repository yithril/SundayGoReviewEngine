from __future__ import annotations

"""
tests/detection/layer1/test_board_tracker.py
---------------------------------------------
Unit tests for BoardTracker.step() using hand-crafted positions on a 9x9 board.

No KataGo, no SGF files — runs instantly.

How positions are built
-----------------------
BoardTracker.step() is the only public way to place stones.  sgfmill's
board.play() accepts any color at any intersection, so we drive setup moves
(any color, any order) before the one trigger move we actually care about.

Coordinate system
-----------------
BoardTracker uses KataGo notation (A1 = bottom-left corner, columns A-H J-T,
rows 1-9 from bottom).  On a 9x9:
  A1=bottom-left, J9=top-right.
  E5 is the centre.

Test layout
-----------
Each test names the setup stones, the trigger move, and the asserted snapshot
field.  Positive tests verify an event IS detected; negative tests verify it
is NOT (falsifiability).
"""

import pytest

from detection.layer1.board_tracker import BoardTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _setup(size: int, *moves: tuple[str, str]) -> BoardTracker:
    """Return a BoardTracker with the given setup moves already played.

    Each entry is (move_str, color) e.g. ("E5", "W").
    """
    tracker = BoardTracker(size)
    for move_str, color in moves:
        tracker.step(move_str, color)
    return tracker


# ---------------------------------------------------------------------------
# Atari detection
# ---------------------------------------------------------------------------

class TestAtariCreated:
    """enemy_liberties_nearby == 1 when a move reduces an adjacent enemy group
    to exactly one liberty."""

    def test_single_stone_reduces_to_one_liberty(self):
        # White at E5 (4 liberties: D5, F5, E4, E6)
        # Black plays D5 and F5, leaving E5 with 2 liberties (E4, E6)
        # Black plays E6 → White E5 has exactly 1 liberty left (E4)
        tracker = _setup(9, ("E5", "W"), ("D5", "B"), ("F5", "B"))
        snapshot = tracker.step("E6", "B")
        assert snapshot.enemy_liberties_nearby == 1

    def test_multi_stone_group_reduces_to_one_liberty(self):
        # White chain: E5-E6 (shared liberties: D5, F5, E4, D6, F6, E7)
        # Black plays D5, F5, E4, D6, F6 (5 of the 6 group liberties)
        # White chain now has 1 liberty: E7
        # Black plays E7 → captures, so let's use a different final move
        # Instead: remove E4 from setup, leave E4 and E7 as 2 liberties, then take E4
        # White chain E5-E6 liberties after D5,F5,D6,F6 are played: E4 and E7
        # Black plays E4 → chain has 1 liberty (E7)
        tracker = _setup(9,
            ("E5", "W"), ("E6", "W"),   # White chain
            ("D5", "B"), ("F5", "B"),   # attack E5 sides
            ("D6", "B"), ("F6", "B"),   # attack E6 sides
        )
        snapshot = tracker.step("E4", "B")  # E5's last non-E7 liberty
        assert snapshot.enemy_liberties_nearby == 1

    def test_no_atari_when_two_liberties_remain(self):
        # White at E5; Black occupies only D5 (E5 still has F5, E4, E6 = 3 liberties)
        # Black plays somewhere far away → enemy_liberties_nearby is not 1
        tracker = _setup(9, ("E5", "W"), ("D5", "B"))
        snapshot = tracker.step("A1", "B")
        assert snapshot.enemy_liberties_nearby != 1

    def test_no_enemy_adjacent_returns_zero(self):
        # Black plays on an empty board with no enemy stones anywhere
        tracker = BoardTracker(9)
        snapshot = tracker.step("E5", "B")
        assert snapshot.enemy_liberties_nearby == 0


# ---------------------------------------------------------------------------
# Capture detection
# ---------------------------------------------------------------------------

class TestCapture:
    """stones_captured > 0 when a move removes enemy stones."""

    def test_single_stone_captured(self):
        # White at E5 surrounded on 3 sides; Black plays the last liberty
        tracker = _setup(9,
            ("E5", "W"),
            ("D5", "B"), ("F5", "B"), ("E6", "B"),
        )
        snapshot = tracker.step("E4", "B")  # last liberty of White E5
        assert snapshot.stones_captured == 1

    def test_two_stone_chain_captured(self):
        # White chain E5-F5; surrounded except E4 and G5
        # Add F4 so E4 is the final liberty to fill.
        tracker = _setup(9,
            ("E5", "W"), ("F5", "W"),
            ("D5", "B"), ("E6", "B"), ("F6", "B"), ("G5", "B"), ("F4", "B"),
        )
        snapshot = tracker.step("E4", "B")  # last liberty
        assert snapshot.stones_captured == 2

    def test_no_capture_when_liberties_remain(self):
        # White at E5 with 2 liberties; Black plays one of them (atari)
        tracker = _setup(9, ("E5", "W"), ("D5", "B"), ("F5", "B"), ("E6", "B"))
        snapshot = tracker.step("E6", "B")
        # E6 already played in setup — let's play E3 instead (not adjacent)
        # Actually redo: White E5 with liberties D5... wait let's use a fresh position
        # White at E5, Black plays D5, F5 (E5 has E4 and E6 left)
        tracker2 = _setup(9, ("E5", "W"), ("D5", "B"), ("F5", "B"))
        snapshot2 = tracker2.step("E6", "B")  # atari, not capture
        assert snapshot2.stones_captured == 0


# ---------------------------------------------------------------------------
# Cut detection
# ---------------------------------------------------------------------------

class TestCutCreated:
    """cut_groups == True when the move is adjacent to two or more separate
    enemy groups."""

    def test_simple_cut_between_two_groups(self):
        # White at D5 and White at F5 (two separate groups, gap at E5)
        # Black plays E5 → adjacent to D5 group and F5 group → cut
        tracker = _setup(9, ("D5", "W"), ("F5", "W"))
        snapshot = tracker.step("E5", "B")
        assert snapshot.cut_groups is True

    def test_no_cut_when_one_enemy_group_adjacent(self):
        # White chain D5-E5 (one connected group); Black plays F5
        # F5 is only adjacent to E5 (one group), not a cut
        tracker = _setup(9, ("D5", "W"), ("E5", "W"))
        snapshot = tracker.step("F5", "B")
        assert snapshot.cut_groups is False

    def test_no_cut_when_no_enemy_adjacent(self):
        tracker = BoardTracker(9)
        snapshot = tracker.step("E5", "B")
        assert snapshot.cut_groups is False


# ---------------------------------------------------------------------------
# Connection attempt detection
# ---------------------------------------------------------------------------

class TestConnectionAttempt:
    """connected_groups == True when the move joins two or more separate
    friendly groups."""

    def test_connects_two_separate_groups(self):
        # Black at D5 and Black at F5 (separate); Black plays E5 → joins them
        tracker = _setup(9, ("D5", "B"), ("F5", "B"))
        snapshot = tracker.step("E5", "B")
        assert snapshot.connected_groups is True

    def test_no_connection_when_no_friendly_groups(self):
        tracker = BoardTracker(9)
        snapshot = tracker.step("E5", "B")
        assert snapshot.connected_groups is False

    def test_no_connection_when_already_one_group(self):
        # Black chain D5-E5; Black plays F5 → extends the chain but does not
        # join two previously separate groups
        tracker = _setup(9, ("D5", "B"), ("E5", "B"))
        snapshot = tracker.step("F5", "B")
        assert snapshot.connected_groups is False


# ---------------------------------------------------------------------------
# Self-atari detection
# ---------------------------------------------------------------------------

class TestSelfAtari:
    """self_liberties == 1 when the played move leaves the moved group with
    exactly one liberty."""

    def test_plays_into_near_surrounded_space(self):
        # White walls around B2: White at C2, B3, A2
        # Board edge is at col A (col=0) so B2 has neighbors: A2, C2, B1, B3
        # A2 White, C2 White, B3 White → B2 would have only B1 left (board row 1)
        tracker = _setup(9, ("C2", "W"), ("B3", "W"), ("A2", "W"))
        snapshot = tracker.step("B2", "B")
        assert snapshot.self_liberties == 1

    def test_normal_move_not_self_atari(self):
        # Black plays E5 on empty board → 4 liberties
        tracker = BoardTracker(9)
        snapshot = tracker.step("E5", "B")
        assert snapshot.self_liberties == 4

    def test_corner_play_has_two_liberties(self):
        # Black plays A1 (corner) on empty board → 2 liberties (A2, B1)
        tracker = BoardTracker(9)
        snapshot = tracker.step("A1", "B")
        assert snapshot.self_liberties == 2


# ---------------------------------------------------------------------------
# nearby_friendly detection
# ---------------------------------------------------------------------------

class TestNearbyFriendly:
    """nearby_friendly counts same-color stones within Chebyshev distance 2
    of the played point, not counting the played point itself, pre-play."""

    def test_no_friendly_stones_on_empty_board(self):
        tracker = BoardTracker(9)
        snapshot = tracker.step("E5", "B")
        assert snapshot.nearby_friendly == 0

    def test_adjacent_stone_counts(self):
        # Black at D5 (Chebyshev distance 1 from E5)
        tracker = _setup(9, ("D5", "B"))
        snapshot = tracker.step("E5", "B")
        assert snapshot.nearby_friendly >= 1

    def test_distance_two_stone_counts(self):
        # Black at C5 (Chebyshev distance 2 from E5) — should count
        tracker = _setup(9, ("C5", "B"))
        snapshot = tracker.step("E5", "B")
        assert snapshot.nearby_friendly == 1

    def test_distance_three_stone_does_not_count(self):
        # Black at B5 (Chebyshev distance 3 from E5) — outside radius
        tracker = _setup(9, ("B5", "B"))
        snapshot = tracker.step("E5", "B")
        assert snapshot.nearby_friendly == 0

    def test_only_same_color_counted(self):
        # White at D5 (distance 1 from E5) — enemy stone, should NOT count
        tracker = _setup(9, ("D5", "W"))
        snapshot = tracker.step("E5", "B")
        assert snapshot.nearby_friendly == 0

    def test_multiple_stones_within_radius(self):
        # Black at D5 (dist 1), E7 (dist 2), C5 (dist 2) — all within radius
        # Black at B5 (dist 3) — outside
        tracker = _setup(9, ("D5", "B"), ("E7", "B"), ("C5", "B"), ("B5", "B"))
        snapshot = tracker.step("E5", "B")
        assert snapshot.nearby_friendly == 3

    def test_invasion_lone_stone_in_enemy_territory(self):
        # Scenario matching the invasion_or_reduction trigger:
        # No Black stones nearby; Black invades into White territory
        tracker = _setup(9,
            ("B2", "W"), ("C2", "W"), ("B3", "W"), ("C3", "W"),
        )
        snapshot = tracker.step("H8", "B")  # far from all setup stones
        assert snapshot.nearby_friendly == 0

from __future__ import annotations

"""
tests/detection/layer1/test_opening_classifier.py
---------------------------------------------------
Unit tests for detect_opening() and classify_first_move().

SGF-based tests load files from tests/test_sgfs/ via parse_sgf() so the
expected move sequences match real game notation exactly.  Inline tests
cover patterns that have no dedicated SGF file (sanrensei, kobayashi top)
and edge cases.
"""

from pathlib import Path

from sgf.parser import parse_sgf
from detection.layer1.opening_classifier import classify_first_move, detect_opening

_SGF_DIR = Path(__file__).parent.parent.parent / "test_sgfs"


def _moves(filename: str) -> list:
    """Load moves from a test SGF file."""
    content = (_SGF_DIR / filename).read_text(encoding="utf-8")
    return parse_sgf(content)["moves"]


# ---------------------------------------------------------------------------
# Opening detection — SGF-based
# ---------------------------------------------------------------------------

def test_kobayashi_bottom():
    result = detect_opening(_moves("kobayashi_test.sgf"), 19)
    assert result is not None
    assert result.name == "kobayashi"
    assert result.orientation == "bottom"


def test_mini_chinese_bottom_right():
    result = detect_opening(_moves("mini_chinese_test.sgf"), 19)
    assert result is not None
    assert result.name == "mini_chinese"
    assert result.orientation == "bottom-right"


def test_mini_chinese_alternate_order():
    # Same pattern; verifies order of moves within the window does not matter.
    result = detect_opening(_moves("mini_chinese_alternate_order_test.sgf"), 19)
    assert result is not None
    assert result.name == "mini_chinese"
    assert result.orientation == "bottom-right"


def test_high_chinese_right():
    result = detect_opening(_moves("high_chinese_test.sgf"), 19)
    assert result is not None
    assert result.name == "high_chinese"
    assert result.orientation == "right"


def test_low_chinese_right():
    result = detect_opening(_moves("low_chinese_test.sgf"), 19)
    assert result is not None
    assert result.name == "low_chinese"
    assert result.orientation == "right"


def test_high_chinese_top():
    result = detect_opening(_moves("high_chinese_alternate.sgf"), 19)
    assert result is not None
    assert result.name == "high_chinese"
    assert result.orientation == "top"


def test_no_opening_too_few_moves():
    # test_opening_corner_moves.sgf has only 4 moves — below every check_at threshold.
    result = detect_opening(_moves("test_opening_corner_moves.sgf"), 19)
    assert result is None


# ---------------------------------------------------------------------------
# Opening detection — inline move lists (no SGF file required)
# ---------------------------------------------------------------------------

def test_sanrensei_right():
    moves = [
        ["B", "Q16"], ["W", "D4"],
        ["B", "Q10"], ["W", "D16"],
        ["B", "Q4"],
    ]
    result = detect_opening(moves, 19)
    assert result is not None
    assert result.name == "sanrensei"
    assert result.orientation == "right"


def test_sanrensei_top():
    moves = [
        ["B", "Q16"], ["W", "D4"],
        ["B", "K16"], ["W", "Q4"],
        ["B", "D16"],
    ]
    result = detect_opening(moves, 19)
    assert result is not None
    assert result.name == "sanrensei"
    assert result.orientation == "top"


def test_kobayashi_top():
    moves = [
        ["B", "Q17"], ["W", "D16"],
        ["B", "K16"], ["W", "Q4"],
        ["B", "F17"], ["W", "C6"],
        ["B", "D4"],
    ]
    result = detect_opening(moves, 19)
    assert result is not None
    assert result.name == "kobayashi"
    assert result.orientation == "top"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_no_opening_returns_none():
    # Ordinary corner moves with no matching pattern.
    moves = [
        ["B", "D4"],  ["W", "Q16"],
        ["B", "D16"], ["W", "Q4"],
        ["B", "K10"],
    ]
    result = detect_opening(moves, 19)
    assert result is None


def test_non_19x19_returns_none():
    # Opening detection is disabled for non-19x19 boards.
    moves = [
        ["B", "Q16"], ["W", "D4"],
        ["B", "Q10"], ["W", "D16"],
        ["B", "Q4"],
    ]
    result = detect_opening(moves, 13)
    assert result is None


def test_extra_white_stones_ignored():
    # Kobayashi bottom pattern holds even when White has stones in extra corners.
    # White plays D4 (required) plus Q16 and D16 (extra — should be ignored).
    moves = [
        ["B", "Q3"],  ["W", "D4"],
        ["B", "K4"],  ["W", "Q16"],
        ["B", "F3"],  ["W", "D16"],
        ["B", "C10"],            # Black's 4th move is elsewhere — not part of pattern
    ]
    result = detect_opening(moves, 19)
    assert result is not None
    assert result.name == "kobayashi"
    assert result.orientation == "bottom"


# ---------------------------------------------------------------------------
# classify_first_move
# ---------------------------------------------------------------------------

def test_first_move_corner_black():
    # B's first move in test_opening_corner_moves.sgf is pd → Q16 (corner).
    moves = _moves("test_opening_corner_moves.sgf")
    result = classify_first_move(moves, "B", 19)
    assert result is not None
    assert result.move == "Q16"
    assert result.zone == "corner"


def test_first_move_corner_white():
    # W's first move in test_opening_corner_moves.sgf is dc → D17 (corner).
    moves = _moves("test_opening_corner_moves.sgf")
    result = classify_first_move(moves, "W", 19)
    assert result is not None
    assert result.zone == "corner"


def test_first_move_center():
    moves = [["B", "K10"]]  # tengen
    result = classify_first_move(moves, "B", 19)
    assert result is not None
    assert result.zone == "center"


def test_first_move_side():
    moves = [["B", "K4"]]  # bottom side, not near a corner column
    result = classify_first_move(moves, "B", 19)
    assert result is not None
    assert result.zone == "side"


def test_first_move_no_moves_returns_none():
    result = classify_first_move([], "B", 19)
    assert result is None


def test_first_move_white_no_second_move_returns_none():
    # Only one move in the game (Black's) — White has no first move.
    result = classify_first_move([["B", "D4"]], "W", 19)
    assert result is None

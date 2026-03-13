from __future__ import annotations

"""
detection/layer1/opening_classifier.py
---------------------------------------
One-shot opening recognition for 19×19 games.

Two public functions:
  detect_opening()      — checks at move 5 (Chinese / sanrensei) or move 7
                          (Kobayashi / Mini Chinese) whether a known pattern is
                          present.  Returns OpeningInfo or None.
  classify_first_move() — finds the reviewed player's first stone and labels
                          its board zone as "corner", "side", or "center".

No KataGo data or board state is required; only game["moves"] is read.
Both functions are O(1) in the number of moves (constant-size coordinate sets).
"""

from typing import Optional

from detection.types import Color, FirstMoveInfo, OpeningInfo
from sgf.parser import gtp_to_col_row


# ---------------------------------------------------------------------------
# Opening lookup table
# ---------------------------------------------------------------------------
# Each entry describes one named opening.  "check_at" is the number of moves
# that must have been played before the check runs (5 or 7).
# Each orientation is a pair of frozensets: required Black stones and required
# White stones.  Extra stones on the board are ignored — detection uses ⊆.
#
# Coordinates are in standard Go notation (A-T skipping I, rows 1-19 from
# bottom).  Derived from sgf_examples/standard_openings/.
#
# Orientations checked:
#   sanrensei / high_chinese / low_chinese : right, top
#   kobayashi / mini_chinese              : bottom, top

_O = OpeningInfo  # local alias to keep the table compact


class _Pattern:
    __slots__ = ("name", "check_at", "orientations")

    def __init__(
        self,
        name: str,
        check_at: int,
        orientations: list[tuple[str, frozenset[str], frozenset[str]]],
    ) -> None:
        self.name = name
        self.check_at = check_at
        # Each orientation: (label, required_black, required_white)
        self.orientations = orientations


_PATTERNS: list[_Pattern] = [
    # ── move-5 patterns (no White stone required) ───────────────────────────
    _Pattern("sanrensei", 5, [
        ("right", frozenset({"Q16", "Q10", "Q4"}),     frozenset()),
        ("top",   frozenset({"Q16", "K16", "D16"}),    frozenset()),
    ]),
    _Pattern("high_chinese", 5, [
        ("right", frozenset({"Q16", "Q9", "Q3"}),      frozenset()),
        ("top",   frozenset({"Q16", "J16", "C16"}),    frozenset()),
    ]),
    _Pattern("low_chinese", 5, [
        ("right", frozenset({"Q16", "R9", "Q3"}),      frozenset()),
        ("top",   frozenset({"Q16", "J17", "C16"}),    frozenset()),
    ]),
    # ── move-7 patterns (White star-point stone required) ───────────────────
    _Pattern("kobayashi", 7, [
        ("bottom", frozenset({"Q3",  "K4",  "F3"}),    frozenset({"D4"})),
        ("top",    frozenset({"Q17", "K16", "F17"}),   frozenset({"D16"})),
    ]),
    _Pattern("mini_chinese", 7, [
        ("bottom-right", frozenset({"Q16", "R4", "F3", "L3"}), frozenset({"D4"})),
        ("top-right",    frozenset({"R16", "F17", "L17"}),     frozenset({"D16"})),
    ]),
]

# ---------------------------------------------------------------------------
# Opening detection
# ---------------------------------------------------------------------------


def detect_opening(
    moves: list[list[str]],
    board_size: int = 19,
) -> Optional[OpeningInfo]:
    """Return the first recognised opening pattern, or None.

    Checks move-5 patterns first, then move-7 patterns.  Each pattern is
    recognised when its required Black *and* White stones are a subset of
    the stones played within the first check_at moves.

    Only runs on 19×19 boards; returns None for any other size.
    """
    if board_size != 19:
        return None

    total = len(moves)

    for pattern in _PATTERNS:
        if total < pattern.check_at:
            continue

        window = moves[: pattern.check_at]
        black_played: set[str] = set()
        white_played: set[str] = set()
        for entry in window:
            color: str = entry[0]
            move_str: str = entry[1] if len(entry) > 1 else "pass"
            if move_str.upper() == "PASS":
                continue
            if color == "B":
                black_played.add(move_str.upper())
            else:
                white_played.add(move_str.upper())

        for label, req_black, req_white in pattern.orientations:
            # Normalise required sets to uppercase for safe comparison
            req_b = frozenset(s.upper() for s in req_black)
            req_w = frozenset(s.upper() for s in req_white)
            if req_b <= black_played and req_w <= white_played:
                return OpeningInfo(name=pattern.name, orientation=label)

    return None


# ---------------------------------------------------------------------------
# First-move zone classification
# ---------------------------------------------------------------------------

# On a 19×19 board, "corner" means both col and row are within 6 lines of
# a corner edge (0-based indices 0–5 or 13–18).  "side" means exactly one
# axis is in that range.  Everything else is "center".
_CORNER_THRESHOLD = 6  # 0-based; lines 1–6 or 14–19 in 1-based notation


def classify_first_move(
    moves: list[list[str]],
    player_color: Color,
    board_size: int = 19,
) -> Optional[FirstMoveInfo]:
    """Return zone info for the reviewed player's first move.

    The first Black move is move index 0 in the list; the first White move is
    index 1.  Returns None if the player has no moves or the move is a pass.
    """
    start_index = 0 if player_color == "B" else 1
    if start_index >= len(moves):
        return None

    entry = moves[start_index]
    move_str: str = entry[1] if len(entry) > 1 else "pass"
    if move_str.upper() == "PASS":
        return None

    coord = gtp_to_col_row(move_str)
    if coord is None:
        return None

    col, row = coord
    n = board_size
    threshold = _CORNER_THRESHOLD

    col_near_edge = col <= threshold - 1 or col >= n - threshold
    row_near_edge = row <= threshold - 1 or row >= n - threshold

    if col_near_edge and row_near_edge:
        zone = "corner"
    elif col_near_edge or row_near_edge:
        zone = "side"
    else:
        zone = "center"

    return FirstMoveInfo(move=move_str.upper(), zone=zone)  # type: ignore[arg-type]

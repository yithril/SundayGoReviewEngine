from __future__ import annotations

from enum import Enum


class GamePhase(str, Enum):
    OPENING_1     = "opening_1"      # moves   1–15   Corners and first approaches
    OPENING_2     = "opening_2"      # moves  16–30   Frameworks forming
    EARLY_MIDDLE  = "early_middle"   # moves  31–60   First real fights
    MID_MIDDLE    = "mid_middle"     # moves  61–100  Big battles
    LATE_MIDDLE   = "late_middle"    # moves 101–140  Territory becoming defined
    EARLY_ENDGAME = "early_endgame"  # moves 141–180  Large yose
    LATE_ENDGAME  = "late_endgame"   # moves 181+     Small yose


# Inclusive start, inclusive end (None = unbounded upper limit).
PHASE_BOUNDARIES: list[tuple[int, int | None, GamePhase]] = [
    (1,   15,  GamePhase.OPENING_1),
    (16,  30,  GamePhase.OPENING_2),
    (31,  60,  GamePhase.EARLY_MIDDLE),
    (61,  100, GamePhase.MID_MIDDLE),
    (101, 140, GamePhase.LATE_MIDDLE),
    (141, 180, GamePhase.EARLY_ENDGAME),
    (181, None, GamePhase.LATE_ENDGAME),
]


def get_phase(move_index: int) -> GamePhase:
    """Return the GamePhase for a 1-based move index."""
    for start, end, phase in PHASE_BOUNDARIES:
        if move_index >= start and (end is None or move_index <= end):
            return phase
    return GamePhase.LATE_ENDGAME

from __future__ import annotations

from enum import Enum


class RankBand(str, Enum):
    """Rank bands used throughout the review pipeline.

    Formalises the bare string literals scattered across review/builder.py.
    The string values are kept identical to the existing strings so that
    existing code can adopt this enum incrementally without a flag day.
    """
    NOVICE       = "novice"
    BEGINNER     = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED     = "advanced"
    DAN          = "dan"

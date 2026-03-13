from __future__ import annotations

"""
detection/layer3/pipeline.py
-----------------------------
Public API for Layer 3.  Receives Layer 2's GameEvents and produces the
complete NarrativeOutput consumed by review/builder.py.

v1: all formatters are stubs returning placeholder content.
"""

from detection.layer3.formatters import (
    format_did_well,
    format_highlights,
    format_needs_improvement,
    format_story,
)
from detection.skills.evaluator import evaluate_skills
from typing import Optional

from detection.types import FirstMoveInfo, GameEvent, NarrativeOutput, OpeningInfo


def run_layer3(
    events: list[GameEvent],
    game: dict,
    move_quality: list[str],
    rank_band: str,
    opening_info: Optional[OpeningInfo] = None,
    first_move_info: Optional[FirstMoveInfo] = None,
) -> NarrativeOutput:
    """Produce the full narrative output from classified GameEvents.

    Parameters
    ----------
    events          : output of run_layer2()
    game            : parsed SGF dict
    move_quality    : per-move quality labels from review/builder.py
    rank_band       : e.g. "beginner" — used to calibrate explanation detail
    opening_info    : recognised opening pattern from the opening classifier,
                      or None if no standard opening was detected
    first_move_info : reviewed player's first-move zone from the opening
                      classifier, or None if not applicable

    Returns
    -------
    NarrativeOutput with all fields populated.
    """
    return NarrativeOutput(
        story=format_story(events, game, move_quality, rank_band),
        skills_used=evaluate_skills(events, move_quality, rank_band),
        did_well=format_did_well(events, move_quality),
        needs_improvement=format_needs_improvement(events, move_quality),
        match_highlights=format_highlights(events, move_quality),
        opening_info=opening_info,
        first_move_info=first_move_info,
    )

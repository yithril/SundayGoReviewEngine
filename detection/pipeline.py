from __future__ import annotations

"""
detection/pipeline.py
----------------------
Top-level composition of the three detection layers.

This is the only entry point that review/builder.py needs to import.
All three layers are composed here; callers never import from individual
layer sub-packages.

Data flow:
  run_layer1()  →  list[HotspotCandidate]
  run_layer2()  →  list[GameEvent]
  run_layer3()  →  NarrativeOutput
"""

from detection.layer1.opening_classifier import classify_first_move, detect_opening
from detection.layer1.pipeline import run_layer1
from detection.layer2.pipeline import run_layer2
from detection.layer3.pipeline import run_layer3
from detection.types import Color, NarrativeOutput


def run_detection(
    game: dict,
    katago_responses: dict[int, dict],
    player_color: Color,
    rank_band: str,
    move_quality: list[str],
) -> NarrativeOutput:
    """Run the full detection pipeline and return the narrative output.

    Parameters
    ----------
    game             : parsed SGF dict from sgf.parser.parse_sgf()
    katago_responses : turn_number → KataGo response dict
    player_color     : "B" or "W" (the reviewed player)
    rank_band        : e.g. "beginner" — used by Layer 3 for calibration
    move_quality     : per-move quality labels from review/builder.py
                       (built before calling this function)

    Returns
    -------
    NarrativeOutput with story, skills_used, did_well, needs_improvement,
    match_highlights, opening_info, and first_move_info all populated.
    """
    moves      = game.get("moves", [])
    board_size = game.get("board_size", 19)

    hotspots       = run_layer1(game, katago_responses, player_color)
    opening_info   = detect_opening(moves, board_size)
    first_move     = classify_first_move(moves, player_color, board_size)
    events         = run_layer2(
        hotspots,
        game,
        katago_responses,
        reviewed_player_color=player_color,
    )
    return run_layer3(
        events,
        game,
        move_quality,
        rank_band,
        opening_info=opening_info,
        first_move_info=first_move,
    )

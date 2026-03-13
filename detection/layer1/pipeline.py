from __future__ import annotations

"""
detection/layer1/pipeline.py
-----------------------------
Public API for Layer 1.  All callers outside this sub-package import from
here; internal modules (facts, triggers, hotspots) are private.

Entry point: run_layer1()
"""

from detection.layer1.board_tracker import BoardTracker
from detection.layer1.facts import collect_facts
from detection.layer1.hotspots import merge_hotspots
from detection.layer1.triggers import emit_triggers
from detection.types import Color, HotspotCandidate, TriggerSignal


def run_layer1(
    game: dict,
    katago_responses: dict[int, dict],
    player_color: Color,
) -> list[HotspotCandidate]:
    """Run the full Layer 1 pipeline for a game.

    Steps
    -----
    1. Create a single BoardTracker for the game.
    2. For each move in order:
       a. Call tracker.step() — plays the move exactly once, returns BoardSnapshot
       b. Call collect_facts() with the snapshot — reads board state from snapshot
       c. Call emit_triggers() on the resulting MoveFacts
    3. merge_hotspots on the full accumulated signal list.

    O(1) per-move guarantee
    -----------------------
    BoardTracker.step() is the ONLY place board.play() is called.  It is
    called exactly once per move in move-index order.  collect_facts() only
    reads the immutable BoardSnapshot; it never touches the Board object.
    This ensures Layer 1 is O(N) total (one sgfmill play per move), not O(N²).

    Parameters
    ----------
    game             : parsed SGF dict from sgf.parser.parse_sgf()
    katago_responses : turn_number → KataGo response dict
    player_color     : "B" or "W" (the reviewed player)

    Returns
    -------
    list[HotspotCandidate] sorted by center_move_index, ready for Layer 2.
    """
    moves      = game["moves"]
    board_size = game.get("board_size", 19)
    total_moves = len(moves)

    tracker = BoardTracker(board_size)

    all_signals: list[TriggerSignal] = []
    prev_moyo_cell_count: int = 0

    for move_index in range(1, total_moves + 1):
        move_entry = moves[move_index - 1]
        move_color: str = move_entry[0]
        move_str: str = move_entry[1] if len(move_entry) > 1 else "pass"

        # Step the board — exactly once per move
        snapshot = tracker.step(move_str, move_color, move_index=move_index)

        facts = collect_facts(
            move_index=move_index,
            moves=moves,
            katago_responses=katago_responses,
            player_color=player_color,
            board_size=board_size,
            prev_signals=all_signals,
            prev_moyo_cell_count=prev_moyo_cell_count,
            snapshot=snapshot,
        )

        new_signals = emit_triggers(facts)
        all_signals.extend(new_signals)
        prev_moyo_cell_count = facts.moyo_cell_count

    return merge_hotspots(all_signals)

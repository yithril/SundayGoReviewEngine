from __future__ import annotations

"""
tests/integration/phase2/test_cuts.py
----------------------------------------
Integration tests for the `cut_created` Layer 1 trigger.

What cut_created means
----------------------
A move is adjacent to two or more distinct enemy groups — a cheap but
effective proxy for a cutting move.  Detected via:

  BoardSnapshot.cut_groups == True

BoardTracker.step() sets this by checking whether >= 2 distinct enemy
groups are adjacent to the played intersection before the move.

Note on the proxy
-----------------
This proxy can fire when the two enemy groups were not previously connected
through other paths (i.e., the move doesn't actually sever a connection).
Layer 2 is responsible for confirming a genuine cut.  Layer 1's job is to
flag the candidate.

Test strategy
-------------
Three tests, all driving the pipeline manually on the 174-move novice game:

  no_false_positives : every `cut_created` signal has cut_groups == True
  no_false_negatives : every move where cut_groups == True fires `cut_created`
  fires_at_least_n   : signal fires >= 3 times (0 would mean board state is broken)

KataGo sanity test
------------------
test_cut_position_sgfs_are_analyzable verifies that the position SGFs in
sgf_examples/shapes/ can be parsed by KataGo without error.
"""

import pytest
from pathlib import Path

from tests.integration.helpers import analyze_game_sgf, analyze_position_sgf
from detection.layer1.board_tracker import BoardTracker
from detection.layer1.facts import collect_facts
from detection.layer1.triggers import emit_triggers
from detection.types import TriggerSignal

NOVICE_GAME_SGF = Path(
    "sgf_examples/real_games/novice/85012080-174-DangoApp_bot_3-jg250226_uwshhcr.sgf"
)

CUT_SGFS = [
    Path("sgf_examples/shapes/possible_cut.sgf"),
    Path("sgf_examples/shapes/possible_cut_2.sgf"),
    Path("sgf_examples/shapes/possible_cut_3.sgf"),
    Path("sgf_examples/shapes/possible_cut_4.sgf"),
    Path("sgf_examples/shapes/keima_cut.sgf"),
]


async def _run_pipeline(katago):
    """Drive the full pipeline manually, returning (facts_list, signals_per_move)."""
    game, responses = await analyze_game_sgf(NOVICE_GAME_SGF, katago)
    moves = game["moves"]
    board_size = game.get("board_size", 19)

    tracker = BoardTracker(board_size)
    prev_signals: list[TriggerSignal] = []
    all_facts = []
    all_signals_per_move = []

    for move_index in range(1, len(moves) + 1):
        move_entry = moves[move_index - 1]
        move_color = move_entry[0]
        move_str = move_entry[1] if len(move_entry) > 1 else "pass"

        snapshot = tracker.step(move_str, move_color)
        facts = collect_facts(
            move_index=move_index,
            moves=moves,
            katago_responses=responses,
            player_color="B",
            board_size=board_size,
            prev_signals=prev_signals,
            snapshot=snapshot,
        )
        signals = emit_triggers(facts)
        prev_signals.extend(signals)

        all_facts.append(facts)
        all_signals_per_move.append(signals)

    return all_facts, all_signals_per_move


@pytest.mark.integration
async def test_cut_created_no_false_positives(katago):
    """Every `cut_created` signal must have cut_groups == True.

    If this fails, the trigger condition in triggers.py disagrees with the
    board state — a signal fired when the board reported no cut adjacency.
    """
    all_facts, all_signals_per_move = await _run_pipeline(katago)

    for facts, signals in zip(all_facts, all_signals_per_move):
        if any(s.trigger_type == "cut_created" for s in signals):
            assert facts.cut_groups is True, (
                f"Move {facts.move_index} ({facts.player_color} {facts.move}): "
                f"cut_created fired but cut_groups=False"
            )


@pytest.mark.integration
async def test_cut_created_no_false_negatives(katago):
    """Every move where cut_groups == True must fire `cut_created`.

    If this fails, the trigger condition in triggers.py is wrong.
    """
    all_facts, all_signals_per_move = await _run_pipeline(katago)

    for facts, signals in zip(all_facts, all_signals_per_move):
        if facts.cut_groups is True:
            fired = [s.trigger_type for s in signals]
            assert "cut_created" in fired, (
                f"Move {facts.move_index} ({facts.player_color} {facts.move}): "
                f"cut_groups=True but cut_created did not fire (fired: {fired})"
            )


@pytest.mark.integration
async def test_cut_fires_at_least_n_times(katago):
    """cut_created must fire at least 3 times in a 174-move novice game.

    Adjacency to two enemy groups is common in real games.  A count of 0
    would mean BoardTracker is never setting cut_groups=True.
    """
    all_facts, all_signals_per_move = await _run_pipeline(katago)

    count = sum(
        1 for signals in all_signals_per_move
        if any(s.trigger_type == "cut_created" for s in signals)
    )
    assert count >= 3, (
        f"Expected cut_created to fire >= 3 times in a 174-move novice game; "
        f"fired {count} times"
    )


@pytest.mark.integration
async def test_cut_position_sgfs_are_analyzable(katago):
    """Sanity: all cut SGFs should be parseable by KataGo without errors."""
    for sgf_path in CUT_SGFS:
        response = await analyze_position_sgf(sgf_path, katago)
        assert "rootInfo" in response or "moveInfos" in response, (
            f"KataGo returned unexpected response for {sgf_path.name}: {response!r}"
        )

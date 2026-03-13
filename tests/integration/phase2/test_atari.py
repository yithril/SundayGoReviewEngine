from __future__ import annotations

"""
tests/integration/phase2/test_atari.py
----------------------------------------
Integration tests for the `atari_created` Layer 1 trigger.

What atari_created means
------------------------
A move puts an adjacent enemy group in atari — reduces it to exactly one
liberty.  Applies to groups of any size.  Detected via:

  BoardSnapshot.enemy_liberties_nearby == 1

which BoardTracker.step() computes by finding the minimum liberty count of
all enemy groups adjacent to the played intersection after the move.

Test strategy
-------------
Three tests, all driving the pipeline manually on the 174-move novice game:

  no_false_positives : every `atari_created` signal has enemy_liberties_nearby == 1
  no_false_negatives : every move where enemy_liberties_nearby == 1 fires `atari_created`
  fires_at_least_n   : signal fires >= 5 times (0 would mean board state is broken)

The bidirectional invariant (positives + negatives) catches both wrong
board-state computation and wrong trigger conditions independently.
"""

import pytest
from pathlib import Path

from tests.integration.helpers import analyze_game_sgf
from detection.layer1.board_tracker import BoardTracker
from detection.layer1.facts import collect_facts
from detection.layer1.triggers import emit_triggers
from detection.types import TriggerSignal

NOVICE_GAME_SGF = Path(
    "sgf_examples/real_games/novice/85012080-174-DangoApp_bot_3-jg250226_uwshhcr.sgf"
)


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
async def test_atari_created_no_false_positives(katago):
    """Every `atari_created` signal must have enemy_liberties_nearby == 1.

    If this fails, BoardTracker is computing wrong liberty counts — a move
    was flagged as creating atari when no enemy group was actually reduced
    to one liberty.
    """
    all_facts, all_signals_per_move = await _run_pipeline(katago)

    for facts, signals in zip(all_facts, all_signals_per_move):
        if any(s.trigger_type == "atari_created" for s in signals):
            assert facts.enemy_liberties_nearby == 1, (
                f"Move {facts.move_index} ({facts.player_color} {facts.move}): "
                f"atari_created fired but enemy_liberties_nearby="
                f"{facts.enemy_liberties_nearby} (expected 1)"
            )


@pytest.mark.integration
async def test_atari_created_no_false_negatives(katago):
    """Every move where enemy_liberties_nearby == 1 must fire `atari_created`.

    If this fails, the trigger condition in triggers.py is wrong.
    """
    all_facts, all_signals_per_move = await _run_pipeline(katago)

    for facts, signals in zip(all_facts, all_signals_per_move):
        if facts.enemy_liberties_nearby == 1:
            fired = [s.trigger_type for s in signals]
            assert "atari_created" in fired, (
                f"Move {facts.move_index} ({facts.player_color} {facts.move}): "
                f"enemy_liberties_nearby=1 but atari_created did not fire "
                f"(fired: {fired})"
            )


@pytest.mark.integration
async def test_atari_fires_at_least_n_times(katago):
    """atari_created must fire at least 5 times in a 174-move novice game.

    Novice games have frequent atari moves.  A count of 0 would mean
    BoardTracker is never computing enemy_liberties_nearby == 1, indicating
    the board state is entirely broken.
    """
    all_facts, all_signals_per_move = await _run_pipeline(katago)

    count = sum(
        1 for signals in all_signals_per_move
        if any(s.trigger_type == "atari_created" for s in signals)
    )
    assert count >= 5, (
        f"Expected atari_created to fire >= 5 times in a 174-move novice game; "
        f"fired {count} times"
    )


@pytest.mark.integration
async def test_double_atari_position_loads(katago):
    """Sanity check: double_atari.sgf is a valid position SGF that KataGo can analyze."""
    from tests.integration.helpers import analyze_position_sgf

    double_atari = Path("sgf_examples/shapes/double_atari.sgf")
    response = await analyze_position_sgf(double_atari, katago)

    assert "rootInfo" in response, (
        f"KataGo returned unexpected response for double_atari.sgf: {response!r}"
    )

from __future__ import annotations

"""
tests/integration/phase2/test_capture.py
------------------------------------------
Integration tests for the `capture` Layer 1 trigger.

Status: active.

How it works
------------
The `capture` trigger fires when a move removes at least one enemy stone from
the board:

  BoardSnapshot.stones_captured > 0

BoardTracker.step() sets this via len(captured_set) from sgfmill's board.play().
collect_facts() passes it through to MoveFacts.stones_captured.
triggers.py fires `capture` when facts.stones_captured > 0.

SGFs used
---------
The net tesuji positions in sgf_examples/tesuji/ are ideal: they show ladder
and net sequences where stones are imminently captured.  We use these as
position SGFs to verify KataGo can analyse them, and annotate the assertions
that require a real game run as xfail until triggers.py is updated.
"""

import pytest
from pathlib import Path

from tests.integration.helpers import analyze_position_sgf

NET_SGFS = [
    Path("sgf_examples/tesuji/net_1.sgf"),
    Path("sgf_examples/tesuji/net_2.sgf"),
]

NOVICE_GAME_SGF = Path(
    "sgf_examples/real_games/novice/85012080-174-DangoApp_bot_3-jg250226_uwshhcr.sgf"
)


@pytest.mark.integration
async def test_capture_position_sgfs_are_analyzable(katago):
    """Sanity: net tesuji SGFs should be parseable by KataGo without errors."""
    for sgf_path in NET_SGFS:
        response = await analyze_position_sgf(sgf_path, katago)
        assert "rootInfo" in response or "moveInfos" in response, (
            f"KataGo returned unexpected response for {sgf_path.name}: {response!r}"
        )


@pytest.mark.integration
async def test_capture_fires_in_novice_game(katago):
    """A 174-move novice game must contain at least one capture."""
    from tests.integration.helpers import run_layer1_on_sgf

    hotspots = await run_layer1_on_sgf(NOVICE_GAME_SGF, katago, player_color="B")
    fired_types = {t for hs in hotspots for t in hs.trigger_types}
    assert "capture" in fired_types, (
        "Expected at least one capture trigger in a 174-move novice game; "
        f"got: {fired_types}"
    )


@pytest.mark.integration
async def test_stones_captured_nonzero_when_capture_fires(katago):
    """When `capture` trigger fires, the facts must show stones_captured > 0."""
    from tests.integration.helpers import analyze_game_sgf
    from detection.layer1.facts import collect_facts
    from detection.layer1.triggers import emit_triggers
    from detection.layer1.board_tracker import BoardTracker
    from detection.types import TriggerSignal

    game, responses = await analyze_game_sgf(NOVICE_GAME_SGF, katago)
    moves = game["moves"]
    board_size = game.get("board_size", 19)

    tracker = BoardTracker(board_size)
    prev_signals: list[TriggerSignal] = []
    capture_facts = []

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

        if any(s.trigger_type == "capture" for s in signals):
            capture_facts.append(facts)

    assert capture_facts, "No capture triggers fired"

    for facts in capture_facts:
        assert facts.stones_captured > 0, (
            f"capture trigger fired at move {facts.move_index} but "
            f"stones_captured={facts.stones_captured}"
        )

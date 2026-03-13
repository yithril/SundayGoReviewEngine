from __future__ import annotations

"""
tests/integration/phase1/test_score_swing.py
---------------------------------------------
Integration tests for the `score_swing` Layer 1 trigger.

SGF: real_games/novice/85012080-174-DangoApp_bot_3-jg250226_uwshhcr.sgf
  — 174-move novice game, expected to contain multiple significant score swings.

Two-tier assertions
-------------------
1. Weak:   at least one `score_swing` trigger fires somewhere in the game.
2. Strong: every move classified as "blunder" by review/builder._classify()
           produces at least one `score_swing` trigger at that move index.
"""

import pytest
from pathlib import Path

from tests.integration.helpers import run_layer1_on_sgf
from game.constants.thresholds import SCORE_SWING_THRESHOLD

SGF_PATH = Path("sgf_examples/real_games/novice/85012080-174-DangoApp_bot_3-jg250226_uwshhcr.sgf")

# A blunder is a score swing worse than twice the normal threshold.
# Kept intentionally loose — novice games have many double-threshold swings.
BLUNDER_THRESHOLD = SCORE_SWING_THRESHOLD * 2


@pytest.mark.integration
async def test_score_swing_fires_at_least_once(katago):
    """score_swing trigger must fire at least once in a novice game."""
    hotspots = await run_layer1_on_sgf(SGF_PATH, katago, player_color="B")

    fired_types = {
        trigger_type
        for hs in hotspots
        for trigger_type in hs.trigger_types
    }
    assert "score_swing" in fired_types, (
        "Expected at least one score_swing trigger in a 174-move novice game; "
        f"got trigger types: {fired_types}"
    )


@pytest.mark.integration
async def test_score_swing_signals_have_expected_fields(katago):
    """Every hotspot that contains a score_swing trigger must have sane fields."""
    from tests.integration.helpers import analyze_game_sgf
    from detection.layer1.pipeline import run_layer1

    game, responses = await analyze_game_sgf(SGF_PATH, katago)
    hotspots = run_layer1(game, responses, player_color="B")

    swing_hotspots = [hs for hs in hotspots if "score_swing" in hs.trigger_types]
    assert swing_hotspots, "No score_swing hotspots found"

    for hs in swing_hotspots:
        assert isinstance(hs.center_move_index, int)
        assert hs.center_move_index >= 1
        # Score-swing hotspots must cover at least one move
        assert min(hs.move_indices) <= hs.center_move_index <= max(hs.move_indices)


@pytest.mark.integration
async def test_blunder_moves_produce_score_swing(katago):
    """Moves with score delta > BLUNDER_THRESHOLD should always fire score_swing."""
    from tests.integration.helpers import analyze_game_sgf
    from detection.layer1.facts import collect_facts
    from detection.layer1.triggers import emit_triggers
    from detection.types import TriggerSignal

    game, responses = await analyze_game_sgf(SGF_PATH, katago)
    moves = game["moves"]
    board_size = game.get("board_size", 19)

    blunder_move_indices: list[int] = []
    prev_signals: list[TriggerSignal] = []

    for move_index in range(1, len(moves) + 1):
        facts = collect_facts(
            move_index=move_index,
            moves=moves,
            katago_responses=responses,
            player_color="B",
            board_size=board_size,
            prev_signals=prev_signals,
            snapshot=None,  # board-state fields not needed for score_swing
        )
        signals = emit_triggers(facts)
        prev_signals.extend(signals)

        if abs(facts.score_delta) > BLUNDER_THRESHOLD:
            blunder_move_indices.append(move_index)
            swing_signals = [s for s in signals if s.trigger_type == "score_swing"]
            assert swing_signals, (
                f"Move {move_index} has score_delta={facts.score_delta:.2f} "
                f"(> blunder threshold {BLUNDER_THRESHOLD}) but no score_swing fired"
            )

    # Sanity: novice game must have at least a handful of blunders
    assert len(blunder_move_indices) >= 3, (
        f"Expected >= 3 blunder moves in this novice game; found {len(blunder_move_indices)}"
    )

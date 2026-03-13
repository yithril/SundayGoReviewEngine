from __future__ import annotations

"""
tests/integration/phase1/test_policy_mismatch.py
--------------------------------------------------
Integration tests for the `policy_mismatch` Layer 1 trigger.

SGF: real_games/novice/85012080-174-DangoApp_bot_3-jg250226_uwshhcr.sgf
  — 174-move novice game.  Novice players routinely play moves that KataGo
    ranks well outside the top 5, so policy_mismatch should fire many times.

Two-tier assertions
-------------------
1. Weak:   at least one `policy_mismatch` trigger fires somewhere in the game.
2. Strong: every move where policy_rank > POLICY_RANK_THRESHOLD produces a
           policy_mismatch trigger at that move index.
"""

import pytest
from pathlib import Path

from tests.integration.helpers import run_layer1_on_sgf
from game.constants.thresholds import POLICY_RANK_THRESHOLD

SGF_PATH = Path("sgf_examples/real_games/novice/85012080-174-DangoApp_bot_3-jg250226_uwshhcr.sgf")


@pytest.mark.integration
async def test_policy_mismatch_fires_at_least_once(katago):
    """policy_mismatch trigger must fire at least once in a novice game."""
    hotspots = await run_layer1_on_sgf(SGF_PATH, katago, player_color="B")

    fired_types = {
        trigger_type
        for hs in hotspots
        for trigger_type in hs.trigger_types
    }
    assert "policy_mismatch" in fired_types, (
        "Expected at least one policy_mismatch trigger in a 174-move novice game; "
        f"got trigger types: {fired_types}"
    )


@pytest.mark.integration
async def test_policy_mismatch_fires_many_times_novice(katago):
    """Novice game should produce many policy_mismatch triggers, not just one."""
    hotspots = await run_layer1_on_sgf(SGF_PATH, katago, player_color="B")

    swing_hotspots = [hs for hs in hotspots if "policy_mismatch" in hs.trigger_types]
    assert len(swing_hotspots) >= 5, (
        f"Expected >= 5 policy_mismatch hotspots in a novice game; "
        f"got {len(swing_hotspots)}"
    )


@pytest.mark.integration
async def test_policy_mismatch_fires_exactly_when_rank_exceeded(katago):
    """Moves with policy_rank > POLICY_RANK_THRESHOLD must produce policy_mismatch."""
    from tests.integration.helpers import analyze_game_sgf
    from detection.layer1.facts import collect_facts
    from detection.layer1.triggers import emit_triggers
    from detection.types import TriggerSignal

    game, responses = await analyze_game_sgf(SGF_PATH, katago)
    moves = game["moves"]
    board_size = game.get("board_size", 19)

    prev_signals: list[TriggerSignal] = []
    mismatched_indices: list[int] = []

    for move_index in range(1, len(moves) + 1):
        facts = collect_facts(
            move_index=move_index,
            moves=moves,
            katago_responses=responses,
            player_color="B",
            board_size=board_size,
            prev_signals=prev_signals,
            snapshot=None,
        )
        signals = emit_triggers(facts)
        prev_signals.extend(signals)

        if facts.policy_rank > POLICY_RANK_THRESHOLD:
            mismatched_indices.append(move_index)
            mismatch_signals = [s for s in signals if s.trigger_type == "policy_mismatch"]
            assert mismatch_signals, (
                f"Move {move_index} has policy_rank={facts.policy_rank} "
                f"(> threshold {POLICY_RANK_THRESHOLD}) but no policy_mismatch fired"
            )

    assert len(mismatched_indices) >= 10, (
        f"Expected >= 10 policy_mismatch moves in this novice game; "
        f"found {len(mismatched_indices)}"
    )

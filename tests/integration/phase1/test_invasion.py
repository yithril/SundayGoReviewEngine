from __future__ import annotations

"""
tests/integration/phase1/test_invasion.py
------------------------------------------
Integration tests for the `invasion` Layer 1 trigger.

SGF: sgf_examples/invasion/invasion1.sgf — a game containing a known invasion
sequence where one player enters deep into the opponent's sphere of influence.

Assertions
----------
1. At least one `invasion` trigger fires.
2. The move that fired it satisfies the configured rule inputs:
   dmoyo threshold, own_here ceiling, and side/center location.
"""

import pytest
from pathlib import Path

from tests.integration.helpers import analyze_game_sgf, run_layer1_on_sgf
from detection.layer1.facts import collect_facts
from detection.layer1.triggers import emit_triggers
from detection.types import TriggerSignal
from game.constants.thresholds import DMOYO_INVASION_MIN, OWN_HERE_INVASION_MAX

SGF_PATH = Path("sgf_examples/invasion/invasion1.sgf")


@pytest.mark.integration
async def test_invasion_trigger_fires(katago):
    """invasion must fire at least once in an invasion game."""
    hotspots = await run_layer1_on_sgf(SGF_PATH, katago, player_color="B")

    fired_types = {
        trigger_type
        for hs in hotspots
        for trigger_type in hs.trigger_types
    }
    assert "invasion" in fired_types, (
        "Expected at least one invasion trigger in invasion1.sgf; "
        f"got trigger types: {fired_types}"
    )


@pytest.mark.integration
async def test_invasion_move_matches_rule_inputs(katago):
    """The move that fired invasion must satisfy dmoyo/own_here/location rule inputs."""
    game, responses = await analyze_game_sgf(SGF_PATH, katago)
    moves = game["moves"]
    board_size = game.get("board_size", 19)

    prev_signals: list[TriggerSignal] = []
    invasion_facts = []
    prev_moyo_cell_count = 0

    for move_index in range(1, len(moves) + 1):
        facts = collect_facts(
            move_index=move_index,
            moves=moves,
            katago_responses=responses,
            player_color="B",
            board_size=board_size,
            prev_signals=prev_signals,
            prev_moyo_cell_count=prev_moyo_cell_count,
            snapshot=None,  # entered_influence derived from ownership, no board state needed
        )
        signals = emit_triggers(facts)
        prev_signals.extend(signals)
        prev_moyo_cell_count = facts.moyo_cell_count

        has_invasion = any(s.trigger_type == "invasion" for s in signals)
        has_reduction = any(s.trigger_type == "reduction" for s in signals)
        if has_invasion:
            invasion_facts.append(facts)
            assert not has_reduction, "A move should not be both invasion and reduction"

    assert invasion_facts, "No invasion trigger fired"

    valid_location = {"top", "bottom", "left", "right", "center"}
    matching = [
        f for f in invasion_facts
        if (
            f.dmoyo >= DMOYO_INVASION_MIN
            and f.own_here <= OWN_HERE_INVASION_MAX
            and f.move_sector_9 in valid_location
        )
    ]
    assert matching, (
        "invasion fired but no triggering move matched dmoyo/own_here/location rule; "
        f"candidates: {[(f.move_index, f.dmoyo, round(f.own_here, 3), f.move_sector_9) for f in invasion_facts]}"
    )

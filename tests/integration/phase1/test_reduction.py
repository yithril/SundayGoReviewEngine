from __future__ import annotations

import pytest
from pathlib import Path

from tests.integration.helpers import analyze_game_sgf, run_layer1_on_sgf
from detection.layer1.facts import collect_facts
from detection.layer1.triggers import emit_triggers
from detection.types import TriggerSignal
from game.constants.thresholds import (
    DMOYO_REDUCTION_MIN,
    DMOYO_REDUCTION_MAX_EXCLUSIVE,
    OWN_HERE_REDUCTION_MAX,
)

SGF_PATH = Path("sgf_examples/reduction/reduction.sgf")


@pytest.mark.integration
async def test_reduction_trigger_fires(katago):
    hotspots = await run_layer1_on_sgf(SGF_PATH, katago, player_color="B")
    fired_types = {trigger_type for hs in hotspots for trigger_type in hs.trigger_types}
    assert "reduction" in fired_types, (
        "Expected at least one reduction trigger in reduction.sgf; "
        f"got trigger types: {fired_types}"
    )


@pytest.mark.integration
async def test_reduction_move_matches_rule_inputs(katago):
    game, responses = await analyze_game_sgf(SGF_PATH, katago)
    moves = game["moves"]
    board_size = game.get("board_size", 19)

    prev_signals: list[TriggerSignal] = []
    prev_moyo_cell_count = 0
    reduction_facts = []

    for move_index in range(1, len(moves) + 1):
        facts = collect_facts(
            move_index=move_index,
            moves=moves,
            katago_responses=responses,
            player_color="B",
            board_size=board_size,
            prev_signals=prev_signals,
            prev_moyo_cell_count=prev_moyo_cell_count,
            snapshot=None,
        )
        signals = emit_triggers(facts)
        prev_signals.extend(signals)
        prev_moyo_cell_count = facts.moyo_cell_count

        has_reduction = any(s.trigger_type == "reduction" for s in signals)
        has_invasion = any(s.trigger_type == "invasion" for s in signals)
        if has_reduction:
            reduction_facts.append(facts)
            assert not has_invasion, "A move should not be both reduction and invasion"

    assert reduction_facts, "No reduction trigger fired"

    valid_location = {"top", "bottom", "left", "right", "center"}
    matching = [
        f for f in reduction_facts
        if (
            DMOYO_REDUCTION_MIN <= f.dmoyo < DMOYO_REDUCTION_MAX_EXCLUSIVE
            and f.own_here <= OWN_HERE_REDUCTION_MAX
            and f.move_sector_9 in valid_location
        )
    ]
    assert matching, (
        "reduction fired but no triggering move matched dmoyo/own_here/location rule; "
        f"candidates: {[(f.move_index, f.dmoyo, round(f.own_here, 3), f.move_sector_9) for f in reduction_facts]}"
    )


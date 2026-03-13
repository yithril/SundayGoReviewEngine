from __future__ import annotations

"""
tests/integration/phase1/test_moyo.py
---------------------------------------
Integration tests for the `moyo_formation` Layer 1 trigger.

SGF: sgf_examples/moyo/moyo1.sgf — game with a known large moyo.

The moyo_formation trigger fires from rule inputs:
- dmoyo <= threshold
- own_here >= threshold
- adjacent_friendly >= threshold
- adjacent_enemy == threshold
- move is side/center

Assertions
----------
1. At least one `moyo_formation` trigger fires.
2. When it fires, the move matches the configured rule inputs.
3. The trigger appears in at least one moyo SGF.
"""

import pytest
from pathlib import Path

from tests.integration.helpers import analyze_game_sgf, run_layer1_on_sgf
from detection.layer1.facts import collect_facts
from detection.layer1.triggers import emit_triggers
from detection.types import TriggerSignal

SGF_PATH = Path("sgf_examples/moyo/moyo1.sgf")


@pytest.mark.integration
async def test_moyo_formed_fires_at_least_once(katago):
    """moyo_formation trigger must fire at least once in moyo1.sgf."""
    hotspots = await run_layer1_on_sgf(SGF_PATH, katago, player_color="B")

    fired_types = {
        trigger_type
        for hs in hotspots
        for trigger_type in hs.trigger_types
    }
    assert "moyo_formation" in fired_types, (
        "Expected at least one moyo_formation trigger in moyo1.sgf; "
        f"got trigger types: {fired_types}"
    )


@pytest.mark.integration
async def test_moyo_cell_count_meets_threshold_when_triggered(katago):
    """When moyo_formation fires, facts must match the rule inputs."""
    game, responses = await analyze_game_sgf(SGF_PATH, katago)
    moves = game["moves"]
    board_size = game.get("board_size", 19)

    prev_signals: list[TriggerSignal] = []
    prev_moyo_cell_count = 0
    moyo_trigger_facts = []

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

        if any(s.trigger_type == "moyo_formation" for s in signals):
            moyo_trigger_facts.append(facts)

        prev_moyo_cell_count = facts.moyo_cell_count

    assert moyo_trigger_facts, "No moyo_formation triggers fired"

    valid_location = {"top", "bottom", "left", "right", "center"}
    for facts in moyo_trigger_facts:
        assert (
            facts.dmoyo <= 3
            and facts.own_here >= 0.30
            and facts.adjacent_friendly >= 1
            and facts.adjacent_enemy == 0
            and facts.move_sector_9 in valid_location
        ), (
            f"moyo_formation fired at move {facts.move_index} with non-matching rule inputs: "
            f"(dmoyo={facts.dmoyo}, own_here={facts.own_here:.3f}, "
            f"adj_f={facts.adjacent_friendly}, adj_e={facts.adjacent_enemy}, sector={facts.move_sector_9})"
        )


@pytest.mark.integration
async def test_moyo_trigger_covers_multiple_games(katago):
    """moyo_formation should fire in at least one moyo game file."""
    moyo_sgfs = [
        Path("sgf_examples/moyo/moyo1.sgf"),
        Path("sgf_examples/moyo/moyo2.sgf"),
    ]
    games_with_moyo = 0
    for sgf_path in moyo_sgfs:
        hotspots = await run_layer1_on_sgf(sgf_path, katago, player_color="B")
        fired_types = {t for hs in hotspots for t in hs.trigger_types}
        if "moyo_formation" in fired_types:
            games_with_moyo += 1

    assert games_with_moyo >= 1, (
        f"Expected moyo_formation to fire in at least 1 of {len(moyo_sgfs)} moyo games; "
        f"fired in {games_with_moyo}"
    )

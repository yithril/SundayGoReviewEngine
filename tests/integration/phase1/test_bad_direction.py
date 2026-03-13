from __future__ import annotations

import pytest
from pathlib import Path

from tests.integration.helpers import analyze_game_sgf
from detection.layer1.facts import collect_facts
from detection.layer1.triggers import emit_triggers
from detection.layer1.zones import is_opposite_or_adjacent_opposite
from detection.types import TriggerSignal
from game.constants.phases import GamePhase
from game.constants.thresholds import BAD_DIRECTION_MIN_TOP3_PRIOR_SUM

SGF_PATH = Path("sgf_examples/real_games/advanced/test_advanced.sgf")


@pytest.mark.integration
async def test_bad_direction_trigger_matches_zone_opposition_rule(katago):
    game, responses = await analyze_game_sgf(SGF_PATH, katago)
    moves = game["moves"]
    board_size = game.get("board_size", 19)

    prev_signals: list[TriggerSignal] = []
    prev_moyo_cell_count = 0
    candidates = []
    triggered = []

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

        expected = (
            facts.game_phase in {
                GamePhase.OPENING_2,
                GamePhase.EARLY_MIDDLE,
                GamePhase.MID_MIDDLE,
                GamePhase.LATE_MIDDLE,
            }
            and
            facts.preferred_top3_prior_sum >= BAD_DIRECTION_MIN_TOP3_PRIOR_SUM
            and is_opposite_or_adjacent_opposite(
                facts.move_sector_9,
                facts.preferred_move_sector_9,
            )
        )
        fired = any(s.trigger_type == "bad_direction_of_play" for s in signals)
        if expected:
            candidates.append((facts.move_index, facts.move_sector_9, facts.preferred_move_sector_9))
        if fired:
            triggered.append((facts.move_index, facts.move_sector_9, facts.preferred_move_sector_9))
            assert expected, (
                "bad_direction_of_play fired on a move that does not satisfy zone opposition rule: "
                f"move={facts.move_index}, played={facts.move_sector_9}, preferred={facts.preferred_move_sector_9}, "
                f"top3_mass={facts.preferred_top3_prior_sum:.3f}"
            )

    assert candidates, "No zone-opposition candidates found for bad_direction_of_play in test_advanced.sgf"
    assert triggered, (
        "Found zone-opposition candidates but no bad_direction_of_play trigger fired; "
        f"candidate_moves={candidates[:10]}"
    )


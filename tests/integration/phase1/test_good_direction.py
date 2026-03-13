from __future__ import annotations

import pytest
from pathlib import Path

from tests.integration.helpers import analyze_game_sgf
from detection.layer1.facts import collect_facts
from detection.layer1.triggers import emit_triggers
from detection.layer1.zones import is_preferred_or_adjacent_preferred
from detection.types import TriggerSignal
from game.constants.phases import GamePhase
from game.constants.thresholds import GOOD_DIRECTION_MIN_TOP3_PRIOR_SUM

SGF_PATH = Path("sgf_examples/real_games/advanced/test_advanced.sgf")


@pytest.mark.integration
async def test_good_direction_trigger_matches_zone_alignment_rule(katago):
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
            and facts.preferred_top3_prior_sum >= GOOD_DIRECTION_MIN_TOP3_PRIOR_SUM
            and is_preferred_or_adjacent_preferred(
                facts.move_sector_9,
                facts.preferred_move_sector_9,
            )
        )
        fired = any(s.trigger_type == "good_direction_of_play" for s in signals)
        if expected:
            candidates.append((facts.move_index, facts.move_sector_9, facts.preferred_move_sector_9))
        if fired:
            triggered.append((facts.move_index, facts.move_sector_9, facts.preferred_move_sector_9))
            assert expected, (
                "good_direction_of_play fired on a move that does not satisfy zone-alignment rule: "
                f"move={facts.move_index}, played={facts.move_sector_9}, preferred={facts.preferred_move_sector_9}, "
                f"top3_mass={facts.preferred_top3_prior_sum:.3f}"
            )

    assert candidates, "No preferred-zone candidates found for good_direction_of_play in test_advanced.sgf"
    assert triggered, (
        "Found preferred-zone candidates but no good_direction_of_play trigger fired; "
        f"candidate_moves={candidates[:10]}"
    )


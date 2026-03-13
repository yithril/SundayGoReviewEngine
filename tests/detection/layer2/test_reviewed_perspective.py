from __future__ import annotations

from detection.layer2.pipeline import run_layer2
from detection.types import HotspotCandidate


def test_event_scoring_uses_reviewed_black_perspective():
    hotspots = [
        HotspotCandidate(
            center_move_index=1,
            move_indices=[1],
            trigger_types=["good_direction_of_play"],
            max_winrate_delta=0.0,
            max_score_delta=0.0,
        )
    ]
    game = {"moves": [["B", "D4"]], "board_size": 19}
    responses = {
        0: {"rootInfo": {"scoreLead": 0.0, "winrate": 0.5}},
        1: {"rootInfo": {"scoreLead": 2.0, "winrate": 0.6}},
    }
    events = run_layer2(hotspots, game, responses, reviewed_player_color="B")
    assert len(events) == 1
    assert events[0].score_swing == 2.0
    assert events[0].event_polarity == "positive"


def test_event_scoring_uses_reviewed_white_perspective():
    hotspots = [
        HotspotCandidate(
            center_move_index=1,
            move_indices=[1],
            trigger_types=["good_direction_of_play"],
            max_winrate_delta=0.0,
            max_score_delta=0.0,
        )
    ]
    game = {"moves": [["B", "D4"]], "board_size": 19}
    responses = {
        0: {"rootInfo": {"scoreLead": 0.0, "winrate": 0.5}},
        1: {"rootInfo": {"scoreLead": 2.0, "winrate": 0.6}},
    }
    events = run_layer2(hotspots, game, responses, reviewed_player_color="W")
    assert len(events) == 1
    assert events[0].score_swing == -2.0
    # Direction alignment is still explicitly positive signal, but severity is perspective-correct.
    assert events[0].score_swing_abs == 2.0

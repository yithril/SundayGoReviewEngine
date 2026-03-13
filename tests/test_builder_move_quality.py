from __future__ import annotations

from review.builder import _classify, _score_loss, build_report


class _NarrativeStub:
    def to_report_fields(self) -> dict:
        return {
            "story": "",
            "skills_used": [],
            "did_well": [],
            "needs_improvement": [],
            "match_highlights": [],
        }


def test_classify_threshold_boundaries():
    assert _classify(0.3) == "excellent"
    assert _classify(0.31) == "great"
    assert _classify(0.8) == "great"
    assert _classify(0.81) == "good"
    assert _classify(1.5) == "good"
    assert _classify(1.51) == "inaccuracy"
    assert _classify(3.0) == "inaccuracy"
    assert _classify(3.01) == "mistake"
    assert _classify(6.0) == "mistake"
    assert _classify(6.01) == "blunder"


def test_score_loss_uses_reviewed_player_perspective_for_white():
    prev_resp = {"moveInfos": [{"scoreLead": -2.0}]}
    curr_resp = {"rootInfo": {"scoreLead": 1.5}}
    # White perspective: best=2.0, played=-1.5 => loss=3.5
    assert _score_loss(prev_resp, curr_resp, player_color="W") == 3.5


def test_large_point_loss_not_labeled_excellent():
    assert _classify(8.0) == "blunder"


def test_build_report_counts_only_reviewed_player_moves(monkeypatch):
    monkeypatch.setattr("review.builder.run_detection", lambda **kwargs: _NarrativeStub())

    game = {
        "moves": [["B", "D4"], ["W", "Q16"], ["B", "C3"], ["W", "R17"]],
        "board_size": 19,
        "player_black": "BPlayer",
        "player_white": "WPlayer",
        "game_date": "",
    }
    katago_responses = {
        0: {"rootInfo": {"winrate": 0.5, "scoreLead": 0.0}, "moveInfos": [{"scoreLead": 10.0}]},
        1: {"rootInfo": {"winrate": 0.5, "scoreLead": 2.0}},
        2: {"rootInfo": {"winrate": 0.5, "scoreLead": 1.0}, "moveInfos": [{"scoreLead": 5.0}]},
        3: {"rootInfo": {"winrate": 0.5, "scoreLead": 4.2}},
        4: {"rootInfo": {"winrate": 0.5, "scoreLead": 4.2}},
    }

    report = build_report(
        game=game,
        katago_responses=katago_responses,
        player_color="B",
        rank_band="novice",
        katago_seconds=0.0,
        total_seconds=0.0,
    )

    assert report["move_quality"] == ["blunder", "neutral", "great", "neutral"]
    assert report["move_quality_counts"]["blunder"] == 1
    assert report["move_quality_counts"]["great"] == 1
    assert report["move_quality_counts"]["excellent"] == 0
    assert sum(report["move_quality_counts"].values()) == 2

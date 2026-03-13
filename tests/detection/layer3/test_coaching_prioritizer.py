from __future__ import annotations

from detection.layer3.formatters import format_did_well, format_highlights, format_needs_improvement
from detection.types import GameEvent, HotspotCandidate
from game.constants.phases import GamePhase


def _event(event_type: str, center: int, score_swing: float, winrate_swing: float, polarity: str) -> GameEvent:
    return GameEvent(
        event_type=event_type,  # type: ignore[arg-type]
        move_start=center,
        move_end=center,
        center_move_index=center,
        hotspots=[
            HotspotCandidate(
                center_move_index=center,
                move_indices=[center],
                trigger_types=["score_swing"],
                max_winrate_delta=abs(winrate_swing),
                max_score_delta=abs(score_swing),
            )
        ],
        player_color="B",
        phase=GamePhase.EARLY_MIDDLE,
        description_hint=f"{event_type}-{center}",
        score_swing=score_swing,
        winrate_swing=winrate_swing,
        score_swing_abs=abs(score_swing),
        event_polarity=polarity,  # type: ignore[arg-type]
    )


def test_needs_improvement_prefers_largest_negative_score_swing():
    events = [
        _event("shape_liability", center=30, score_swing=-3.0, winrate_swing=-0.08, polarity="negative"),
        _event("bad_direction_shift", center=40, score_swing=-8.0, winrate_swing=-0.02, polarity="negative"),
        _event("liberty_tactic_failure", center=50, score_swing=-5.0, winrate_swing=-0.04, polarity="negative"),
    ]
    needs = format_needs_improvement(events, move_quality=[])
    assert needs[0].move_number == 40


def test_did_well_prefers_largest_positive_score_swing():
    events = [
        _event("shape_strength", center=12, score_swing=2.0, winrate_swing=0.01, polarity="positive"),
        _event("cut_defense_success", center=16, score_swing=6.0, winrate_swing=0.03, polarity="positive"),
    ]
    did = format_did_well(events, move_quality=[])
    assert did[0].move_number == 16


def test_highlights_include_top_absolute_events():
    events = [
        _event("shape_strength", center=10, score_swing=1.0, winrate_swing=0.01, polarity="positive"),
        _event("shape_liability", center=20, score_swing=-7.0, winrate_swing=-0.03, polarity="negative"),
        _event("liberty_tactic_success", center=30, score_swing=5.0, winrate_swing=0.02, polarity="positive"),
    ]
    highlights = format_highlights(events, move_quality=[])
    assert [h.move_number for h in highlights[:2]] == [20, 30]

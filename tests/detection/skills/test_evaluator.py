from __future__ import annotations

from detection.skills.evaluator import evaluate_skills
from detection.types import GameEvent, HotspotCandidate
from game.constants.phases import GamePhase
from game.constants.skills import GoSkillId


def _event(event_type: str, polarity: str = "positive") -> GameEvent:
    return GameEvent(
        event_type=event_type,  # type: ignore[arg-type]
        move_start=10,
        move_end=10,
        center_move_index=10,
        hotspots=[
            HotspotCandidate(
                center_move_index=10,
                move_indices=[10],
                trigger_types=["score_swing"],
                max_winrate_delta=0.0,
                max_score_delta=0.0,
            )
        ],
        player_color="B",
        phase=GamePhase.EARLY_MIDDLE,
        description_hint="test",
        score_swing=2.0 if polarity == "positive" else -2.0,
        winrate_swing=0.05 if polarity == "positive" else -0.05,
        score_swing_abs=2.0,
        event_polarity=polarity,  # type: ignore[arg-type]
    )


def test_strict_rank_bucket_filtering():
    skills = evaluate_skills(
        events=[_event("ko_fight"), _event("opening_framework")],
        move_quality=["excellent", "neutral", "great"],
        rank_band="novice",
    )
    ids = {s.skill_id for s in skills}
    assert GoSkillId.KO_FIGHTING not in ids
    assert GoSkillId.OPENING not in ids
    assert ids == {
        GoSkillId.BASIC_SHAPE_KNOWLEDGE,
        GoSkillId.COUNTING_LIBERTIES,
        GoSkillId.DEFENDING_CUTTING_POINTS,
    }


def test_points_accumulate_and_cap_at_ten():
    skills = evaluate_skills(
        events=[_event("ko_fight")] * 5,
        move_quality=["good", "neutral", "good"],
        rank_band="beginner",
    )
    ko = next(s for s in skills if s.skill_id == GoSkillId.KO_FIGHTING)
    assert ko.points == 10


def test_no_skill_needed_game_not_globally_zeroed():
    skills = evaluate_skills(
        events=[],
        move_quality=["excellent", "great", "neutral", "great", "excellent"],
        rank_band="novice",
    )
    assert any(skill.points > 0 for skill in skills)


def test_negative_events_do_not_award_points():
    skills = evaluate_skills(
        events=[_event("bad_direction_shift", polarity="negative"), _event("liberty_tactic_failure", polarity="negative")],
        move_quality=["good", "neutral", "good"],
        rank_band="beginner",
    )
    assert all(skill.points >= 0 for skill in skills)
    assert not any(skill.points >= 3 for skill in skills)

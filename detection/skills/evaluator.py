from __future__ import annotations

"""Skill scoring evaluator used as the Layer 3 source of truth."""

from collections import Counter

from detection.types import GameEvent, SkillMention
from game.constants.skills import GoSkillId

_RANK_SKILL_ORDER: dict[str, tuple[GoSkillId, ...]] = {
    "novice": (
        GoSkillId.BASIC_SHAPE_KNOWLEDGE,
        GoSkillId.COUNTING_LIBERTIES,
        GoSkillId.DEFENDING_CUTTING_POINTS,
    ),
    "beginner": (
        GoSkillId.CAPTURING_RACES,
        GoSkillId.CORNER_MOVES_IN_THE_OPENING,
        GoSkillId.END_GAME,
        GoSkillId.KO_FIGHTING,
        GoSkillId.LADDERS,
        GoSkillId.LIFE_AND_DEATH,
        GoSkillId.NETS,
        GoSkillId.SHORTAGE_OF_LIBERTIES,
    ),
    "intermediate": (
        GoSkillId.BASICS_OF_STRATEGY,
        GoSkillId.END_GAME,
        GoSkillId.JOSEKI,
        GoSkillId.LIFE_AND_DEATH,
        GoSkillId.OPENING,
        GoSkillId.TESUJI,
    ),
    "advanced": (
        GoSkillId.FIGHTING_TECHNIQUE,
        GoSkillId.JOSEKI,
        GoSkillId.LIFE_AND_DEATH,
        GoSkillId.OPENING,
        GoSkillId.POSITIONAL_JUDGEMENT,
        GoSkillId.PUSHING_BATTLES_CENTER_CONTROL,
    ),
    "expert": (
        GoSkillId.BALANCE,
        GoSkillId.END_GAME,
        GoSkillId.FIGHTING_TECHNIQUE,
        GoSkillId.JOSEKI,
        GoSkillId.FLEXIBILITY,
        GoSkillId.LIFE_AND_DEATH,
        GoSkillId.POSITIONAL_JUDGEMENT,
        GoSkillId.READING,
        GoSkillId.AJI_AWARENESS,
    ),
}

_EVENT_SKILL_POINTS: dict[str, tuple[tuple[GoSkillId, int], ...]] = {
    "cut_defense_success": ((GoSkillId.DEFENDING_CUTTING_POINTS, 2),),
    "shape_strength": ((GoSkillId.BASIC_SHAPE_KNOWLEDGE, 2),),
    "liberty_tactic_success": (
        (GoSkillId.COUNTING_LIBERTIES, 2),
        (GoSkillId.CAPTURING_RACES, 1),
    ),
    "capture_sequence": (
        (GoSkillId.COUNTING_LIBERTIES, 2),
        (GoSkillId.CAPTURING_RACES, 2),
        (GoSkillId.SHORTAGE_OF_LIBERTIES, 1),
        (GoSkillId.FIGHTING_TECHNIQUE, 1),
    ),
    "group_death": (
        (GoSkillId.LIFE_AND_DEATH, 2),
        (GoSkillId.READING, 1),
        (GoSkillId.TESUJI, 1),
    ),
    "group_saved": (
        (GoSkillId.LIFE_AND_DEATH, 2),
        (GoSkillId.READING, 1),
        (GoSkillId.DEFENDING_CUTTING_POINTS, 1),
    ),
    "invasion_settled": (
        (GoSkillId.BASICS_OF_STRATEGY, 2),
        (GoSkillId.POSITIONAL_JUDGEMENT, 1),
        (GoSkillId.OPENING, 1),
    ),
    "ko_fight": ((GoSkillId.KO_FIGHTING, 3),),
    "semeai": (
        (GoSkillId.CAPTURING_RACES, 2),
        (GoSkillId.COUNTING_LIBERTIES, 2),
        (GoSkillId.READING, 1),
    ),
    "large_territory_swing": (
        (GoSkillId.POSITIONAL_JUDGEMENT, 2),
        (GoSkillId.COUNTING_TERRITORY, 1),
    ),
    "opening_framework": (
        (GoSkillId.OPENING, 2),
        (GoSkillId.CORNER_MOVES_IN_THE_OPENING, 1),
        (GoSkillId.JOSEKI, 1),
    ),
    "tenuki_punished": (
        (GoSkillId.POSITIONAL_JUDGEMENT, 1),
        (GoSkillId.DEFENDING_CUTTING_POINTS, 1),
    ),
    "weak_group_crisis": (
        (GoSkillId.LIFE_AND_DEATH, 1),
        (GoSkillId.BASIC_SHAPE_KNOWLEDGE, 1),
    ),
    "moyo_established": (
        (GoSkillId.BASICS_OF_STRATEGY, 2),
        (GoSkillId.OPENING, 1),
        (GoSkillId.PUSHING_BATTLES_CENTER_CONTROL, 1),
    ),
    "good_direction_shift": (
        (GoSkillId.BASICS_OF_STRATEGY, 1),
        (GoSkillId.OPENING, 1),
        (GoSkillId.POSITIONAL_JUDGEMENT, 1),
    ),
}


def _allowed_skills(rank_band: str) -> tuple[GoSkillId, ...]:
    normalized = (rank_band or "").strip().lower()
    if normalized == "dan":
        normalized = "expert"
    return _RANK_SKILL_ORDER.get(normalized, _RANK_SKILL_ORDER["beginner"])


def _general_execution_bonus(move_quality: list[str]) -> int:
    player_labels = [label for label in move_quality if label != "neutral"]
    if not player_labels:
        return 0
    excellent_or_great = sum(1 for label in player_labels if label in {"excellent", "great"})
    ratio = excellent_or_great / len(player_labels)
    if ratio >= 0.65:
        return 2
    if ratio >= 0.45:
        return 1
    return 0


def evaluate_skills(
    events: list[GameEvent],
    move_quality: list[str],
    rank_band: str,
) -> list[SkillMention]:
    """Evaluate allowed skills for the rank bucket and assign 0-10 points each."""
    allowed = _allowed_skills(rank_band)
    points: Counter[GoSkillId] = Counter({skill: 0 for skill in allowed})

    for event in events:
        if event.event_polarity != "positive":
            continue
        for skill_id, delta in _EVENT_SKILL_POINTS.get(event.event_type, ()):
            if skill_id in points:
                points[skill_id] += delta

    bonus = _general_execution_bonus(move_quality)
    for anchor in (
        GoSkillId.POSITIONAL_JUDGEMENT,
        GoSkillId.BASICS_OF_STRATEGY,
        GoSkillId.BASIC_SHAPE_KNOWLEDGE,
    ):
        if anchor in points:
            points[anchor] += bonus
            break

    return [
        SkillMention(skill_id=skill_id, points=max(0, min(10, int(points[skill_id]))))
        for skill_id in allowed
    ]

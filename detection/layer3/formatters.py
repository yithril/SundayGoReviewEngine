from __future__ import annotations

"""
detection/layer3/formatters.py
-------------------------------
One formatter function per NarrativeOutput field.  Each accepts the list
of GameEvents produced by Layer 2 plus supporting context.

v1: each formatter returns the placeholder content previously in
review/analysis.py.  When you are ready to implement a specific output
field, replace exactly one function here without touching the others.

Real implementations will:
  - Iterate the GameEvent list to find relevant events
  - Use event type, phase, score_swing, and description_hint to generate text
  - Optionally call an LLM with a structured prompt seeded by description_hint
"""

from game.constants.skills import GoSkillId
from detection.types import GameEvent, KeyMomentOutput, SkillMention


# ---------------------------------------------------------------------------
# Placeholder content (migrated from review/analysis.py)
# ---------------------------------------------------------------------------

_LOREM_STORY = (
    "The game opened with a solid territorial framework, and both sides "
    "contested the corners with familiar joseki patterns.  A pivotal exchange "
    "around move 40 shifted the balance — a quick local sequence that looked "
    "safe turned out to gift your opponent an unexpected foothold in the centre.  "
    "From there the middle game became a careful dance of reductions.  Despite "
    "the difficulty you managed to stabilise your groups and reach the endgame "
    "with a fighting chance.  Small but consistent endgame play ultimately "
    "decided the outcome."
)

_PLACEHOLDER_SKILLS: list[SkillMention] = [
    SkillMention(skill_id=GoSkillId.LIFE_AND_DEATH, points=0),
    SkillMention(skill_id=GoSkillId.JOSEKI,         points=0),
    SkillMention(skill_id=GoSkillId.END_GAME,       points=0),
]

_PLACEHOLDER_DID_WELL: list[KeyMomentOutput] = [
    KeyMomentOutput(
        explanation=(
            "Your opening development was well-balanced and established a "
            "strong framework early."
        ),
        move_number=None,
    ),
    KeyMomentOutput(
        explanation=(
            "You maintained good shape throughout the middle game and avoided "
            "overconcentration."
        ),
        move_number=None,
    ),
]

_PLACEHOLDER_NEEDS_IMPROVEMENT: list[KeyMomentOutput] = [
    KeyMomentOutput(
        explanation=(
            "There were a few moments where connecting your groups early would "
            "have saved you defensive moves later."
        ),
        move_number=None,
    ),
    KeyMomentOutput(
        explanation=(
            "Watch for overextensions in the opening — a tighter approach move "
            "can be more reliable than a wide pincer."
        ),
        move_number=None,
    ),
]

_PLACEHOLDER_HIGHLIGHTS: list[KeyMomentOutput] = [
    KeyMomentOutput(
        explanation=(
            "The game's key turning point came in the middle game — a positional "
            "decision that had lasting consequences for both sides."
        ),
        move_number=None,
    ),
    KeyMomentOutput(
        explanation=(
            "An important local sequence determined the fate of a large group "
            "and effectively decided the game's outcome."
        ),
        move_number=None,
    ),
]


# ---------------------------------------------------------------------------
# Formatter functions — one per NarrativeOutput field
# ---------------------------------------------------------------------------

def format_story(
    events: list[GameEvent],
    game: dict,
    move_quality: list[str],
    rank_band: str,
) -> str:
    """Return a multi-sentence narrative describing how the game unfolded.

    TODO: Implement using events to identify key turning points:
      - events sorted by |score_swing| give the most important moments
      - event.phase gives narrative context ("in the opening / middle game")
      - event.description_hint seeds an LLM prompt or template string
    The output should read like a short match report, ~3–5 sentences.
    """
    return _LOREM_STORY


def format_skills(
    events: list[GameEvent],
    move_quality: list[str],
    rank_band: str,
) -> list[SkillMention]:
    """Return skill areas observed (or notably absent) in this game.

    TODO: Implement by mapping GameEventType → skill_id:
      - "capture_sequence" / "semeai"    → counting_liberties / capturing_races
      - "group_death" / "group_saved"    → life_and_death
      - "opening_framework"              → corner_moves_in_the_opening
      - "moyo_established"               → basics_of_strategy
      - "ko_fight"                       → ko_fighting
      - "tenuki_punished"                → defending_cutting_points
    Point rating: 10 = strong evidence, 0 = notable absence or error.
    Return only skills meaningfully represented (>= 1 point) plus 0-point
    skills where the game clearly called for them.
    """
    return _PLACEHOLDER_SKILLS


def format_did_well(
    events: list[GameEvent],
    move_quality: list[str],
) -> list[KeyMomentOutput]:
    """Return positive observations with optional board snapshot anchors.

    TODO: Implement by finding:
      - GameEvents with positive score_swing > threshold for the player
      - Sequences of >= 3 consecutive excellent/great moves in move_quality
      - Moves where the player matched KataGo's top suggestion in a complex pos
    For each, generate a short explanation and record center_move_index.
    """
    ranked = sorted(
        [e for e in events if e.event_polarity == "positive"],
        key=lambda e: (e.score_swing_abs, abs(e.winrate_swing), -e.center_move_index),
        reverse=True,
    )
    if not ranked:
        return _PLACEHOLDER_DID_WELL
    return [
        KeyMomentOutput(
            explanation=e.description_hint,
            move_number=e.center_move_index,
        )
        for e in ranked[:3]
    ]


def format_needs_improvement(
    events: list[GameEvent],
    move_quality: list[str],
) -> list[KeyMomentOutput]:
    """Return coaching observations about areas to improve.

    TODO: Implement by finding:
      - GameEvents with negative score_swing for the player
        (group_death, tenuki_punished, weak_group_crisis)
      - Blunder / mistake moves in move_quality; describe the best alternative
        from KataGo's moveInfos[0]
      - Patterns of repeated error (same event type firing multiple times)
    Keep explanations constructive and specific (include move number).
    """
    ranked = sorted(
        [e for e in events if e.event_polarity == "negative"],
        key=lambda e: (e.score_swing_abs, abs(e.winrate_swing), -e.center_move_index),
        reverse=True,
    )
    if not ranked:
        return _PLACEHOLDER_NEEDS_IMPROVEMENT
    return [
        KeyMomentOutput(
            explanation=e.description_hint,
            move_number=e.center_move_index,
        )
        for e in ranked[:3]
    ]


def format_highlights(
    events: list[GameEvent],
    move_quality: list[str],
) -> list[KeyMomentOutput]:
    """Return the most memorable or instructive moments of the game.

    TODO: Implement by finding:
      - The single event with the largest |score_swing| (the turning point)
      - The single best player move (highest positive score_swing, player turn)
      - Any move that exactly matched KataGo's first choice in a complex
        position (winrate uncertainty > 0.15 before the move)
    Return up to 3 highlights with board snapshot anchors.
    """
    ranked = sorted(
        events,
        key=lambda e: (e.score_swing_abs, abs(e.winrate_swing), -e.center_move_index),
        reverse=True,
    )
    if not ranked:
        return _PLACEHOLDER_HIGHLIGHTS
    return [
        KeyMomentOutput(
            explanation=e.description_hint,
            move_number=e.center_move_index,
        )
        for e in ranked[:3]
    ]

from __future__ import annotations

"""Canonical Go skill identifiers, derived from docs/goskills.md.

GoSkillId is the single source of truth for skill slugs used throughout
the detection pipeline.  SkillMention.skill_id must be a GoSkillId value.
SKILL_DISPLAY_NAMES maps each slug to the human-readable label shown to
the player — this is what to_report_fields() emits as "name".
"""

from enum import Enum


class GoSkillId(str, Enum):
    # Novice
    BASIC_SHAPE_KNOWLEDGE      = "basic_shape_knowledge"
    COUNTING_LIBERTIES         = "counting_liberties"
    COUNTING_TERRITORY         = "counting_territory"
    DEFENDING_CUTTING_POINTS   = "defending_cutting_points"

    # Beginner
    CAPTURING_RACES            = "capturing_races"
    CORNER_MOVES_IN_THE_OPENING = "corner_moves_in_the_opening"
    END_GAME                   = "end_game"
    KO_FIGHTING                = "ko_fighting"
    LADDERS                    = "ladders"
    LIFE_AND_DEATH             = "life_and_death"
    NETS                       = "nets"
    SHORTAGE_OF_LIBERTIES      = "shortage_of_liberties"

    # Intermediate
    BASICS_OF_STRATEGY         = "basics_of_strategy"
    JOSEKI                     = "joseki"
    OPENING                    = "opening"
    TESUJI                     = "tesuji"

    # Advanced
    FIGHTING_TECHNIQUE         = "fighting_technique"
    POSITIONAL_JUDGEMENT       = "positional_judgement"
    PUSHING_BATTLES_CENTER_CONTROL = "pushing_battles_center_control"

    # Expert
    AJI_AWARENESS              = "aji_awareness"
    BALANCE                    = "balance"
    FLEXIBILITY                = "flexibility"
    READING                    = "reading"


SKILL_DISPLAY_NAMES: dict[GoSkillId, str] = {
    GoSkillId.BASIC_SHAPE_KNOWLEDGE:          "Basic Shape Knowledge",
    GoSkillId.COUNTING_LIBERTIES:             "Counting Liberties",
    GoSkillId.COUNTING_TERRITORY:             "Counting Territory",
    GoSkillId.DEFENDING_CUTTING_POINTS:       "Defending Cutting Points",
    GoSkillId.CAPTURING_RACES:                "Capturing Races",
    GoSkillId.CORNER_MOVES_IN_THE_OPENING:    "Corner Moves in the Opening",
    GoSkillId.END_GAME:                       "End Game",
    GoSkillId.KO_FIGHTING:                    "Ko Fighting",
    GoSkillId.LADDERS:                        "Ladders",
    GoSkillId.LIFE_AND_DEATH:                 "Life and Death",
    GoSkillId.NETS:                           "Nets",
    GoSkillId.SHORTAGE_OF_LIBERTIES:          "Shortage of Liberties",
    GoSkillId.BASICS_OF_STRATEGY:             "Basics of Strategy",
    GoSkillId.JOSEKI:                         "Joseki",
    GoSkillId.OPENING:                        "Opening",
    GoSkillId.TESUJI:                         "Tesuji",
    GoSkillId.FIGHTING_TECHNIQUE:             "Fighting Technique",
    GoSkillId.POSITIONAL_JUDGEMENT:           "Positional Judgement",
    GoSkillId.PUSHING_BATTLES_CENTER_CONTROL: "Pushing Battles / Center Control",
    GoSkillId.AJI_AWARENESS:                  "Aji Awareness",
    GoSkillId.BALANCE:                        "Balance",
    GoSkillId.FLEXIBILITY:                    "Flexibility",
    GoSkillId.READING:                        "Reading",
}

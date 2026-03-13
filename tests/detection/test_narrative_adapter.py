from __future__ import annotations

"""Tests for NarrativeOutput.to_report_fields() — the Layer 3 → report adapter."""

from game.constants.skills import GoSkillId
from detection.types import KeyMomentOutput, NarrativeOutput, SkillMention


def _make_narrative() -> NarrativeOutput:
    return NarrativeOutput(
        story="test story",
        skills_used=[SkillMention(skill_id=GoSkillId.LIFE_AND_DEATH, points=6)],
        did_well=[KeyMomentOutput(explanation="good move", move_number=42)],
        needs_improvement=[KeyMomentOutput(explanation="missed cut", move_number=None)],
        match_highlights=[KeyMomentOutput(explanation="turning point", move_number=80)],
    )


def test_keys_present():
    fields = _make_narrative().to_report_fields()
    assert set(fields.keys()) == {
        "story", "skills_used", "did_well", "needs_improvement", "match_highlights"
    }


def test_story_passthrough():
    assert _make_narrative().to_report_fields()["story"] == "test story"


def test_skill_id_serialised_as_display_name():
    skills = _make_narrative().to_report_fields()["skills_used"]
    assert skills == [{"name": "Life and Death", "points": 6}]


def test_key_moment_shape():
    did_well = _make_narrative().to_report_fields()["did_well"]
    assert did_well == [{"explanation": "good move", "move_number": 42}]


def test_move_number_none_preserved():
    improvements = _make_narrative().to_report_fields()["needs_improvement"]
    assert improvements[0]["move_number"] is None


def test_highlights_shape():
    highlights = _make_narrative().to_report_fields()["match_highlights"]
    assert highlights == [{"explanation": "turning point", "move_number": 80}]


def test_empty_narrative():
    fields = NarrativeOutput(story="").to_report_fields()
    assert fields["story"] == ""
    assert fields["skills_used"] == []
    assert fields["did_well"] == []
    assert fields["needs_improvement"] == []
    assert fields["match_highlights"] == []

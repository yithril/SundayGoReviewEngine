from __future__ import annotations

"""
review/analysis.py
------------------
Enrichment stubs for the per-game review sections.

Each function accepts the same core inputs (parsed game dict, per-move quality
labels, raw KataGo responses, and the reviewed player's color) and returns a
typed structure that the report dict and email renderer depend on.

Stub implementations return placeholder data so the email template can be
built against a stable contract today.  Real implementations — LLM calls,
pattern-matching, joseki-library lookups, etc. — slot in here without
touching builder.py or the email layer.
"""

_LOREM = (
    "The game opened with a solid territorial framework, and both sides "
    "contested the corners with familiar joseki patterns.  A pivotal exchange "
    "around move 40 shifted the balance — a quick local sequence that looked "
    "safe turned out to gift your opponent an unexpected foothold in the centre.  "
    "From there the middle game became a careful dance of reductions.  Despite "
    "the difficulty you managed to stabilise your groups and reach the endgame "
    "with a fighting chance.  Small but consistent endgame play ultimately "
    "decided the outcome."
)


# ---------------------------------------------------------------------------
# Story
# ---------------------------------------------------------------------------

def generate_story(
    game: dict,
    move_quality: list[str],
    katago_responses: dict[int, dict],
    player_color: str,
) -> str:
    """
    Return a multi-sentence narrative describing how the game unfolded.

    TODO: Implement with an LLM prompt that receives:
      - The sequence of moves (game["moves"])
      - Per-move quality labels (move_quality)
      - Key swing points from katago_responses (largest score-lead changes)
      - player_color so the narration is written from the right perspective
    The output should read like a short match report, ~3-5 sentences.
    """
    return _LOREM


# ---------------------------------------------------------------------------
# Go Skills
# ---------------------------------------------------------------------------

def identify_skills(
    game: dict,
    move_quality: list[str],
    katago_responses: dict[int, dict],
    player_color: str,
) -> list[dict]:
    """
    Return a list of Go skill areas observed in this game, each with a star
    rating from 0 (not demonstrated) to 5 (masterful).

    Return shape: [{"name": str, "stars": int}, ...]   (up to ~5 entries)

    TODO: Implement by scanning move_quality and katago_responses for patterns:
      - Count how many excellent/great moves occurred in joseki positions
        → joseki recognition score
      - Look for successful life-and-death sequences (stable groups after
        local fights) → L&D / reading score
      - Measure endgame efficiency (score-loss distribution in last 30 moves)
        → endgame score
      - Detect large-scale direction-of-play decisions from score-lead swings
        → strategic thinking score
    Each pattern maps to a 0-5 star rating; return only skills that are
    meaningfully represented (≥ 1 star) plus any skills with notable absence
    (0 stars in an area that clearly came up).
    """
    return [
        {"name": "Life & Death",      "stars": 0},
        {"name": "Joseki Recognition","stars": 0},
        {"name": "Endgame Precision", "stars": 0},
    ]


# ---------------------------------------------------------------------------
# Things You Did Well
# ---------------------------------------------------------------------------

def find_strengths(
    game: dict,
    move_quality: list[str],
    katago_responses: dict[int, dict],
    player_color: str,
) -> list[dict]:
    """
    Return a list of positive observations about the player's game.

    Return shape: [{"explanation": str, "move_number": int | None}, ...]
      - move_number: the 1-indexed game move to show as a board snapshot.
        Set to None when the observation is general (no specific move to pin).

    TODO: Implement by finding:
      - Sequences of ≥ 3 consecutive excellent/great moves
      - Moves where the player matched KataGo's top suggestion exactly
      - Successful recoveries after an earlier blunder (score-lead rebounds)
      - Solid shape choices (heuristic: no empty triangles, good extensions)
    For each finding, generate a short explanation sentence and record the
    central move number so the frontend can render the board position.
    """
    return [
        {
            "explanation": "Your opening development was well-balanced and established a strong framework early.",
            "move_number": None,
        },
        {
            "explanation": "You maintained good shape throughout the middle game and avoided overconcentration.",
            "move_number": None,
        },
    ]


# ---------------------------------------------------------------------------
# Things to Improve
# ---------------------------------------------------------------------------

def find_improvements(
    game: dict,
    move_quality: list[str],
    katago_responses: dict[int, dict],
    player_color: str,
) -> list[dict]:
    """
    Return a list of areas where the player can improve, with specific examples.

    Return shape: [{"explanation": str, "move_number": int | None}, ...]

    TODO: Implement by finding:
      - Blunder and mistake moves; for each, compute the best alternative from
        katago_responses[move_num]["moveInfos"][0] and describe the difference
      - Patterns of repeated error type (e.g., three separate over-plays in a row)
      - Missed cuts or connection moves flagged by a large score-lead drop
      - Groups left weak that later required defensive reinforcement
    Keep explanations constructive and specific ("On move 42, playing at R14
    instead would have…").
    """
    return [
        {
            "explanation": "There were a few moments where connecting your groups early would have saved you defensive moves later.",
            "move_number": None,
        },
        {
            "explanation": "Watch for overextensions in the opening — a tighter approach move can be more reliable than a wide pincer.",
            "move_number": None,
        },
    ]


# ---------------------------------------------------------------------------
# Match Highlights
# ---------------------------------------------------------------------------

def find_highlights(
    game: dict,
    move_quality: list[str],
    katago_responses: dict[int, dict],
    player_color: str,
) -> list[dict]:
    """
    Return the most memorable or instructive moments of the game.

    Return shape: [{"explanation": str, "move_number": int | None}, ...]

    TODO: Implement by finding:
      - The single largest positive score-lead swing on the player's move
        (their best moment)
      - The single largest negative swing (the turning point)
      - Any move that exactly matched KataGo's first choice in a complex
        position (winrate uncertainty > 0.15)
    These become the "highlight reel" items — shown with board snapshots so
    the player can replay the key moment.
    """
    return [
        {
            "explanation": "The game's key turning point came in the middle game — a positional decision that had lasting consequences for both sides.",
            "move_number": None,
        },
        {
            "explanation": "An important local sequence determined the fate of a large group and effectively decided the game's outcome.",
            "move_number": None,
        },
    ]

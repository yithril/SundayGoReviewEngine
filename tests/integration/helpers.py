from __future__ import annotations

"""
tests/integration/helpers.py
-----------------------------
Shared helpers for integration tests.  Three public functions cover the two
SGF formats used in this test suite:

  analyze_game_sgf()       → (game_dict, katago_responses)
  analyze_position_sgf()   → single katago_response dict
  run_layer1_on_sgf()      → list[HotspotCandidate]

SGF formats
-----------
Game SGFs  (real_games/, invasion/, moyo/, etc.)
  Normal game trees.  parse_sgf() extracts the move sequence.  KataGo is asked
  to analyze every turn via analyzeTurns.

Position SGFs  (shapes/)
  Root node only — stones placed with AB/AW setup properties, no move sequence.
  KataGo is queried with initialStones at turn 0 to get policy/ownership for
  that fixed position.
"""

import uuid
from pathlib import Path
from typing import Any

import sgfmill.sgf

from katago.engine import KataGoEngine
from sgf.parser import parse_sgf, sgf_coord_to_katago
from detection.layer1.pipeline import run_layer1
from detection.types import Color, HotspotCandidate

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_SGFMILL_TO_COLOR = {"b": "B", "w": "W"}


def _load_sgf(sgf_path: str | Path) -> bytes:
    return Path(sgf_path).read_bytes()


def _build_analyze_turns_query(
    game: dict,
    visits: int,
    query_id: str,
) -> tuple[dict, int]:
    """Build a KataGo analyzeTurns query for every turn in the game.

    Returns (query_dict, num_turns).
    """
    moves = game["moves"]
    num_turns = len(moves)
    analyze_turns = list(range(num_turns + 1))  # 0 = before first move

    query = {
        "id":               query_id,
        "moves":            moves,
        "rules":            "chinese",
        "komi":             game["komi"],
        "boardXSize":       game["board_size"],
        "boardYSize":       game["board_size"],
        "analyzeTurns":     analyze_turns,
        "maxVisits":        visits,
        "includeOwnership": True,
        "includePVVisits":  False,
    }
    return query, len(analyze_turns)


def _build_position_query(
    initial_stones: list[list[str]],
    board_size: int,
    komi: float,
    visits: int,
    query_id: str,
) -> dict:
    """Build a KataGo query for a static position (no move sequence).

    Uses the initialStones API to set up the board without any moves.
    analyzeTurns=[0] analyzes the position at turn 0.
    """
    return {
        "id":               query_id,
        "initialStones":    initial_stones,   # [["B","D4"], ["W","Q16"], ...]
        "moves":            [],
        "rules":            "chinese",
        "komi":             komi,
        "boardXSize":       board_size,
        "boardYSize":       board_size,
        "analyzeTurns":     [0],
        "maxVisits":        visits,
        "includeOwnership": True,
    }


def _parse_setup_stones(sgf_path: str | Path) -> tuple[list[list[str]], int, float]:
    """Read AB/AW setup stones from an SGF root node.

    Returns (initial_stones, board_size, komi) where initial_stones is in
    KataGo format: [["B","D4"], ["W","Q16"], ...].
    """
    raw = _load_sgf(sgf_path)
    if isinstance(raw, bytes):
        raw_str = raw.decode("utf-8", errors="replace")
    else:
        raw_str = raw

    game_obj = sgfmill.sgf.Sgf_game.from_string(raw_str)
    board_size = game_obj.get_size()
    raw_komi = game_obj.get_komi()
    komi = float(raw_komi) if raw_komi is not None else 6.5

    root = game_obj.get_root()
    stones: list[list[str]] = []

    for sgf_color, prop_name in (("black", "AB"), ("white", "AW")):
        try:
            coords = root.get(prop_name)
        except KeyError:
            continue
        if coords is None:
            continue
        katago_color = "B" if sgf_color == "black" else "W"
        for row, col in coords:
            katago_coord = sgf_coord_to_katago(row, col, board_size)
            stones.append([katago_color, katago_coord])

    return stones, board_size, komi


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def analyze_game_sgf(
    sgf_path: str | Path,
    engine: KataGoEngine,
    visits: int = 50,
) -> tuple[dict, dict[int, dict]]:
    """Analyze every turn of a game SGF and return (game_dict, katago_responses).

    Parameters
    ----------
    sgf_path  : path to the game SGF file
    engine    : running KataGoEngine instance
    visits    : maxVisits per turn (50 is fast enough for trigger detection)

    Returns
    -------
    game_dict        : parse_sgf() output — board_size, komi, moves, players
    katago_responses : turn_number → KataGo response dict (same shape as the
                       production pipeline, keyed 0..len(moves))
    """
    raw = _load_sgf(sgf_path)
    game = parse_sgf(raw)
    query_id = str(uuid.uuid4())
    query, num_turns = _build_analyze_turns_query(game, visits, query_id)
    responses = await engine.analyze(query, num_turns=num_turns)
    return game, responses


async def analyze_position_sgf(
    sgf_path: str | Path,
    engine: KataGoEngine,
    visits: int = 50,
) -> dict[str, Any]:
    """Analyze a static position SGF (AB/AW stones, no move sequence).

    Parameters
    ----------
    sgf_path : path to the position SGF (shapes/*, etc.)
    engine   : running KataGoEngine instance
    visits   : maxVisits (50 is enough for atari / cut detection tests)

    Returns
    -------
    A single KataGo response dict containing:
      rootInfo, moveInfos, ownership
    """
    initial_stones, board_size, komi = _parse_setup_stones(sgf_path)
    query_id = str(uuid.uuid4())
    query = _build_position_query(initial_stones, board_size, komi, visits, query_id)
    responses = await engine.analyze(query, num_turns=1)
    return responses.get(0) or next(iter(responses.values()))


async def run_layer1_on_sgf(
    sgf_path: str | Path,
    engine: KataGoEngine,
    player_color: Color,
    visits: int = 50,
) -> list[HotspotCandidate]:
    """Run the full Layer 1 pipeline on a game SGF.

    Convenience wrapper that calls analyze_game_sgf() then run_layer1().
    The BoardTracker inside run_layer1() ensures the sgfmill Board is
    updated exactly once per move (O(N) total, never O(N²)).

    Parameters
    ----------
    sgf_path     : path to the game SGF file
    engine       : running KataGoEngine instance
    player_color : "B" or "W" — the player whose perspective we analyse
    visits       : maxVisits passed to KataGo

    Returns
    -------
    list[HotspotCandidate] — full Layer 1 output, ready for assertions
    """
    game, responses = await analyze_game_sgf(sgf_path, engine, visits=visits)
    return run_layer1(game, responses, player_color)

from __future__ import annotations

import logging

from katago.engine import KataGoEngine

logger = logging.getLogger(__name__)


async def evaluate_position(
    engine: KataGoEngine,
    moves: list,
    board_size: int,
    komi: float,
    visits: int = 200,
) -> dict:
    """
    Analyze a single board position and return top moves + ownership + root eval.

    Parameters
    ----------
    engine     : running KataGoEngine instance
    moves      : full move history as [["B","D4"], ["W","Q16"], ...]
    board_size : 9, 13, or 19
    komi       : komi value
    visits     : maxVisits for the search (default 200 — fast and strong enough)

    Returns
    -------
    {
        "root":      { "winrate", "score_lead", "visits" },
        "top_moves": [ { "move", "winrate", "score_lead", "visits", "prior", "pv" } ],
        "ownership": [ float × board_size² ]
    }
    """
    num_moves = len(moves)

    query = {
        "id":               "eval",
        "moves":            moves,
        "rules":            "chinese",
        "komi":             komi,
        "boardXSize":       board_size,
        "boardYSize":       board_size,
        "analyzeTurns":     [num_moves],   # analyze the current position only
        "maxVisits":        visits,
        "includeOwnership": True,
    }

    responses = await engine.analyze(query, num_turns=1)
    resp = responses.get(num_moves) or next(iter(responses.values()))

    root_info = resp.get("rootInfo", {})
    move_infos = resp.get("moveInfos", [])
    ownership = resp.get("ownership", [])

    top_moves = [
        {
            "move":       m.get("move"),
            "winrate":    round(m.get("winrate", 0.0), 4),
            "score_lead": round(m.get("scoreLead", 0.0), 2),
            "visits":     m.get("visits", 0),
            "prior":      round(m.get("prior", 0.0), 4),
            "pv":         m.get("pv", []),
        }
        for m in move_infos[:5]
    ]

    return {
        "root": {
            "winrate":    round(root_info.get("winrate", 0.5), 4),
            "score_lead": round(root_info.get("scoreLead", 0.0), 2),
            "visits":     root_info.get("visits", visits),
        },
        "top_moves": top_moves,
        "ownership":  [round(v, 4) for v in ownership],
    }

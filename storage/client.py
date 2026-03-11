from __future__ import annotations

import os
import logging

from supabase import create_client, Client

logger = logging.getLogger(__name__)

_client: Client | None = None


def _get_client() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        _client = create_client(url, key)
    return _client


def save_report(job: dict, report: dict) -> str:
    """
    Insert a row into the game_reviews table and return the new review UUID.

    Parameters
    ----------
    job    : dict with keys user_id and sgf (from the RunPod handler input)
    report : the dict returned by review.builder.build_report()
    """
    client = _get_client()

    row = {
        "user_id":      job.get("user_id"),
        "sgf":          job["sgf"],
        "player_color": report["player_color"],
        "rank_band":    report["rank_band"],
        "game_summary": report["game_summary"],
        "total_moves":  report["total_moves"],
        "board_size":   report["board_size"],
        "report":       report,
    }

    result = client.table("game_reviews").insert(row).execute()
    review_id: str = result.data[0]["id"]
    logger.info("Saved review %s to Supabase", review_id)
    return review_id

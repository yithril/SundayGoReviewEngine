import asyncio
import json
import logging
from katago_engine import KataGoEngine
from sgf_parser import parse_sgf
from db import get_next_queued_job, mark_processing, update_progress, complete_job, fail_job
from config import settings

logger = logging.getLogger(__name__)

# SSE listener registry: job_id -> list of asyncio.Queue
_listeners: dict[str, list[asyncio.Queue]] = {}


def register_listener(job_id: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _listeners.setdefault(job_id, []).append(q)
    return q


def unregister_listener(job_id: str, q: asyncio.Queue):
    if job_id in _listeners:
        try:
            _listeners[job_id].remove(q)
        except ValueError:
            pass
        if not _listeners[job_id]:
            del _listeners[job_id]


async def _notify(job_id: str, data: dict):
    for q in _listeners.get(job_id, []):
        await q.put(data)


def _build_result(responses: dict[int, dict], moves: list, board_size: int) -> dict:
    """
    Turn KataGo's raw per-turn responses into our API result format.

    win_rates[i]   = black win rate AFTER move i (index 0 = empty board)
    score_leads[i] = score lead from black's perspective after move i
    """
    num_turns = len(moves) + 1  # turn 0 (empty board) through turn N (after last move)

    win_rates: list[float] = []
    score_leads: list[float] = []
    move_details: dict[int, dict] = {}

    for turn in range(num_turns):
        resp = responses.get(turn)
        if resp is None:
            win_rates.append(win_rates[-1] if win_rates else 0.5)
            score_leads.append(score_leads[-1] if score_leads else 0.0)
            continue

        root = resp.get("rootInfo", {})
        raw_winrate = root.get("winrate", 0.5)
        raw_score = root.get("scoreLead", 0.0)

        # Normalize to black's perspective
        # At even turns (0, 2, 4...) Black is to move — winrate is already Black's
        # At odd turns (1, 3, 5...) White is to move — flip winrate
        if turn % 2 == 0:
            black_winrate = raw_winrate
            black_score = raw_score
        else:
            black_winrate = 1.0 - raw_winrate
            black_score = -raw_score

        win_rates.append(round(black_winrate, 4))
        score_leads.append(round(black_score, 2))

        # Store move details for lazy loading (turns 1+ represent actual moves)
        if turn >= 1:
            move_infos = resp.get("moveInfos", [])
            best_move = move_infos[0]["move"] if move_infos else "pass"
            top_moves = [
                {
                    "move": m["move"],
                    "winrate": round(m.get("winrate", 0), 4),
                    "scoreLead": round(m.get("scoreLead", 0), 2),
                }
                for m in move_infos[:5]
            ]
            move_details[turn] = {
                "turn": turn,
                "best_move": best_move,
                "top_moves": top_moves,
                "ownership": resp.get("ownership"),
            }

    # Detect key moments: moves where the playing side lost more than 7% win rate
    key_moments: list[int] = []
    for move_num in range(1, len(moves) + 1):
        turn = move_num  # after this move
        if turn >= len(win_rates):
            break
        wr_before = win_rates[turn - 1]
        wr_after = win_rates[turn]
        # Determine whose move it was (move_num 1 = black, 2 = white, alternating)
        is_black_move = (move_num % 2 == 1)
        drop = (wr_before - wr_after) if is_black_move else (wr_after - wr_before)
        if drop > 0.07:
            key_moments.append(move_num)

    final_wr = win_rates[-1] if win_rates else 0.5
    black_blunders = sum(
        1 for m in key_moments if m % 2 == 1
    )
    white_blunders = sum(
        1 for m in key_moments if m % 2 == 0
    )

    return {
        "win_rates": win_rates,
        "score_leads": score_leads,
        "key_moments": key_moments,
        "summary": {
            "total_moves": len(moves),
            "black_win_rate_final": final_wr,
            "black_blunders": black_blunders,
            "white_blunders": white_blunders,
        },
        "move_details": move_details,
    }


async def run_worker(engine: KataGoEngine):
    logger.info("Job worker started")
    while True:
        job = await get_next_queued_job()
        if not job:
            await asyncio.sleep(2)
            continue

        job_id = job["job_id"]
        logger.info(f"Starting job {job_id} (mode={job['mode']})")

        try:
            await mark_processing(job_id)
            await _notify(job_id, {"status": "processing", "progress": 0.0})

            game = parse_sgf(job["sgf"])
            moves = game["moves"]
            num_turns = len(moves) + 1
            analyze_turns = list(range(num_turns))

            visits = {
                "quick": settings.visits_quick,
                "standard": settings.visits_standard,
                "deep": settings.visits_deep,
            }.get(job["mode"], settings.visits_quick)

            query = {
                "id": job_id,
                "moves": moves,
                "rules": "japanese",
                "komi": game["komi"],
                "boardXSize": game["board_size"],
                "boardYSize": game["board_size"],
                "analyzeTurns": analyze_turns,
                "maxVisits": visits,
                "includeOwnership": True,
            }

            async def on_progress(progress: float):
                await update_progress(job_id, progress)
                await _notify(job_id, {"status": "processing", "progress": round(progress, 3)})

            responses = await engine.analyze(query, num_turns, on_progress)
            result = _build_result(responses, moves, game["board_size"])

            await complete_job(job_id, result)
            await _notify(job_id, {"status": "complete", "progress": 1.0})
            logger.info(f"Job {job_id} complete")

        except Exception as exc:
            logger.exception(f"Job {job_id} failed")
            await fail_job(job_id, str(exc))
            await _notify(job_id, {"status": "failed", "error": str(exc)})

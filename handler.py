import logging
import os
import subprocess
import time

import runpod

from sgf.parser     import parse_sgf
from katago.engine  import KataGoEngine
from review.builder import build_report
from storage.client import save_report
from mailer.sender  import send_success_email, send_failure_email

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

KATAGO_BINARY = os.environ.get("KATAGO_BINARY", "/usr/local/bin/katago")
KATAGO_MODEL  = os.environ.get("KATAGO_MODEL",  "/opt/katago/model.bin.gz")
KATAGO_CONFIG = os.environ.get("KATAGO_CONFIG", "/opt/katago/analysis.cfg")
VISITS        = int(os.environ.get("VISITS_STANDARD", "100"))


async def _run(job_input: dict) -> dict:
    sgf          = job_input["sgf"]
    player_color = job_input.get("player_color", "B")
    rank_band    = job_input.get("rank_band", "beginner")

    wall_start = time.perf_counter()

    # --- Parse SGF ---
    game      = parse_sgf(sgf)
    moves     = game["moves"]
    num_turns = len(moves) + 1   # turn 0 (before any move) through turn N

    logger.info(
        "Job parsed: %d moves, board=%dx%d, komi=%.1f, player=%s, rank=%s",
        len(moves), game["board_size"], game["board_size"],
        game["komi"], player_color, rank_band,
    )

    # --- Build KataGo query ---
    query = {
        "id":           "review",
        "moves":        moves,
        "rules":        "chinese",
        "komi":         game["komi"],
        "boardXSize":   game["board_size"],
        "boardYSize":   game["board_size"],
        "analyzeTurns": list(range(num_turns)),
        "maxVisits":    VISITS,
        "includeOwnership": False,
    }

    # --- Run KataGo (timed) ---
    engine = KataGoEngine(KATAGO_BINARY, KATAGO_MODEL, KATAGO_CONFIG)
    await engine.start()

    katago_start = time.perf_counter()
    try:
        responses = await engine.analyze(query, num_turns)
    finally:
        await engine.stop()

    katago_seconds = time.perf_counter() - katago_start
    total_seconds  = time.perf_counter() - wall_start

    logger.info(
        "KataGo finished: %d turns in %.2fs (total %.2fs)",
        num_turns, katago_seconds, total_seconds,
    )

    # --- Build report ---
    report = build_report(
        game=game,
        katago_responses=responses,
        player_color=player_color,
        rank_band=rank_band,
        katago_seconds=katago_seconds,
        total_seconds=total_seconds,
    )

    return report


async def handler(job: dict) -> dict:
    inp   = job.get("input", {})
    email = inp.get("email", "")

    if not inp.get("sgf"):
        raise ValueError("No SGF provided in input")

    try:
        report = await _run(inp)

        job_meta = {
            "user_id": inp.get("user_id"),
            "sgf":     inp["sgf"],
        }

        review_id = save_report(job_meta, report)

        if email:
            send_success_email(email, report, review_id)
        else:
            logger.warning("No email address provided — skipping success email")

        return {
            "review_id":      review_id,
            "total_moves":    report["total_moves"],
            "katago_seconds": report["katago_seconds"],
            "total_seconds":  report["total_seconds"],
        }

    except Exception as exc:
        logger.exception("Job failed: %s", exc)
        if email:
            try:
                send_failure_email(email, str(exc))
            except Exception as mail_exc:
                logger.error("Failed to send failure email: %s", mail_exc)
        raise


def _startup_diagnostics():
    for path in (KATAGO_BINARY, KATAGO_MODEL, KATAGO_CONFIG):
        exists = os.path.exists(path)
        size   = os.path.getsize(path) if exists else None
        logger.info("[startup] %s  exists=%s  size=%s", path, exists, size)

    try:
        result = subprocess.run(
            [KATAGO_BINARY, "version"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        logger.info("[startup] katago version rc=%s", result.returncode)
        if result.stdout:
            logger.info("[startup] katago version stdout: %s", result.stdout.strip())
        if result.stderr:
            logger.info("[startup] katago version stderr: %s", result.stderr.strip())
    except Exception as exc:
        logger.error("[startup] katago version probe failed: %r", exc)


_startup_diagnostics()
runpod.serverless.start({"handler": handler})

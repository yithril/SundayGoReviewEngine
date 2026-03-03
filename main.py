import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from katago_engine import KataGoEngine, KataGoEngineError

from config import settings
from models import (
    AnalyzeRequest,
    SubmitResponse,
    JobStatusResponse,
    MoveDetailResponse,
    SuggestRequest,
    SuggestResponse,
    CoachEvaluateRequest,
    CoachEvaluateResponse,
    TopMove,
)
from db import init_db, create_job, get_job, get_queue_depth, get_queue_position
from worker import run_worker, register_listener, unregister_listener

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def _engine_fast() -> KataGoEngine:
    config = settings.katago_config_fast or settings.katago_config
    return KataGoEngine(
        binary=settings.katago_binary,
        model=settings.katago_human_model,
        config=config,
    )


def _engine_slow() -> KataGoEngine:
    config = settings.katago_config_slow or settings.katago_config
    return KataGoEngine(
        binary=settings.katago_binary,
        model=settings.katago_model,
        config=config,
    )


engine_fast = _engine_fast()
engine_slow = _engine_slow()

VISITS_PER_MODE = {
    "quick": settings.visits_quick,
    "standard": settings.visits_standard,
    "deep": settings.visits_deep,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await engine_fast.start()
    await engine_slow.start()
    asyncio.create_task(run_worker(engine_slow))
    yield
    await engine_fast.stop()
    await engine_slow.stop()


app = FastAPI(title="KataGo API", lifespan=lifespan)


@app.exception_handler(KataGoEngineError)
async def katago_engine_error_handler(request: Request, exc: KataGoEngineError):
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
        headers={"Retry-After": "10"},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins.split(","),
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# --- Auth dependency ---

async def require_api_key(x_api_key: str = Header(...)):
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


# --- Endpoints ---

@app.get("/health")
async def health():
    depth = await get_queue_depth()
    return {
        "status": "ok",
        "katago_fast": engine_fast.status(),
        "katago_slow": engine_slow.status(),
        "queue_depth": depth,
    }


@app.post("/analyze", response_model=SubmitResponse, dependencies=[Depends(require_api_key)])
async def submit_analysis(req: AnalyzeRequest):
    depth = await get_queue_depth()
    if depth >= settings.max_queue_depth:
        raise HTTPException(status_code=503, detail="Server busy — queue is full. Try again shortly.")

    job_id = await create_job(req.sgf, req.mode.value)
    position = await get_queue_position(job_id)
    visits = VISITS_PER_MODE.get(req.mode.value, settings.visits_quick)
    # ~0.3s per turn per 32 visits, 200 moves average
    estimated_seconds = int(position * 200 * (visits / 32) * 0.3)

    return SubmitResponse(
        job_id=job_id,
        status="queued",
        queue_position=position,
        estimated_wait_seconds=estimated_seconds,
    )


@app.get("/analyze/{job_id}", dependencies=[Depends(require_api_key)])
async def get_analysis(job_id: str):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If complete or failed, return immediately (no streaming needed)
    if job["status"] in ("complete", "failed"):
        return _job_response(job)

    # Otherwise stream progress via SSE
    return StreamingResponse(
        _sse_stream(job_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/move/{job_id}/{move_number}", dependencies=[Depends(require_api_key)])
async def get_move_detail(job_id: str, move_number: int):
    job = await get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "complete":
        raise HTTPException(status_code=400, detail="Analysis not complete yet")

    result = json.loads(job["result_json"])
    details = result.get("move_details", {})
    move_data = details.get(str(move_number))

    if not move_data:
        raise HTTPException(status_code=404, detail=f"No detail found for move {move_number}")

    win_rates = result["win_rates"]
    score_leads = result["score_leads"]
    turn = move_number

    return MoveDetailResponse(
        move_number=move_number,
        win_rate_before=win_rates[turn - 1] if turn - 1 < len(win_rates) else 0.5,
        win_rate_after=win_rates[turn] if turn < len(win_rates) else 0.5,
        score_lead_before=score_leads[turn - 1] if turn - 1 < len(score_leads) else 0.0,
        score_lead_after=score_leads[turn] if turn < len(score_leads) else 0.0,
        score_swing=abs(
            (score_leads[turn - 1] if turn - 1 < len(score_leads) else 0)
            - (score_leads[turn] if turn < len(score_leads) else 0)
        ),
        best_move=move_data.get("best_move", "pass"),
        top_moves=move_data.get("top_moves", []),
        ownership=move_data.get("ownership"),
    )


@app.post("/suggest", response_model=SuggestResponse, dependencies=[Depends(require_api_key)])
async def suggest_move(req: SuggestRequest):
    rank_profile = f"rank_{req.rank.value}"  # e.g. "rank_7k"
    num_moves = len(req.moves)

    query = {
        "id": f"suggest_{uuid.uuid4().hex[:8]}",
        "moves": req.moves,
        "rules": "japanese",
        "komi": req.komi,
        "boardXSize": req.board_size,
        "boardYSize": req.board_size,
        "analyzeTurns": [num_moves],    # only the current position
        "maxVisits": 50,                # fast — enough for rank emulation
        "includeOwnership": False,
        "overrideSettings": {
            "humanSLProfile": rank_profile,
            "ignorePreRootHistory": False,
        },
    }
    logger.info("suggest: query_id=%s num_moves=%s rank=%s", query["id"], num_moves, req.rank.value)

    logger.info("suggest: entering engine_fast.analyze")
    responses = await engine_fast.analyze(query, num_turns=1)
    logger.info("suggest: engine_fast.analyze returned")
    resp = responses.get(num_moves, {})
    move_infos = resp.get("moveInfos", [])
    best = move_infos[0] if move_infos else {}

    is_black_turn = (num_moves % 2 == 0)
    raw_wr = resp.get("rootInfo", {}).get("winrate", 0.5)
    black_wr = raw_wr if is_black_turn else 1.0 - raw_wr

    return SuggestResponse(
        move=best.get("move", "pass"),
        win_rate=round(black_wr, 4),
        rank=req.rank.value,
    )


COACH_EVALUATE_TIMEOUT_SEC = 3.0


@app.post("/coaching/evaluate", dependencies=[Depends(require_api_key)])
async def coaching_evaluate(req: CoachEvaluateRequest):
    """
    Single-position analysis for coaching: root stats, top 5 moves with PV,
    ownership, ownership_stdev, policy. Uses strong engine. On timeout or
    KataGo error returns 200 with { "utterance_key": null }.
    """
    num_moves = len(req.moves)
    query = {
        "id": "coach",
        "moves": req.moves,
        "rules": "japanese",
        "komi": req.komi,
        "boardXSize": req.board_size,
        "boardYSize": req.board_size,
        "analyzeTurns": [num_moves],
        "maxVisits": 150,
        "analysisPVLen": 8,
        "includeOwnership": True,
        "includeOwnershipStdev": True,
        "includePolicy": True,
        "includeMovesOwnership": False,
        "includePVVisits": False,
        "includeNoResultValue": False,
    }
    try:
        responses = await asyncio.wait_for(
            engine_slow.analyze(query, num_turns=1),
            timeout=COACH_EVALUATE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
        logger.warning("coaching/evaluate: KataGo call timed out after %s s", COACH_EVALUATE_TIMEOUT_SEC)
        return JSONResponse(status_code=200, content={"utterance_key": None})
    except KataGoEngineError as e:
        logger.warning("coaching/evaluate: KataGo error: %s", e)
        return JSONResponse(status_code=200, content={"utterance_key": None})

    resp = responses.get(num_moves, {})
    move_infos = resp.get("moveInfos", [])
    root_info = resp.get("rootInfo", {})

    # ownership: +1.0 = Black, -1.0 = White, row-major
    ownership = resp.get("ownership") or []
    ownership_stdev = resp.get("ownershipStdev") or []
    policy = resp.get("policy") or []

    root = {
        "winrate": round(root_info.get("winrate", 0.5), 4),
        "score_lead": round(root_info.get("scoreLead", 0.0), 2),
        "current_player": root_info.get("currentPlayer", "B"),
        "visits": root_info.get("visits", 0),
    }

    top_moves: list[TopMove] = []
    for m in move_infos[:5]:
        top_moves.append(
            TopMove(
                move=m.get("move", "pass"),
                order=m.get("order", len(top_moves)),
                winrate=round(m.get("winrate", 0.0), 4),
                score_lead=round(m.get("scoreLead", 0.0), 2),
                visits=m.get("visits", 0),
                pv=m.get("pv", []),
                prior=round(m.get("prior", 0.0), 4),
                lcb=round(m.get("lcb", 0.0), 4),
                score_stdev=round(m.get("scoreStdev", 0.0), 2),
            )
        )

    return CoachEvaluateResponse(
        root=root,
        top_moves=top_moves,
        ownership=ownership,
        ownership_stdev=ownership_stdev,
        policy=policy,
    )


# --- Helpers ---

def _job_response(job: dict) -> dict:
    if job["status"] == "failed":
        return {"job_id": job["job_id"], "status": "failed", "error": job.get("error")}

    result = json.loads(job["result_json"])
    return {
        "job_id": job["job_id"],
        "status": "complete",
        "progress": 1.0,
        "win_rates": result["win_rates"],
        "score_leads": result["score_leads"],
        "key_moments": result["key_moments"],
        "summary": result["summary"],
    }


async def _sse_stream(job_id: str):
    q = register_listener(job_id)
    try:
        while True:
            try:
                data = await asyncio.wait_for(q.get(), timeout=30)
            except asyncio.TimeoutError:
                # Send a heartbeat to keep the connection alive
                yield ": heartbeat\n\n"
                continue

            yield f"data: {json.dumps(data)}\n\n"

            if data.get("status") in ("complete", "failed"):
                # If complete, send the full result as a final event
                if data.get("status") == "complete":
                    job = await get_job(job_id)
                    if job:
                        yield f"data: {json.dumps(_job_response(job))}\n\n"
                break
    finally:
        unregister_listener(job_id, q)

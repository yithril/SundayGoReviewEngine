from pydantic import BaseModel
from typing import Optional
from enum import Enum


class AnalysisMode(str, Enum):
    quick = "quick"
    standard = "standard"
    deep = "deep"


class Rank(str, Enum):
    k20 = "20k"
    k15 = "15k"
    k10 = "10k"
    k9  = "9k"
    k8  = "8k"
    k7  = "7k"
    k6  = "6k"
    k5  = "5k"
    k4  = "4k"
    k3  = "3k"
    k2  = "2k"
    k1  = "1k"
    d1  = "1d"
    d2  = "2d"
    d3  = "3d"
    d4  = "4d"
    d5  = "5d"
    d6  = "6d"
    d7  = "7d"
    d8  = "8d"
    d9  = "9d"


class SuggestRequest(BaseModel):
    moves: list[list[str]]  # e.g. [["B","D4"], ["W","Q16"]]
    rank: Rank
    board_size: int = 19    # 9, 13, or 19
    komi: float = 6.5


class SuggestResponse(BaseModel):
    move: str       # e.g. "R16" or "pass"
    win_rate: float # from Black's perspective
    rank: str       # echoed back


class AnalyzeRequest(BaseModel):
    sgf: str
    mode: AnalysisMode = AnalysisMode.quick


class SubmitResponse(BaseModel):
    job_id: str
    status: str
    queue_position: int
    estimated_wait_seconds: int


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: float
    win_rates: Optional[list[float]] = None
    score_leads: Optional[list[float]] = None
    key_moments: Optional[list[int]] = None
    summary: Optional[dict] = None
    error: Optional[str] = None


class MoveDetailResponse(BaseModel):
    move_number: int
    win_rate_before: float
    win_rate_after: float
    score_lead_before: float
    score_lead_after: float
    score_swing: float
    best_move: str
    top_moves: list[dict]
    ownership: Optional[list[float]] = None


# --- Coaching evaluate (same moves format as SuggestRequest) ---

class CoachEvaluateRequest(BaseModel):
    moves: list[list[str]]  # same as /suggest: [["B","D4"], ["W","Q16"]]
    board_size: int  # 9, 13, or 19
    komi: float = 6.5
    player_color: str  # "B" or "W"


class TopMove(BaseModel):
    move: str
    order: int
    winrate: float
    score_lead: float
    visits: int
    pv: list[str]
    prior: float
    lcb: float
    score_stdev: float


class CoachEvaluateResponse(BaseModel):
    root: dict  # winrate, score_lead, current_player, visits
    top_moves: list[TopMove]  # capped at 5
    ownership: list[float]  # 361 floats, +1=Black -1=White
    ownership_stdev: list[float]
    policy: list[float]  # 362 floats

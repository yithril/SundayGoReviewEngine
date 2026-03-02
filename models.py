from pydantic import BaseModel
from typing import Optional
from enum import Enum


class AnalysisMode(str, Enum):
    quick = "quick"
    standard = "standard"
    deep = "deep"


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

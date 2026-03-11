# RunPod Worker Migration Guide

**Purpose:** This document gives a Python AI everything it needs to rewrite the
AI Game Review pipeline in Python on a RunPod GPU pod, running alongside the
native KataGo binary. It is written for the AI that will do the porting work —
not for human readers — so it is exhaustive and precise.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [What Stays in Next.js](#2-what-stays-in-nextjs)
3. [Supabase Job Queue Table](#3-supabase-job-queue-table)
4. [New Next.js API Routes](#4-new-nextjs-api-routes)
5. [Frontend Change in ai-review-explorer.tsx](#5-frontend-change)
6. [KataGo Native Analysis Protocol](#6-katago-native-analysis-protocol)
7. [Pipeline: All 6 Phases](#7-pipeline-all-6-phases)
8. [All Data Types (as Python)](#8-all-data-types-as-python)
9. [All Threshold Constants](#9-all-threshold-constants)
10. [Board State Representation](#10-board-state-representation)
11. [SGF Parser](#11-sgf-parser)
12. [Move Classifier](#12-move-classifier)
13. [Skill Feedback System](#13-skill-feedback-system)
14. [Event Reconciler](#14-event-reconciler)
15. [Template Generator](#15-template-generator)
16. [Saving to Supabase](#16-saving-to-supabase)
17. [Sending the Email via Resend](#17-sending-the-email-via-resend)
18. [Worker Polling Loop](#18-worker-polling-loop)
19. [Environment Variables](#19-environment-variables)
20. [What NOT to Touch](#20-what-not-to-touch)

---

## 1. System Overview

```
Browser (Next.js)                   RunPod Pod
─────────────────                   ──────────
User uploads SGF
  POST /api/ai-reviews/submit
    → inserts game_review_jobs row
    ← returns { jobId }
  shows "check your email" UI

                                    Python worker polls Supabase
                                    every 5s for pending jobs

                                    For each job:
                                      1. parse SGF
                                      2. run KataGo analysis (GPU)
                                      3. move classification
                                      4. skill event detection
                                      5. build ReviewReport
                                      6. save to game_reviews table
                                      7. send HTML email via Resend
                                      8. mark job completed
```

The Python worker is the only new code you write. It runs as a persistent process
on the RunPod pod (e.g. `python worker.py` in a `while True` loop). It never
serves HTTP — it only reads from and writes to Supabase, runs KataGo as a
subprocess, and calls the Resend API.

---

## 2. What Stays in Next.js

The following files are **not ported** — they stay in the Next.js app unchanged:

| File | Why it stays |
|---|---|
| `src/domains/bot-game/**` | Client-side, uses ONNX humanSL model, entirely separate |
| `src/domains/katago-web/**` | ONNX Web Worker for bot game only |
| `src/domains/ai-reviews/components/**` | React UI components |
| `src/domains/ai-reviews/hooks/use-game-review.ts` | Replaced by the Python worker; the hook itself is left in place but its `startReview()` call is no longer invoked for new reviews |
| `src/app/api/game-reviews/**` | Existing routes for fetching/displaying saved reviews — unchanged |

The Next.js app still handles:
- User auth (Supabase)
- Enqueuing jobs (`POST /api/ai-reviews/submit`)
- Serving the saved review viewer (the existing `/reviews/[id]` page)
- Displaying past reviews

---

## 3. Supabase Job Queue Table

Create this table in the Supabase dashboard (SQL editor):

```sql
CREATE TABLE game_review_jobs (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID REFERENCES auth.users,
  email            TEXT NOT NULL,
  sgf              TEXT NOT NULL,
  rank_band        TEXT NOT NULL,
  player_color     TEXT NOT NULL,
  status           TEXT NOT NULL DEFAULT 'pending',
  -- status values: 'pending' | 'processing' | 'completed' | 'failed'
  error_message    TEXT,
  review_id        UUID,   -- filled in when completed (references game_reviews.id)
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at       TIMESTAMPTZ,
  completed_at     TIMESTAMPTZ
);

-- Index for efficient polling
CREATE INDEX game_review_jobs_status_created
  ON game_review_jobs (status, created_at);
```

**`rank_band` values** (these come from the frontend exactly as written):
`"novice"` | `"beginner"` | `"intermediate"` | `"advanced"` | `"dan"`

**`player_color` values**: `"B"` | `"W"`

---

## 4. New Next.js API Routes

These need to be added to the Next.js app by the Next.js developer. Documented
here so the Python worker knows exactly what data to expect.

### POST /api/ai-reviews/submit

Request body (JSON):
```json
{
  "sgf": "(;GM[1]FF[4]...)",
  "rankBand": "beginner",
  "playerColor": "B"
}
```

Response:
```json
{ "jobId": "uuid-here" }
```

Server-side logic (Next.js):
1. Get user from Supabase session
2. Get user email from `auth.users`
3. Basic SGF validation (check it parses, has moves)
4. Insert row into `game_review_jobs`
5. Return `{ jobId }`

### GET /api/ai-reviews/jobs/[id]

Response:
```json
{
  "status": "pending" | "processing" | "completed" | "failed",
  "reviewId": "uuid-or-null",
  "errorMessage": "null-or-string"
}
```

The frontend can poll this to auto-redirect when done.

---

## 5. Frontend Change

In `src/domains/ai-reviews/components/explorer/ai-review-explorer.tsx`, the
change is minimal. The existing code calls `useGameReview()` and `startReview()`.
After the change:

- The SGF upload form still exists
- On submit, instead of calling `startReview()`, it calls
  `POST /api/ai-reviews/submit` with the SGF, rankBand, playerColor
- The analysis progress screen is replaced with a confirmation:
  "Your review is being processed. We'll email you at [email] when it's ready."
- Optionally: poll `GET /api/ai-reviews/jobs/[jobId]` every 10s and redirect
  to `/reviews/[reviewId]` when status becomes `"completed"`

The `EngineLoadingScreen`, `useKatagoEngine`, and the ONNX worker are **not
touched** — they're still used by the position analysis panel (`usePositionAnalysis`)
which remains active for the SGF explorer view.

---

## 6. KataGo Native Analysis Protocol

KataGo's analysis mode accepts JSON on stdin and returns JSON on stdout.

### Start KataGo

```bash
katago analysis \
  -config /path/to/analysis.cfg \
  -model /path/to/kata1-model.bin.gz
```

KataGo prints a header line then waits for newline-delimited JSON queries.

### Query Format

Send one JSON object per line:

```json
{
  "id": "move-10",
  "initialPlayer": "B",
  "moves": [["B","D4"],["W","Q16"],["B","Q4"]],
  "rules": "chinese",
  "komi": 7.5,
  "boardXSize": 19,
  "boardYSize": 19,
  "analyzeTurns": [3],
  "maxVisits": 400,
  "includeOwnership": true,
  "includePolicy": false
}
```

**Field notes:**
- `"id"` — any string; echoed back in the response so you can match async results
- `"moves"` — list of `[color, gtp_coordinate]` pairs up to but NOT including the
  position you want analyzed. So `analyzeTurns: [N]` means "analyze after N moves
  have been played." For move index `i` (0-based), pass `moves[0..i]` (i+1 moves)
  and `analyzeTurns: [i+1]`. Wait — simpler: pass all moves up to and including
  index `i` in the `moves` array and set `analyzeTurns: [i+1]` to analyze that turn.
  Actually the cleanest approach: for move at index `i`, pass `moves[0..i]` as the
  sequence (length i+1), and set `analyzeTurns: [i+1]`. KataGo will analyze after
  those `i+1` moves.
- `"rules"` — use `"chinese"` for standard play
- `"komi"` — parsed from the SGF `KM[...]` tag; default 7.5 for Chinese rules
- `"maxVisits"` — 400 is fast and high quality on GPU; can go to 800 for more accuracy
- `"includeOwnership": true` — required; the ownership array drives moyo and
  territory detectors

### Response Format

KataGo writes one JSON object per line:

```json
{
  "id": "move-10",
  "turnNumber": 11,
  "moveInfos": [
    {
      "move": "R4",
      "visits": 215,
      "winrate": 0.623,
      "scoreLead": 4.1,
      "prior": 0.18,
      "order": 0
    },
    ...
  ],
  "rootInfo": {
    "winrate": 0.612,
    "scoreLead": 3.8,
    "visits": 400
  },
  "ownership": [0.82, -0.74, ..., 0.91]
}
```

**What you extract per query:**
- `winRate` = `rootInfo.winrate` (Black's win probability, 0.0–1.0)
- `scoreLead` = `rootInfo.scoreLead` (positive = Black ahead)
- `topMoves` = `moveInfos[0..4]` sorted by `order`, each with `.move`, `.winrate`,
  `.scoreLead`, `.prior`, `.visits`
- `bestMove` = `moveInfos[0].move` (the top suggestion)
- `ownership` = flat array of length `boardXSize * boardYSize`, row-major (y=0 is
  the top row). Values range -1.0 (White) to +1.0 (Black).

### Batching

For efficiency, you can write all N queries (one per sampled move) to stdin in a
tight loop, then read all N responses. KataGo processes them and writes responses
as they complete (possibly out of order — use the `id` field to match them).

```python
import subprocess, json

proc = subprocess.Popen(
    ["katago", "analysis", "-config", cfg, "-model", model],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    text=True,
    bufsize=1,  # line-buffered
)

# Write all queries
for query in queries:
    proc.stdin.write(json.dumps(query) + "\n")
    proc.stdin.flush()

# Read all responses
results = {}
for _ in range(len(queries)):
    line = proc.stdout.readline()
    resp = json.loads(line)
    results[resp["id"]] = resp
```

---

## 7. Pipeline: All 6 Phases

This is the direct port of `use-game-review.ts → startReview()`. The Python
function signature:

```python
def run_review(sgf: str, rank_band: str, player_color: str) -> ReviewReport:
    ...
```

### Phase 1 — Parse SGF

See [Section 11](#11-sgf-parser) for the SGF parser spec.

Output: `moves: list[MoveEntry]`, `board_size: int`, `komi: float`,
`player_black: str`, `player_white: str`

Raise an exception if `len(moves) == 0`.

### Phase 2 — Sparse KataGo Sampling

Constants (from `review-constants.ts`):
```
KATAGO_ANALYSIS_INTERVAL = 10
EARLY_TERMINATION_THRESHOLD = 0.90
EARLY_TERMINATION_CONSECUTIVE_MOVES = 5
EARLY_TERMINATION_MIN_MOVES = 120
```

Logic:
```
sample_indices = [i for i in range(total_moves)
                  if i % KATAGO_ANALYSIS_INTERVAL == 0 or i == total_moves - 1]

For each sample index i:
  - Build KataGo query with moves[0..i+1], analyzeTurns=[i+1]
  - Store result: { win_rate, score_lead, top_moves, best_move, ownership }

After each sampled result, check early termination:
  - If i >= EARLY_TERMINATION_MIN_MOVES
    AND (win_rate >= 0.90 OR win_rate <= 0.10):
      decisive_count += 1
      if decisive_count >= 5:
        early_termination_at = i
        break
  else:
    decisive_count = 0

analyzed_move_count = early_termination_at + 1  (or total_moves if no early stop)
```

Send queries in batch for speed (see Section 6).

### Phase 3 — Linear Interpolation

For every move index `0..analyzed_move_count`:
- If it was sampled → use the sampled win_rate / score_lead directly
- If not sampled → linearly interpolate between the nearest sampled anchor
  points below and above it

```python
def interpolated_at(move_index, field, sampled_results):
    indices = sorted(sampled_results.keys())
    lo = indices[0]
    hi = indices[-1]
    for idx in indices:
        if idx <= move_index:
            lo = idx
        else:
            hi = idx
            break
    lo_val = sampled_results[lo][field]
    hi_val = sampled_results[hi][field]
    if lo == hi:
        return lo_val
    t = (move_index - lo) / (hi - lo)
    return lo_val + t * (hi_val - lo_val)
```

### Phase 4 — Hot Segment Detection

```
HOT_SEGMENT_WIN_RATE_THRESHOLD = 0.15
opening_cutoff = get_opening_cutoff(board_size)
  # 40 for 19x19, 20 for 13x13, 10 for 9x9  (see Section 9)

hot_moves = set()

# Opening is always hot
for i in range(min(opening_cutoff, analyzed_move_count)):
    hot_moves.add(i)

# Intervals with large win-rate swings are hot
sorted_sample_indices = sorted(sampled_results.keys())
for s in range(len(sorted_sample_indices) - 1):
    lo = sorted_sample_indices[s]
    hi = sorted_sample_indices[s+1]
    if hi >= analyzed_move_count:
        break
    lo_wr = sampled_results[lo]['win_rate']
    hi_wr = sampled_results[hi]['win_rate']
    if abs(hi_wr - lo_wr) >= HOT_SEGMENT_WIN_RATE_THRESHOLD:
        for m in range(lo, hi + 1):
            hot_moves.add(m)
```

### Phase 5 — Build MoveAnalysis[] + Event Detection

For each move index `i` in `0..analyzed_move_count`:

```python
color, label = moves[i]   # e.g. ("B", "D4")
sampled = sampled_results.get(i)
is_interpolated = sampled is None

win_rate_after = sampled['win_rate'] if sampled else interpolated_at(i, 'win_rate')
score_after = sampled['score_lead'] if sampled else interpolated_at(i, 'score_lead')
win_rate_before = prev_win_rate   # from previous iteration, start = 0.5
score_before = prev_score         # from previous iteration, start = 0.0

# Win rate delta is from the PLAYED PLAYER's perspective (positive = good for them)
if color == "B":
    win_rate_delta = win_rate_after - win_rate_before
    score_delta = score_after - score_before
else:
    win_rate_delta = win_rate_before - win_rate_after
    score_delta = score_before - score_after

classification = classify_move(win_rate_delta, rank_band)

# Advance board state (see Section 10)
prev_board_state = current_board_state
current_board_state = place_stone(current_board_state, label, color, board_size)

analysis = MoveAnalysis(
    move_index=i,
    moves=moves[:i+1],
    played_move=label,
    player_color=color,
    win_rate_before=win_rate_before,
    win_rate_after=win_rate_after,
    score_before=score_before,
    score_after=score_after,
    win_rate_delta=win_rate_delta,
    score_delta=score_delta,
    ownership_after=sampled['ownership'] if sampled else [],
    best_move=sampled['best_move'] if sampled else "",
    top_moves=sampled['top_moves'] if sampled else [],
    classification=classification,
    events=[],
    is_interpolated=is_interpolated,
    prev_board_state=prev_board_state,
    board_state=current_board_state,
)

# Run always-on detectors
always_fb = detect_always_run_feedback(analysis, rank_band, board_size)
# Run hot-segment detectors only if this move is hot
hot_fb = []
if i in hot_moves:
    hot_fb = detect_hot_segment_feedback(analysis, rank_band, board_size)

analysis.events = [to_move_event(fb) for fb in always_fb + hot_fb]
all_feedback.extend(always_fb + hot_fb)
move_analyses.append(analysis)
win_rates.append(win_rate_after)
score_leads.append(score_after)

prev_win_rate = win_rate_after
prev_score = score_after
```

### Phase 6 — Cap, Post-process, Assemble Report

```python
# Cap each quality bucket at 5 (by largest |win_rate_delta|)
MOVE_QUALITY_CAP_PER_CATEGORY = 5
CAPPED_CATEGORIES = ["brilliant","great","good","inaccuracy","mistake","blunder"]
for cls in CAPPED_CATEGORIES:
    bucket = [a for a in move_analyses if a.classification == cls]
    bucket.sort(key=lambda a: abs(a.win_rate_delta), reverse=True)
    for a in bucket[MOVE_QUALITY_CAP_PER_CATEGORY:]:
        a.classification = "neutral"

# Full-game feedback (endgame, phase snapshots)
full_game_fb = detect_full_game_feedback(move_analyses, rank_band, board_size)
all_feedback.extend(full_game_fb)

# Build highlights
did_well, could_improve = build_key_moments_from_events(
    all_feedback, move_analyses, board_size, rank_band
)

# Skill scores
band_skills = SKILLS_BY_BAND[rank_band]  # see Section 13
observed_skill_ids = {fb.skill_id for fb in all_feedback}
observed_skills = [s for s in band_skills if s['id'] in observed_skill_ids]
skills_to_score = observed_skills if observed_skills else band_skills[:3]

skill_scores = []
for skill in skills_to_score:
    score = stub_skill_score(skill['id'], all_feedback)
    fallback = skill.get('description', 'Keep practicing this skill.')
    comment = pick_skill_comment(skill['id'], all_feedback, fallback)
    skill_scores.append(SkillScore(
        skill_id=skill['id'],
        label=skill['label'],
        score=score,
        comment=comment,
        occurrences=sum(1 for fb in all_feedback if fb.skill_id == skill['id']),
    ))

game_summary = build_game_summary(move_analyses, player_color, board_size, win_rates)
practice_areas = build_practice_areas(skill_scores)

return ReviewReport(
    game_summary=game_summary,
    move_analyses=move_analyses,
    raw_events=[to_move_event(fb) for fb in all_feedback],
    did_well_moments=did_well,
    could_improve_moments=could_improve,
    skill_scores=skill_scores,
    practice_areas=practice_areas,
    win_rates=win_rates,
    score_leads=score_leads,
    total_moves=len(move_analyses),
    player_color=player_color,
    rank_band=rank_band,
    board_size=board_size,
)
```

---

## 8. All Data Types (as Python)

```python
from dataclasses import dataclass, field
from typing import Literal, Optional

MoveClassification = Literal[
    "brilliant", "great", "good", "neutral",
    "inaccuracy", "mistake", "blunder"
]
MoveEventSeverity = Literal["positive", "minor", "significant", "critical"]
KeyMomentLabel = Literal[
    "brilliant", "great", "turning_point",
    "inaccuracy", "mistake", "blunder"
]
ExplanationMode = Literal["skill", "turning_point", "tactical"]
Color = Literal["B", "W"]
# MoveEntry = (color, gtp_label)  e.g. ("B", "D4") or ("B", "pass")
MoveEntry = tuple[Color, str]

@dataclass
class MoveEvent:
    move_index: int
    event_type: str          # templateKey string e.g. "counting_liberties/self_atari"
    severity: MoveEventSeverity
    actor_color: Optional[Color] = None
    payload: dict = field(default_factory=dict)

@dataclass
class MoveCandidate:
    move: str           # GTP label e.g. "R4"
    win_rate: float
    score_lead: float
    prior: float
    visits: int

@dataclass
class MoveAnalysis:
    move_index: int
    moves: list[MoveEntry]
    played_move: str
    player_color: Color
    win_rate_before: float
    win_rate_after: float
    score_before: float
    score_after: float
    win_rate_delta: float       # from played player's perspective
    score_delta: float          # from played player's perspective
    ownership_after: list[float]  # flat array len board_size^2, or [] if interpolated
    best_move: str
    top_moves: list[MoveCandidate]
    classification: MoveClassification
    events: list[MoveEvent]
    is_interpolated: bool
    prev_board_state: "BoardState"
    board_state: "BoardState"

@dataclass
class KeyMoment:
    move_index: int
    label: KeyMomentLabel
    explanation: Optional[str]   # None for "tactical" mode
    explanation_mode: ExplanationMode
    skill_tag: Optional[str]     # GoSkillId or None
    moves: list[MoveEntry]

@dataclass
class SkillScore:
    skill_id: str
    label: str
    score: int          # 0-100
    comment: str
    occurrences: int

@dataclass
class ReviewReport:
    game_summary: str
    move_analyses: list[MoveAnalysis]
    raw_events: list[MoveEvent]
    did_well_moments: list[KeyMoment]
    could_improve_moments: list[KeyMoment]
    skill_scores: list[SkillScore]
    practice_areas: list[str]   # list of GoSkillId
    win_rates: list[float]      # Black's win rate per move index
    score_leads: list[float]
    total_moves: int
    player_color: Color
    rank_band: str
    board_size: int

@dataclass
class DetectedFeedback:
    skill_id: str
    move_index: int
    severity: MoveEventSeverity
    template_key: str
    text: str           # interpolated template text
```

---

## 9. All Threshold Constants

```python
# Early termination
EARLY_TERMINATION_THRESHOLD = 0.90
EARLY_TERMINATION_CONSECUTIVE_MOVES = 5
EARLY_TERMINATION_MIN_MOVES = 120

# Highlight caps
MAX_HIGHLIGHT_MOMENTS_PER_SECTION = 3
TURNING_POINT_FALLBACK_DELTA = 0.15

# Min delta for a canonical event to become a highlight card
MIN_DELTA_FOR_HIGHLIGHT = {
    "novice":       0.04,
    "beginner":     0.03,
    "intermediate": 0.02,
    "advanced":     0.02,
    "dan":          0.015,
}

# Move quality cap per category
MOVE_QUALITY_CAP_PER_CATEGORY = 5

# Move classification thresholds (positive = good for player)
CLASSIFY_BRILLIANT_MIN_DELTA = {
    "novice": 0.10, "beginner": 0.12, "intermediate": 0.15,
    "advanced": 0.15, "dan": 0.15,
}
CLASSIFY_GREAT_MIN_DELTA = {
    "novice": 0.05, "beginner": 0.06, "intermediate": 0.08,
    "advanced": 0.08, "dan": 0.08,
}
CLASSIFY_GOOD_MIN_DELTA = {
    "novice": 0.015, "beginner": 0.02, "intermediate": 0.03,
    "advanced": 0.03, "dan": 0.03,
}
CLASSIFY_INACCURACY_MAX_DELTA = -0.03   # <= -3%
CLASSIFY_MISTAKE_MAX_DELTA    = -0.08   # <= -8%
CLASSIFY_BLUNDER_MAX_DELTA    = -0.15   # <= -15%

# Score context
SCORE_CONTEXT_MIN_POINTS = 1.0

# Sampling
KATAGO_ANALYSIS_INTERVAL = 10
HOT_SEGMENT_WIN_RATE_THRESHOLD = 0.15

# Opening cutoffs by board size (move index, 0-based)
def get_opening_cutoff(board_size: int) -> int:
    if board_size == 19: return 40
    if board_size == 13: return 20
    return 10   # 9x9

# Game phase detection (used by template_generator and endgame detectors)
def get_game_phase(move_number: int, board_size: int) -> str:
    # move_number is 1-based
    cutoff = get_opening_cutoff(board_size)
    total_est = board_size * board_size * 0.6
    if move_number <= cutoff:
        return "opening"
    if move_number <= total_est * 0.6:
        return "middle"
    return "endgame"
```

---

## 10. Board State Representation

The TypeScript app uses a `BoardState` object with a `stones` array. For the
Python port, you need a simple board representation that supports:

1. `place_stone(board_state, gtp_label, color, board_size) → BoardState`
   — places a stone, removes captured groups, returns new state
2. `get_stone(board_state, x, y) → "B" | "W" | None`
3. `get_liberties(board_state, x, y, board_size) → int`
   — counts liberties of the group containing the stone at (x, y)
4. `get_group(board_state, x, y) → list[(x,y)]`
   — flood-fill all connected same-color stones

### Coordinate Conversion (GTP label → (x, y))

GTP uses letters A–T skipping I, with A=0 left column. Row numbers count from
bottom (row 1 = y = board_size - 1).

```python
LETTERS_SKIP_I = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

def gtp_to_xy(label: str, board_size: int) -> tuple[int, int] | None:
    if label.lower() == "pass":
        return None
    col_char = label[0].upper()
    row_num = int(label[1:])
    x = LETTERS_SKIP_I.index(col_char)
    y = board_size - row_num   # y=0 is the top row
    return (x, y)

def xy_to_gtp(x: int, y: int, board_size: int) -> str:
    col_char = LETTERS_SKIP_I[x]
    row_num = board_size - y
    return f"{col_char}{row_num}"
```

### Minimal BoardState

```python
@dataclass
class BoardState:
    size: int
    # stones[y][x] = "B" | "W" | None
    stones: list[list[Optional[str]]]
    next_player: Color = "B"
    # last_captured: count of stones captured on the previous move (for ko detection)
    last_captured: int = 0
    # ko_point: intersection where recapture is currently forbidden
    ko_point: Optional[tuple[int, int]] = None

def create_empty_board(size: int) -> BoardState:
    return BoardState(
        size=size,
        stones=[[None]*size for _ in range(size)],
        next_player="B",
    )
```

### Capture Logic

When placing a stone at (x, y) with `color`:
1. Place the stone on the board (tentatively)
2. For each orthogonal neighbor of opposite color, check if that group now has
   zero liberties → if so, remove all stones in that group (capture)
3. Count total captured stones → store as `last_captured`
4. Check if the played stone's own group has zero liberties → if so, the move
   is suicide (illegal in Chinese rules — do not place, raise error or skip)
5. Set `next_player` to the other color
6. Update `ko_point`: if `last_captured == 1` and the played stone has exactly
   1 liberty, the ko point is that single liberty of the played group

The detectors only need `stones`, `size`, `last_captured`, and `ko_point`. You
do not need full SGF game tree logic — just the incremental one-move advance.

---

## 11. SGF Parser

Port of the `parseSgfMoves()` function in `use-game-review.ts`:

```python
import re

LETTERS_SKIP_I = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

def parse_sgf_moves(sgf: str) -> dict:
    size_match = re.search(r'SZ\[(\d+)\]', sgf)
    board_size = int(size_match.group(1)) if size_match else 19

    komi_match = re.search(r'KM\[([0-9.]+)\]', sgf)
    komi = float(komi_match.group(1)) if komi_match else 6.5

    pb_match = re.search(r'PB\[([^\]]*)\]', sgf)
    pw_match = re.search(r'PW\[([^\]]*)\]', sgf)

    moves = []
    for m in re.finditer(r';([BW])\[([a-s]{0,2})\]', sgf):
        color = m.group(1)
        coords = m.group(2)
        if coords == "":
            moves.append((color, "pass"))
            continue
        cx = ord(coords[0]) - ord('a')
        cy = ord(coords[1]) - ord('a')
        col_char = LETTERS_SKIP_I[cx + 1 if cx >= 8 else cx]
        row_num = board_size - cy
        moves.append((color, f"{col_char}{row_num}"))

    return {
        "moves": moves,
        "board_size": board_size,
        "komi": komi,
        "player_black": pb_match.group(1) if pb_match else "Black",
        "player_white": pw_match.group(1) if pw_match else "White",
    }
```

**Note:** The SGF coordinate system uses lowercase `aa`=top-left. The `cx >= 8`
check skips the letter I in GTP notation (matching the TypeScript source exactly).

---

## 12. Move Classifier

```python
def classify_move(win_rate_delta: float, rank_band: str) -> MoveClassification:
    if win_rate_delta >= CLASSIFY_BRILLIANT_MIN_DELTA[rank_band]: return "brilliant"
    if win_rate_delta >= CLASSIFY_GREAT_MIN_DELTA[rank_band]:     return "great"
    if win_rate_delta >= CLASSIFY_GOOD_MIN_DELTA[rank_band]:      return "good"
    if win_rate_delta <= CLASSIFY_BLUNDER_MAX_DELTA:              return "blunder"
    if win_rate_delta <= CLASSIFY_MISTAKE_MAX_DELTA:              return "mistake"
    if win_rate_delta <= CLASSIFY_INACCURACY_MAX_DELTA:           return "inaccuracy"
    return "neutral"
```

---

## 13. Skill Feedback System

### Skill Bands and IDs

Each `rank_band` has a set of relevant skills. The system only fires triggers
for skills in the played band's allowed list.

```python
# Skill definitions per band
SKILLS_BY_BAND = {
    "novice": [
        {"id": "counting_liberties",      "label": "Counting Liberties",      "description": "Count the breathing spaces around your groups before playing."},
        {"id": "basic_shape_knowledge",   "label": "Basic Shape Knowledge",   "description": "Learn efficient shapes: avoid empty triangles, use tiger's mouth and bamboo joint."},
        {"id": "defending_cutting_points","label": "Defending Cutting Points","description": "Spot where your stones can be split and close those gaps."},
    ],
    "beginner": [
        {"id": "counting_liberties",      "label": "Counting Liberties",      "description": "Count liberties carefully to win capturing races and avoid self-atari."},
        {"id": "ladders",                 "label": "Ladders",                  "description": "Read ladders to the edge before playing them."},
        {"id": "basic_shape_knowledge",   "label": "Basic Shape Knowledge",   "description": "Use solid shapes; avoid the empty triangle and recognize vulnerable knight's moves."},
        {"id": "corner_moves_in_the_opening","label":"Corner Moves in the Opening","description": "Claim corners early and approach correctly."},
        {"id": "life_and_death",          "label": "Life and Death",           "description": "Make two genuine eyes for your groups; attack opponent groups that lack eyes."},
        {"id": "defending_cutting_points","label": "Defending Cutting Points","description": "Protect cut points before the opponent exploits them."},
        {"id": "capturing_races",         "label": "Capturing Races",          "description": "Count liberties in races; use net and throw-in techniques."},
        {"id": "ko_fighting",             "label": "Ko Fighting",              "description": "Make and respond to ko threats correctly."},
        {"id": "shortage_of_liberties",   "label": "Shortage of Liberties",   "description": "Use throw-in and snapback; avoid attempting captures when your group has fewer liberties."},
        {"id": "end_game",                "label": "Endgame",                  "description": "Prioritize sente endgame moves and don't leave large gote moves unplayed."},
        {"id": "counting_territory",      "label": "Counting Territory",       "description": "Track the score at key phase transitions."},
    ],
    "intermediate": [],   # not yet defined — use beginner skills as fallback
    "advanced":     [],
    "dan":          [],
}
```

### How `isSkillAllowedForLevel` Works

A skill is allowed for a rank band if it appears in `SKILLS_BY_BAND[rank_band]`.
"novice" skills are also allowed at "beginner" and higher (upward compatibility).

```python
SKILL_BAND_ORDER = ["novice", "beginner", "intermediate", "advanced", "dan"]

def is_skill_allowed_for_level(rank_band: str, skill_id: str) -> bool:
    band_idx = SKILL_BAND_ORDER.index(rank_band)
    for i in range(band_idx + 1):
        band = SKILL_BAND_ORDER[i]
        if any(s['id'] == skill_id for s in SKILLS_BY_BAND.get(band, [])):
            return True
    return False
```

### Trigger Structure

Each trigger is a dict:
```python
{
    "skill_id": str,
    "allowed_bands": list[str],
    "hot_segment_only": bool,   # default False
    "detect": Callable[[list[MoveAnalysis], int], list[TriggerResult]]
}
```

Each detector function returns a list of `TriggerResult`:
```python
@dataclass
class TriggerResult:
    move_index: int
    severity: MoveEventSeverity
    template_key: str
    params: dict[str, str]
```

### All Per-Move Triggers

Below is the complete list. Each entry includes:
- `skill_id` — which skill it belongs to
- `allowed_bands` — only fires if `rank_band` is in this list (or higher via upward compat)
- `hot_segment_only` — True means only evaluate on moves in `hot_moves` set
- Detection logic — what to check on the `MoveAnalysis`

---

**1. Self-Atari** (`counting_liberties/self_atari`)
- `skill_id`: `"counting_liberties"`
- `allowed_bands`: `["novice"]`
- Detection: After placing the stone, the played group has exactly 1 liberty
  (i.e. is in atari immediately after the move). The stone is NOT part of a
  capture (last_captured == 0).
- `severity`: `"significant"`
- `params`: `{n, coord, best_move, player}`

---

**2. Failed Ladder** (`ladders/failed_ladder`)
- `skill_id`: `"ladders"`
- `allowed_bands`: `["beginner"]`
- Detection: The played move starts a chase sequence where the chased stone
  has 2 liberties that form a diagonal path toward an edge, but a friendly
  stone interrupts the path. In practice: after the move, the opponent's
  group that was just put in atari has 2 liberties and those liberties zigzag
  toward the edge AND there is an opponent stone in the ladder path. This
  detector is complex — the TypeScript source delegates to `detectClientBlunder`
  with key `"blunder_ladder"`. Implement a basic ladder-break check:
  simulate the ladder sequence and see if it breaks before the edge.
- `severity`: `"significant"`
- `params`: `{n, coord, player}`

---

**3. Empty Triangle** (`basic_shape_knowledge/empty_triangle`)
- `skill_id`: `"basic_shape_knowledge"`
- `allowed_bands`: `["novice"]`
- Detection: After the move, the player's stones include an L-shape where
  the inner corner is empty. Specifically: the played stone at (x,y), plus
  two of its orthogonal neighbors of the same color, where those two
  neighbors are also adjacent to each other orthogonally (forming an L),
  and the inner corner of the L is empty (no stone of either color).
- `hot_segment_only`: False
- `severity`: `"minor"`
- `params`: `{n, coord, player}`

---

**4. Large Score Swing in Opening** (`corner_moves_in_the_opening/early_loss`)
- `skill_id`: `"corner_moves_in_the_opening"`
- `allowed_bands`: `["beginner"]`
- `hot_segment_only`: True
- Detection: `move_index <= opening_cutoff` AND `win_rate_delta <= -0.10`
- `severity`: `"significant"`
- `params`: `{n, coord, best_move, player}`

---

**5. Good Attack** (`life_and_death/good_attack`)
- `skill_id`: `"life_and_death"`
- `allowed_bands`: `["beginner"]`
- Detection: After the move, an opponent group that previously had >= 3
  liberties now has <= 1 liberty (put in atari). The group was not already
  in atari before the move. Compares `prev_board_state` vs `board_state`.
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**6. Good Defense / Escape** (`counting_liberties/good_defense`)
- `skill_id`: `"counting_liberties"`
- `allowed_bands`: `["novice"]`
- Detection: A player's group that had 1 liberty in `prev_board_state` now
  has >= 3 liberties in `board_state` (the group escaped atari).
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**7. Strong Connection** (`defending_cutting_points/good_connection`)
- `skill_id`: `"defending_cutting_points"`
- `allowed_bands`: `["novice"]`
- Detection: Two separate player groups (distinct connected components) in
  `prev_board_state` are now one group in `board_state` (they merged via
  the played stone).
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**8. Life Secured** (`life_and_death/clean_life`)
- `skill_id`: `"life_and_death"`
- `allowed_bands`: `["beginner"]`
- Detection: A player group that had 0 or 1 eye-spaces in `prev_board_state`
  now has 2 genuine eye-spaces in `board_state`. (Eye detection: an empty
  point completely surrounded by same-color stones on all orthogonal sides,
  where at most 1 diagonal is occupied by the opponent.)
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**9. Big Capture** (`capturing_races/big_capture`)
- `skill_id`: `"capturing_races"`
- `allowed_bands`: `["beginner"]`
- Detection: Approximate capture size from `win_rate_delta`:
  if `win_rate_delta > 0.08` → approx 6 stones captured;
  if `win_rate_delta > 0.05` → approx 4 stones captured;
  else → 0.
  Fires only if approx captured >= 4 on a 19x19 (threshold scales: >= 3 on
  13x13, >= 2 on 9x9).
- `severity`: `"positive"`
- `params`: `{n, coord, player, points}` — `points` = `f"~{round(abs(score_delta))} pts"` if `abs(score_delta) >= 1.0` else `""`

---

**10. Tiger's Mouth** (`basic_shape_knowledge/tigers_mouth`)
- `skill_id`: `"basic_shape_knowledge"`
- `allowed_bands`: `["novice"]`
- Detection: After the move, the played stone at (x,y) completes a formation
  where 3 orthogonal neighbors of (x,y) are the same color and the 4th
  orthogonal neighbor is empty. That empty point is the "mouth" — playing
  there would be suicide for the opponent (it would immediately be captured).
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**11. Bamboo Joint** (`basic_shape_knowledge/bamboo_joint`)
- `skill_id`: `"basic_shape_knowledge"`
- `allowed_bands`: `["novice"]`
- Detection: After the move, the board contains a bamboo joint pattern for
  the player. A bamboo joint is two pairs of same-color stones where:
  - Pair A: stones at (x,y) and (x+1,y)
  - Pair B: stones at (x,y+2) and (x+1,y+2)
  - Both (x,y+1) and (x+1,y+1) are empty
  Or the horizontal equivalent. The played stone must be part of the joint.
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**12. Knight's Move Vulnerable** (`basic_shape_knowledge/knights_move_cut`)
- `skill_id`: `"basic_shape_knowledge"`
- `allowed_bands`: `["novice"]`
- `hot_segment_only`: True
- Detection: `win_rate_delta <= -0.05` AND after the move, two of the player's
  stones that are one knight's move apart (2×1 offset) have both cut-through
  points occupied by opponent stones. A knight's move from (x,y) to (x+2,y+1)
  has cut points at (x+1,y) and (x+1,y+1) — if both are opponent stones, the
  connection is severed.
- `severity`: `"minor"`
- `params`: `{n, coord, player}`

---

**13. Large Knight's Move Vulnerable** (`basic_shape_knowledge/large_knights_move_cut`)
- `skill_id`: `"basic_shape_knowledge"`
- `allowed_bands`: `["novice"]`
- `hot_segment_only`: True
- Detection: Same as above but for a 3×1 knight's move (from (x,y) to (x+3,y+1)).
  The cut points are at (x+1,y), (x+2,y), (x+1,y+1), (x+2,y+1) — all four
  being opponent stones means the large knight's move is cut.
- `severity`: `"minor"`
- `params`: `{n, coord, player}`

---

**14. One-Space Jump Cut** (`defending_cutting_points/one_space_jump_cut`)
- `skill_id`: `"defending_cutting_points"`
- `allowed_bands`: `["novice"]`
- `hot_segment_only`: True
- Detection: `win_rate_delta <= -0.05` AND two player stones at (x,y) and
  (x+2,y) (or (x,y) and (x,y+2)) where the middle point (x+1,y) is now an
  opponent stone after the move.
- `severity`: `"minor"`
- `params`: `{n, coord, player}`

---

**15. Defended Cut Point** (`defending_cutting_points/defended_cut`)
- `skill_id`: `"defending_cutting_points"`
- `allowed_bands`: `["novice"]`
- Detection: The played stone at (x,y) fills a point that was previously an
  intersection where two opponent stones were diagonally adjacent and both
  orthogonal connections were empty (a "cutting point"). Now those two
  neighboring player groups are connected through (x,y). In simpler terms:
  before the move, (x,y) was empty and had >=2 player stones adjacent to it
  from different groups (disconnected); after the move, those groups are
  connected.
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**16. Double Atari** (`counting_liberties/double_atari`)
- `skill_id`: `"counting_liberties"`
- `allowed_bands`: `["novice"]`
- Detection: After the move, the played stone threatens two distinct opponent
  groups simultaneously and both are in atari (1 liberty). The two groups
  must be different connected components.
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**17. Double Atari Danger** (`counting_liberties/double_atari_danger`)
- `skill_id`: `"counting_liberties"`
- `allowed_bands`: `["novice"]`
- `hot_segment_only`: True
- Detection: `win_rate_delta <= -0.05` AND after the move, two of the player's
  groups are each in atari (1 liberty) and share a common liberty point
  (i.e. the opponent can play one point to put both in atari simultaneously).
- `severity`: `"minor"`
- `params`: `{n, coord, player}`

---

**18. Capturing Race Winning** (`capturing_races/race_winning`)
- `skill_id`: `"capturing_races"`
- `allowed_bands`: `["beginner"]`
- Detection: There exist two groups — one player, one opponent — that are
  mutually adjacent (share a region) and the player's group has strictly more
  liberties than the opponent's group. Both groups must have <= 4 liberties
  (actively racing, not just adjacent groups with plenty of room).
- `severity`: `"positive"`
- `params`: `{n, coord, player, points}`

---

**19. Capturing Race Losing** (`capturing_races/race_losing`)
- `skill_id`: `"capturing_races"`
- `allowed_bands`: `["beginner"]`
- `hot_segment_only`: True
- Detection: `win_rate_delta <= -0.04` AND same as above but opponent group
  has more liberties than player group.
- `severity`: `"significant"`
- `params`: `{n, coord, player, points}`

---

**20. Net** (`capturing_races/net`)
- `skill_id`: `"capturing_races"`
- `allowed_bands`: `["beginner"]`
- Detection: An opponent group has multiple liberties but every liberty is
  adjacent to a player stone (all escape routes are guarded). The opponent
  cannot escape even though they have liberties. To detect: for each liberty
  of the opponent group, check that playing there would still leave the group
  with 0 liberties (because all other liberties are also guarded). This is a
  simplified version of net detection.
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**21. Group Made Life** (`life_and_death/two_eyes_made`)
- `skill_id`: `"life_and_death"`
- `allowed_bands`: `["beginner"]`
- Detection: Same as trigger #8 (Life Secured). A player group now has 2
  genuine eyes.
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**22. Group in Atari Danger** (`life_and_death/group_in_danger`)
- `skill_id`: `"life_and_death"`
- `allowed_bands`: `["beginner"]`
- `hot_segment_only`: True
- Detection: `win_rate_delta <= -0.04` AND a player group is in atari (1
  liberty) AND that group has only 0 or 1 eye-spaces.
- `severity`: `"significant"`
- `params`: `{n, coord, player}`

---

**23. False Eye** (`life_and_death/false_eye`)
- `skill_id`: `"life_and_death"`
- `allowed_bands`: `["beginner"]`
- `hot_segment_only`: True
- Detection: `win_rate_delta <= -0.03` AND a player group has an eye-shaped
  empty point where >= 2 diagonal neighbors are opponent stones (making the
  "eye" destroyable — it's a false eye).
- `severity`: `"minor"`
- `params`: `{n, coord, player}`

---

**24. Opponent Group Dying** (`life_and_death/opponent_dying`)
- `skill_id`: `"life_and_death"`
- `allowed_bands`: `["beginner"]`
- Detection: An opponent group that had 2+ eye-spaces in `prev_board_state`
  now has <= 1 eye-space in `board_state` (the player has reduced the
  opponent to a dying group).
- `severity`: `"positive"`
- `params`: `{n, coord, player, points}`

---

**25. Ladder Capture** (`ladders/ladder_capture`)
- `skill_id`: `"ladders"`
- `allowed_bands`: `["beginner"]`
- Detection: The played stone puts an opponent group in atari AND that atari
  initiates a working ladder (simulate the ladder and confirm it reaches the
  edge without breaking).
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**26. Ko Threat Played** (`ko_fighting/threat_played`)
- `skill_id`: `"ko_fighting"`
- `allowed_bands`: `["beginner"]`
- Detection: A ko was active in `prev_board_state` (there was a `ko_point`)
  AND the player did NOT recapture the ko — they played elsewhere. The played
  move put a different opponent group in atari or captured something (positive
  impact move while a ko is ongoing).
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**27. Ko Ignored** (`ko_fighting/ko_ignored`)
- `skill_id`: `"ko_fighting"`
- `allowed_bands`: `["beginner"]`
- `hot_segment_only`: True
- Detection: `win_rate_delta <= -0.05` AND in `prev_board_state` the player
  had a group in atari near an active ko AND the player did not play to
  connect that group or address the ko threat.
- `severity`: `"significant"`
- `params`: `{n, coord, player}`

---

**28. Throw-In** (`shortage_of_liberties/throw_in`)
- `skill_id`: `"shortage_of_liberties"`
- `allowed_bands`: `["beginner"]`
- Detection: The played stone is placed adjacent to an opponent group with 1
  or 2 liberties and is immediately captured (`last_captured >= 1` for the
  opponent's recapture), but this capture reduces the opponent group's
  liberty count (the opponent now has fewer liberties than before). This is
  the "fill from outside" sacrifice technique.
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**29. Shortage Capture Failure** (`shortage_of_liberties/capture_failure`)
- `skill_id`: `"shortage_of_liberties"`
- `allowed_bands`: `["beginner"]`
- `hot_segment_only`: True
- Detection: `win_rate_delta <= -0.05` AND the player attempted to capture
  a group (played adjacent to it) but the player's surrounding group has
  fewer liberties than the target group → the player's group gets captured
  instead.
- `severity`: `"significant"`
- `params`: `{n, coord, player}`

---

**30. Named Opening** (`corner_moves_in_the_opening/named_opening`)
- `skill_id`: `"corner_moves_in_the_opening"`
- `allowed_bands`: `["beginner"]`
- Detection: The played stone completes a recognized corner joseki pattern.
  Check for these named openings by comparing the corner stones to known
  patterns:
  - **Shusaku Opening** (komoku + approaching move): Black stones at the
    4-4 point of one corner plus an approach at the 3-4 point of an adjacent corner.
  - **Chinese Opening**: Black stones forming the Chinese fuseki (komoku +
    extending to the side in a specific way).
  - **Sanrensei**: Three black stones on the 4-4 points of the top or left side.
  - **3-4 Point (Komoku)**: A stone at a 3-4 point in a corner within the
    first 10 moves.
  - **4-4 Point (Hoshi)**: A stone at a 4-4 point in a corner within the
    first 10 moves.
  Return the `opening_name` string for use in the template `{opening}` param.
- `severity`: `"positive"`
- `params`: `{n, coord, player, opening}` — `opening` is the name string

---

**31. Corner Approach** (`corner_moves_in_the_opening/good_approach`)
- `skill_id`: `"corner_moves_in_the_opening"`
- `allowed_bands`: `["beginner"]`
- Detection: `move_index <= opening_cutoff` AND the played stone is adjacent
  to (within 2 intersections of) an opponent stone that is in a corner region
  (within 4 lines of a corner), AND the played stone is not itself in the
  immediate corner (not within 3 lines of the corner on both axes).
- `severity`: `"positive"`
- `params`: `{n, coord, player}`

---

**32. Empty Corner in Opening** (`corner_moves_in_the_opening/empty_corner`)
- `skill_id`: `"corner_moves_in_the_opening"`
- `allowed_bands`: `["beginner"]`
- Detection: After the move, all four corners of the board are still unclaimed
  (no stone of either color within 4 lines of any corner on both axes), AND
  `move_index` is within the opening phase.
- `severity`: `"minor"`
- `params`: `{n, coord, player}`

---

### Full-Game Triggers

These run once after the entire `move_analyses` list is built (Phase 6).

---

**33. Sente Endgame** (`end_game/sente`)
- `skill_id`: `"end_game"`
- `allowed_bands`: `["beginner"]`
- Detection per move: The move is in the endgame phase (after 60% of
  estimated total moves) AND `win_rate_delta > 0.02` AND the move was
  sente (the opponent's next move responded to it — i.e., the next move in
  the sequence is by the opponent in the same area). Simplified detection:
  just check game phase + positive delta in endgame.
- `severity`: `"positive"`
- `params`: `{n, coord, player, points}`

---

**34. Missed Endgame** (`end_game/missed`)
- `skill_id`: `"end_game"`
- `allowed_bands`: `["beginner"]`
- Detection per move: `win_rate_delta <= -0.03` AND the move is in the
  endgame phase AND `best_move != played_move` (the engine had a better
  move).
- `severity`: `"significant"`
- `params`: `{n, coord, best_move, player, points}`

---

**35. Game Phase Snapshots** (`counting_territory/phase_*`)
- `skill_id`: `"counting_territory"`
- `allowed_bands`: `["beginner"]`
- Detection: Find the move indices closest to:
  1. End of opening (`opening_cutoff`)
  2. Middle of midgame (`opening_cutoff + (endgame_start - opening_cutoff) * 0.5`)
  3. Start of endgame (`total_moves * 0.6`)
  For each, generate a snapshot event with the win rate and score lead at
  that point.
  - `phase` values: `"opening_end"`, `"midgame_middle"`, `"endgame_start"`
  - `leader`: `"B"` if `score_lead > 2`, `"W"` if `score_lead < -2`, else `"even"`
- Generates up to 3 events, one per phase.
- `template_key`: `"counting_territory/phase_opening_end"`, etc.
- `severity`: `"positive"`
- `params`: `{phase, leader, margin, win_rate}`
  - `phase` = `"end of the opening"` / `"middle of the midgame"` / `"beginning of the endgame"`
  - `leader` = `"Black"` / `"White"` / `"the game"`
  - `margin` = `"roughly even"` / `"ahead by about N points"`
  - `win_rate` = `"62%"` (formatted as integer percent)

---

### Template Strings (All 35 Templates)

These are the exact text strings. Use `{param}` substitution.

```python
TEMPLATES = {
    "counting_liberties/self_atari":
        "On move {n}, your stone at {coord} was placed with no liberties remaining "
        "and was immediately at risk. Before playing, count the breathing spaces "
        "around your group. {best_move} would have been safer.",

    "counting_liberties/good_defense":
        "On move {n}, you spotted a group in danger and gave it room to breathe. "
        "Good awareness of your group's liberties.",

    "counting_liberties/double_atari":
        "Move {n} at {coord} threatened two opponent groups simultaneously — a double "
        "atari! When two groups share a single-liberty situation from one move, the "
        "opponent can only save one. Nice tactical reading.",

    "counting_liberties/double_atari_danger":
        "After move {n}, two of your groups are sharing a critical liberty point. "
        "The opponent can play there and threaten both at once. Make sure to count "
        "liberties carefully when your groups are close together.",

    "ladders/failed_ladder":
        "The sequence around move {n} set up a chase that doesn't work out in your "
        "favor. Before playing out a ladder, read all the way to the edge — if "
        "there's a friendly stone in the path, it breaks.",

    "ladders/ladder_capture":
        "Move {n} set up a working ladder — you correctly read that the opponent "
        "cannot escape. Always verify the ladder all the way to the edge (or the "
        "nearest friendly stone) before playing it.",

    "basic_shape_knowledge/empty_triangle":
        "The three stones around move {n} formed an empty triangle — an L-shape "
        "with the inner corner empty. This shape uses three stones to do the work "
        "of two. A solid connection or a stretch would be more efficient.",

    "basic_shape_knowledge/tigers_mouth":
        "Move {n} at {coord} created a tiger's mouth — three friendly stones "
        "surrounding an empty point on three sides. Playing into that empty point "
        "would be suicide for the opponent. Good shape that makes your group harder "
        "to attack.",

    "basic_shape_knowledge/bamboo_joint":
        "Around move {n} your stones formed a bamboo joint — two adjacent pairs "
        "connected by a gap with two empty points. This is one of the strongest "
        "connection shapes: it cannot be cut and gives your groups breathing room.",

    "basic_shape_knowledge/knights_move_cut":
        "After move {n}, your knight's move has been skewered — both cut-through "
        "points are occupied by the opponent. A knight's move is fast but thin; "
        "when the opponent fills both cut points, the connection breaks and both "
        "stones become isolated.",

    "basic_shape_knowledge/large_knights_move_cut":
        "After move {n}, your large knight's move has been cut through. Large "
        "knight's moves cover more ground but are even more vulnerable to being "
        "sliced apart. Consider a tighter connection when defending.",

    "corner_moves_in_the_opening/early_loss":
        "Move {n} was an early exchange that shifted the balance. In the opening, "
        "corners and sides anchor your territory. When a corner move goes wrong it "
        "tends to have a big ripple effect — {best_move} would have held the "
        "position better.",

    "corner_moves_in_the_opening/named_opening":
        "You played the {opening} opening. This is a well-known formation that "
        "balances corner territory with side influence. Recognizing and using "
        "named openings is a sign of growing understanding.",

    "corner_moves_in_the_opening/good_approach":
        "Move {n} was a well-placed approach to the corner. Approaching at the "
        "right distance — close enough to prevent the corner being settled cheaply, "
        "far enough not to be pushed around — is an important opening principle.",

    "corner_moves_in_the_opening/empty_corner":
        "Move {n} was played in the middle while all four corners were still "
        "unclaimed. Corners are the most efficient territory to claim in the opening "
        "because they can be secured with fewer stones. It is usually worth claiming "
        "or approaching a corner before playing in the middle.",

    "life_and_death/good_attack":
        "On move {n} you put pressure on your opponent's group effectively. "
        "The threat reduced their options and gave you an advantage.",

    "life_and_death/clean_life":
        "Move {n} secured the life of a group that had been under pressure. "
        "Knowing when and how to make two eyes is fundamental to Go.",

    "life_and_death/two_eyes_made":
        "Move {n} completed the second eye for your group. A group with two genuine "
        "eyes can never be captured, no matter how many moves the opponent makes. "
        "Good instinct for when to secure life.",

    "life_and_death/group_in_danger":
        "After move {n}, one of your groups is in atari and only has one eye "
        "region. Without two genuine eyes it cannot survive if the opponent keeps "
        "attacking. Look for a chance to create a second eye space or connect to "
        "safety.",

    "life_and_death/false_eye":
        "After move {n}, what looks like an eye in your group is actually a false "
        "eye — opponent stones at two or more diagonal points mean it can be "
        "destroyed. Make sure both eyes in your group are genuine before assuming "
        "your group is safe.",

    "life_and_death/opponent_dying":
        "Move {n} reduced the opponent's group to one eye region{points}. A group "
        "that cannot form two eyes is as good as dead — the opponent will need to "
        "spend many moves just to stay alive.",

    "defending_cutting_points/good_connection":
        "Move {n} joined two groups that were at risk of being split. Keeping your "
        "stones connected reduces vulnerabilities and makes your whole position "
        "stronger.",

    "defending_cutting_points/one_space_jump_cut":
        "After move {n}, the opponent has cut your one-space jump. A one-space jump "
        "links two stones quickly, but the middle point is always a target. When "
        "the opponent plays there, your two stones are separated.",

    "defending_cutting_points/defended_cut":
        "Move {n} at {coord} defended a potential cutting point — either with a "
        "solid bridge or a tiger's mouth. Recognizing where your stones can be "
        "split and closing those gaps before the opponent strikes is a key novice "
        "skill.",

    "capturing_races/big_capture":
        "The capture around move {n} was a significant gain{points}. Reading ahead "
        "to confirm the capture before committing is good practice — you did that "
        "well here.",

    "capturing_races/race_winning":
        "Around move {n} you were ahead in a capturing race — your group had more "
        "liberties than the opponent's. Keeping that lead by extending rather than "
        "filling liberties is key to winning races{points}.",

    "capturing_races/race_losing":
        "Around move {n} the opponent was ahead in the capturing race — they had "
        "more liberties than your group{points}. When you're behind in a race, look "
        "for a way to add outside liberties or create a ko instead of racing "
        "straight into capture.",

    "capturing_races/net":
        "Move {n} set up a net — the opponent's group has liberties but every "
        "escape point is guarded. A net is often stronger than a direct capture "
        "because it works even when a ladder would be broken.",

    "ko_fighting/threat_played":
        "Move {n} was a good ko threat — you played somewhere that demanded a "
        "response before the opponent could recapture. Ko fights require threats "
        "on both sides; you handled this one well.",

    "ko_fighting/ko_ignored":
        "Around move {n} a ko was active near a group of yours that was in atari. "
        "Playing away without connecting or responding let the opponent keep the "
        "threat alive. In a ko fight, your group's safety always comes first.",

    "shortage_of_liberties/throw_in":
        "Move {n} was a throw-in — you sacrificed a stone to reduce the opponent's "
        "liberties. This technique exploits a shortage of liberties and can turn an "
        "unwinnable direct capture into a winning sequence.",

    "shortage_of_liberties/capture_failure":
        "Around move {n} you attempted to capture an opponent group, but your own "
        "group had fewer liberties. When your group is shorter on liberties, "
        "attempting a direct capture backfires — consider adding outside liberties "
        "or playing a ko threat first.",

    "end_game/sente":
        "Move {n} was a good endgame move{points} — you played in an area with "
        "contested ownership and came out ahead. In the endgame, prioritising moves "
        "that are sente (forcing a reply) keeps the initiative and adds up over time.",

    "end_game/missed":
        "Around move {n} there was a larger endgame move available{points}. "
        "{best_move} would have secured more territory. In the endgame it is worth "
        "pausing to compare the size of available moves before playing.",

    "counting_territory/phase_opening_end":
        "At the {phase}, {leader} was {margin} (Black win rate: {win_rate}).",

    "counting_territory/phase_midgame_middle":
        "At the {phase}, {leader} was {margin} (Black win rate: {win_rate}).",

    "counting_territory/phase_endgame_start":
        "At the {phase}, {leader} was {margin} (Black win rate: {win_rate}).",
}
```

### Running the Triggers

```python
def run_triggers(triggers, analyses, rank_band, board_size):
    results = []
    for trigger in triggers:
        if rank_band not in trigger['allowed_bands']:
            # also allow if rank_band is higher than an allowed band
            if not any(is_skill_allowed_for_level(rank_band, trigger['skill_id'])
                       for b in trigger['allowed_bands']):
                continue
        raw_results = trigger['detect'](analyses, board_size)
        for tr in raw_results:
            template_text = TEMPLATES.get(tr.template_key)
            if not template_text:
                continue
            text = template_text
            for key, val in tr.params.items():
                text = text.replace(f"{{{key}}}", val)
            results.append(DetectedFeedback(
                skill_id=trigger['skill_id'],
                move_index=tr.move_index,
                severity=tr.severity,
                template_key=tr.template_key,
                text=text,
            ))
    return results

def detect_always_run_feedback(analysis, rank_band, board_size):
    always_triggers = [t for t in PER_MOVE_TRIGGERS if not t.get('hot_segment_only')]
    return run_triggers(always_triggers, [analysis], rank_band, board_size)

def detect_hot_segment_feedback(analysis, rank_band, board_size):
    hot_triggers = [t for t in PER_MOVE_TRIGGERS if t.get('hot_segment_only')]
    return run_triggers(hot_triggers, [analysis], rank_band, board_size)

def detect_full_game_feedback(analyses, rank_band, board_size):
    return run_triggers(FULL_GAME_TRIGGERS, analyses, rank_band, board_size)
```

### Skill Score Functions

```python
def stub_skill_score(skill_id: str, feedback: list[DetectedFeedback]) -> int:
    relevant = [f for f in feedback if f.skill_id == skill_id]
    if not relevant:
        return 65
    positives = sum(1 for f in relevant if f.severity == "positive")
    negatives = sum(1 for f in relevant if f.severity in ("significant", "critical"))
    return max(0, min(100, 65 + positives * 10 - negatives * 15))

def pick_skill_comment(skill_id: str, feedback: list[DetectedFeedback], fallback: str) -> str:
    relevant = [f for f in feedback if f.skill_id == skill_id]
    if not relevant:
        return fallback
    order = {"critical": 0, "significant": 1, "minor": 2, "positive": 3}
    sorted_fb = sorted(relevant, key=lambda f: order.get(f.severity, 4))
    return sorted_fb[0].text

def to_move_event(fb: DetectedFeedback) -> MoveEvent:
    return MoveEvent(
        move_index=fb.move_index,
        event_type=fb.template_key,
        severity=fb.severity,
        actor_color=None,
        payload={"template_key": fb.template_key, "skill_id": fb.skill_id},
    )
```

---

## 14. Event Reconciler

Port of `event-reconciler.ts → buildKeyMomentsFromEvents()`:

```python
def build_key_moments_from_events(
    feedback: list[DetectedFeedback],
    analyses: list[MoveAnalysis],
    board_size: int,
    rank_band: str,
) -> tuple[list[KeyMoment], list[KeyMoment]]:

    min_delta = MIN_DELTA_FOR_HIGHLIGHT[rank_band]
    analysis_map = {a.move_index: a for a in analyses}

    # Step 1: Best feedback per move (highest severity wins)
    severity_order = {"critical": 0, "significant": 1, "positive": 2, "minor": 3}
    best_by_move = {}
    for fb in feedback:
        existing = best_by_move.get(fb.move_index)
        if not existing or severity_order[fb.severity] < severity_order[existing.severity]:
            best_by_move[fb.move_index] = fb

    skill_candidate_indices = set()
    candidate_map = {}

    for fb in best_by_move.values():
        analysis = analysis_map.get(fb.move_index)
        if not analysis:
            continue
        has_teachable = is_skill_allowed_for_level(rank_band, fb.skill_id)
        explanation_mode = "skill" if has_teachable else "tactical"
        is_worthy = has_teachable or abs(analysis.win_rate_delta) >= min_delta
        if not is_worthy:
            continue
        skill_candidate_indices.add(fb.move_index)
        candidate_map[fb.move_index] = KeyMoment(
            move_index=fb.move_index,
            label=label_from_delta(analysis.win_rate_delta, rank_band),
            explanation=fb.text if explanation_mode == "skill" else None,
            explanation_mode=explanation_mode,
            skill_tag=fb.skill_id,
            moves=analysis.moves,
        )

    # Step 2: Fallback candidates (large swings, no skill event)
    TURNING_POINT_POSITIVE_COPY = "Move {n} was a turning point — you found a sharp move that significantly improved your position."
    TURNING_POINT_NEGATIVE_COPY = "Move {n} was a turning point — this was the moment that most shifted the game against you."

    for a in analyses:
        if a.move_index in skill_candidate_indices:
            continue
        if abs(a.win_rate_delta) < TURNING_POINT_FALLBACK_DELTA:
            continue
        copy = TURNING_POINT_POSITIVE_COPY if a.win_rate_delta > 0 else TURNING_POINT_NEGATIVE_COPY
        explanation = copy.replace("{n}", str(a.move_index + 1))
        candidate_map[a.move_index] = KeyMoment(
            move_index=a.move_index,
            label=label_from_delta(a.win_rate_delta, rank_band),
            explanation=explanation,
            explanation_mode="turning_point",
            skill_tag=None,
            moves=a.moves,
        )

    # Step 3: Split positive / negative
    candidates = list(candidate_map.values())
    positive = [c for c in candidates if (analysis_map[c.move_index].win_rate_delta > 0)]
    negative = [c for c in candidates if (analysis_map[c.move_index].win_rate_delta < 0)]

    great_threshold = CLASSIFY_GREAT_MIN_DELTA[rank_band]
    mistake_threshold = abs(CLASSIFY_MISTAKE_MAX_DELTA)

    def sort_key_positive(c):
        d = abs(analysis_map[c.move_index].win_rate_delta)
        has_skill = c.explanation_mode == "skill"
        is_impactful = d >= great_threshold
        # Tier 1: skill + impactful
        t1 = 0 if (has_skill and is_impactful) else 1
        # Tier 2: impactful
        t2 = 0 if is_impactful else 1
        # Tier 3: skill
        t3 = 0 if has_skill else 1
        return (t1, t2, t3, -d)

    def sort_key_negative(c):
        d = abs(analysis_map[c.move_index].win_rate_delta)
        has_skill = c.explanation_mode == "skill"
        is_severe = d >= mistake_threshold
        is_impactful = d >= great_threshold
        t1 = 0 if (has_skill and is_impactful) else 1
        t2 = 0 if is_severe else 1
        t3 = 0 if has_skill else 1
        return (t1, t2, t3, -d)

    did_well = sorted(positive, key=sort_key_positive)[:MAX_HIGHLIGHT_MOMENTS_PER_SECTION]
    could_improve = sorted(negative, key=sort_key_negative)[:MAX_HIGHLIGHT_MOMENTS_PER_SECTION]
    return did_well, could_improve


def label_from_delta(win_rate_delta: float, rank_band: str) -> KeyMomentLabel:
    if win_rate_delta >= CLASSIFY_BRILLIANT_MIN_DELTA[rank_band]: return "brilliant"
    if win_rate_delta >= CLASSIFY_GREAT_MIN_DELTA[rank_band]:     return "great"
    if win_rate_delta <= CLASSIFY_BLUNDER_MAX_DELTA:              return "blunder"
    if win_rate_delta <= CLASSIFY_MISTAKE_MAX_DELTA:              return "mistake"
    if win_rate_delta < 0:                                        return "inaccuracy"
    return "turning_point"
```

---

## 15. Template Generator

```python
def build_game_summary(
    analyses: list[MoveAnalysis],
    player_color: str,
    board_size: int,
    win_rates: list[float],
) -> str:
    if not analyses:
        return "Game analysis is complete."

    total_moves = len(analyses)
    player_label = "Black" if player_color == "B" else "White"

    biggest_swing = 0
    biggest_swing_move = 0
    for a in analyses:
        if a.player_color == player_color:
            swing = abs(a.win_rate_delta)
            if swing > biggest_swing:
                biggest_swing = swing
                biggest_swing_move = a.move_index + 1

    phase = get_game_phase(biggest_swing_move, board_size)
    phase_label = {"opening": "the opening", "middle": "the middle game", "endgame": "the endgame"}[phase]

    final_wr = win_rates[-1] if win_rates else 0.5
    player_final = final_wr if player_color == "B" else 1 - final_wr
    is_ahead = player_final > 0.55
    is_behind = player_final < 0.45

    blunders = sum(1 for a in analyses if a.player_color == player_color and a.classification == "blunder")
    brilliant = sum(1 for a in analyses if a.player_color == player_color and a.classification == "brilliant")

    if brilliant > 0 and blunders == 0:
        count = "several" if brilliant > 1 else "one"
        plural = "s" if brilliant > 1 else ""
        summary = f"{player_label} played a sharp game with {count} excellent move{plural}."
    elif blunders > 1:
        summary = f"{player_label} had a tough game with {blunders} significant mistakes."
    elif blunders == 1:
        summary = f"{player_label} played well overall, but one key mistake shifted the balance."
    else:
        summary = f"{player_label} played a steady game across {total_moves} moves."

    if biggest_swing >= 0.15:
        summary += f" The biggest swing came in {phase_label} around move {biggest_swing_move}."
    elif is_ahead:
        summary += " The position was generally in your favor."
    elif is_behind:
        summary += " The engine suggests the position was challenging throughout."

    return summary


def build_practice_areas(skill_scores: list[SkillScore], count: int = 3) -> list[str]:
    sorted_scores = sorted(skill_scores, key=lambda s: s.score)
    return [s.skill_id for s in sorted_scores[:count]]
```

---

## 16. Saving to Supabase

The worker saves the completed review to the `game_reviews` table (same table
the Next.js app already reads from) and then marks the job completed.

The `game_reviews` table already exists. Its columns (from the existing
`/api/game-reviews` route behavior):
- `id` — UUID, auto-generated
- `user_id` — UUID from `game_review_jobs.user_id`
- `sgf` — the raw SGF string
- `player_color` — `"B"` or `"W"`
- `rank_band` — e.g. `"beginner"`
- `game_summary` — the generated summary string
- `total_moves` — integer
- `board_size` — integer
- `report` — JSONB column containing the full serialized `ReviewReport`
- `created_at` — auto-set

```python
import os
from supabase import create_client

supabase = create_client(
    os.environ["SUPABASE_URL"],
    os.environ["SUPABASE_SERVICE_ROLE_KEY"],
)

def save_review(job: dict, report: ReviewReport) -> str:
    """Returns the new review UUID."""
    result = supabase.table("game_reviews").insert({
        "user_id": job["user_id"],
        "sgf": job["sgf"],
        "player_color": report.player_color,
        "rank_band": report.rank_band,
        "game_summary": report.game_summary,
        "total_moves": report.total_moves,
        "board_size": report.board_size,
        "report": report_to_dict(report),   # serialize to plain dict
    }).execute()
    return result.data[0]["id"]

def mark_job_completed(job_id: str, review_id: str):
    from datetime import datetime, timezone
    supabase.table("game_review_jobs").update({
        "status": "completed",
        "review_id": review_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job_id).execute()

def mark_job_failed(job_id: str, error_message: str):
    from datetime import datetime, timezone
    supabase.table("game_review_jobs").update({
        "status": "failed",
        "error_message": error_message[:2000],
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job_id).execute()
```

**Serializing `ReviewReport` to dict:** Convert all dataclasses to plain
dicts/lists recursively. `BoardState` objects inside `MoveAnalysis` should be
serialized as `{"size": N, "stones": [[...], ...]}` — but be careful: the
`report` JSON stored in the database is large. The `moveAnalyses` field
contains every move's `prevBoardState` and `boardState`, which doubles the
stored size. Consider omitting `prevBoardState` and `boardState` from the
stored JSON (the Next.js viewer reconstructs board state from the SGF). Only
the following fields in `MoveAnalysis` are actually read by the Next.js
review viewer:
- `moveIndex`, `playedMove`, `playerColor`
- `winRateBefore`, `winRateAfter`, `winRateDelta`
- `scoreBefore`, `scoreAfter`, `scoreDelta`
- `classification`, `events`
- `bestMove`, `topMoves`
- `isInterpolated`

You can safely omit `prevBoardState`, `boardState`, `moves`, and `ownershipAfter`
from the serialized JSON to keep the stored payload small.

---

## 17. Sending the Email via Resend

```python
import requests

RESEND_API_KEY = os.environ["RESEND_API_KEY"]
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "no-reply@sundaygolessons.com")
APP_BASE_URL = os.environ.get("APP_BASE_URL", "https://sundaygolessons.com")

def send_review_email(to_email: str, report: ReviewReport, review_id: str):
    review_url = f"{APP_BASE_URL}/reviews/{review_id}"
    html = build_review_email_html(report, review_url)
    text = build_review_email_text(report, review_url)

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": RESEND_FROM_EMAIL,
            "to": [to_email],
            "subject": "Your Sunday Go Lessons Game Review is Ready",
            "html": html,
            "text": text,
        },
    )
    response.raise_for_status()
```

### Email HTML Content

Build an HTML email with these sections (inline styles only — no CSS classes,
no external stylesheets, as email clients strip them):

1. **Header:** "Your Game Review is Ready" — `font-family: sans-serif; color: #111`
2. **Game Summary:** The `report.game_summary` string in a `<p>` tag
3. **Win Rate Summary:** A simple text description, e.g.
   "You played {N} moves as {Black/White}. Final win rate: {X}%."
4. **Move Quality Breakdown:** A small HTML table:
   | Category | Count |
   |---|---|
   | Brilliant | N |
   | Great | N |
   | Good | N |
   | Inaccuracy | N |
   | Mistake | N |
   | Blunder | N |
5. **Did Well (up to 3):** For each `KeyMoment` in `did_well_moments`:
   - Move number and label
   - `explanation` text
6. **Could Improve (up to 3):** Same for `could_improve_moments`
7. **Skill Scores:** For each `SkillScore`:
   - Skill label + score (0-100)
   - `comment` text
8. **Practice Recommendations:** List the `practice_areas` skill IDs (convert
   to readable labels from `SKILLS_BY_BAND`)
9. **CTA button:** "View Full Interactive Review" linking to `review_url`
   styled as a button: `background: #4f46e5; color: white; padding: 12px 24px;
   border-radius: 6px; text-decoration: none; display: inline-block`

The email should be self-contained — someone reading only the email gets the
full picture without needing to visit the site. The button is a bonus for users
who want the interactive board replay.

---

## 18. Worker Polling Loop

```python
import time
from datetime import datetime, timezone

def poll_for_job() -> dict | None:
    result = supabase.table("game_review_jobs") \
        .select("*") \
        .eq("status", "pending") \
        .order("created_at") \
        .limit(1) \
        .execute()
    return result.data[0] if result.data else None

def claim_job(job_id: str) -> bool:
    """Atomically mark a job as processing. Returns True if successful."""
    try:
        supabase.table("game_review_jobs").update({
            "status": "processing",
            "started_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", job_id).eq("status", "pending").execute()
        return True
    except Exception:
        return False

def run_worker():
    print("Worker started. Polling for jobs...")
    while True:
        try:
            job = poll_for_job()
            if not job:
                time.sleep(5)
                continue

            if not claim_job(job["id"]):
                # Another worker claimed it first (if you ever run multiple)
                time.sleep(1)
                continue

            print(f"Processing job {job['id']} for {job['email']}")
            try:
                report = run_review(job["sgf"], job["rank_band"], job["player_color"])
                review_id = save_review(job, report)
                send_review_email(job["email"], report, review_id)
                mark_job_completed(job["id"], review_id)
                print(f"Job {job['id']} completed. Review saved as {review_id}.")
            except Exception as e:
                print(f"Job {job['id']} failed: {e}")
                mark_job_failed(job["id"], str(e))

        except Exception as e:
            print(f"Worker error: {e}")
            time.sleep(10)

if __name__ == "__main__":
    run_worker()
```

---

## 19. Environment Variables

The Python worker needs these environment variables on the RunPod pod:

```bash
# Supabase
SUPABASE_URL=https://brrjkzwahapdkhfkflud.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<from .env.local: SUPABASE_SERVICE_ROLE_KEY>

# Resend
RESEND_API_KEY=<from .env.local: RESEND_API_KEY>
RESEND_FROM_EMAIL=no-reply@sundaygolessons.com

# App
APP_BASE_URL=https://sundaygolessons.com   # production URL, no trailing slash

# KataGo
KATAGO_BINARY=/path/to/katago
KATAGO_MODEL=/path/to/kata1-model.bin.gz
KATAGO_CONFIG=/path/to/analysis.cfg
```

The `.bin.gz` model for the native binary is different from the `.onnx` model
used by the browser. Download a suitable model from the KataGo releases page:
https://github.com/lightvector/KataGo/releases

Recommended model: `kata1-b28c512nbt-s11101799680-d4654699190.bin.gz`
(28 blocks, strong and fast on GPU).

---

## 20. What NOT to Touch

These files and systems must not be modified:

| What | Why |
|---|---|
| `src/domains/bot-game/**` | Client-side bot game; uses ONNX humanSL model; separate from review |
| `src/domains/katago-web/**` | ONNX Web Worker; used by bot game and position analysis panel |
| `src/app/api/game-reviews/**` | Existing GET/DELETE routes for reading saved reviews |
| The `game_reviews` Supabase table schema | The Next.js viewer already reads from it |
| `NEXT_PUBLIC_KATAGO_HUMANSL_MODEL_URL` | The humanSL ONNX model for the bot; unrelated to review |
| `NEXT_PUBLIC_KATAGO_MODEL_URL` | The standard ONNX model for position analysis panel; also unrelated |

The bot game runs entirely in the browser using the ONNX runtime — it never
touches the job queue or the Python worker. These two systems are fully
independent and share only the Supabase database (different tables).

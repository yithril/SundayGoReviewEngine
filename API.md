# SundayGoReviewEngine API

Base URL: `https://api.sundaygolessons.com`

All endpoints except `/health` require the header:
```
X-API-Key: your-api-key
```

---

## Endpoints

### 1. Health Check
**No auth required.**

```
GET /health
```

**Response:**
```json
{
  "status": "ok",
  "katago": "running",
  "queue_depth": 1
}
```

---

### 2. Submit a Game for Analysis

```
POST /analyze
Content-Type: application/json
X-API-Key: your-api-key
```

**Request body:**
```json
{
  "sgf": "(;FF[4]GM[1]SZ[19]KM[6.5];B[pd];W[dp];B[pp];W[dd]...)",
  "mode": "quick"
}
```

| Field | Type   | Required | Description |
|-------|--------|----------|-------------|
| `sgf` | string | yes      | Full SGF string of the game |
| `mode` | string | no | `"quick"` (default), `"standard"`, or `"deep"` |

**Analysis modes:**

| Mode | Visits/move | Approx time (200-move game) | Intended use |
|------|------------|----------------------------|--------------|
| `quick` | 32 | ~45 seconds | Free tier, coaching |
| `standard` | 100 | ~3 minutes | Premium users |
| `deep` | 400 | ~12 minutes | Serious review |

**Response (immediate — job queued, analysis running in background):**
```json
{
  "job_id": "a3f9c12b44",
  "status": "queued",
  "queue_position": 1,
  "estimated_wait_seconds": 60
}
```

Save `job_id` — you will need it to retrieve results. Associate it with the user's account in your database.

**Error — queue full (503):**
```json
{
  "detail": "Server busy — queue is full. Try again shortly."
}
```

---

### 3. Get Analysis Results (SSE stream or instant)

```
GET /analyze/{job_id}
X-API-Key: your-api-key
```

This endpoint behaves differently depending on job state:

- **Job still processing** → returns a Server-Sent Events (SSE) stream of progress updates
- **Job already complete** → returns the full result immediately as JSON
- **Job failed** → returns error JSON immediately

#### While processing — SSE stream

The response is a stream of events. Each event is a JSON object on a `data:` line:

```
data: {"status": "processing", "progress": 0.12}

data: {"status": "processing", "progress": 0.45}

data: {"status": "processing", "progress": 0.89}

data: {"status": "complete", "progress": 1.0}

data: { ...full result object... }
```

Progress goes from `0.0` to `1.0`. The final event when status is `"complete"` contains the full result (same shape as below).

#### When complete — full result JSON

```json
{
  "job_id": "a3f9c12b44",
  "status": "complete",
  "progress": 1.0,
  "win_rates": [0.50, 0.52, 0.49, 0.51, 0.68, 0.51, 0.49, 0.47],
  "score_leads": [0.0, 0.3, -0.1, 0.5, 4.2, -1.1, -1.4, -2.0],
  "key_moments": [5, 23, 67, 104],
  "summary": {
    "total_moves": 198,
    "black_win_rate_final": 0.38,
    "black_blunders": 3,
    "white_blunders": 1
  }
}
```

**Field explanations:**

| Field | Description |
|-------|-------------|
| `win_rates` | Array of Black's win probability (0–1) after each move. Index 0 = empty board, index N = after move N. Length = total_moves + 1. Use this to render the win rate bar. |
| `score_leads` | Array of score lead from Black's perspective after each move. Positive = Black ahead, negative = White ahead. Same indexing as `win_rates`. |
| `key_moments` | Array of move numbers where the playing side's win rate dropped more than 7%. These are the blunders. Use this to place markers on the board or highlight moves. |
| `summary.black_win_rate_final` | Black's win probability after the last move of the game. |
| `summary.black_blunders` | Number of moves by Black that dropped win rate >7%. |
| `summary.white_blunders` | Number of moves by White that dropped win rate >7%. |

**Important:** `win_rates` and `score_leads` are always from **Black's perspective**. At even-numbered positions (Black to move) this is raw KataGo output; at odd-numbered positions (White to move) it is already flipped for you.

#### On failure:
```json
{
  "job_id": "a3f9c12b44",
  "status": "failed",
  "error": "SGF parse error: invalid coordinate"
}
```

---

### 4. Get Move Detail (lazy load)

Call this only when the user clicks on a specific move to inspect it. Not needed for the win rate bar.

```
GET /move/{job_id}/{move_number}
X-API-Key: your-api-key
```

Example: `GET /move/a3f9c12b44/67`

**Response:**
```json
{
  "move_number": 67,
  "win_rate_before": 0.68,
  "win_rate_after": 0.51,
  "score_lead_before": 4.2,
  "score_lead_after": -1.1,
  "score_swing": 5.3,
  "best_move": "R10",
  "top_moves": [
    { "move": "R10", "winrate": 0.69, "scoreLead": 4.5 },
    { "move": "Q10", "winrate": 0.67, "scoreLead": 4.0 },
    { "move": "P3",  "winrate": 0.64, "scoreLead": 3.1 }
  ],
  "ownership": [0.9, 0.85, 0.7, 0.5, ..., -0.7, -0.9]
}
```

**Field explanations:**

| Field | Description |
|-------|-------------|
| `win_rate_before` | Black's win rate just before this move was played |
| `win_rate_after` | Black's win rate just after this move was played |
| `score_swing` | How many points this move gained or lost (absolute value) |
| `best_move` | The move KataGo would have played instead (coordinate string like `"R10"`) |
| `top_moves` | KataGo's top 5 candidate moves with their win rates and score leads |
| `ownership` | 361 floats (19×19 board), row by row top to bottom, left to right. Values from -1.0 (White territory) to 1.0 (Black territory). Use to render an ownership/territory heatmap. |

---

## Next.js Integration Examples

### Submitting a game

```typescript
async function submitGame(sgf: string, mode = "quick") {
  const res = await fetch("https://api.sundaygolessons.com/analyze", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": process.env.KATAGO_API_KEY!,
    },
    body: JSON.stringify({ sgf, mode }),
  })
  if (!res.ok) throw new Error(await res.text())
  return res.json() // { job_id, status, queue_position, estimated_wait_seconds }
}
```

### Consuming the SSE stream

```typescript
function watchJob(jobId: string, onProgress: (p: number) => void, onComplete: (result: any) => void) {
  const url = `https://api.sundaygolessons.com/analyze/${jobId}`
  const source = new EventSource(url) // Note: EventSource doesn't support custom headers
                                       // See note below about auth

  source.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.status === "processing") {
      onProgress(data.progress)
    }
    if (data.status === "complete") {
      onComplete(data)
      source.close()
    }
    if (data.status === "failed") {
      console.error("Analysis failed:", data.error)
      source.close()
    }
  }

  source.onerror = () => source.close()
  return source
}
```

> **Note on SSE auth:** Browser `EventSource` does not support custom headers. For production, pass the API key as a query param (`?api_key=...`) or proxy through your Next.js API route. The simplest approach: create a Next.js API route at `/api/analyze/[jobId]` that adds the header server-side and streams the response to the browser.

### Fetching move detail on click

```typescript
async function getMoveDetail(jobId: string, moveNumber: number) {
  const res = await fetch(
    `https://api.sundaygolessons.com/move/${jobId}/${moveNumber}`,
    { headers: { "X-API-Key": process.env.KATAGO_API_KEY! } }
  )
  return res.json()
}
```

### Rendering the win rate bar

```typescript
// winRates is the array from the analysis result
// currentMove is the move the user is currently viewing (0 = start)
function WinRateBar({ winRates, currentMove }: { winRates: number[], currentMove: number }) {
  const blackWinRate = winRates[currentMove] ?? 0.5
  const blackPct = Math.round(blackWinRate * 100)
  const whitePct = 100 - blackPct

  return (
    <div style={{ display: "flex", height: 24, width: "100%" }}>
      <div style={{ background: "#1a1a1a", width: `${blackPct}%`, transition: "width 0.3s" }} />
      <div style={{ background: "#f0f0f0", width: `${whitePct}%`, transition: "width 0.3s" }} />
    </div>
  )
}
```

---

---

### 5. Bot Move Suggestion

Returns KataGo's recommended move at a specific rank strength. Synchronous — no job ID, responds in ~1-2 seconds.

```
POST /suggest
Content-Type: application/json
X-API-Key: your-api-key
```

**Request body:**
```json
{
  "moves": [["B","D4"], ["W","Q16"], ["B","Q4"]],
  "rank": "7k",
  "board_size": 19,
  "komi": 6.5
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `moves` | array | yes | Full move history as `[["B"\|"W", "coord"], ...]` |
| `rank` | string | yes | Rank to play at — see `RANKS.md` for all valid values |
| `board_size` | int | no | `9`, `13`, or `19` (default: `19`) |
| `komi` | float | no | Komi value (default: `6.5`) |

Valid rank values: `"20k"`, `"15k"`, `"10k"`, `"9k"` through `"1k"`, `"1d"` through `"9d"`. Full reference in [RANKS.md](RANKS.md).

**Response:**
```json
{
  "move": "R16",
  "win_rate": 0.5312,
  "rank": "7k"
}
```

| Field | Description |
|---|---|
| `move` | KataGo's recommended move at the given rank, e.g. `"R16"` or `"pass"` |
| `win_rate` | Black's win probability (0–1) from the current position |
| `rank` | The rank that was used (echoed back) |

**Example Next.js usage:**
```typescript
async function getBotMove(moves: string[][], rank: string, boardSize = 19) {
  const res = await fetch("https://api.sundaygolessons.com/suggest", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-API-Key": process.env.KATAGO_API_KEY!,
    },
    body: JSON.stringify({ moves, rank, board_size: boardSize, komi: 6.5 }),
  })
  return res.json() // { move, win_rate, rank }
}
```

---

## Deployment Notes

- The API key is set in `/opt/SundayGoReviewEngine/.env` on the VPS as `API_KEY=...`
- To update the code: `cd /opt/SundayGoReviewEngine && git pull && systemctl restart katago-api`
- To view live logs: `journalctl -u katago-api -f`
- To check queue status: `curl https://api.sundaygolessons.com/health`

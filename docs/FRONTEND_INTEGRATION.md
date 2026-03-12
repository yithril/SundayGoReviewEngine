# Frontend Integration Guide

How to wire your Next.js app to the RunPod serverless worker.

---

## Architecture

```
Browser (SGF upload form)
  │
  │  POST /api/ai-reviews/submit  { sgf, playerColor, rankBand }
  ▼
Next.js API route  (server-side — holds the RunPod key)
  │
  │  POST https://api.runpod.ai/v2/{ENDPOINT_ID}/run
  ▼
RunPod worker  (GPU, ~6-10s for a full game)
  │
  ├─▶ Saves review to Supabase  game_reviews table
  └─▶ Sends email with link to /reviews/{review_id}

User clicks email link
  │
  ▼
/reviews/[id]  reads report from Supabase  →  renders review viewer
```

The frontend **never waits** for KataGo to finish. It fires the job, shows a
confirmation screen, and the user gets the result by email. This sidesteps cold-start
timeouts entirely.

---

## Credentials you need

| Credential           | Where to find it |
|----------------------|-----------------|
| `RUNPOD_API_KEY`     | RunPod dashboard → top-right avatar → **API Keys** → Create key |
| `RUNPOD_ENDPOINT_ID` | RunPod dashboard → **Serverless** → click your endpoint → copy the ID from the URL (`/serverless/XXXXXXXXXX/overview`) |

Add both to your Next.js `.env.local` (server-only — no `NEXT_PUBLIC_` prefix):

```bash
# .env.local  (Next.js app — NOT this repo)
RUNPOD_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
RUNPOD_ENDPOINT_ID=xxxxxxxxxx
```

These are never sent to the browser. Only the Next.js server process reads them.

---

## Next.js API route

Create `src/app/api/ai-reviews/submit/route.ts` (App Router) or
`pages/api/ai-reviews/submit.ts` (Pages Router).

### App Router version

```typescript
// src/app/api/ai-reviews/submit/route.ts
import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"  // your server Supabase helper

const RUNPOD_URL = `https://api.runpod.ai/v2/${process.env.RUNPOD_ENDPOINT_ID}/run`

export async function POST(req: NextRequest) {
  // 1. Auth — get the logged-in user
  const supabase = createClient()
  const { data: { user }, error: authError } = await supabase.auth.getUser()
  if (authError || !user) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 })
  }

  // 2. Parse request body
  const { sgf, playerColor, rankBand } = await req.json()
  if (!sgf) {
    return NextResponse.json({ error: "sgf is required" }, { status: 400 })
  }

  // 3. Fire the RunPod job (async — do not await the analysis result)
  const response = await fetch(RUNPOD_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${process.env.RUNPOD_API_KEY}`,
    },
    body: JSON.stringify({
      input: {
        sgf,
        player_color: playerColor ?? "B",
        rank_band:    rankBand ?? "beginner",
        email:        user.email ?? "",
        user_id:      user.id,
      },
    }),
  })

  if (!response.ok) {
    const text = await response.text()
    console.error("RunPod submit failed:", text)
    return NextResponse.json({ error: "Failed to submit review" }, { status: 502 })
  }

  // 4. Return immediately — worker will email the user when done
  return NextResponse.json({ submitted: true })
}
```

### Pages Router version

```typescript
// pages/api/ai-reviews/submit.ts
import type { NextApiRequest, NextApiResponse } from "next"
import { createClient } from "@/lib/supabase/server"

const RUNPOD_URL = `https://api.runpod.ai/v2/${process.env.RUNPOD_ENDPOINT_ID}/run`

export default async function handler(req: NextApiRequest, res: NextApiResponse) {
  if (req.method !== "POST") return res.status(405).end()

  const supabase = createClient({ req, res })
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return res.status(401).json({ error: "Unauthorized" })

  const { sgf, playerColor, rankBand } = req.body
  if (!sgf) return res.status(400).json({ error: "sgf is required" })

  const response = await fetch(RUNPOD_URL, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${process.env.RUNPOD_API_KEY}`,
    },
    body: JSON.stringify({
      input: {
        sgf,
        player_color: playerColor ?? "B",
        rank_band:    rankBand ?? "beginner",
        email:        user.email ?? "",
        user_id:      user.id,
      },
    }),
  })

  if (!response.ok) return res.status(502).json({ error: "Failed to submit review" })
  return res.status(200).json({ submitted: true })
}
```

---

## Request payload the worker expects

The `input` object sent to RunPod must match this shape exactly:

```json
{
  "input": {
    "sgf":          "(;GM[1]FF[4]SZ[19]KM[6.5]...)",
    "player_color": "B",
    "rank_band":    "beginner",
    "email":        "user@example.com",
    "user_id":      "1d87ba11-2168-4182-87d8-32af42d16f19"
  }
}
```

| Field          | Type   | Required | Values |
|----------------|--------|----------|--------|
| `sgf`          | string | yes      | Full SGF game record |
| `player_color` | string | yes      | `"B"` or `"W"` |
| `rank_band`    | string | yes      | `"novice"` `"beginner"` `"intermediate"` `"advanced"` `"dan"` |
| `email`        | string | no       | If provided, success/failure email is sent |
| `user_id`      | string | no       | Supabase auth UUID — used to associate the review with the user |

---

## What the worker returns

The RunPod job completes with this output (visible in RunPod logs, not needed by the
async frontend flow):

```json
{
  "output": {
    "review_id":      "d0c293a3-d0c3-45f1-beeb-ac421f5b6cf1",
    "total_moves":    255,
    "katago_seconds": 6.2,
    "total_seconds":  8.1
  }
}
```

The `review_id` is the Supabase UUID of the saved review. The email sent to the user
contains a link to `/reviews/{review_id}`.

---

## Review data in Supabase

The worker inserts one row into the `game_reviews` table:

| Column              | Type      | Notes |
|---------------------|-----------|-------|
| `id`                | uuid      | Auto-generated — this is the `review_id` |
| `user_id`           | uuid      | References `auth.users` |
| `sgf`               | text      | Raw SGF string |
| `player_color`      | text      | `"B"` or `"W"` |
| `rank_band`         | text      | e.g. `"beginner"` |
| `game_summary`      | text      | Generated one-sentence summary |
| `total_moves`       | integer   | Number of moves in the game |
| `board_size`        | integer   | e.g. `19` |
| `report`            | jsonb     | Full analysis — see structure below |
| `created_at`        | timestamptz | Auto-set |

### `report` JSONB structure

```typescript
{
  player_color:        "B" | "W",
  player_name:         string,       // from SGF PB/PW tag
  opponent_name:       string,
  rank_band:           string,
  board_size:          number,
  total_moves:         number,
  win_rates:           number[],     // reviewed player's win probability after each turn (0–1, up = good for you)
                                     // index 0 = empty board, length = total_moves + 1
  score_leads:         number[],     // score lead from the reviewed player's perspective, same indexing
                                     // positive = you are ahead; already flipped for White players
  move_quality:        string[],     // per-move label, length = total_moves
                                     // "excellent"|"great"|"good"|"inaccuracy"|"mistake"|"blunder"|"neutral"
                                     // "neutral" = opponent's move (placeholder, not displayed)
  move_quality_counts: {             // counts for the reviewed player's moves only
    excellent:   number,
    great:       number,
    good:        number,
    inaccuracy:  number,
    mistake:     number,
    blunder:     number,
  },
  game_summary:        string,       // same as the top-level column
  katago_seconds:      number,
  total_seconds:       number,
  // skeleton fields (populated in future iterations):
  skills_used:         [],
  did_well:            [],
  needs_improvement:   [],
  story:               "",
}
```

### Reading a review in Next.js

```typescript
// /reviews/[id]/page.tsx  (or pages/reviews/[id].tsx)
const { data: review } = await supabase
  .from("game_reviews")
  .select("*")
  .eq("id", reviewId)
  .single()

const report = review.report  // the full object above
const winRates = report.win_rates
const moveQuality = report.move_quality
```

---

## Frontend form (what fields to collect)

Minimum fields needed from the user:

| Field           | UI element | Passed to API as |
|-----------------|------------|-----------------|
| SGF game record | File upload or textarea | `sgf` |
| Player color    | Toggle / radio: Black / White | `playerColor` |
| Rank band       | Dropdown | `rankBand` |

`email` and `user_id` come from the authenticated session — the user does not enter these.

---

## Position Evaluation (hint / explore a variation)

Use this when the user wants to see what KataGo thinks about the current position —
top move suggestions, a territory heatmap, and the current win rate.

### How it differs from game review

| | Game review | Position evaluate |
|---|---|---|
| `job_type` | `"review"` (default) | `"evaluate"` |
| RunPod call | `/run` (async) | `/runsync` (sync — wait for result) |
| Input | SGF string | Move list array |
| Output | Saved to Supabase + email | Returned directly in response |
| GPU time | 6-10s | 0.5-2s |

### Request payload

```json
{
  "input": {
    "job_type":   "evaluate",
    "moves":      [["B","D4"], ["W","Q16"], ["B","D16"]],
    "board_size": 19,
    "komi":       6.5,
    "visits":     200
  }
}
```

| Field        | Type   | Required | Default | Notes |
|--------------|--------|----------|---------|-------|
| `job_type`   | string | yes      | —       | Must be `"evaluate"` |
| `moves`      | array  | yes      | —       | `[["B"\|"W", "coord"], ...]` — full history up to current position |
| `board_size` | number | no       | `19`    | `9`, `13`, or `19` |
| `komi`       | number | no       | `6.5`   | |
| `visits`     | number | no       | `200`   | Higher = stronger but slower |

### Response

```json
{
  "output": {
    "root": {
      "winrate":    0.62,
      "score_lead": 3.4,
      "visits":     200
    },
    "top_moves": [
      {
        "move":       "R10",
        "winrate":    0.64,
        "score_lead": 3.8,
        "visits":     87,
        "prior":      0.18,
        "pv":         ["R10", "Q10", "P3", "O3"]
      }
    ],
    "ownership": [0.9, 0.85, 0.4, -0.3, ..., -0.8]
  }
}
```

| Field | Description |
|---|---|
| `root.winrate` | Black's win probability (0–1) for the current position |
| `root.score_lead` | Score lead from Black's perspective (positive = Black ahead) |
| `top_moves` | Up to 5 candidate moves, sorted best first |
| `top_moves[].pv` | Principal variation — the sequence of moves KataGo expects to follow |
| `ownership` | `board_size²` floats, row-major top-to-bottom left-to-right. `+1.0` = Black territory, `-1.0` = White territory. Use to render the heatmap overlay. |

### Next.js API route

```typescript
// src/app/api/ai-reviews/evaluate/route.ts
import { NextRequest, NextResponse } from "next/server"

const RUNPOD_URL = `https://api.runpod.ai/v2/${process.env.RUNPOD_ENDPOINT_ID}/runsync`

export async function POST(req: NextRequest) {
  const { moves, boardSize, komi, visits } = await req.json()

  const response = await fetch(RUNPOD_URL, {
    method: "POST",
    headers: {
      "Content-Type":  "application/json",
      "Authorization": `Bearer ${process.env.RUNPOD_API_KEY}`,
    },
    body: JSON.stringify({
      input: {
        job_type:   "evaluate",
        moves,
        board_size: boardSize ?? 19,
        komi:       komi ?? 6.5,
        visits:     visits ?? 200,
      },
    }),
  })

  if (!response.ok) {
    return NextResponse.json({ error: "Evaluation failed" }, { status: 502 })
  }

  const data = await response.json()
  return NextResponse.json(data.output)
}
```

### Usage from the browser

```typescript
async function evaluatePosition(moves: string[][], boardSize = 19, komi = 6.5) {
  const res = await fetch("/api/ai-reviews/evaluate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ moves, boardSize, komi, visits: 200 }),
  })
  return res.json()
  // { root, top_moves, ownership }
}
```

Call this whenever the user navigates to a move or plays out a variation. The response
arrives in ~1-2 seconds on a warm worker.

---

## Notes

- **Cold start**: The first job after the worker has been idle scales up a new pod, which
  takes 60-120 seconds. Subsequent jobs on a warm worker take ~6-10 seconds. The
  fire-and-forget + email pattern handles this gracefully since the user is not waiting
  at a spinner.

- **RunPod API key security**: Never use `NEXT_PUBLIC_RUNPOD_API_KEY`. The key must stay
  server-side. All calls to RunPod must go through a Next.js API route.

- **Testing the endpoint**: Open `test.html` in a browser, fill in the form, copy the
  generated payload, and paste it into RunPod dashboard → your endpoint → **Requests** tab.

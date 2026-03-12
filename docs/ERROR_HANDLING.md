# Error Handling — Frontend Guide

RunPod always returns HTTP 200, even for failed jobs. Success or failure lives
inside the JSON body. If you only check `response.ok` you will silently swallow
errors and get `undefined` data on the frontend.

---

## RunPod response shapes

### Job completed successfully
```json
{
  "id":     "abc123",
  "status": "COMPLETED",
  "output": { ... }
}
```

### Job failed (handler threw an exception)
```json
{
  "id":     "abc123",
  "status": "FAILED",
  "error":  "{\"error_type\": \"...\", \"error_message\": \"KataGo engine died during analysis\", ...}"
}
```

### Job timed out on /runsync (took longer than RunPod's sync limit ~30s)
```json
{
  "id":     "abc123",
  "status": "IN_PROGRESS"
}
```

---

## Corrected Next.js route — evaluate

```typescript
// src/app/api/ai-reviews/evaluate/route.ts
import { NextRequest, NextResponse } from "next/server"

const RUNPOD_URL = `https://api.runpod.ai/v2/${process.env.RUNPOD_ENDPOINT_ID}/runsync`

export async function POST(req: NextRequest) {
  const { moves, boardSize, komi, visits } = await req.json()

  let response: Response
  try {
    response = await fetch(RUNPOD_URL, {
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
  } catch (err) {
    // Network error — RunPod unreachable
    console.error("RunPod network error:", err)
    return NextResponse.json({ error: "Analysis service unreachable" }, { status: 503 })
  }

  if (!response.ok) {
    // RunPod returned a non-200 HTTP status (rare, usually auth or rate limit)
    const text = await response.text()
    console.error("RunPod HTTP error:", response.status, text)
    return NextResponse.json({ error: "Analysis service error" }, { status: 502 })
  }

  const data = await response.json()

  // RunPod timed out waiting for the job (cold start took >30s)
  if (data.status === "IN_PROGRESS" || data.status === "IN_QUEUE") {
    return NextResponse.json(
      { error: "Analysis timed out — worker is warming up, try again in a moment" },
      { status: 503 }
    )
  }

  // Job failed inside the worker (KataGo crash, bad input, etc.)
  if (data.status === "FAILED") {
    console.error("RunPod job failed:", data.error)
    return NextResponse.json(
      { error: "Analysis failed — please try again" },
      { status: 500 }
    )
  }

  // Success
  return NextResponse.json(data.output)
}
```

---

## Corrected Next.js route — review submit

For the async review (`/run`), the HTTP response tells you only whether the job
was **queued** successfully — not whether it completed. Failures during processing
are delivered by email. However you still need to handle queueing errors:

```typescript
// src/app/api/ai-reviews/submit/route.ts  (error handling section)

const response = await fetch(RUNPOD_URL, { ... })

if (!response.ok) {
  console.error("RunPod submit failed:", await response.text())
  return NextResponse.json(
    { error: "Could not submit review — please try again" },
    { status: 502 }
  )
}

const data = await response.json()

// /run returns status "IN_QUEUE" on success
if (data.status !== "IN_QUEUE") {
  console.error("Unexpected RunPod submit status:", data.status)
  return NextResponse.json(
    { error: "Could not queue review — please try again" },
    { status: 502 }
  )
}

return NextResponse.json({ submitted: true })
```

---

## What to show the user

| Error | User-facing message |
|---|---|
| Network / 503 | "Analysis is temporarily unavailable. Please try again in a moment." |
| 500 / FAILED | "Something went wrong during analysis. Please try again." |
| Timeout / IN_PROGRESS | "The analysis server is warming up. Please try again in 30 seconds." |
| Review submit failed | "Could not submit your game for review. Please try again." |

Keep messages vague to the user — log the full error server-side with `console.error`
so you can diagnose from Vercel / your hosting logs.

---

## Cold start behaviour

When the RunPod endpoint has been idle (min workers = 0), the first job spins up a
new GPU pod. This takes 60-120 seconds.

- **Review** (`/run`): not a problem — fire-and-forget, user is not waiting.
- **Evaluate** (`/runsync`): the sync timeout is ~30s, which is shorter than a cold
  start. The job will return `IN_PROGRESS` instead of `COMPLETED`.

**Options for evaluate cold starts:**
1. Show "warming up, try again in a moment" and let the user retry (simplest).
2. Set **min workers = 1** on the RunPod endpoint so there is always a warm worker.
   Costs ~$0.50-1.00/day depending on GPU but eliminates cold starts entirely.
3. Send a "warmup" evaluate request (empty moves list) when the user opens the
   game explorer page, before they actually need a result.

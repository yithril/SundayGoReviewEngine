# Handling 503 from the Bot Endpoint

`POST /suggest` can return `503 Service Unavailable` when the bot engine is at capacity.

## When it happens

The bot engine (`engine_fast`) handles up to 4 concurrent requests. If all 4 slots are in use, the next request gets a 503 instead of waiting.

## Response format

```json
{
  "detail": "Bot engine is busy. Retry shortly."
}
```

The response includes a `Retry-After: 5` header (seconds).

## What the frontend should do

1. **Catch 503** on `/suggest` responses.
2. **Show a user-friendly message** — e.g. "The bot is thinking for other players. Please try again in a few seconds."
3. **Retry after a short delay** — use `Retry-After` if present, otherwise 5 seconds. One or two retries is usually enough.
4. **Disable the "get bot move" button** while waiting, or show a spinner, so the user doesn't spam requests.

## Example (fetch)

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

  if (res.status === 503) {
    const retryAfter = parseInt(res.headers.get("Retry-After") ?? "5", 10)
    throw new Error(`Bot busy. Retry in ${retryAfter}s`)
  }

  if (!res.ok) throw new Error(await res.text())
  return res.json()
}
```

## Example (retry with backoff)

```typescript
async function getBotMoveWithRetry(
  moves: string[][],
  rank: string,
  maxRetries = 2
): Promise<{ move: string; win_rate: number; rank: string }> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const res = await fetch(/* ... */)

    if (res.status === 503 && attempt < maxRetries) {
      const retryAfter = parseInt(res.headers.get("Retry-After") ?? "5", 10) * 1000
      await new Promise((r) => setTimeout(r, retryAfter))
      continue
    }

    if (!res.ok) throw new Error(await res.text())
    return res.json()
  }
  throw new Error("Bot engine busy after retries")
}
```

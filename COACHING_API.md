# Coaching Evaluate API (frontend integration)

Single-position analysis for coaching: root evaluation, top moves with principal variation, ownership, and policy. Use this when the user asks for a hint or when you need to show “what KataGo thinks” about the current position.

---

## Endpoint

```
POST /coaching/evaluate
```

**Auth:** Same as other API routes. Send header:

```
X-API-Key: <your-api-key>
```

**Content-Type:** `application/json`

---

## Request body

| Field          | Type              | Required | Description |
|----------------|-------------------|----------|-------------|
| `moves`        | `array of [color, coord]` | Yes | Same format as `/suggest`: `[["B","D4"], ["W","Q16"], ...]`. Color is `"B"` or `"W"`, coord is KataGo style (e.g. `"D4"`, `"Q16"`, `"pass"`). |
| `board_size`   | number            | Yes      | `9`, `13`, or `19`. |
| `komi`         | number            | No       | Default `6.5`. |
| `player_color` | string            | Yes      | `"B"` or `"W"` (who is to move / whose perspective). |

**Example:**

```json
{
  "moves": [["B", "D4"], ["W", "Q16"], ["B", "D16"]],
  "board_size": 19,
  "komi": 6.5,
  "player_color": "W"
}
```

---

## Success response (HTTP 200)

When the backend gets a valid KataGo result, the body has this shape (all keys snake_case):

```ts
// TypeScript-friendly shape
interface TopMove {
  move: string;        // e.g. "R10" or "pass"
  order: number;       // 0 = best, 1 = second, ...
  winrate: number;     // 0–1
  score_lead: number;  // points (side to move)
  visits: number;
  pv: string[];        // principal variation, e.g. ["R10", "Q10", ...]
  prior: number;       // 0–1, policy prior
  lcb: number;         // lower confidence bound (win rate)
  score_stdev: number;
}

interface CoachEvaluateResponse {
  root: {
    winrate: number;       // 0–1, position evaluation
    score_lead: number;    // points for side to move
    current_player: "B" | "W";
    visits: number;
  };
  top_moves: TopMove[];   // up to 5 moves, may be fewer
  ownership: number[];    // 361 floats (19×19), see below
  ownership_stdev: number[];
  policy: number[];       // 362 floats (361 points + pass), NN policy before search
}
```

**Ownership:** Length 361 (19×19), **row-major** (first row left-to-right, then next row, etc.). `+1.0` = Black territory, `-1.0` = White territory.

**Policy:** Length 362. Same row-major order for the first 361; the last value is the pass probability. Values are in [0, 1] and sum to 1 for legal moves; illegal moves are typically 0 or a sentinel.

---

## Empty / error response (HTTP 200)

On timeout (~3 s) or KataGo engine error, the API still returns **HTTP 200** so the client does not block. The body is:

```json
{
  "utterance_key": null
}
```

**How to integrate:** Check for `utterance_key === null` (or absence of `root` / `top_moves`) to treat the response as “no coaching data” and show a message like “Analysis unavailable, try again” or hide the hint UI.

---

## Example usage

```javascript
const res = await fetch(`${API_BASE}/coaching/evaluate`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY,
  },
  body: JSON.stringify({
    moves: gameMoves,  // [["B","D4"], ["W","Q16"], ...]
    board_size: 19,
    komi: 6.5,
    player_color: "W",
  }),
});

const data = await res.json();

if (data.utterance_key === null || !data.root) {
  // No data — timeout or engine error
  showMessage("Analysis unavailable. Try again in a moment.");
  return;
}

// Success: use data.root, data.top_moves, data.ownership, data.policy
const bestMove = data.top_moves[0]?.move;
const positionWinRate = data.root.winrate;
// ...
```

---

## Summary

| Item | Value |
|------|--------|
| Method + path | `POST /coaching/evaluate` |
| Auth | `X-API-Key` header |
| Request | `moves`, `board_size`, `komi`, `player_color` (same `moves` format as `/suggest`) |
| Success | `root`, `top_moves` (≤5), `ownership`, `ownership_stdev`, `policy` |
| No data | HTTP 200 with `{ "utterance_key": null }` |

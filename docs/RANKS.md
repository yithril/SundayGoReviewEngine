# KataGo Rank Reference

Valid rank values for the `POST /suggest` endpoint's `rank` field.

KataGo was trained on KGS game data and can genuinely emulate human play at each of these levels — it doesn't just play randomly or limit search depth. It learned human patterns at each rank.

## Kyu Ranks (beginner → intermediate)

| `rank` value | Level |
|---|---|
| `"20k"` | Complete beginner |
| `"15k"` | Beginner |
| `"10k"` | Casual player |
| `"9k"` | |
| `"8k"` | |
| `"7k"` | |
| `"6k"` | Intermediate |
| `"5k"` | |
| `"4k"` | |
| `"3k"` | |
| `"2k"` | |
| `"1k"` | Strong intermediate |

## Dan Ranks (advanced → expert)

| `rank` value | Level |
|---|---|
| `"1d"` | Advanced amateur |
| `"2d"` | |
| `"3d"` | |
| `"4d"` | |
| `"5d"` | Strong amateur |
| `"6d"` | |
| `"7d"` | |
| `"8d"` | |
| `"9d"` | Top amateur / near professional |

## Usage Example

```typescript
const res = await fetch("https://api.sundaygolessons.com/suggest", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "X-API-Key": process.env.KATAGO_API_KEY!,
  },
  body: JSON.stringify({
    moves: [["B", "D4"], ["W", "Q16"], ["B", "Q4"]],
    rank: "7k",
    board_size: 19,
    komi: 6.5,
  }),
})

const { move, win_rate, rank } = await res.json()
// move    → "R16"
// win_rate → 0.5312  (Black's win probability)
// rank    → "7k"
```

## Notes

- `board_size` can be `9`, `13`, or `19`
- `komi` defaults to `6.5` if omitted
- `moves` is the full game history so far as `[["B"|"W", "coordinate"], ...]`
- Coordinates use KataGo format: column letter (A–T skipping I) + row number (1–19 from bottom), e.g. `"D4"`, `"Q16"`, `"R10"`
- A pass is represented as `"pass"`
- The response `move` is in the same coordinate format

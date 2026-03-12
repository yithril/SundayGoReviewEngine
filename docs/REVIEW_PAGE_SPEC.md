# Review Page UI Spec

Reference document for building `/reviews/[id]` in the frontend.
The email template (`mailer/sender.py`) is the canonical source of the layout and
design decisions; this spec translates those decisions into web-native terms.

---

## Brand Tokens

```ts
// Use these everywhere — don't hardcode hex values inline
const colors = {
  background:  "#f1f5f4",   // page/card background
  surface:     "#ffffff",   // card interior
  textPrimary: "#122120",   // all body and heading text
  textMuted:   "#6b7280",   // secondary labels, dates, captions
  textFaint:   "#aab8b5",   // placeholder / coming-soon text
  primary:     "#0ac254",   // Jade Green — CTA, YOU badge, filled stars, chart line
  accent:      "#ff2200",   // Coral — errors, blunder label, error borders
  divider:     "#e5edeb",   // horizontal rules between sections
  cardShadow:  "0 2px 8px rgba(18,33,32,0.10)",

  // Move quality label colors (match email exactly)
  quality: {
    excellent:  "#0ac254",
    great:      "#2563eb",
    good:       "#16a34a",
    inaccuracy: "#d97706",
    mistake:    "#ea580c",
    blunder:    "#ff2200",
  },

  // Stars
  starFilled: "#0ac254",
  starEmpty:  "#ccd8d6",
}
```

```ts
const fonts = {
  body:    "'Inter', Arial, Helvetica, sans-serif",
  heading: "'Playfair Display', Georgia, serif",
}
// Google Fonts import:
// Inter: weights 400, 600, 700
// Playfair Display: weight 700
```

---

## Data Source

```ts
// /reviews/[id]/page.tsx
const { data: review } = await supabase
  .from("game_reviews")
  .select("*")
  .eq("id", params.id)
  .single()

const report = review.report
```

Full `report` shape is documented in [`FRONTEND_INTEGRATION.md`](./FRONTEND_INTEGRATION.md#report-jsonb-structure).
New fields added since that document was written:

```ts
report.game_date         // string — from SGF "DT" tag, e.g. "2024-11-03". May be "".
report.story             // string — narrative paragraph. Empty string until analysis is implemented.
report.skills_used       // { name: string; stars: number }[]  — stars 0–5. Empty array until implemented.
report.did_well          // { explanation: string; move_number: number | null }[]
report.needs_improvement // { explanation: string; move_number: number | null }[]
report.match_highlights  // { explanation: string; move_number: number | null }[]
// move_number: 1-indexed game move to show as board snapshot. null = no snapshot for this item.
```

---

## Page Layout

Max content width: **860px** (wider than the email's 600px — use the extra space).
Side padding: **24px** on mobile, **32px** on desktop.
Background: `#f1f5f4`.

The page is a single vertical column of sections inside a white rounded card,
matching the email card structure. Sections are separated by `1px solid #e5edeb` rules.

```
┌──────────────────────────────────────────────────────┐
│  HEADER BANNER  (#122120 bg, full width)             │
├──────────────────────────────────────────────────────┤
│  Player identity line + game date                    │
├──────────────────────────────────────────────────────┤
│  Win Rate Chart  (full width, ~120px tall)           │
├──────────────────────────────────────────────────────┤
│  The Story of the Game  (full width)                 │
├──────────────────────────────────────────────────────┤
│  Move Quality  │  Go Skills Showed Off This Game     │
│  (50% / 50%)   │  (50% / 50%)                        │
├──────────────────────────────────────────────────────┤
│  Things You Did Well  (full width)                   │
├──────────────────────────────────────────────────────┤
│  Things to Improve  (full width)                     │
├──────────────────────────────────────────────────────┤
│  Match Highlights  (full width)                      │
└──────────────────────────────────────────────────────┘
```

---

## Section Specs

### 1. Header Banner

Background: `#122120`. Padding: `28px 32px`.

```
"Your Game Review is Ready"          font: Playfair Display 700, 28px, white
"SUNDAY GO LESSONS"                  font: Inter 700, 13px, #0ac254,
                                          uppercase, letter-spacing 0.05em
```

On the web page this is the hero — consider making the title larger (32–36px)
since you aren't constrained by email width.

---

### 2. Player Identity

```
DaveGo4545 (YOU) · Black   vs   SnakeMing · White
2024-11-03
```

Markup logic:

```tsx
<p>
  <span className="font-bold text-[17px]">{report.player_name}</span>
  {" "}
  <span className="font-bold text-primary">(YOU)</span>
  <span className="text-muted text-[15px]"> · {playerLabel}</span>
  <span className="text-primary font-normal"> {" vs "} </span>
  <span className="font-bold text-[17px]">{report.opponent_name}</span>
  <span className="text-muted text-[15px]"> · {opponentLabel}</span>
</p>
{report.game_date && (
  <p className="text-[13px] text-muted mt-1">{report.game_date}</p>
)}
```

Where `playerLabel = report.player_color === "B" ? "Black" : "White"` and
`opponentLabel` is the inverse.

---

### 3. Win Rate Chart

**Email**: static PNG via QuickChart.io (email constraint).
**Web**: use a real charting library — Recharts or Chart.js recommended.

Chart spec:

| Property | Value |
|---|---|
| Height | ~120px |
| Width | 100% of container |
| Y axis range | 0 – 1 (shown as 0% / 50% / 100%) |
| X axis | hidden (move count is not meaningful at trend scale) |
| Data | `report.win_rates` — already from the reviewed player's perspective, plot directly |
| Downsampling | ~50 evenly-spaced points for trend clarity |
| Line color | `#0ac254`, width 2px |
| Area fill | `rgba(10,194,84,0.15)` below the line |
| 50% reference | flat dashed line, `#ccd8d6`, 1px, dash `[5,4]` |
| Point dots | none (`pointRadius: 0`) |
| Curve tension | 0.5 (smooth bezier) |
| Background | `#f1f5f4` rounded `6px` |
| Legend | none |

**Recharts example:**

```tsx
import { LineChart, Line, ReferenceLine, ResponsiveContainer, YAxis } from "recharts"

const data = playerRates.map((v, i) => ({ i, v }))

<ResponsiveContainer width="100%" height={120}>
  <LineChart data={data}>
    <YAxis domain={[0, 1]} ticks={[0, 0.5, 1]}
           tickFormatter={v => v === 0 ? "0%" : v === 0.5 ? "50%" : "100%"}
           width={36} tick={{ fontSize: 10, fill: "#6b7280" }} axisLine={false} tickLine={false} />
    <ReferenceLine y={0.5} stroke="#ccd8d6" strokeDasharray="5 4" strokeWidth={1} />
    <Line type="monotone" dataKey="v" stroke="#0ac254" strokeWidth={2}
          dot={false} isAnimationActive={false} />
  </LineChart>
</ResponsiveContainer>
```

---

### 4. The Story of the Game

Section heading: Playfair Display 700, 20px, `#122120`.
Body text: Inter 400, 15px, `#122120`, line-height 1.7.

```tsx
<h2 style={{ fontFamily: fonts.heading, fontSize: 20, fontWeight: 700 }}>
  The Story of the Game
</h2>
<p style={{ fontSize: 15, lineHeight: 1.7, color: colors.textPrimary }}>
  {report.story || LOREM_IPSUM_PLACEHOLDER}
</p>
```

When `report.story` is an empty string, render a placeholder paragraph.

---

### 5. Move Quality + Go Skills (Two-Column Row)

Side by side, divided by a `1px solid #e5edeb` vertical rule.
On mobile (< 640px): stack vertically; Move Quality on top, separated by a
horizontal rule.

#### Move Quality (left column)

Section label: Inter 700, 12px, `#6b7280`, uppercase, letter-spacing 0.08em.

One row per category in this order: `excellent → great → good → inaccuracy → mistake → blunder`.

```ts
const QUALITY_META = {
  excellent:  { icon: "⭐", color: "#0ac254" },
  great:      { icon: "👍", color: "#2563eb" },
  good:       { icon: "✅", color: "#16a34a" },
  inaccuracy: { icon: "⚠️", color: "#d97706" },
  mistake:    { icon: "❌", color: "#ea580c" },
  blunder:    { icon: "💥", color: "#ff2200" },
}
```

Each row: `[icon]  [colored label]  [count right-aligned]`

- Icon: 15px, vertically centered
- Label: 14px, `font-weight: 600`, color from `QUALITY_META[label].color`, capitalized
- Count: 14px, `font-weight: 700`, `#122120`, right-aligned
- Fixed column widths: icon ~28px, label ~100px, count ~28px

```tsx
{QUALITY_ORDER.map(label => (
  <tr key={label}>
    <td style={{ width: 28, fontSize: 15 }}>{QUALITY_META[label].icon}</td>
    <td style={{ width: 100, color: QUALITY_META[label].color, fontWeight: 600,
                 fontSize: 14, textTransform: "capitalize", paddingRight: 16 }}>
      {label}
    </td>
    <td style={{ width: 28, fontWeight: 700, fontSize: 14, textAlign: "right" }}>
      {report.move_quality_counts[label] ?? 0}
    </td>
  </tr>
))}
```

#### Go Skills (right column)

Section label: same style as Move Quality label.

Each skill: `[name]  [★★★☆☆]`

- Name column: flexible width, 14px, `#122120`, `font-weight: 600`
- Stars column: fixed ~90px, `white-space: nowrap`
- Filled star (★): `#0ac254`, 16px, letter-spacing 1px
- Empty star (☆): `#ccd8d6`, 16px, letter-spacing 1px
- Max 5 stars per skill

**Placeholder state** (when `report.skills_used` is `[]`):
- Render 3 rows with name "Coming soon…" in `#aab8b5` italic 13px, all 0 stars

```tsx
function StarRating({ stars, max = 5 }: { stars: number; max?: number }) {
  return (
    <span style={{ whiteSpace: "nowrap" }}>
      <span style={{ color: "#0ac254", fontSize: 16, letterSpacing: 1 }}>
        {"★".repeat(Math.min(stars, max))}
      </span>
      <span style={{ color: "#ccd8d6", fontSize: 16, letterSpacing: 1 }}>
        {"☆".repeat(max - Math.min(stars, max))}
      </span>
    </span>
  )
}
```

---

### 6. Content Sections: Things You Did Well / Things to Improve / Match Highlights

All three sections follow identical structure. Each is separated from the previous by
a `1px solid #e5edeb` horizontal rule.

**Section heading**: Playfair Display 700, 19px, `#122120`, line-height 1.2.

**Each item** is one of two layouts depending on whether `move_number` is set:

#### With board snapshot (`move_number !== null`)

Two-column row: 160px snapshot on the left, explanation text on the right.

```tsx
<div style={{ display: "flex", gap: 16, alignItems: "center", marginBottom: 16 }}>
  <div style={{ flexShrink: 0, width: 140, height: 140,
                background: "#e2eae8", borderRadius: 6,
                display: "flex", alignItems: "center", justifyContent: "center" }}>
    {/* TODO: render SGF board snapshot at move_number */}
    <span style={{ fontSize: 11, color: "#6b7280", textAlign: "center" }}>
      Board Position<br/>(Move {item.move_number})
    </span>
  </div>
  <p style={{ fontSize: 14, color: "#122120", lineHeight: 1.6 }}>
    {item.explanation}
  </p>
</div>
```

On mobile: stack vertically (snapshot on top, text below).

#### Without board snapshot (`move_number === null`)

Full-width explanation, center-justified.

```tsx
<p style={{ fontSize: 14, color: "#122120", lineHeight: 1.6,
            textAlign: "center", marginBottom: 16 }}>
  {item.explanation}
</p>
```

**Empty state** (when the section array is `[]`):

```tsx
<p style={{ fontSize: 14, color: "#aab8b5", fontStyle: "italic", textAlign: "center" }}>
  Analysis coming soon — check back after the full review is processed.
</p>
```

---

### 7. Differences from the Email

The web page can do things the email cannot:

| Feature | Email | Web page |
|---|---|---|
| Win rate chart | Static PNG (QuickChart.io) | Live Recharts/Chart.js with hover tooltips showing exact win% and move number |
| Board snapshots | Grey placeholder box | Real SGF board renderer (when `move_number` is set) |
| Move explorer | Not possible | Click any item to jump to that move in an interactive board |
| Responsiveness | Media query only | Full responsive layout with breakpoints |
| Fonts | May fall back to Georgia/Arial | Always Inter + Playfair Display |
| Card width | 600px fixed | Max 860px, fluid |

The chart hover tooltip suggestion for the web:

```
Move 42 — 68%
```

Shown on cursor position, formatted as `Move {move_number} — {Math.round(winRate * 100)}%`.

---

## Component Checklist

When building the page, one component per section:

- [ ] `ReviewHeader` — banner with title + branding
- [ ] `PlayerIdentity` — names, YOU badge, color labels, date
- [ ] `WinRateChart` — Recharts line chart with 50% reference and area fill
- [ ] `GameStory` — heading + paragraph, lorem ipsum fallback
- [ ] `MoveQualityTable` — icon / label / count rows
- [ ] `GoSkillsTable` — name / star rating rows, placeholder state
- [ ] `ContentSection` — reusable for Did Well, To Improve, Highlights; accepts heading + items array
- [ ] `SectionItem` — handles snapshot-left/text-right vs full-width layouts
- [ ] `StarRating` — filled/empty stars

All components read from `report` (the JSONB object from Supabase) — nothing is
fetched separately.

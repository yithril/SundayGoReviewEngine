from __future__ import annotations

import json
import os
import logging
import math
import urllib.parse
import requests

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"

QUALITY_ORDER = ["excellent", "great", "good", "inaccuracy", "mistake", "blunder"]

QUALITY_META = {
    "excellent":  {"icon": "⭐", "color": "#0ac254"},
    "great":      {"icon": "👍", "color": "#2563eb"},
    "good":       {"icon": "✅", "color": "#16a34a"},
    "inaccuracy": {"icon": "⚠️", "color": "#d97706"},
    "mistake":    {"icon": "❌", "color": "#ea580c"},
    "blunder":    {"icon": "💥", "color": "#ff2200"},
}

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _resend_headers() -> dict:
    return {
        "Authorization": f"Bearer {os.environ['RESEND_API_KEY']}",
        "Content-Type": "application/json",
    }


def _from_address() -> str:
    return os.environ.get("RESEND_FROM_EMAIL", "no-reply@sundaygolessons.com")


def _review_url(review_id: str) -> str:
    base = os.environ.get("APP_BASE_URL", "https://sundaygolessons.com").rstrip("/")
    return f"{base}/reviews/{review_id}"


# ---------------------------------------------------------------------------
# Win-rate chart (QuickChart.io PNG — email-safe img tag)
# ---------------------------------------------------------------------------

_QUICKCHART_BASE = "https://quickchart.io/chart"
_CHART_TARGET_POINTS = 50  # always reduce to this for a clean trend line


def _win_rate_img(win_rates: list[float], player_color: str) -> str:
    """
    Return an <img> tag containing a win-rate line chart rendered by QuickChart.io.

    Inline SVG is stripped by Gmail and most email clients, leaving only leaked
    text nodes.  QuickChart.io accepts a Chart.js config via URL and returns a
    PNG, which every email client renders as a plain <img> tag.

    The chart shows the reviewed player's win rate (0–1 on Y) across moves
    (X axis).  A flat 0.5 reference dataset provides the 50 % midline.
    Win rates from build_report are stored from Black's perspective; we flip
    for White so the line always represents "your" position.
    """
    if not win_rates:
        return ""

    # Convert to player perspective
    if player_color == "B":
        player_rates = win_rates
    else:
        player_rates = [round(1.0 - wr, 4) for wr in win_rates]

    # Always downsample to a trend-friendly point count
    n = len(player_rates)
    if n > _CHART_TARGET_POINTS:
        step = math.ceil(n / _CHART_TARGET_POINTS)
        sampled = player_rates[::step]
        # Always include the final value so the line ends at the true result
        if sampled[-1] != player_rates[-1]:
            sampled.append(player_rates[-1])
        player_rates = sampled

    n_points = len(player_rates)
    labels   = list(range(n_points))
    midline  = [0.5] * n_points

    config = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Win Rate",
                    "data": player_rates,
                    "fill": True,
                    "backgroundColor": "rgba(10,194,84,0.15)",
                    "borderColor": "#0ac254",
                    "borderWidth": 2,
                    "pointRadius": 0,
                    "tension": 0.5,
                    "order": 1,
                },
                {
                    "label": "50%",
                    "data": midline,
                    "fill": False,
                    "borderColor": "#ccd8d6",
                    "borderWidth": 1,
                    "borderDash": [5, 4],
                    "pointRadius": 0,
                    "tension": 0,
                    "order": 2,
                },
            ],
        },
        "options": {
            "legend":  {"display": False},
            "scales": {
                "xAxes": [{"display": False}],
                "yAxes": [
                    {
                        "display": True,
                        "ticks": {
                            "min": 0,
                            "max": 1,
                            "stepSize": 0.5,
                            "callback": "function(v){return v===0?'0%':v===0.5?'50%':v===1?'100%':''}",
                            "fontColor": "#6b7280",
                            "fontSize": 10,
                        },
                        "gridLines": {"display": False},
                    }
                ],
            },
            "plugins": {"datalabels": {"display": False}},
        },
    }

    encoded = urllib.parse.quote(json.dumps(config, separators=(",", ":")))
    src = f"{_QUICKCHART_BASE}?w=536&h=110&bkg=%23f1f5f4&c={encoded}"

    return (
        f'<img src="{src}" width="536" height="110"'
        f' style="display:block;max-width:100%;border-radius:6px"'
        f' alt="Win rate across the game">'
    )


# ---------------------------------------------------------------------------
# Move quality table rows (with icons)
# ---------------------------------------------------------------------------

def _quality_table_rows(counts: dict) -> str:
    rows = [
        # Invisible header row fixes column widths so counts don't shift
        '<tr>'
        '<td style="width:28px"></td>'
        '<td style="width:100px"></td>'
        '<td style="width:28px"></td>'
        '</tr>'
    ]
    for label in QUALITY_ORDER:
        n     = counts.get(label, 0)
        meta  = QUALITY_META[label]
        icon  = meta["icon"]
        color = meta["color"]
        rows.append(
            f'<tr>'
            f'<td style="padding:5px 8px 5px 0;font-size:15px;line-height:1;'
            f'vertical-align:middle">{icon}</td>'
            f'<td style="padding:5px 16px 5px 0;color:{color};font-weight:600;'
            f'text-transform:capitalize;font-size:14px;vertical-align:middle">{label}</td>'
            f'<td style="padding:5px 0;color:#122120;font-size:14px;font-weight:700;'
            f'text-align:right;vertical-align:middle">{n}</td>'
            f'</tr>'
        )
    return "".join(rows)


# ---------------------------------------------------------------------------
# Go Skills stars
# ---------------------------------------------------------------------------

def _skill_stars(stars: int, max_stars: int = 5) -> str:
    filled = "★" * min(stars, max_stars)
    empty  = "☆" * (max_stars - min(stars, max_stars))
    return (
        f'<span style="color:#0ac254;font-size:16px;letter-spacing:1px">{filled}</span>'
        f'<span style="color:#ccd8d6;font-size:16px;letter-spacing:1px">{empty}</span>'
    )


def _skills_rows(skills: list[dict]) -> str:
    if not skills:
        skills = [
            {"name": "Coming soon…", "stars": 0},
            {"name": "Coming soon…", "stars": 0},
            {"name": "Coming soon…", "stars": 0},
        ]
        placeholder = True
    else:
        placeholder = False

    rows = [
        # Fix column widths: name expands, stars column stays fixed
        '<tr>'
        '<td style="width:auto"></td>'
        '<td style="width:90px"></td>'
        '</tr>'
    ]
    for skill in skills:
        name_style = (
            "color:#aab8b5;font-style:italic;font-size:13px"
            if placeholder
            else "color:#122120;font-weight:600;font-size:14px"
        )
        rows.append(
            f'<tr>'
            f'<td style="padding:5px 14px 5px 0;vertical-align:middle;{name_style}">'
            f'{skill["name"]}</td>'
            f'<td style="padding:5px 0;vertical-align:middle;white-space:nowrap">'
            f'{_skill_stars(skill["stars"])}</td>'
            f'</tr>'
        )
    return "".join(rows)


# ---------------------------------------------------------------------------
# Content section items (did well / improve / highlights)
# ---------------------------------------------------------------------------

_PLACEHOLDER_ITEM = {
    "explanation": "Analysis coming soon — check your full interactive review.",
    "move_number": None,
}


def _section_items(items: list[dict]) -> str:
    if not items:
        items = [_PLACEHOLDER_ITEM]

    rows = []
    for item in items:
        explanation = item.get("explanation", "")
        move_number = item.get("move_number")

        if move_number is not None:
            # Two-column: board snapshot placeholder on left, text on right
            rows.append(f"""
      <tr>
        <td valign="top" width="160" style="padding:0 16px 16px 0;text-align:center">
          <div style="width:140px;height:140px;background:#e2eae8;border-radius:6px;
                      display:inline-flex;align-items:center;justify-content:center;
                      font-size:11px;color:#6b7280;font-family:Georgia,serif;
                      line-height:1.4;text-align:center">
            Board<br>Position<br><span style="font-size:10px">(Move {move_number})</span>
          </div>
        </td>
        <td valign="middle" style="padding:0 0 16px 0;text-align:center">
          <p style="margin:0;font-size:14px;color:#122120;line-height:1.6">{explanation}</p>
        </td>
      </tr>""")
        else:
            # Full-width explanation
            rows.append(f"""
      <tr>
        <td colspan="2" style="padding:0 0 16px 0;text-align:center">
          <p style="margin:0;font-size:14px;color:#122120;line-height:1.6">{explanation}</p>
        </td>
      </tr>""")

    return "".join(rows)


def _section_block(heading: str, items: list[dict]) -> str:
    return f"""
      <!-- {heading} -->
      <tr><td style="padding:0 32px"><hr style="border:none;border-top:1px solid #e5edeb;margin:0"></td></tr>
      <tr><td style="padding:24px 32px 0 32px">
        <p style="margin:0 0 16px 0;font-size:19px;font-weight:700;color:#122120;
                  font-family:'Playfair Display',Georgia,serif;line-height:1.2">{heading}</p>
        <table width="100%" cellpadding="0" cellspacing="0">
          {_section_items(items)}
        </table>
      </td></tr>"""


# ---------------------------------------------------------------------------
# Success email HTML
# ---------------------------------------------------------------------------

def _success_html(report: dict, review_url: str) -> str:
    player_color   = report["player_color"]
    player_label   = "Black" if player_color == "B" else "White"
    opponent_label = "White" if player_color == "B" else "Black"
    player_name    = report.get("player_name", player_label)
    opponent_name  = report.get("opponent_name", "Opponent")
    game_date      = report.get("game_date", "")
    counts         = report.get("move_quality_counts", {})
    win_rates      = report.get("win_rates", [])
    story          = report.get("story", "")
    skills         = report.get("skills_used", [])
    did_well       = report.get("did_well", [])
    improvements   = report.get("needs_improvement", [])
    highlights     = report.get("match_highlights", [])

    win_svg        = _win_rate_img(win_rates, player_color)
    quality_rows   = _quality_table_rows(counts)
    skills_rows    = _skills_rows(skills)

    date_line = (
        f'<p style="margin:4px 0 0 0;font-size:13px;color:#6b7280">{game_date}</p>'
        if game_date else ""
    )

    story_text = story or (
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. "
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris."
    )

    did_well_block    = _section_block("Things You Did Well", did_well)
    improve_block     = _section_block("Things to Improve", improvements)
    highlights_block  = _section_block("Match Highlights", highlights)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
  <style>
    body {{ margin:0;padding:0;background:#f1f5f4;
           font-family:'Inter',Arial,Helvetica,sans-serif;color:#122120 }}
    h1,h2,h3 {{ font-family:'Playfair Display',Georgia,serif }}
    @media only screen and (max-width:620px) {{
      .outer-wrap  {{ padding:16px 0 !important }}
      .main-card   {{ width:100% !important;border-radius:0 !important }}
      .card-pad    {{ padding:20px 16px !important }}
      .two-col td  {{ display:block !important;width:100% !important;
                      border-right:none !important;padding-left:0 !important }}
      .two-col .divider-col {{ border-bottom:1px solid #e5edeb;padding-bottom:20px !important;
                               margin-bottom:20px }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background:#f1f5f4;
             font-family:'Inter',Arial,Helvetica,sans-serif;color:#122120">

<table width="100%" cellpadding="0" cellspacing="0" class="outer-wrap"
       style="background:#f1f5f4;padding:32px 0">
  <tr><td align="center">
    <table width="600" class="main-card" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:10px;overflow:hidden;
                  box-shadow:0 2px 8px rgba(18,33,32,.10)">

      <!-- ── Header banner ─────────────────────────────────────── -->
      <tr><td style="background:#122120;padding:28px 32px">
        <p style="margin:0;font-size:24px;font-weight:700;color:#ffffff;
                  font-family:'Playfair Display',Georgia,serif;line-height:1.2">
          Your Game Review is Ready
        </p>
        <p style="margin:8px 0 0 0;font-size:13px;color:#0ac254;
                  font-family:'Inter',Arial,Helvetica,sans-serif;letter-spacing:.05em;
                  text-transform:uppercase">
          Sunday Go Lessons
        </p>
      </td></tr>

      <!-- ── Player identity ───────────────────────────────────── -->
      <tr><td style="padding:24px 32px 0 32px">
        <p style="margin:0;font-size:17px;font-weight:700;color:#122120;line-height:1.5">
          {player_name}
          <span style="color:#0ac254;font-weight:700">(YOU)</span>
          <span style="color:#6b7280;font-weight:400;font-size:15px">&nbsp;·&nbsp;{player_label}</span>
          <span style="color:#122120;font-weight:400">&nbsp;vs&nbsp;</span>
          {opponent_name}
          <span style="color:#6b7280;font-weight:400;font-size:15px">&nbsp;·&nbsp;{opponent_label}</span>
        </p>
        {date_line}
      </td></tr>

      <!-- ── Win-rate line graph ────────────────────────────────── -->
      <tr><td style="padding:20px 32px 0 32px">
        <p style="margin:0 0 8px 0;font-size:12px;font-weight:600;color:#6b7280;
                  text-transform:uppercase;letter-spacing:.06em">Win Rate</p>
        {win_svg}
      </td></tr>

      <!-- ── Story of the game ─────────────────────────────────── -->
      <tr><td style="padding:28px 32px 0 32px">
        <p style="margin:0 0 12px 0;font-size:20px;font-weight:700;color:#122120;
                  font-family:'Playfair Display',Georgia,serif">
          The Story of the Game
        </p>
        <p style="margin:0;font-size:15px;color:#122120;line-height:1.7">
          {story_text}
        </p>
      </td></tr>

      <!-- ── Move quality + Go skills (two columns) ────────────── -->
      <tr><td style="padding:28px 32px 0 32px">
        <table width="100%" cellpadding="0" cellspacing="0" class="two-col">
          <tr valign="top">

            <!-- Move quality -->
            <td width="50%" class="divider-col"
                style="padding-right:20px;border-right:1px solid #e5edeb">
              <p style="margin:0 0 12px 0;font-size:12px;font-weight:700;
                         text-transform:uppercase;letter-spacing:.08em;color:#6b7280">
                Move Quality
              </p>
              <table width="100%" cellpadding="0" cellspacing="0">
                {quality_rows}
              </table>
            </td>

            <!-- Go skills -->
            <td width="50%" style="padding-left:20px">
              <p style="margin:0 0 12px 0;font-size:12px;font-weight:700;
                         text-transform:uppercase;letter-spacing:.08em;color:#6b7280">
                Go Skills Showed Off This Game
              </p>
              <table width="100%" cellpadding="0" cellspacing="0">
                {skills_rows}
              </table>
            </td>

          </tr>
        </table>
      </td></tr>

      <!-- ── Things You Did Well ───────────────────────────────── -->
      {did_well_block}

      <!-- ── Things to Improve ─────────────────────────────────── -->
      {improve_block}

      <!-- ── Match Highlights ──────────────────────────────────── -->
      {highlights_block}

      <!-- ── CTA button ─────────────────────────────────────────── -->
      <tr><td style="padding:28px 32px 0 32px"><hr style="border:none;border-top:1px solid #e5edeb;margin:0"></td></tr>
      <tr><td style="padding:28px 32px 36px 32px" align="center">
        <a href="{review_url}"
           style="background:#0ac254;color:#ffffff;text-decoration:none;
                  padding:14px 36px;border-radius:6px;font-size:15px;
                  font-weight:700;display:inline-block;
                  font-family:'Inter',Arial,Helvetica,sans-serif;
                  letter-spacing:.03em">
          View Full Interactive Review →
        </a>
      </td></tr>

    </table>
  </td></tr>
</table>

</body>
</html>"""


# ---------------------------------------------------------------------------
# Success email plain text
# ---------------------------------------------------------------------------

def _success_text(report: dict, review_url: str) -> str:
    player_color   = report["player_color"]
    player_label   = "Black" if player_color == "B" else "White"
    opponent_label = "White" if player_color == "B" else "Black"
    player_name    = report.get("player_name", player_label)
    opponent_name  = report.get("opponent_name", "Opponent")
    game_date      = report.get("game_date", "")
    counts         = report.get("move_quality_counts", {})
    story          = report.get("story", "")

    date_str = f" · {game_date}" if game_date else ""

    lines = [
        "Your Game Review is Ready — Sunday Go Lessons",
        "",
        f"{player_name} (YOU, {player_label}) vs {opponent_name} ({opponent_label}){date_str}",
        "",
    ]

    if story:
        lines += ["The Story of the Game", "-" * 22, story, ""]

    lines += ["Move Quality", "-" * 12]
    for label in QUALITY_ORDER:
        meta = QUALITY_META[label]
        lines.append(f"  {meta['icon']} {label.capitalize()}: {counts.get(label, 0)}")

    lines += [
        "",
        "View your full interactive review:",
        review_url,
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public send functions
# ---------------------------------------------------------------------------

def send_success_email(to: str, report: dict, review_id: str) -> None:
    url  = _review_url(review_id)
    html = _success_html(report, url)
    text = _success_text(report, url)

    player_label = "Black" if report["player_color"] == "B" else "White"
    game_date    = report.get("game_date", "")
    date_part    = f", {game_date}" if game_date else ""
    subject = f"Your Sunday Go Lessons review is ready ({player_label}{date_part})"

    resp = requests.post(
        RESEND_URL,
        headers=_resend_headers(),
        json={
            "from":    _from_address(),
            "to":      [to],
            "subject": subject,
            "html":    html,
            "text":    text,
        },
        timeout=15,
    )
    resp.raise_for_status()
    logger.info("Success email sent to %s (review %s)", to, review_id)


# ---------------------------------------------------------------------------
# Failure email
# ---------------------------------------------------------------------------

def send_failure_email(to: str, error_msg: str) -> None:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Playfair+Display:wght@700&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:#f1f5f4;font-family:'Inter',Arial,Helvetica,sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0"
           style="background:#ffffff;border-radius:10px;overflow:hidden;
                  box-shadow:0 2px 8px rgba(18,33,32,.10)">
      <tr><td style="background:#122120;padding:28px 32px">
        <p style="margin:0;font-size:24px;font-weight:700;color:#ffffff;
                  font-family:'Playfair Display',Georgia,serif">
          Review Processing Failed
        </p>
        <p style="margin:8px 0 0 0;font-size:13px;color:#0ac254;
                  text-transform:uppercase;letter-spacing:.05em">
          Sunday Go Lessons
        </p>
      </td></tr>
      <tr><td style="padding:28px 32px">
        <p style="margin:0 0 12px 0;font-size:15px;color:#122120;line-height:1.6">
          Unfortunately we were not able to process your game review.
          Please try uploading your SGF again.
        </p>
        <p style="margin:0 0 16px 0;font-size:13px;color:#6b7280;line-height:1.5">
          If the problem persists, please contact us and include the error detail below.
        </p>
        <pre style="margin:0;padding:12px 16px;background:#f1f5f4;border-radius:6px;
                    font-size:12px;color:#122120;white-space:pre-wrap;
                    word-break:break-word;border-left:3px solid #ff2200">{error_msg[:500]}</pre>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""

    text = (
        "Review Processing Failed — Sunday Go Lessons\n\n"
        "Unfortunately we could not process your game review. "
        "Please try uploading your SGF again.\n\n"
        f"Error: {error_msg[:300]}"
    )

    resp = requests.post(
        RESEND_URL,
        headers=_resend_headers(),
        json={
            "from":    _from_address(),
            "to":      [to],
            "subject": "Sunday Go Lessons — your review could not be processed",
            "html":    html,
            "text":    text,
        },
        timeout=15,
    )
    resp.raise_for_status()
    logger.info("Failure email sent to %s", to)

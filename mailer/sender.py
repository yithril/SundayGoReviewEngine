from __future__ import annotations

import os
import logging
import requests

logger = logging.getLogger(__name__)

RESEND_URL = "https://api.resend.com/emails"

QUALITY_ORDER = ["excellent", "great", "good", "inaccuracy", "mistake", "blunder"]
QUALITY_COLORS = {
    "excellent":  "#7c3aed",
    "great":      "#2563eb",
    "good":       "#16a34a",
    "inaccuracy": "#d97706",
    "mistake":    "#ea580c",
    "blunder":    "#dc2626",
}


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
# Success email
# ---------------------------------------------------------------------------

def _quality_table_rows(counts: dict) -> str:
    rows = []
    for label in QUALITY_ORDER:
        n = counts.get(label, 0)
        color = QUALITY_COLORS[label]
        rows.append(
            f'<tr>'
            f'<td style="padding:4px 12px 4px 0;color:{color};font-weight:600;text-transform:capitalize">{label}</td>'
            f'<td style="padding:4px 0;color:#111">{n}</td>'
            f'</tr>'
        )
    return "".join(rows)


def _win_rate_bar(win_rates: list[float], player_color: str) -> str:
    """Render a very simple text-based win rate arc summary."""
    if not win_rates:
        return ""

    final_wr = win_rates[-1] if player_color == "B" else 1.0 - win_rates[-1]
    pct = round(final_wr * 100)

    bar_filled = round(pct / 5)   # out of 20 blocks
    bar = "█" * bar_filled + "░" * (20 - bar_filled)

    return (
        f'<p style="font-family:monospace;font-size:13px;color:#374151;margin:0 0 4px 0">'
        f'Final win rate: {bar} {pct}%'
        f'</p>'
    )


def _success_html(report: dict, review_url: str) -> str:
    player_label   = "Black" if report["player_color"] == "B" else "White"
    player_name    = report.get("player_name", player_label)
    opponent_name  = report.get("opponent_name", "Opponent")
    total_moves    = report["total_moves"]
    katago_secs    = report.get("katago_seconds", 0)
    counts         = report.get("move_quality_counts", {})
    win_rates      = report.get("win_rates", [])

    quality_rows   = _quality_table_rows(counts)
    win_bar        = _win_rate_bar(win_rates, report["player_color"])

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f9fafb;padding:32px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">

      <!-- Header -->
      <tr><td style="background:#1e1b4b;padding:28px 32px">
        <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff">Your Game Review is Ready</p>
        <p style="margin:6px 0 0 0;font-size:14px;color:#a5b4fc">Sunday Go Lessons</p>
      </td></tr>

      <!-- Game identity -->
      <tr><td style="padding:24px 32px 0 32px">
        <p style="margin:0;font-size:15px;color:#374151">
          <strong>{player_name}</strong> played as <strong>{player_label}</strong> vs {opponent_name}
          &nbsp;&middot;&nbsp; {total_moves} moves
        </p>
        <p style="margin:6px 0 0 0;font-size:13px;color:#6b7280">
          KataGo analyzed {total_moves} moves in {katago_secs:.1f} seconds
        </p>
      </td></tr>

      <!-- Game summary -->
      <tr><td style="padding:16px 32px 0 32px">
        <p style="margin:0;font-size:15px;color:#111827">{report.get('game_summary', '')}</p>
      </td></tr>

      <!-- Win rate bar -->
      <tr><td style="padding:16px 32px 0 32px">{win_bar}</td></tr>

      <!-- Move quality table -->
      <tr><td style="padding:20px 32px 0 32px">
        <p style="margin:0 0 10px 0;font-size:14px;font-weight:600;color:#111827;text-transform:uppercase;letter-spacing:.05em">Move Quality</p>
        <table cellpadding="0" cellspacing="0">
          {quality_rows}
        </table>
      </td></tr>

      <!-- Skeleton sections note -->
      <tr><td style="padding:24px 32px 0 32px">
        <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;border-radius:6px">
          <tr><td style="padding:16px 20px">
            <p style="margin:0 0 8px 0;font-size:14px;font-weight:600;color:#374151">Coming soon in your full report</p>
            <ul style="margin:0;padding-left:18px;color:#6b7280;font-size:13px;line-height:1.8">
              <li>Go skills observed in this game</li>
              <li>What you did well</li>
              <li>What to work on next</li>
              <li>The story of the game</li>
            </ul>
          </td></tr>
        </table>
      </td></tr>

      <!-- CTA button -->
      <tr><td style="padding:28px 32px 32px 32px" align="center">
        <a href="{review_url}"
           style="background:#4f46e5;color:#ffffff;text-decoration:none;padding:13px 28px;border-radius:6px;font-size:15px;font-weight:600;display:inline-block">
          View Full Interactive Review
        </a>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def _success_text(report: dict, review_url: str) -> str:
    counts      = report.get("move_quality_counts", {})
    total_moves = report["total_moves"]
    katago_secs = report.get("katago_seconds", 0)

    lines = [
        "Your Game Review is Ready — Sunday Go Lessons",
        "",
        report.get("game_summary", ""),
        f"KataGo analyzed {total_moves} moves in {katago_secs:.1f} seconds.",
        "",
        "Move Quality:",
    ]
    for label in QUALITY_ORDER:
        lines.append(f"  {label.capitalize()}: {counts.get(label, 0)}")

    lines += [
        "",
        "Coming soon: Go skills, what you did well, what to work on, story of the game.",
        "",
        f"View your full interactive review: {review_url}",
    ]
    return "\n".join(lines)


def send_success_email(to: str, report: dict, review_id: str) -> None:
    url  = _review_url(review_id)
    html = _success_html(report, url)
    text = _success_text(report, url)

    player_label = "Black" if report["player_color"] == "B" else "White"
    subject = f"Your Sunday Go Lessons review is ready ({player_label}, {report['total_moves']} moves)"

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
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f9fafb;font-family:sans-serif">
<table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 0">
  <tr><td align="center">
    <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.1)">
      <tr><td style="background:#1e1b4b;padding:28px 32px">
        <p style="margin:0;font-size:22px;font-weight:700;color:#ffffff">Review Processing Failed</p>
        <p style="margin:6px 0 0 0;font-size:14px;color:#a5b4fc">Sunday Go Lessons</p>
      </td></tr>
      <tr><td style="padding:28px 32px">
        <p style="margin:0 0 12px 0;font-size:15px;color:#111827">
          Unfortunately we were not able to process your game review. Please try uploading your SGF again.
        </p>
        <p style="margin:0;font-size:13px;color:#6b7280">
          If the problem persists, please contact us and include the error detail below.
        </p>
        <pre style="margin:16px 0 0 0;padding:12px 16px;background:#f3f4f6;border-radius:4px;font-size:12px;color:#374151;white-space:pre-wrap;word-break:break-word">{error_msg[:500]}</pre>
      </td></tr>
    </table>
  </td></tr>
</table>
</body>
</html>"""

    text = (
        "Review Processing Failed — Sunday Go Lessons\n\n"
        "Unfortunately we could not process your game review. Please try uploading your SGF again.\n\n"
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

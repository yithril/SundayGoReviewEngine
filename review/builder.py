from __future__ import annotations

from review.analysis import (
    generate_story,
    identify_skills,
    find_strengths,
    find_improvements,
    find_highlights,
)

# Score-loss thresholds (points of territory vs the AI's best move) per rank band.
# Tuple order: (excellent, great, good, inaccuracy, mistake).
# Loss is always >= 0 from the reviewed player's perspective.
# Beginners get more leniency; dan players are held to a tighter standard.
LOSS_THRESHOLDS: dict[str, tuple[float, float, float, float, float]] = {
    "novice":       (3.0,  6.0,  12.0, 20.0, 30.0),
    "beginner":     (2.0,  4.0,   8.0, 15.0, 25.0),
    "intermediate": (1.0,  2.0,   4.0, 10.0, 18.0),
    "advanced":     (0.5,  1.2,   2.5,  7.0, 15.0),
    "dan":          (0.2,  0.6,   1.5,  5.0, 12.0),
}
# Fallback to beginner thresholds for any unknown rank band
_DEFAULT_THRESHOLDS = LOSS_THRESHOLDS["beginner"]

QUALITY_LABELS = ["excellent", "great", "good", "inaccuracy", "mistake", "blunder"]


def _classify(score_loss: float, rank_band: str) -> str:
    """Classify a move by how many points were lost vs the AI's best move."""
    t = LOSS_THRESHOLDS.get(rank_band, _DEFAULT_THRESHOLDS)
    excellent, great, good, inaccuracy, mistake = t
    if score_loss <= excellent:
        return "excellent"
    if score_loss <= great:
        return "great"
    if score_loss <= good:
        return "good"
    if score_loss <= inaccuracy:
        return "inaccuracy"
    if score_loss <= mistake:
        return "mistake"
    return "blunder"


def _score_loss(prev_resp: dict, curr_resp: dict, player_color: str) -> float:
    """
    Compute how many points the played move lost vs the AI's best suggestion.

    Both scoreLead values are from Black's perspective (reportAnalysisWinratesAs=BLACK).

    best_score   = prev_resp moveInfos[0].scoreLead  — score if KataGo played at turn N-1
    played_score = curr_resp rootInfo.scoreLead       — score after the player's actual move
    """
    move_infos = prev_resp.get("moveInfos", [])
    if not move_infos:
        return 0.0

    best_score   = move_infos[0].get("scoreLead", 0.0)
    played_score = curr_resp.get("rootInfo", {}).get("scoreLead", 0.0)

    if player_color == "B":
        loss = best_score - played_score
    else:
        # White benefits from lower (more negative) Black scores
        loss = played_score - best_score

    return max(0.0, loss)


def build_report(
    game: dict,
    katago_responses: dict[int, dict],
    player_color: str,
    rank_band: str,
    katago_seconds: float,
    total_seconds: float,
) -> dict:
    """
    Build the skeleton ReviewReport dict from KataGo responses.

    Parameters
    ----------
    game            : parsed SGF dict from sgf.parser.parse_sgf()
    katago_responses: turn_number -> KataGo response, from KataGoEngine.analyze()
    player_color    : "B" or "W" (the player being reviewed)
    rank_band       : e.g. "beginner"
    katago_seconds  : wall-clock seconds spent inside KataGo analysis
    total_seconds   : wall-clock seconds for the full handler run
    """
    moves      = game["moves"]
    board_size = game["board_size"]
    total_moves = len(moves)

    player_black = game.get("player_black", "Black")
    player_white = game.get("player_white", "White")
    game_date    = game.get("game_date", "")

    if player_color == "B":
        player_name   = player_black
        opponent_name = player_white
    else:
        player_name   = player_white
        opponent_name = player_black

    # --- Build win rate / score lead arrays (reviewed player's perspective, one entry per turn 0..N) ---
    win_rates: list[float] = []
    score_leads: list[float] = []

    num_turns = total_moves + 1  # turn 0 = before any move

    for turn in range(num_turns):
        resp = katago_responses.get(turn)
        if resp is None:
            win_rates.append(win_rates[-1] if win_rates else 0.5)
            score_leads.append(score_leads[-1] if score_leads else 0.0)
            continue

        root = resp.get("rootInfo", {})
        raw_wr    = root.get("winrate", 0.5)
        raw_score = root.get("scoreLead", 0.0)

        # reportAnalysisWinratesAs = BLACK in analysis.cfg means KataGo always
        # returns winrate and scoreLead from Black's perspective — no parity flip
        # needed. Convert once to the reviewed player's perspective so the frontend
        # can plot directly (up = good for you).
        player_wr    = raw_wr    if player_color == "B" else 1.0 - raw_wr
        player_score = raw_score if player_color == "B" else -raw_score

        win_rates.append(round(player_wr, 4))
        score_leads.append(round(player_score, 2))

    # --- Classify each move ---
    move_quality: list[str] = []
    counts: dict[str, int] = {label: 0 for label in QUALITY_LABELS}

    for move_num in range(1, total_moves + 1):
        color = moves[move_num - 1][0]  # "B" or "W"

        # Only classify the reviewed player's moves; opponent moves are "neutral"
        if color == player_color:
            prev_resp = katago_responses.get(move_num - 1)
            curr_resp = katago_responses.get(move_num)
            if prev_resp is not None and curr_resp is not None:
                loss  = _score_loss(prev_resp, curr_resp, player_color)
                label = _classify(loss, rank_band)
            else:
                label = "excellent"  # missing response — assume no loss
        else:
            label = "neutral"

        move_quality.append(label)
        if label != "neutral":  # only count the reviewed player's moves
            counts[label] += 1

    # --- Simple game summary ---
    player_label = "Black" if player_color == "B" else "White"
    blunders   = counts["blunder"]
    excellents = counts["excellent"]

    if excellents > total_moves // 2 and blunders == 0:
        summary = f"You played {total_moves} moves as {player_label} — a sharp, accurate game."
    elif blunders > 1:
        summary = f"You played {total_moves} moves as {player_label} with {blunders} significant mistakes."
    elif blunders == 1:
        summary = f"You played {total_moves} moves as {player_label} — solid overall, but one key mistake shifted the balance."
    else:
        summary = f"You played {total_moves} moves as {player_label}."

    player_final = win_rates[-1] if win_rates else 0.5
    if player_final > 0.55:
        summary += " The position was generally in your favor."
    elif player_final < 0.45:
        summary += " The engine suggests the position was challenging throughout."

    # --- Enrichment sections (stubs in review/analysis.py) ---
    story            = generate_story(game, move_quality, katago_responses, player_color)
    skills_used      = identify_skills(game, move_quality, katago_responses, player_color)
    did_well         = find_strengths(game, move_quality, katago_responses, player_color)
    needs_improvement= find_improvements(game, move_quality, katago_responses, player_color)
    match_highlights = find_highlights(game, move_quality, katago_responses, player_color)

    return {
        "player_color":         player_color,
        "player_name":          player_name,
        "opponent_name":        opponent_name,
        "game_date":            game_date,
        "rank_band":            rank_band,
        "board_size":           board_size,
        "total_moves":          total_moves,
        "win_rates":            win_rates,
        "score_leads":          score_leads,
        "move_quality":         move_quality,
        "move_quality_counts":  counts,
        "katago_seconds":       round(katago_seconds, 2),
        "total_seconds":        round(total_seconds, 2),
        "game_summary":         summary,
        "story":                story,
        "skills_used":          skills_used,
        "did_well":             did_well,
        "needs_improvement":    needs_improvement,
        "match_highlights":     match_highlights,
    }

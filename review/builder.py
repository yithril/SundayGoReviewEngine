from __future__ import annotations

from detection.pipeline import run_detection

QUALITY_LABELS = ["excellent", "great", "good", "inaccuracy", "mistake", "blunder"]


def _classify(point_loss: float) -> str:
    """Classify a move by fixed point-loss thresholds."""
    if point_loss > 6.0:
        return "blunder"
    if point_loss > 3.0:
        return "mistake"
    if point_loss > 1.5:
        return "inaccuracy"
    if point_loss > 0.8:
        return "good"
    if point_loss > 0.3:
        return "great"
    return "excellent"


def _to_player_perspective(score_black: float, player_color: str) -> float:
    """Convert Black-perspective scoreLead to reviewed-player perspective."""
    return score_black if player_color == "B" else -score_black


def _point_loss(prev_resp: dict, curr_resp: dict, player_color: str) -> float:
    """Compute max(0, bestScore - playedScore) in reviewed-player perspective.

    bestScore   = score if KataGo's top move from prev turn were played
    playedScore = score after the actual move at current turn
    """
    move_infos = prev_resp.get("moveInfos", [])
    if not move_infos:
        return 0.0

    best_black = float(move_infos[0].get("scoreLead", 0.0))
    played_black = float(curr_resp.get("rootInfo", {}).get("scoreLead", 0.0))

    best_score = _to_player_perspective(best_black, player_color)
    played_score = _to_player_perspective(played_black, player_color)
    return max(0.0, best_score - played_score)


def _label_for_player_move(prev_resp: dict | None, curr_resp: dict | None, player_color: str) -> str:
    """Return quality label for a reviewed-player move with explicit fallback."""
    if prev_resp is None or curr_resp is None:
        return "excellent"
    return _classify(_point_loss(prev_resp, curr_resp, player_color))


def _score_loss(prev_resp: dict, curr_resp: dict, player_color: str) -> float:
    """Backward-compatible alias for point loss used by tests/internal callers."""
    return _point_loss(prev_resp, curr_resp, player_color)


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
            label = _label_for_player_move(prev_resp, curr_resp, player_color)
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

    # --- Enrichment sections (detection pipeline) ---
    narrative = run_detection(
        game=game,
        katago_responses=katago_responses,
        player_color=player_color,
        rank_band=rank_band,
        move_quality=move_quality,
    )

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
        **narrative.to_report_fields(),
    }

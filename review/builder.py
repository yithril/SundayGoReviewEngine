from __future__ import annotations

# Score-loss thresholds (points of territory vs the AI's best move).
# Loss is always >= 0 from the reviewed player's perspective.
LOSS_EXCELLENT   = 0.2
LOSS_GREAT       = 0.6
LOSS_GOOD        = 1.2
LOSS_INACCURACY  = 4.0
LOSS_MISTAKE     = 10.0

QUALITY_LABELS = ["excellent", "great", "good", "inaccuracy", "mistake", "blunder"]


def _classify(score_loss: float) -> str:
    """Classify a move by how many points were lost vs the AI's best move."""
    if score_loss <= LOSS_EXCELLENT:
        return "excellent"
    if score_loss <= LOSS_GREAT:
        return "great"
    if score_loss <= LOSS_GOOD:
        return "good"
    if score_loss <= LOSS_INACCURACY:
        return "inaccuracy"
    if score_loss <= LOSS_MISTAKE:
        return "mistake"
    return "blunder"


def _score_loss(resp: dict, player_color: str) -> float:
    """
    Compute how many points the played move lost vs the AI's best suggestion.

    KataGo's scoreLead is always from Black's perspective (positive = Black ahead).
    We convert to the reviewed player's perspective so that loss is always >= 0
    when the played move was worse than the best move.

    best_score   = moveInfos[0].scoreLead  (what AI would have played)
    played_score = rootInfo.scoreLead      (position after the move was played)
    """
    move_infos = resp.get("moveInfos", [])
    if not move_infos:
        return 0.0

    best_score_black   = move_infos[0].get("scoreLead", 0.0)
    played_score_black = resp.get("rootInfo", {}).get("scoreLead", 0.0)

    if player_color == "B":
        loss = best_score_black - played_score_black
    else:
        # White benefits from lower (more negative) Black scores
        loss = played_score_black - best_score_black

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

    if player_color == "B":
        player_name   = player_black
        opponent_name = player_white
    else:
        player_name   = player_white
        opponent_name = player_black

    # --- Build win rate / score lead arrays (Black's perspective, one entry per turn 0..N) ---
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

        # KataGo always reports from the perspective of the player to move.
        # Even turns (0, 2, 4, ...) = Black to move → raw_wr is already Black's.
        # Odd turns (1, 3, 5, ...)  = White to move → flip.
        if turn % 2 == 0:
            black_wr    = raw_wr
            black_score = raw_score
        else:
            black_wr    = 1.0 - raw_wr
            black_score = -raw_score

        win_rates.append(round(black_wr, 4))
        score_leads.append(round(black_score, 2))

    # --- Classify each move ---
    move_quality: list[str] = []
    counts: dict[str, int] = {label: 0 for label in QUALITY_LABELS}

    for move_num in range(1, total_moves + 1):
        color = moves[move_num - 1][0]  # "B" or "W"

        # Only classify the reviewed player's moves; opponent moves are "neutral"
        if color == player_color:
            resp = katago_responses.get(move_num)
            if resp is not None:
                loss  = _score_loss(resp, player_color)
                label = _classify(loss)
            else:
                label = "excellent"  # missing response — assume no loss
        else:
            label = "neutral"

        move_quality.append(label)
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

    final_wr = win_rates[-1] if win_rates else 0.5
    player_final = final_wr if player_color == "B" else 1.0 - final_wr
    if player_final > 0.55:
        summary += " The position was generally in your favor."
    elif player_final < 0.45:
        summary += " The engine suggests the position was challenging throughout."

    return {
        "player_color":         player_color,
        "player_name":          player_name,
        "opponent_name":        opponent_name,
        "rank_band":            rank_band,
        "board_size":           board_size,
        "total_moves":          total_moves,
        "win_rates":            win_rates,
        "score_leads":          score_leads,
        "move_quality":         move_quality,
        "move_quality_counts":  counts,
        "katago_seconds":       round(katago_seconds, 2),
        "total_seconds":        round(total_seconds, 2),
        # Skeleton sections — populated in a future iteration
        "game_summary":         summary,
        "skills_used":          [],
        "did_well":             [],
        "needs_improvement":    [],
        "story":                "",
    }

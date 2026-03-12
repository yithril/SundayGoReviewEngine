from __future__ import annotations

import sgfmill.sgf

# KataGo uses A-T skipping I
COLS = "ABCDEFGHJKLMNOPQRST"

_KATAGO_KOMI_DEFAULT = 6.5


def _sanitize_komi(komi: float) -> float:
    """Snap komi to the nearest half-integer KataGo accepts (-150..150).

    KataGo requires komi to be an integer or half-integer in [-150, 150].
    If the value is out of that range (or not a half-integer due to a bad
    SGF), default to 6.5 rather than crashing.
    """
    snapped = round(float(komi) * 2) / 2
    if -150.0 <= snapped <= 150.0:
        return snapped
    return _KATAGO_KOMI_DEFAULT


def sgf_coord_to_katago(row: int, col: int, board_size: int) -> str:
    """Convert sgfmill (row, col) zero-indexed from top-left to KataGo coord like 'D4'."""
    return f"{COLS[col]}{board_size - row}"


def parse_sgf(sgf_string: str | bytes) -> dict:
    """
    Parse an SGF string and return the data KataGo needs:
      board_size, komi, and a list of moves as [["B", "D4"], ["W", "Q16"], ...]
    """
    if isinstance(sgf_string, bytes):
        sgf_string = sgf_string.decode("utf-8", errors="replace")
    game = sgfmill.sgf.Sgf_game.from_string(sgf_string)
    board_size = game.get_size()
    raw_komi = game.get_komi()
    komi = _sanitize_komi(raw_komi) if raw_komi is not None else _KATAGO_KOMI_DEFAULT

    moves = []
    for node in game.get_main_sequence()[1:]:  # skip root node
        color, move = node.get_move()
        if color is None:
            continue
        if move is None:
            moves.append([color.upper(), "pass"])
        else:
            row, col = move
            moves.append([color.upper(), sgf_coord_to_katago(row, col, board_size)])

    root = game.get_root()
    player_black = root.get("PB") or "Black"
    player_white = root.get("PW") or "White"
    game_date    = root.get("DT") or ""

    return {
        "board_size":   board_size,
        "komi":         komi,
        "moves":        moves,
        "player_black": player_black,
        "player_white": player_white,
        "game_date":    game_date,
    }

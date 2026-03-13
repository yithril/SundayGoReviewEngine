from __future__ import annotations

import sgfmill.sgf

# KataGo / GTP uses A-T skipping I for columns
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


# ---------------------------------------------------------------------------
# Coordinate conversion helpers — single source of truth
# ---------------------------------------------------------------------------
# Three coordinate systems in play:
#   SGF text  e.g. "pd"     top-left origin; x=col, y=row from top (a=0)
#   sgfmill   e.g. (15, 15) bottom-left origin; (row_from_bottom, col), 0-based
#   GTP/Go    e.g. "Q16"    cols A-T (no I), rows 1-19 from bottom
#
# sgfmill's get_move() returns (row_from_bottom, col) — it has already
# converted SGF's top-origin y into a bottom-origin row internally.
# ---------------------------------------------------------------------------


def sgfmill_point_to_gtp(row: int, col: int) -> str:
    """Convert an sgfmill (row_from_bottom, col) point to GTP notation.

    Examples:
        sgfmill_point_to_gtp(15, 15) -> "Q16"
        sgfmill_point_to_gtp(3,  3)  -> "D4"
    """
    return f"{COLS[col]}{row + 1}"


def sgf_coord_to_katago(row: int, col: int, board_size: int) -> str:
    """Convert an sgfmill (row_from_bottom, col) point to KataGo/GTP notation.

    Delegates to sgfmill_point_to_gtp; the board_size parameter is kept for
    API compatibility but is not used.
    """
    return sgfmill_point_to_gtp(row, col)


def gtp_to_col_row(move: str) -> tuple[int, int] | None:
    """Parse a GTP move string to (col, row_from_bottom), both 0-based.

    Returns None for pass moves or unrecognisable strings.

    Examples:
        gtp_to_col_row("Q16") -> (15, 15)
        gtp_to_col_row("D4")  -> (3,  3)
        gtp_to_col_row("pass")-> None
    """
    if not move or move.upper() == "PASS" or len(move) < 2:
        return None
    col_char = move[0].upper()
    if col_char not in COLS:
        return None
    try:
        col = COLS.index(col_char)
        row = int(move[1:]) - 1
    except (ValueError, IndexError):
        return None
    return col, row


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
    # sgfmill's get() raises KeyError for absent optional properties.
    try:
        player_black = root.get("PB") or "Black"
    except KeyError:
        player_black = "Black"
    try:
        player_white = root.get("PW") or "White"
    except KeyError:
        player_white = "White"
    try:
        game_date = root.get("DT") or ""
    except KeyError:
        game_date = ""

    return {
        "board_size":   board_size,
        "komi":         komi,
        "moves":        moves,
        "player_black": player_black,
        "player_white": player_white,
        "game_date":    game_date,
    }

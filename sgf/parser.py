import sgfmill.sgf

# KataGo uses A-T skipping I
COLS = "ABCDEFGHJKLMNOPQRST"


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
    komi = game.get_komi()
    if komi is None:
        komi = 6.5

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

    return {
        "board_size": board_size,
        "komi": float(komi),
        "moves": moves,
        "player_black": player_black,
        "player_white": player_white,
    }

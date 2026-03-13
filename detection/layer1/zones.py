from __future__ import annotations

from detection.types import MoveSector9

_COLUMNS = "ABCDEFGHJKLMNOPQRST"

_OPPOSITE_OR_ADJACENT: dict[MoveSector9, frozenset[MoveSector9]] = {
    "upper_left": frozenset({"lower_right", "right", "bottom"}),
    "top": frozenset({"bottom", "lower_left", "lower_right"}),
    "upper_right": frozenset({"lower_left", "left", "bottom"}),
    "left": frozenset({"right", "upper_right", "lower_right"}),
    "center": frozenset(),
    "right": frozenset({"left", "upper_left", "lower_left"}),
    "lower_left": frozenset({"upper_right", "right", "top"}),
    "bottom": frozenset({"top", "upper_left", "upper_right"}),
    "lower_right": frozenset({"upper_left", "left", "top"}),
}

_PREFERRED_OR_ADJACENT: dict[MoveSector9, frozenset[MoveSector9]] = {
    "upper_left": frozenset({"upper_left", "top", "left", "center"}),
    "top": frozenset({"top", "upper_left", "upper_right", "center"}),
    "upper_right": frozenset({"upper_right", "top", "right", "center"}),
    "left": frozenset({"left", "upper_left", "lower_left", "center"}),
    "center": frozenset({"center", "top", "right", "bottom", "left"}),
    "right": frozenset({"right", "upper_right", "lower_right", "center"}),
    "lower_left": frozenset({"lower_left", "left", "bottom", "center"}),
    "bottom": frozenset({"bottom", "lower_left", "lower_right", "center"}),
    "lower_right": frozenset({"lower_right", "right", "bottom", "center"}),
}


def parse_gtp_coord(move: str, board_size: int) -> tuple[int, int] | None:
    """Convert GTP coordinate to zero-based (col, row_from_bottom)."""
    if not move or move.upper() == "PASS" or len(move) < 2:
        return None
    col_char = move[0].upper()
    if col_char not in _COLUMNS:
        return None
    try:
        col = _COLUMNS.index(col_char)
        row = int(move[1:]) - 1
    except (ValueError, IndexError):
        return None
    if not (0 <= col < board_size and 0 <= row < board_size):
        return None
    return col, row


def classify_sector_9(
    coord: tuple[int, int] | None,
    board_size: int,
) -> MoveSector9:
    """Classify a point into one of 9 board sectors."""
    if coord is None or board_size <= 0:
        return "center"
    col, row = coord
    band = board_size // 3
    if band <= 0:
        return "center"

    if col < band:
        h = "left"
    elif col >= board_size - band:
        h = "right"
    else:
        h = "center"

    if row < band:
        v = "lower"
    elif row >= board_size - band:
        v = "upper"
    else:
        v = "middle"

    if v == "upper" and h == "left":
        return "upper_left"
    if v == "upper" and h == "center":
        return "top"
    if v == "upper" and h == "right":
        return "upper_right"
    if v == "middle" and h == "left":
        return "left"
    if v == "middle" and h == "center":
        return "center"
    if v == "middle" and h == "right":
        return "right"
    if v == "lower" and h == "left":
        return "lower_left"
    if v == "lower" and h == "center":
        return "bottom"
    return "lower_right"


def preferred_sector_topk_weighted(
    move_infos: list[dict],
    board_size: int,
    top_k: int = 3,
) -> tuple[MoveSector9, float]:
    """Return weighted preferred sector and total prior mass used."""
    if top_k <= 0 or not move_infos:
        return "center", 0.0

    masses: dict[MoveSector9, float] = {}
    total_mass = 0.0
    for info in move_infos[:top_k]:
        move = str(info.get("move", "pass"))
        coord = parse_gtp_coord(move, board_size)
        if coord is None:
            continue
        prior = float(info.get("prior", 0.0))
        if prior < 0.0:
            prior = 0.0
        sector = classify_sector_9(coord, board_size)
        masses[sector] = masses.get(sector, 0.0) + prior
        total_mass += prior

    if not masses:
        return "center", total_mass
    preferred = max(masses.items(), key=lambda item: item[1])[0]
    return preferred, total_mass


def is_opposite_or_adjacent_opposite(
    played_sector: MoveSector9,
    preferred_sector: MoveSector9,
) -> bool:
    """Return True when played sector is opposite/near-opposite preferred."""
    return played_sector in _OPPOSITE_OR_ADJACENT.get(preferred_sector, frozenset())


def is_preferred_or_adjacent_preferred(
    played_sector: MoveSector9,
    preferred_sector: MoveSector9,
) -> bool:
    """Return True when played sector aligns with preferred area."""
    return played_sector in _PREFERRED_OR_ADJACENT.get(preferred_sector, frozenset())


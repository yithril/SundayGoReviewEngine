from __future__ import annotations

"""
detection/layer1/facts.py
-------------------------
Step 1 of the Layer 1 pipeline: collect all cheap per-move facts and
package them into a MoveFacts dataclass.

Data sources:
  - KataGo responses    : score/winrate deltas, policy rank/prob, PV length
  - Ownership map       : entered_influence, moyo_cell_count
                          (shared 2D prefix-sum table, built once per move)
  - Coordinate arithmetic: distance_to_prev
  - Carry-forward        : urgent_local_existed (from recent TriggerSignals)
  - Board state          : BoardSnapshot from board_tracker.py
"""

import math
from typing import Optional

from game.constants.phases import get_phase
from game.constants.thresholds import (
    MOYO_OWNERSHIP_THRESHOLD,
)
from detection.types import CaptureGroupInfo, Color, MoveFacts, TriggerSignal
from detection.layer1.board_tracker import BoardSnapshot
from detection.layer1.zones import (
    classify_sector_9,
    parse_gtp_coord,
    preferred_sector_topk_weighted,
)


# ---------------------------------------------------------------------------
# Board coordinate helpers
# ---------------------------------------------------------------------------


def _chebyshev(a: Optional[tuple[int, int]], b: Optional[tuple[int, int]]) -> float:
    """Chebyshev (chessboard) distance between two board coordinates.

    Returns 0.0 if either coordinate is None (pass move or first move).
    """
    if a is None or b is None:
        return 0.0
    return float(max(abs(a[0] - b[0]), abs(a[1] - b[1])))


# ---------------------------------------------------------------------------
# 2D prefix-sum helpers (shared by entered_influence and moyo detection)
# ---------------------------------------------------------------------------

def _build_prefix_sum(
    ownership: list[float],
    board_size: int,
    player_color: Color,
    threshold: float,
) -> list[list[int]]:
    """Build a 2D prefix-sum table of cells where ownership passes threshold.

    ownership: flat list of board_size² values, row-major (index 0 = top-left,
               y=0 is the top row in KataGo convention).
    Positive values favour Black; negative favour White.

    The prefix table P satisfies:
      P[r+1][c+1] = number of qualifying cells in the rectangle
                    rows [0..r], cols [0..c].
    A rectangular region sum (r1,c1)→(r2,c2) inclusive is then:
      P[r2+1][c2+1] - P[r1][c2+1] - P[r2+1][c1] + P[r1][c1]
    """
    n = board_size
    # P has (n+1) x (n+1) entries, all zero-initialised
    P: list[list[int]] = [[0] * (n + 1) for _ in range(n + 1)]

    for r in range(n):
        for c in range(n):
            val = ownership[r * n + c]
            qualifies = (
                (player_color == "B" and val > threshold) or
                (player_color == "W" and val < -threshold)
            )
            cell = 1 if qualifies else 0
            P[r + 1][c + 1] = cell + P[r][c + 1] + P[r + 1][c] - P[r][c]
    return P


def _rect_sum(P: list[list[int]], r1: int, c1: int, r2: int, c2: int) -> int:
    """Return the prefix-sum count for the inclusive rectangle (r1,c1)→(r2,c2).

    All coordinates are zero-based; r/c must be within [0, board_size-1].
    """
    return P[r2 + 1][c2 + 1] - P[r1][c2 + 1] - P[r2 + 1][c1] + P[r1][c1]


# ---------------------------------------------------------------------------
# Ownership-derived facts
# ---------------------------------------------------------------------------

def _compute_entered_influence(
    coord: Optional[tuple[int, int]],
    P: list[list[int]],
    opponent_color: Color,
    ownership: list[float],
    board_size: int,
) -> bool:
    """Return True if the played move landed inside opponent's ownership territory.

    A 3×3 neighbourhood centred on the played stone is sampled; if the
    majority of cells favour the opponent, the move entered their influence.
    """
    if coord is None or not ownership:
        return False
    col, row = coord
    n = board_size
    threshold = MOYO_OWNERSHIP_THRESHOLD

    r1 = max(0, row - 1)
    r2 = min(n - 1, row + 1)
    c1 = max(0, col - 1)
    c2 = min(n - 1, col + 1)
    neighbourhood_size = (r2 - r1 + 1) * (c2 - c1 + 1)

    # Count cells in the neighbourhood that belong to the opponent
    opp_threshold = threshold if opponent_color == "B" else -threshold
    opp_cells = _rect_sum(P, r1, c1, r2, c2) if opponent_color == "B" else (
        # For White opponent, rebuild with opponent's sign — use raw loop
        sum(
            1 for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)
            if ownership[r * n + c] < -threshold
        )
    )
    return opp_cells > neighbourhood_size // 2


def _compute_moyo_cell_count(
    P: list[list[int]],
    board_size: int,
) -> int:
    """Return the total qualifying moyo cells for the player.

    A qualifying moyo zone must satisfy structural criteria (checked via O(1)
    prefix-sum rectangle queries):
      - Depth: spans from board lines 2–3 into lines 5–7 (0-based rows/cols)
      - Width: at least 3 columns wide at the deepest extent

    We check zones from all four edges and return the maximum qualifying count
    found.  The prefix-sum table is already built by the caller.
    """
    n = board_size
    if n < 9:
        return 0

    # Define "deep" zone: rows/cols 4–6 (0-based), i.e. lines 5–7 in 1-based
    deep_start = 4
    deep_end   = min(6, n - 1)

    best = 0

    # Check zones anchored from each of the four edges.
    # For each edge, the "shallow" side is lines 1–2 (0-based 0–1) and the
    # "deep" side reaches into lines 4–6.
    zones = [
        # (row_start, row_end, col_start, col_end) — 0-based inclusive
        # Bottom edge (rows 0 → deep_end, at least 3 cols wide)
        (0, deep_end, 0, n - 1),
        # Top edge
        (n - 1 - deep_end, n - 1, 0, n - 1),
        # Left edge (cols 0 → deep_end, at least 3 rows tall)
        (0, n - 1, 0, deep_end),
        # Right edge
        (0, n - 1, n - 1 - deep_end, n - 1),
    ]

    for r1, r2, c1, c2 in zones:
        # Require at least 3 columns (or rows) of width in the deep portion
        width = (c2 - c1 + 1) if (r2 - r1 + 1) > (c2 - c1 + 1) else (r2 - r1 + 1)
        if width < 3:
            continue
        count = _rect_sum(P, r1, c1, r2, c2)
        best = max(best, count)

    return best


def _compute_own_here(
    coord: Optional[tuple[int, int]],
    ownership: list[float],
    board_size: int,
    move_color: Color,
) -> float:
    """Return ownership at played point from moving player's perspective [0,1]."""
    if coord is None or not ownership or len(ownership) != board_size * board_size:
        return 0.5
    col, row = coord
    val = float(ownership[row * board_size + col])
    own = (val + 1.0) / 2.0 if move_color == "B" else (1.0 - val) / 2.0
    return max(0.0, min(1.0, own))


def _compute_group_ownership_mean(
    ownership: list[float],
    board_size: int,
    alive_group_stones: dict[int, tuple[tuple[int, int], ...]],
) -> dict[int, float]:
    """Compute per-group ownership mean (black perspective) for future trend use."""
    if not ownership or len(ownership) != board_size * board_size:
        return {}
    result: dict[int, float] = {}
    for group_id, stones in alive_group_stones.items():
        if not stones:
            continue
        total = 0.0
        for row, col in stones:
            total += float(ownership[row * board_size + col])
        result[group_id] = total / len(stones)
    return result


# ---------------------------------------------------------------------------
# Policy rank / probability helpers
# ---------------------------------------------------------------------------

def _find_policy_rank_and_prob(
    played_move: str,
    move_infos: list[dict],
) -> tuple[int, float]:
    """Return (rank, prior) of the played move within KataGo's moveInfos.

    rank 0 = KataGo's first choice.  If the move is not found in the list,
    rank is len(move_infos) (worse than all listed moves) and prob is 0.0.
    """
    played_upper = played_move.upper()
    for i, info in enumerate(move_infos):
        if info.get("move", "").upper() == played_upper:
            return i, float(info.get("prior", 0.0))
    return len(move_infos), 0.0


# ---------------------------------------------------------------------------
# Carry-forward: urgent local issue
# ---------------------------------------------------------------------------

_URGENT_TRIGGER_TYPES = frozenset({
    "atari_created",
    "self_atari_candidate",
    "weak_group_candidate",
    "life_and_death_candidate",
    "local_fight",
    "cut_created",
})

_URGENT_LOOKBACK = 4  # how many previous moves to scan


def _check_urgent_local(
    move_index: int,
    prev_signals: list[TriggerSignal],
) -> bool:
    """Return True if an urgent local trigger fired in the last _URGENT_LOOKBACK moves."""
    cutoff = move_index - _URGENT_LOOKBACK
    return any(
        s.move_index >= cutoff and s.trigger_type in _URGENT_TRIGGER_TYPES
        for s in prev_signals
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def collect_facts(
    move_index: int,
    moves: list[list[str]],
    katago_responses: dict[int, dict],
    player_color: Color,
    board_size: int,
    prev_signals: list[TriggerSignal],
    prev_moyo_cell_count: int = 0,
    snapshot: Optional[BoardSnapshot] = None,
) -> MoveFacts:
    """Collect all cheap per-move facts for the given move_index.

    Parameters
    ----------
    move_index       : 1-based index of the move being analysed
    moves            : full move list from parse_sgf(), e.g. [["B","D4"], ...]
    katago_responses : turn_number → KataGo response dict
    player_color     : "B" or "W" (the reviewed player)
    board_size       : 9, 13, or 19
    prev_signals     : all TriggerSignals emitted so far (for carry-forward)
    snapshot         : BoardSnapshot from BoardTracker.step() for this move;
                       if None (e.g. in unit tests), board-state fields default to 0/False
    """
    move_entry = moves[move_index - 1] if move_index <= len(moves) else ["?", "pass"]
    move_color: Color = move_entry[0]  # type: ignore[assignment]
    move_str: str = move_entry[1] if len(move_entry) > 1 else "pass"

    prev_resp = katago_responses.get(move_index - 1, {})
    curr_resp = katago_responses.get(move_index, {})

    prev_root = prev_resp.get("rootInfo", {})
    curr_root = curr_resp.get("rootInfo", {})

    raw_prev_score = float(prev_root.get("scoreLead", 0.0))
    raw_curr_score = float(curr_root.get("scoreLead", 0.0))
    raw_prev_wr    = float(prev_root.get("winrate", 0.5))
    raw_curr_wr    = float(curr_root.get("winrate", 0.5))

    if player_color == "B":
        score_delta   = raw_curr_score - raw_prev_score
        winrate_delta = raw_curr_wr    - raw_prev_wr
    else:
        score_delta   = -(raw_curr_score - raw_prev_score)
        winrate_delta = -(raw_curr_wr    - raw_prev_wr)

    # Policy rank / probability
    move_infos = prev_resp.get("moveInfos", [])
    policy_rank, policy_prob = _find_policy_rank_and_prob(move_str, move_infos)
    preferred_move_sector_9, preferred_top3_prior_sum = preferred_sector_topk_weighted(
        move_infos, board_size, top_k=3
    )

    # Best PV length (top move's predicted continuation depth)
    best_pv_length = 0
    if move_infos:
        best_pv_length = len(move_infos[0].get("pv", []))

    # Ownership-derived facts (shared prefix-sum table)
    ownership: list[float] = curr_resp.get("ownership", [])
    opponent_color: Color = "W" if player_color == "B" else "B"  # type: ignore[assignment]

    coord = parse_gtp_coord(move_str, board_size)
    move_sector_9 = classify_sector_9(coord, board_size)

    if ownership and len(ownership) == board_size * board_size:
        prefix = _build_prefix_sum(ownership, board_size, player_color, MOYO_OWNERSHIP_THRESHOLD)
        entered_influence = _compute_entered_influence(
            coord, prefix, opponent_color, ownership, board_size
        )
        moyo_cell_count = _compute_moyo_cell_count(prefix, board_size)
        own_here = _compute_own_here(coord, ownership, board_size, move_color)
    else:
        entered_influence = False
        moyo_cell_count   = 0
        own_here = 0.5
    dmoyo = moyo_cell_count - prev_moyo_cell_count

    # Distance to previous move
    prev_move_str = moves[move_index - 2][1] if move_index >= 2 else "pass"
    prev_coord    = parse_gtp_coord(prev_move_str, board_size)
    curr_coord    = coord
    distance_to_prev = _chebyshev(curr_coord, prev_coord)

    # Carry-forward
    urgent_local_existed = _check_urgent_local(move_index, prev_signals)

    # Board state — populated from BoardSnapshot when provided
    ss = snapshot
    captured_groups: tuple[CaptureGroupInfo, ...] = ()
    max_captured_group_size = 0
    alive_group_ownership_mean: dict[int, float] = {}
    if ss:
        captured_groups = tuple(
            CaptureGroupInfo(
                group_id=group_id,
                size=ss.captured_group_sizes.get(group_id, 0),
                zone=ss.captured_group_zones.get(group_id, "center"),
            )
            for group_id in sorted(ss.captured_group_sizes.keys())
        )
        max_captured_group_size = max((g.size for g in captured_groups), default=0)
        alive_group_ownership_mean = _compute_group_ownership_mean(
            ownership=ownership,
            board_size=board_size,
            alive_group_stones=ss.alive_group_stones,
        )

    return MoveFacts(
        move_index=move_index,
        move=move_str,
        player_color=move_color,
        game_phase=get_phase(move_index),
        # KataGo-derived
        score_delta=score_delta,
        winrate_delta=winrate_delta,
        policy_rank=policy_rank,
        policy_prob=policy_prob,
        best_pv_length=best_pv_length,
        preferred_top3_prior_sum=preferred_top3_prior_sum,
        # Ownership map
        entered_influence=entered_influence,
        moyo_cell_count=moyo_cell_count,
        own_here=own_here,
        dmoyo=dmoyo,
        # Coordinate arithmetic
        distance_to_prev=distance_to_prev,
        move_sector_9=move_sector_9,
        preferred_move_sector_9=preferred_move_sector_9,
        # Board state from BoardTracker (zeros/False if no snapshot provided)
        stones_captured=ss.stones_captured if ss else 0,
        self_liberties=ss.self_liberties if ss else 0,
        enemy_liberties_nearby=ss.enemy_liberties_nearby if ss else 0,
        adjacent_friendly=ss.adjacent_friendly if ss else 0,
        adjacent_enemy=ss.adjacent_enemy if ss else 0,
        connected_groups=ss.connected_groups if ss else False,
        cut_groups=ss.cut_groups if ss else False,
        nearby_friendly=ss.nearby_friendly if ss else 0,
        played_group_id=ss.played_group_id if ss else 0,
        friendly_group_ids_adjacent_pre=ss.friendly_group_ids_adjacent_pre if ss else (),
        enemy_group_ids_adjacent_pre=ss.enemy_group_ids_adjacent_pre if ss else (),
        groups_created=ss.groups_created if ss else (),
        groups_captured=ss.groups_captured if ss else (),
        groups_merged_into=ss.groups_merged_into if ss else {},
        played_group_liberties_post=ss.played_group_liberties_post if ss else 0,
        adjacent_enemy_liberties_post=ss.adjacent_enemy_liberties_post if ss else {},
        alive_group_liberties=ss.alive_group_liberties if ss else {},
        alive_group_zone_9=ss.alive_group_zone_9 if ss else {},
        captured_groups=captured_groups,
        max_captured_group_size=max_captured_group_size,
        alive_group_ownership_mean=alive_group_ownership_mean,
        # Carry-forward
        urgent_local_existed=urgent_local_existed,
    )

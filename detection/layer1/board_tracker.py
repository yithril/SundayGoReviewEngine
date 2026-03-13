from __future__ import annotations

"""
detection/layer1/board_tracker.py
-----------------------------------
Wraps sgfmill.boards.Board and is the ONLY place board.play() is ever called
in the Layer 1 pipeline.

Architecture guarantee
----------------------
run_layer1() creates one BoardTracker per game and calls tracker.step() exactly
once per move in sequence.  collect_facts() receives the resulting BoardSnapshot
— a plain dataclass of pre-computed integers and booleans — and never touches
the Board directly.  This ensures the board state is O(N) total across the game
(one play() call per move), never O(N²) from replaying.

BoardSnapshot fields
--------------------
Every field maps 1-to-1 to a currently-stubbed field in MoveFacts.  When
board_tracker is wired into collect_facts(), all # TODO: board state stubs
are replaced by snapshot reads.
"""

from dataclasses import dataclass
from typing import Optional

from sgfmill import boards
from detection.layer1.zones import classify_sector_9
from detection.types import MoveSector9

# KataGo / SGF column letters (no I)
_COLS = "ABCDEFGHJKLMNOPQRST"


def _katago_to_rowcol(move_str: str, board_size: int) -> Optional[tuple[int, int]]:
    """Convert a KataGo move string like 'D4' to sgfmill (row, col).

    sgfmill uses (row, col) where row=0 is the TOP of the board and
    col=0 is the LEFT.  KataGo's row numbers start from 1 at the BOTTOM.

    Returns None for pass moves or unparseable strings.
    """
    if not move_str or move_str.upper() == "PASS" or len(move_str) < 2:
        return None
    col_char = move_str[0].upper()
    if col_char not in _COLS:
        return None
    try:
        col = _COLS.index(col_char)
        katago_row = int(move_str[1:])          # 1-based from bottom
        row = board_size - katago_row           # convert to 0-based from top
    except (ValueError, IndexError):
        return None
    if not (0 <= row < board_size and 0 <= col < board_size):
        return None
    return row, col


def _count_liberties(board: boards.Board, group: frozenset) -> int:
    """Count unique empty intersections adjacent to any stone in *group*."""
    liberties: set[tuple[int, int]] = set()
    size = board.side
    for row, col in group:
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = row + dr, col + dc
            if 0 <= nr < size and 0 <= nc < size:
                if board.get(nr, nc) is None:
                    liberties.add((nr, nc))
    return len(liberties)


def _get_group(board: boards.Board, row: int, col: int) -> frozenset[tuple[int, int]]:
    """Return the full connected group at (row, col) using 4-neighbor BFS."""
    color = board.get(row, col)
    if color is None:
        return frozenset()

    size = board.side
    seen: set[tuple[int, int]] = set()
    stack: list[tuple[int, int]] = [(row, col)]

    while stack:
        cr, cc = stack.pop()
        if (cr, cc) in seen:
            continue
        if board.get(cr, cc) != color:
            continue
        seen.add((cr, cc))
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = cr + dr, cc + dc
            if 0 <= nr < size and 0 <= nc < size and (nr, nc) not in seen:
                if board.get(nr, nc) == color:
                    stack.append((nr, nc))
    return frozenset(seen)


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass
class BoardSnapshot:
    """Pre-computed board-state facts for one move.

    Produced by BoardTracker.step() and consumed by collect_facts().
    All fields are plain Python scalars — no sgfmill objects leak out.
    """
    stones_captured: int          # exact count of stones removed by this move
    self_liberties: int           # liberty count of the moved group after play
    enemy_liberties_nearby: int   # min liberties of any adjacent enemy group (1 = atari created)
    adjacent_friendly: int        # number of adjacent same-color stones before play
    adjacent_enemy: int           # number of adjacent opponent-color stones before play
    connected_groups: bool        # move joined two or more previously separate friendly groups
    cut_groups: bool              # move is adjacent to two or more separate enemy groups
    nearby_friendly: int          # same-color stones within Chebyshev-2 radius, pre-play
    played_group_id: int          # persistent group ID of the played stone's resulting group
    friendly_group_ids_adjacent_pre: tuple[int, ...]   # persistent IDs adjacent before play
    enemy_group_ids_adjacent_pre: tuple[int, ...]      # persistent IDs adjacent before play
    groups_created: tuple[int, ...]                    # group IDs created on this move
    groups_captured: tuple[int, ...]                   # group IDs captured on this move
    groups_merged_into: dict[int, tuple[int, ...]]     # target group -> merged source group IDs
    played_group_liberties_post: int                   # post-play liberties for played group
    adjacent_enemy_liberties_post: dict[int, int]      # post-play adjacent enemy group ID -> liberties
    alive_group_liberties: dict[int, int]              # all currently alive groups -> liberties
    alive_group_zone_9: dict[int, MoveSector9]         # all currently alive groups -> 9-sector zone
    captured_group_sizes: dict[int, int]               # captured group ID -> stone count
    captured_group_zones: dict[int, MoveSector9]       # captured group ID -> representative zone
    alive_group_stones: dict[int, tuple[tuple[int, int], ...]]  # live group ID -> stones (row,col)


@dataclass
class GroupRecord:
    """Persistent group lifecycle record."""

    group_id: int
    color: str
    stones: frozenset[tuple[int, int]]
    liberties: set[tuple[int, int]]
    liberty_count: int
    created_move: int
    last_seen_move: int
    alive: bool
    captured_move: int | None = None


@dataclass
class GroupDebugState:
    """Debug-only snapshot of current live groups and board mapping."""

    move_index: int
    board_size: int
    group_map: list[list[int]]
    groups: dict[int, dict[str, object]]


# Sentinel used when the move is a pass or off-board
PASS_SNAPSHOT = BoardSnapshot(
    stones_captured=0,
    self_liberties=0,
    enemy_liberties_nearby=0,
    adjacent_friendly=0,
    adjacent_enemy=0,
    connected_groups=False,
    cut_groups=False,
    nearby_friendly=0,
    played_group_id=0,
    friendly_group_ids_adjacent_pre=(),
    enemy_group_ids_adjacent_pre=(),
    groups_created=(),
    groups_captured=(),
    groups_merged_into={},
    played_group_liberties_post=0,
    adjacent_enemy_liberties_post={},
    alive_group_liberties={},
    alive_group_zone_9={},
    captured_group_sizes={},
    captured_group_zones={},
    alive_group_stones={},
)


# ---------------------------------------------------------------------------
# BoardTracker
# ---------------------------------------------------------------------------

class BoardTracker:
    """Maintains a running sgfmill Board updated exactly once per move.

    Usage in run_layer1():
        tracker = BoardTracker(board_size)
        for move_index, (color, move_str) in enumerate(moves, 1):
            snapshot = tracker.step(move_str, color)
            facts = collect_facts(..., snapshot=snapshot)
    """

    def __init__(self, board_size: int) -> None:
        self._board = boards.Board(board_size)
        self._size = board_size
        self._groups: dict[int, GroupRecord] = {}
        self._alive_groups_by_stones: dict[frozenset[tuple[int, int]], int] = {}
        self._next_group_id = 1
        self._move_counter = 0

    def _resolve_move_index(self, move_index: int | None) -> int:
        if move_index is None:
            self._move_counter += 1
            return self._move_counter
        self._move_counter = move_index
        return move_index

    def _new_group_id(self) -> int:
        group_id = self._next_group_id
        self._next_group_id += 1
        return group_id

    def _group_liberties(self, group: frozenset[tuple[int, int]]) -> set[tuple[int, int]]:
        liberties: set[tuple[int, int]] = set()
        size = self._board.side
        for row, col in group:
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = row + dr, col + dc
                if 0 <= nr < size and 0 <= nc < size and self._board.get(nr, nc) is None:
                    liberties.add((nr, nc))
        return liberties

    def _create_group_record(
        self,
        color: str,
        stones: frozenset[tuple[int, int]],
        move_index: int,
    ) -> int:
        group_id = self._new_group_id()
        liberties = self._group_liberties(stones)
        self._groups[group_id] = GroupRecord(
            group_id=group_id,
            color=color,
            stones=stones,
            liberties=liberties,
            liberty_count=len(liberties),
            created_move=move_index,
            last_seen_move=move_index,
            alive=True,
        )
        self._alive_groups_by_stones[stones] = group_id
        return group_id

    def _ensure_group_id_for_stones(
        self,
        stones: frozenset[tuple[int, int]],
        color: str,
        move_index: int,
    ) -> int:
        existing = self._alive_groups_by_stones.get(stones)
        if existing is not None and self._groups[existing].alive:
            self._groups[existing].last_seen_move = move_index
            return existing
        return self._create_group_record(color=color, stones=stones, move_index=move_index)

    def _ensure_group_id_at_position(self, row: int, col: int, move_index: int) -> int:
        color = self._board.get(row, col)
        if color is None:
            raise ValueError("Cannot get group ID for empty intersection")
        stones = _get_group(self._board, row, col)
        return self._ensure_group_id_for_stones(stones=stones, color=color, move_index=move_index)

    def _refresh_group_record(self, group_id: int, stones: frozenset[tuple[int, int]], move_index: int) -> None:
        record = self._groups[group_id]
        old_stones = record.stones
        if self._alive_groups_by_stones.get(old_stones) == group_id:
            del self._alive_groups_by_stones[old_stones]
        liberties = self._group_liberties(stones)
        record.stones = stones
        record.liberties = liberties
        record.liberty_count = len(liberties)
        record.last_seen_move = move_index
        record.alive = True
        self._alive_groups_by_stones[stones] = group_id

    def _mark_group_captured(self, group_id: int, move_index: int) -> None:
        record = self._groups[group_id]
        if self._alive_groups_by_stones.get(record.stones) == group_id:
            del self._alive_groups_by_stones[record.stones]
        record.alive = False
        record.last_seen_move = move_index
        record.captured_move = move_index
        record.liberties = set()
        record.liberty_count = 0

    def _mark_group_merged(self, group_id: int, move_index: int) -> None:
        record = self._groups[group_id]
        if self._alive_groups_by_stones.get(record.stones) == group_id:
            del self._alive_groups_by_stones[record.stones]
        record.alive = False
        record.last_seen_move = move_index
        record.liberties = set()
        record.liberty_count = 0

    def _refresh_group_at_position(self, row: int, col: int, move_index: int) -> int | None:
        if self._board.get(row, col) is None:
            return None
        group_id = self._ensure_group_id_at_position(row, col, move_index)
        stones = _get_group(self._board, row, col)
        self._refresh_group_record(group_id, stones, move_index)
        return group_id

    def _alive_group_liberties(self) -> dict[int, int]:
        return {
            group_id: record.liberty_count
            for group_id, record in sorted(self._groups.items())
            if record.alive
        }

    def _alive_group_zone_9(self) -> dict[int, MoveSector9]:
        """Return zone map for all alive groups using stone-majority sector."""
        return {
            group_id: self._group_sector_9(record.stones)
            for group_id, record in sorted(self._groups.items())
            if record.alive
        }

    def _alive_group_stones(self) -> dict[int, tuple[tuple[int, int], ...]]:
        return {
            group_id: tuple(sorted(record.stones))
            for group_id, record in sorted(self._groups.items())
            if record.alive
        }

    def _group_sector_9(self, stones: frozenset[tuple[int, int]]) -> MoveSector9:
        counts: dict[MoveSector9, int] = {}
        rows_from_bottom: list[int] = []
        cols: list[int] = []
        for row_top, col in stones:
            row_bottom = self._size - 1 - row_top
            sector = classify_sector_9((col, row_bottom), self._size)
            counts[sector] = counts.get(sector, 0) + 1
            rows_from_bottom.append(row_bottom)
            cols.append(col)
        if not counts:
            return "center"
        best_count = max(counts.values())
        winners = [sector for sector, count in counts.items() if count == best_count]
        if len(winners) == 1:
            return winners[0]
        centroid_col = sum(cols) / len(cols)
        centroid_row = sum(rows_from_bottom) / len(rows_from_bottom)
        centroid_sector = classify_sector_9(
            (int(round(centroid_col)), int(round(centroid_row))),
            self._size,
        )
        if centroid_sector in winners:
            return centroid_sector
        return sorted(winners)[0]

    def _rebuild_groups_from_board(self, move_index: int) -> None:
        """Re-scan board and rebuild persistent group records from scratch."""
        self._groups = {}
        self._alive_groups_by_stones = {}
        self._next_group_id = 1

        visited: set[tuple[int, int]] = set()
        for row in range(self._size):
            for col in range(self._size):
                if (row, col) in visited:
                    continue
                color = self._board.get(row, col)
                if color is None:
                    continue
                stones = _get_group(self._board, row, col)
                visited.update(stones)
                self._create_group_record(color=color, stones=stones, move_index=move_index)

    def apply_setup_stones(
        self,
        black_points: list[tuple[int, int]],
        white_points: list[tuple[int, int]],
        empty_points: list[tuple[int, int]] | None = None,
    ) -> bool:
        """Apply SGF setup stones (AB/AW/AE) before stepping through moves."""
        ok = self._board.apply_setup(black_points, white_points, empty_points or [])
        self._move_counter = 0
        self._rebuild_groups_from_board(move_index=0)
        return ok

    def debug_group_state(self) -> GroupDebugState:
        """Return a debug view of currently alive groups and board IDs."""
        group_map = [[0 for _ in range(self._size)] for _ in range(self._size)]
        groups: dict[int, dict[str, object]] = {}
        for group_id, record in sorted(self._groups.items()):
            if not record.alive:
                continue
            groups[group_id] = {
                "color": "B" if record.color == "b" else "W",
                "stones": sorted(record.stones),
                "liberty_count": record.liberty_count,
                "liberties": sorted(record.liberties),
                "created_move": record.created_move,
                "last_seen_move": record.last_seen_move,
            }
            for row, col in record.stones:
                group_map[row][col] = group_id
        return GroupDebugState(
            move_index=self._move_counter,
            board_size=self._size,
            group_map=group_map,
            groups=groups,
        )

    def step(self, move_str: str, color: str, move_index: int | None = None) -> BoardSnapshot:
        """Play *move_str* for *color* and return a BoardSnapshot.

        This is the ONLY place board.play() is called.  Called exactly once
        per move by run_layer1() in move-index order.

        Parameters
        ----------
        move_str : KataGo coordinate string e.g. 'D4', or 'pass'
        color    : 'B' or 'W'
        """
        current_move = self._resolve_move_index(move_index)
        coord = _katago_to_rowcol(move_str, self._size)
        if coord is None:
            return BoardSnapshot(
                stones_captured=0,
                self_liberties=0,
                enemy_liberties_nearby=0,
                adjacent_friendly=0,
                adjacent_enemy=0,
                connected_groups=False,
                cut_groups=False,
                nearby_friendly=0,
                played_group_id=0,
                friendly_group_ids_adjacent_pre=(),
                enemy_group_ids_adjacent_pre=(),
                groups_created=(),
                groups_captured=(),
                groups_merged_into={},
                played_group_liberties_post=0,
                adjacent_enemy_liberties_post={},
                alive_group_liberties=self._alive_group_liberties(),
                alive_group_zone_9=self._alive_group_zone_9(),
                captured_group_sizes={},
                captured_group_zones={},
                alive_group_stones=self._alive_group_stones(),
            )

        row, col = coord
        sgf_color = "b" if color == "B" else "w"
        opp_color = "w" if color == "B" else "b"

        # --- Pre-play: gather adjacency and connectivity info ---------------

        adj_friendly = 0
        adj_enemy    = 0
        friendly_group_ids: set[int] = set()
        enemy_group_ids: set[int] = set()
        enemy_group_stones_pre: dict[int, frozenset[tuple[int, int]]] = {}

        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = row + dr, col + dc
            if not (0 <= nr < self._size and 0 <= nc < self._size):
                continue
            occupant = self._board.get(nr, nc)
            if occupant == sgf_color:
                adj_friendly += 1
                friendly_group_ids.add(self._ensure_group_id_at_position(nr, nc, current_move))
            elif occupant == opp_color:
                adj_enemy += 1
                enemy_group_id = self._ensure_group_id_at_position(nr, nc, current_move)
                enemy_group_ids.add(enemy_group_id)
                enemy_group_stones_pre[enemy_group_id] = self._groups[enemy_group_id].stones

        # Count same-color stones within Chebyshev distance 2 (5×5 box, pre-play)
        nearby_friendly = 0
        for dr in range(-2, 3):
            for dc in range(-2, 3):
                if dr == 0 and dc == 0:
                    continue
                nr, nc = row + dr, col + dc
                if 0 <= nr < self._size and 0 <= nc < self._size:
                    if self._board.get(nr, nc) == sgf_color:
                        nearby_friendly += 1

        connected_groups = len(friendly_group_ids) >= 2

        # Enemy group connectivity before the move (for cut detection)
        # Two enemy groups are "connected through" the played point if they
        # share an adjacent liberty at (row, col).  After the move they will
        # be separated — that's a cut.
        # Simplified: if >= 2 distinct enemy groups are adjacent to the move
        # point, this move may cut between them.  Exact cut detection would
        # require checking whether they were previously connected via other
        # paths, but for Layer 1 we use adjacency count as a cheap proxy.
        cut_groups = len(enemy_group_ids) >= 2

        # --- Play the move --------------------------------------------------
        try:
            captured_result = self._board.play(row, col, sgf_color)
        except ValueError:
            # Illegal move (ko violation, occupied point, etc.) — skip
            return BoardSnapshot(
                stones_captured=0,
                self_liberties=0,
                enemy_liberties_nearby=0,
                adjacent_friendly=0,
                adjacent_enemy=0,
                connected_groups=False,
                cut_groups=False,
                nearby_friendly=0,
                played_group_id=0,
                friendly_group_ids_adjacent_pre=tuple(sorted(friendly_group_ids)),
                enemy_group_ids_adjacent_pre=tuple(sorted(enemy_group_ids)),
                groups_created=(),
                groups_captured=(),
                groups_merged_into={},
                played_group_liberties_post=0,
                adjacent_enemy_liberties_post={},
                alive_group_liberties=self._alive_group_liberties(),
                alive_group_zone_9=self._alive_group_zone_9(),
                captured_group_sizes={},
                captured_group_zones={},
                alive_group_stones=self._alive_group_stones(),
            )

        captured_coords: set[tuple[int, int]] = set()
        if captured_result is not None:
            captured_coords = set(captured_result)

        if not captured_coords and enemy_group_stones_pre:
            for stones in enemy_group_stones_pre.values():
                still_present = any(self._board.get(sr, sc) == opp_color for sr, sc in stones)
                if not still_present:
                    captured_coords.update(stones)

        stones_captured = len(captured_coords)
        groups_created: list[int] = []
        groups_captured: list[int] = []
        groups_merged_into: dict[int, tuple[int, ...]] = {}
        captured_group_sizes: dict[int, int] = {}
        captured_group_zones: dict[int, MoveSector9] = {}

        # --- Post-play: liberty counts --------------------------------------

        # Self liberties: count liberties of the group we just joined/formed
        try:
            own_group = _get_group(self._board, row, col)
            self_liberties = _count_liberties(self._board, own_group)
            if not friendly_group_ids:
                played_group_id = self._create_group_record(
                    color=sgf_color, stones=own_group, move_index=current_move
                )
                groups_created.append(played_group_id)
            else:
                surviving_group_id = min(friendly_group_ids)
                merged_sources = sorted(gid for gid in friendly_group_ids if gid != surviving_group_id)
                if merged_sources:
                    groups_merged_into[surviving_group_id] = tuple(merged_sources)
                    for source_id in merged_sources:
                        self._mark_group_merged(source_id, current_move)
                self._refresh_group_record(surviving_group_id, own_group, current_move)
                played_group_id = surviving_group_id
        except Exception:
            self_liberties = 0
            played_group_id = 0

        # Enemy liberties nearby: minimum liberty count of all adjacent enemy
        # groups still on the board (captured groups are already removed)
        enemy_lib_min = 0
        adjacent_enemy_liberties_post: dict[int, int] = {}
        seen_enemy_groups: set[int] = set()
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nr, nc = row + dr, col + dc
            if not (0 <= nr < self._size and 0 <= nc < self._size):
                continue
            if self._board.get(nr, nc) == opp_color:
                group_id = self._ensure_group_id_at_position(nr, nc, current_move)
                if group_id not in seen_enemy_groups:
                    seen_enemy_groups.add(group_id)
                    g = _get_group(self._board, nr, nc)
                    libs = _count_liberties(self._board, g)
                    self._refresh_group_record(group_id, g, current_move)
                    adjacent_enemy_liberties_post[group_id] = libs
                    if enemy_lib_min == 0 or libs < enemy_lib_min:
                        enemy_lib_min = libs

        if captured_coords:
            for enemy_group_id in enemy_group_ids:
                record = self._groups.get(enemy_group_id)
                if record and record.alive and record.stones.issubset(captured_coords):
                    captured_group_sizes[enemy_group_id] = len(record.stones)
                    captured_group_zones[enemy_group_id] = self._group_sector_9(record.stones)
                    self._mark_group_captured(enemy_group_id, current_move)
                    groups_captured.append(enemy_group_id)

            # Captures can change liberties for neighboring groups beyond the
            # move's immediate neighbors, so refresh groups bordering captures.
            for crow, ccol in captured_coords:
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = crow + dr, ccol + dc
                    if not (0 <= nr < self._size and 0 <= nc < self._size):
                        continue
                    refreshed_id = self._refresh_group_at_position(nr, nc, current_move)
                    if refreshed_id is not None and self._groups[refreshed_id].color == opp_color:
                        adjacent_enemy_liberties_post[refreshed_id] = self._groups[refreshed_id].liberty_count

        if played_group_id and self._groups.get(played_group_id) and self._groups[played_group_id].alive:
            played_group_liberties_post = self._groups[played_group_id].liberty_count
        else:
            played_group_liberties_post = self_liberties

        return BoardSnapshot(
            stones_captured=stones_captured,
            self_liberties=self_liberties,
            enemy_liberties_nearby=enemy_lib_min,
            adjacent_friendly=adj_friendly,
            adjacent_enemy=adj_enemy,
            connected_groups=connected_groups,
            cut_groups=cut_groups,
            nearby_friendly=nearby_friendly,
            played_group_id=played_group_id,
            friendly_group_ids_adjacent_pre=tuple(sorted(friendly_group_ids)),
            enemy_group_ids_adjacent_pre=tuple(sorted(enemy_group_ids)),
            groups_created=tuple(sorted(groups_created)),
            groups_captured=tuple(sorted(groups_captured)),
            groups_merged_into=groups_merged_into,
            played_group_liberties_post=played_group_liberties_post,
            adjacent_enemy_liberties_post=adjacent_enemy_liberties_post,
            alive_group_liberties=self._alive_group_liberties(),
            alive_group_zone_9=self._alive_group_zone_9(),
            captured_group_sizes=captured_group_sizes,
            captured_group_zones=captured_group_zones,
            alive_group_stones=self._alive_group_stones(),
        )

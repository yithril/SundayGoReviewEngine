#!/usr/bin/env python
"""
scripts/run_layer1_demo.py
---------------------------
Run the Layer 1 pipeline on a real game SGF and print a move-by-move
trigger table plus a hotspot cluster summary.

Usage
-----
    python scripts/run_layer1_demo.py [--sgf PATH] [--player B|W] [--visits N]

Environment variables (same as integration tests)
--------------------------------------------------
    KATAGO_BINARY   path to katago.exe   (default: C:/katago/katago.exe)
    KATAGO_MODEL    path to .bin.gz model (REQUIRED)
    KATAGO_CONFIG   path to analysis.cfg (default: analysis.cfg)

Output example
--------------
    === Layer 1 Trigger Signals  (85012080-174-...  |  Black  |  174 moves) ===
    Move  12  B  R16    score_swing, policy_mismatch       dscore=+4.2  dwinrate=+8.3%
    Move  45  W  D4     capture                            dscore=+1.1  dwinrate=+2.1%
    ...
    Total signals: 31

    === Hotspot Clusters ===
      #1  center= 45  moves=[ 42.. 47]  capture, score_swing      dscore=4.2  dwinrate=8.3%
    ...
    Total hotspots: 9
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

# Ensure the project root is on sys.path when running as a script
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv

# Load .env.local first (local overrides), then fall back to .env.
# Shell environment variables always take precedence (override=False).
load_dotenv(_PROJECT_ROOT / ".env.local", override=False)
load_dotenv(_PROJECT_ROOT / ".env", override=False)

from katago.engine import KataGoEngine
from sgf.parser import parse_sgf
from detection.layer1.board_tracker import BoardTracker
from detection.layer1.facts import collect_facts
from detection.layer1.hotspots import merge_hotspots
from detection.layer1.triggers import emit_triggers
from detection.layer1.zones import is_opposite_or_adjacent_opposite
from detection.types import MoveFacts, TriggerSignal

_DEFAULT_SGF = (
    _PROJECT_ROOT
    / "sgf_examples/real_games/novice/85012080-174-DangoApp_bot_3-jg250226_uwshhcr.sgf"
)

_KATAGO_BINARY = os.getenv("KATAGO_BINARY", "C:/katago/katago.exe")
_KATAGO_MODEL  = os.getenv("KATAGO_MODEL", "")
_KATAGO_CONFIG = os.getenv("KATAGO_CONFIG", "analysis.cfg")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Layer 1 trigger demo")
    p.add_argument("--sgf",    default=str(_DEFAULT_SGF), help="Path to game SGF")
    p.add_argument("--player", default="B", choices=["B", "W"], help="Reviewed player colour")
    p.add_argument("--visits", default=50, type=int, help="KataGo maxVisits per turn")
    p.add_argument("--moves",  default=None, type=int, help="Only analyze first N moves (default: all)")
    p.add_argument(
        "--show-groups",
        action="store_true",
        help="Print group map + group summaries after each move",
    )
    p.add_argument(
        "--group-moves",
        default=30,
        type=int,
        help="How many early moves to print group debug info for (default: 30)",
    )
    return p.parse_args()


async def _analyze(sgf_path: Path, engine: KataGoEngine, visits: int, max_moves: int | None = None) -> tuple[dict, dict]:
    """Analyze turns of a game SGF and return (game_dict, katago_responses)."""
    raw = sgf_path.read_bytes()
    game = parse_sgf(raw)
    all_moves = game["moves"]
    moves = all_moves[:max_moves] if max_moves else all_moves
    num_turns = len(moves)
    query_id = str(uuid.uuid4())

    query = {
        "id":               query_id,
        "moves":            moves,
        "rules":            "chinese",
        "komi":             game["komi"],
        "boardXSize":       game["board_size"],
        "boardYSize":       game["board_size"],
        "analyzeTurns":     list(range(num_turns + 1)),
        "maxVisits":        visits,
        "includeOwnership": True,
        "includePVVisits":  False,
    }
    responses = await engine.analyze(query, num_turns=num_turns + 1)
    # Stitch truncated move list back into a copy of game dict
    game_slice = dict(game)
    game_slice["moves"] = moves
    return game_slice, responses


def _fmt_delta(value: float, unit: str = "") -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}{unit}"


def _row_to_go_label(row_from_top: int, board_size: int) -> int:
    """Convert top-origin row index to Go row label (1 at bottom)."""
    return board_size - row_from_top


def _print_group_debug(tracker: BoardTracker, move_index: int, move_color: str, move_str: str) -> None:
    """Render current group map and per-group metadata for visual debugging."""
    state = tracker.debug_group_state()
    board_size = state.board_size

    print()
    print(f"--- Group Debug: move {move_index} ({move_color} {move_str}) ---")
    print("Board group IDs (0 = empty):")
    for row in range(board_size):
        go_row = _row_to_go_label(row, board_size)
        row_values = " ".join(f"{gid:>3}" for gid in state.group_map[row])
        print(f"{go_row:>2} | {row_values}")
    print("    " + "---" * board_size)
    print("      " + " ".join(f"{i+1:>2}" for i in range(board_size)))

    if not state.groups:
        print("Groups: (none)")
        return

    print("Groups:")
    for group_id, info in state.groups.items():
        color = info["color"]
        liberty_count = info["liberty_count"]
        created_move = info["created_move"]
        stones = info["stones"]
        print(
            f"  G{group_id:>3}  color={color}  libs={liberty_count}  "
            f"created={created_move}  stones={stones}"
        )


async def main() -> None:
    args = _parse_args()

    if not _KATAGO_MODEL:
        print("ERROR: KATAGO_MODEL environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(_KATAGO_BINARY):
        print(f"ERROR: KataGo binary not found at {_KATAGO_BINARY!r}", file=sys.stderr)
        sys.exit(1)

    sgf_path = Path(args.sgf)
    if not sgf_path.exists():
        print(f"ERROR: SGF not found: {sgf_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Starting KataGo ({_KATAGO_BINARY})...", flush=True)
    engine = KataGoEngine(_KATAGO_BINARY, _KATAGO_MODEL, _KATAGO_CONFIG)
    await engine.start()

    try:
        move_desc = f"{args.moves} moves" if args.moves else "all moves"
        print(f"Analyzing {sgf_path.name} — {move_desc}, {args.visits} visits per turn...", flush=True)
        game, responses = await _analyze(sgf_path, engine, args.visits, max_moves=args.moves)
    finally:
        await engine.stop()

    player     = args.player
    board_size = game.get("board_size", 19)
    all_moves  = game["moves"]
    total      = min(args.moves, len(all_moves)) if args.moves else len(all_moves)
    moves      = all_moves[:total]

    # ------------------------------------------------------------------
    # Drive the pipeline manually to collect per-move TriggerSignals
    # ------------------------------------------------------------------
    tracker = BoardTracker(board_size)
    prev_signals: list[TriggerSignal] = []
    prev_moyo_cell_count = 0

    # (move_index, move_color, move_str, facts, [signals])
    per_move: list[tuple[int, str, str, MoveFacts, list[TriggerSignal]]] = []

    for move_index in range(1, total + 1):
        entry = moves[move_index - 1]
        move_color: str = entry[0]
        move_str:   str = entry[1] if len(entry) > 1 else "pass"

        snapshot = tracker.step(move_str, move_color, move_index=move_index)
        facts = collect_facts(
            move_index=move_index,
            moves=moves,
            katago_responses=responses,
            player_color=player,
            board_size=board_size,
            prev_signals=prev_signals,
            prev_moyo_cell_count=prev_moyo_cell_count,
            snapshot=snapshot,
        )
        signals = emit_triggers(facts)
        prev_signals.extend(signals)
        prev_moyo_cell_count = facts.moyo_cell_count

        per_move.append((move_index, move_color, move_str, facts, signals))

        if args.show_groups and move_index <= args.group_moves:
            _print_group_debug(tracker, move_index, move_color, move_str)

    hotspots = merge_hotspots(prev_signals)

    # ------------------------------------------------------------------
    # Print trigger table
    # ------------------------------------------------------------------
    header = (
        f"=== Layer 1 Trigger Signals  "
        f"({sgf_path.name}  |  {'Black' if player == 'B' else 'White'}  |  {total} moves) ==="
    )
    print()
    print(header)

    triggered_moves = [(mi, mc, ms, facts, sigs) for mi, mc, ms, facts, sigs in per_move if sigs]

    if not triggered_moves:
        print("  (no triggers fired)")
    else:
        for move_index, move_color, move_str, facts, signals in triggered_moves:
            type_str  = ", ".join(s.trigger_type for s in signals)
            score_d   = signals[0].score_delta
            winrate_d = signals[0].winrate_delta
            coord_col = f"{move_color}  {move_str:<4}"
            zone_hint = (
                f"{facts.move_sector_9}->{facts.preferred_move_sector_9}"
                + ("*" if is_opposite_or_adjacent_opposite(facts.move_sector_9, facts.preferred_move_sector_9) else "")
            )
            print(
                f"  Move {move_index:>3}  {coord_col}"
                f"  {type_str:<45}"
                f"  zone={zone_hint:<23}"
                f"  dscore={_fmt_delta(score_d, 'pts')}"
                f"  dwinrate={_fmt_delta(winrate_d * 100, '%')}"
            )

    total_signals = sum(len(sigs) for _, _, _, _, sigs in per_move)
    print(f"\nTotal signals: {total_signals}")

    # ------------------------------------------------------------------
    # Print hotspot clusters
    # ------------------------------------------------------------------
    print()
    print("=== Hotspot Clusters ===")
    if not hotspots:
        print("  (no hotspots)")
    else:
        for i, hs in enumerate(hotspots, 1):
            types_str = ", ".join(hs.trigger_types)
            lo = min(hs.move_indices)
            hi = max(hs.move_indices)
            print(
                f"  #{i:<3} center={hs.center_move_index:>3}"
                f"  moves=[{lo:>3}..{hi:>3}]"
                f"  {types_str:<45}"
                f"  dscore={hs.max_score_delta:.1f}pts"
                f"  dwinrate={hs.max_winrate_delta * 100:.1f}%"
            )
    print(f"\nTotal hotspots: {len(hotspots)}")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python
from __future__ import annotations

"""
Build one combined calibration table for moyo + invasion SGFs.

The report is intended for visual side-by-side pattern inspection across files.
It supports both:
  - normal game SGFs
  - setup-position SGFs (AB/AW/AE root setup + one/few played moves)
"""

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from time import perf_counter
from pathlib import Path
from typing import Any

import sgfmill.sgf
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

load_dotenv(_PROJECT_ROOT / ".env.local", override=False)
load_dotenv(_PROJECT_ROOT / ".env", override=False)

from detection.layer1.board_tracker import BoardTracker
from detection.layer1.facts import collect_facts
from detection.layer1.triggers import emit_triggers
from detection.layer1.zones import is_opposite_or_adjacent_opposite
from detection.types import TriggerSignal
from katago.engine import KataGoEngine
from sgf.parser import gtp_to_col_row, parse_sgf, sgf_coord_to_katago

_KATAGO_BINARY = os.getenv("KATAGO_BINARY", "C:/katago/katago.exe")
_KATAGO_MODEL = os.getenv("KATAGO_MODEL", "")
_KATAGO_CONFIG = os.getenv("KATAGO_CONFIG", "analysis.cfg")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build combined moyo/invasion pattern table")
    p.add_argument(
        "--motifs",
        nargs="+",
        default=["moyo", "invasion"],
        help="SGF motif folders under sgf_examples/",
    )
    p.add_argument("--tail-moves", type=int, default=15, help="Trailing moves for game SGFs")
    p.add_argument("--visits", type=int, default=5, help="KataGo maxVisits per turn")
    p.add_argument(
        "--output",
        default="docs/calibration/moyo_invasion_pattern_table.txt",
        help="Output report path relative to repo root",
    )
    return p.parse_args()


def _load_sgf_game(path: Path) -> tuple[sgfmill.sgf.Sgf_game, dict[str, Any]]:
    raw = path.read_bytes()
    parsed = parse_sgf(raw)
    raw_text = raw.decode("utf-8", errors="replace")
    game_obj = sgfmill.sgf.Sgf_game.from_string(raw_text)
    return game_obj, parsed


def _extract_setup(
    game_obj: sgfmill.sgf.Sgf_game, board_size: int
) -> tuple[list[list[str]], list[tuple[int, int]], list[tuple[int, int]], list[tuple[int, int]], bool]:
    root = game_obj.get_root()
    initial_stones: list[list[str]] = []
    black_points: list[tuple[int, int]] = []
    white_points: list[tuple[int, int]] = []
    empty_points: list[tuple[int, int]] = []

    for prop, dest, color in (
        ("AB", black_points, "B"),
        ("AW", white_points, "W"),
        ("AE", empty_points, None),
    ):
        try:
            coords = root.get(prop)
        except KeyError:
            coords = None
        if not coords:
            continue
        for row, col in coords:
            dest.append((row, col))
            if color is not None:
                initial_stones.append([color, sgf_coord_to_katago(row, col, board_size)])

    has_setup = bool(black_points or white_points or empty_points)
    return initial_stones, black_points, white_points, empty_points, has_setup


def _collect_sgfs(project_root: Path, motifs: list[str]) -> list[tuple[str, Path]]:
    selected: list[tuple[str, Path]] = []
    for motif in motifs:
        motif_dir = project_root / "sgf_examples" / motif
        if not motif_dir.exists():
            continue
        files = sorted(motif_dir.glob("*.sgf"), key=lambda p: p.name.lower())
        selected.extend((motif, path) for path in files)
    return selected


def _build_query(
    parsed_game: dict[str, Any],
    moves: list[list[str]],
    visits: int,
    initial_stones: list[list[str]],
) -> tuple[dict[str, Any], int]:
    analyze_turns = list(range(len(moves) + 1))
    query: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "moves": moves,
        "rules": "chinese",
        "komi": parsed_game["komi"],
        "boardXSize": parsed_game["board_size"],
        "boardYSize": parsed_game["board_size"],
        "analyzeTurns": analyze_turns,
        "maxVisits": visits,
        "includeOwnership": True,
        "includePVVisits": False,
    }
    if initial_stones:
        query["initialStones"] = initial_stones
    return query, len(analyze_turns)


def _ownership_at_move(move: str, ownership: list[float], board_size: int) -> float:
    coord = gtp_to_col_row(move)
    if coord is None or len(ownership) != board_size * board_size:
        return 0.0
    col, row_from_bottom = coord
    row_from_top = board_size - 1 - row_from_bottom
    idx = row_from_top * board_size + col
    return float(ownership[idx])


def _pick_move_window(total_moves: int, has_setup: bool, tail_moves: int) -> tuple[str, set[int]]:
    # Treat short setup-driven files as position examples: keep all played moves.
    if has_setup and total_moves <= 5:
        return "position_all", set(range(1, total_moves + 1))
    start = max(1, total_moves - tail_moves + 1)
    return "game_tail", set(range(start, total_moves + 1))


def _format_float(value: float, digits: int = 3) -> str:
    return f"{value:.{digits}f}"


def _render_table(rows: list[dict[str, str]], output_path: Path, metadata_lines: list[str]) -> None:
    columns = [
        ("motif", "motif"),
        ("sgf", "sgf"),
        ("mode", "mode"),
        ("move", "move"),
        ("color", "clr"),
        ("coord", "coord"),
        ("score_delta", "dscore"),
        ("winrate_delta", "dwr_pct"),
        ("policy_rank", "prank"),
        ("policy_prob", "pprob"),
        ("ownership_here", "own_here"),
        ("move_sector_9", "sector"),
        ("preferred_sector_9", "pref_sec"),
        ("opposite_preferred_zone", "opp_pref"),
        ("entered_influence", "entered"),
        ("moyo_cells", "moyo"),
        ("moyo_delta", "dmoyo"),
        ("nearby_friendly", "near_f"),
        ("adjacent_friendly", "adj_f"),
        ("adjacent_enemy", "adj_e"),
        ("self_liberties", "self_lib"),
        ("enemy_liberties_nearby", "enemy_lib"),
        ("triggers", "triggers"),
    ]

    widths: dict[str, int] = {}
    for key, title in columns:
        max_content = max((len(r.get(key, "")) for r in rows), default=0)
        widths[key] = max(len(title), max_content)

    header = " | ".join(title.ljust(widths[key]) for key, title in columns)
    sep = "-+-".join("-" * widths[key] for key, _ in columns)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for line in metadata_lines:
            f.write(f"{line}\n")
        f.write("\n")
        f.write(header + "\n")
        f.write(sep + "\n")
        for row in rows:
            line = " | ".join(row.get(key, "").ljust(widths[key]) for key, _ in columns)
            f.write(line + "\n")


async def main() -> None:
    args = _parse_args()
    run_started = perf_counter()

    if not _KATAGO_MODEL:
        print("ERROR: KATAGO_MODEL environment variable is not set.", file=sys.stderr)
        sys.exit(1)
    if not os.path.exists(_KATAGO_BINARY):
        print(f"ERROR: KataGo binary not found at {_KATAGO_BINARY!r}", file=sys.stderr)
        sys.exit(1)

    selected = _collect_sgfs(_PROJECT_ROOT, args.motifs)
    if not selected:
        print("ERROR: No SGFs matched requested motifs.", file=sys.stderr)
        sys.exit(1)
    print(
        f"[start] selected {len(selected)} SGFs across motifs={','.join(args.motifs)} "
        f"(tail_moves={args.tail_moves}, visits={args.visits})",
        flush=True,
    )

    engine = KataGoEngine(_KATAGO_BINARY, _KATAGO_MODEL, _KATAGO_CONFIG)
    print("[start] launching KataGo engine...", flush=True)
    await engine.start()
    print("[start] KataGo ready", flush=True)

    rows: list[dict[str, str]] = []
    processed_files = 0
    skipped_files = 0

    try:
        for file_idx, (motif, sgf_path) in enumerate(selected, start=1):
            file_started = perf_counter()
            before_rows = len(rows)
            print(f"[{file_idx}/{len(selected)}] {motif}/{sgf_path.name} ...", flush=True)
            game_obj, parsed = _load_sgf_game(sgf_path)
            moves: list[list[str]] = parsed["moves"]
            board_size = parsed["board_size"]

            initial_stones, black_points, white_points, empty_points, has_setup = _extract_setup(
                game_obj, board_size
            )
            mode, chosen_moves = _pick_move_window(len(moves), has_setup, args.tail_moves)

            if not moves:
                skipped_files += 1
                elapsed = perf_counter() - file_started
                print(
                    f"[{file_idx}/{len(selected)}] {motif}/{sgf_path.name} "
                    f"SKIP (no moves) in {elapsed:.1f}s",
                    flush=True,
                )
                continue

            query, expected_turns = _build_query(parsed, moves, args.visits, initial_stones)
            responses = await engine.analyze(query, num_turns=expected_turns)

            tracker = BoardTracker(board_size)
            if has_setup:
                tracker.apply_setup_stones(black_points, white_points, empty_points)

            prev_signals: list[TriggerSignal] = []
            prev_moyo_cell_count = 0

            for move_index, move_entry in enumerate(moves, start=1):
                move_color = move_entry[0]
                move_str = move_entry[1] if len(move_entry) > 1 else "pass"
                snapshot = tracker.step(move_str, move_color, move_index=move_index)
                facts = collect_facts(
                    move_index=move_index,
                    moves=moves,
                    katago_responses=responses,
                    player_color=move_color,  # mover-centric perspective for calibration rows
                    board_size=board_size,
                    prev_signals=prev_signals,
                    prev_moyo_cell_count=prev_moyo_cell_count,
                    snapshot=snapshot,
                )
                signals = emit_triggers(facts)
                prev_signals.extend(signals)
                prev_moyo_cell_count = facts.moyo_cell_count

                if move_index not in chosen_moves:
                    continue

                curr_resp = responses.get(move_index, {})
                ownership = curr_resp.get("ownership", [])
                ownership_here = _ownership_at_move(move_str, ownership, board_size)

                rows.append(
                    {
                        "motif": motif,
                        "sgf": sgf_path.name,
                        "mode": mode,
                        "move": str(move_index),
                        "color": move_color,
                        "coord": move_str,
                        "score_delta": _format_float(facts.score_delta, 2),
                        "winrate_delta": _format_float(facts.winrate_delta * 100, 2),
                        "policy_rank": str(facts.policy_rank),
                        "policy_prob": _format_float(facts.policy_prob, 3),
                        "ownership_here": _format_float(ownership_here, 3),
                        "move_sector_9": facts.move_sector_9,
                        "preferred_sector_9": facts.preferred_move_sector_9,
                        "opposite_preferred_zone": (
                            "Y"
                            if is_opposite_or_adjacent_opposite(
                                facts.move_sector_9, facts.preferred_move_sector_9
                            )
                            else "N"
                        ),
                        "entered_influence": "Y" if facts.entered_influence else "N",
                        "moyo_cells": str(facts.moyo_cell_count),
                        "moyo_delta": str(facts.dmoyo),
                        "nearby_friendly": str(facts.nearby_friendly),
                        "adjacent_friendly": str(facts.adjacent_friendly),
                        "adjacent_enemy": str(facts.adjacent_enemy),
                        "self_liberties": str(facts.self_liberties),
                        "enemy_liberties_nearby": str(facts.enemy_liberties_nearby),
                        "triggers": ",".join(s.trigger_type for s in signals) or "-",
                    }
                )
            processed_files += 1
            elapsed = perf_counter() - file_started
            added_rows = len(rows) - before_rows
            print(
                f"[{file_idx}/{len(selected)}] {motif}/{sgf_path.name} "
                f"done ({mode}, moves={len(moves)}, rows+={added_rows}) in {elapsed:.1f}s",
                flush=True,
            )
    finally:
        await engine.stop()
        print("[end] KataGo stopped", flush=True)

    rows.sort(key=lambda r: (r["motif"], r["sgf"], int(r["move"])))

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = _PROJECT_ROOT / out_path

    metadata = [
        "# Layer 1 Moyo/Invasion calibration table",
        f"# generated_utc={datetime.now(timezone.utc).isoformat()}",
        f"# motifs={','.join(args.motifs)} tail_moves={args.tail_moves} visits={args.visits}",
        f"# files_processed={processed_files} files_skipped_no_moves={skipped_files} rows={len(rows)}",
    ]
    _render_table(rows, out_path, metadata)
    total_elapsed = perf_counter() - run_started
    print(f"Wrote report: {out_path}", flush=True)
    print(f"[end] total elapsed: {total_elapsed:.1f}s", flush=True)


if __name__ == "__main__":
    asyncio.run(main())

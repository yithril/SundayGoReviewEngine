from __future__ import annotations

"""
detection/layer1/hotspots.py
-----------------------------
Step 3 of the Layer 1 pipeline: group nearby TriggerSignals into
HotspotCandidates and pass the list to Layer 2.

v1 strategy — move-index window grouping
-----------------------------------------
Signals within HOTSPOT_WINDOW moves of each other are merged into a
single candidate.  The candidate's center_move_index is the signal with
the largest absolute win-rate delta.

v2 note: replace window grouping with spatial (board-coordinate) proximity
once coordinate parsing is in place, so that signals in the same local area
are clustered regardless of move-index distance.
"""

from game.constants.thresholds import HOTSPOT_WINDOW
from detection.types import CaptureGroupInfo, HotspotCandidate, TriggerSignal


def merge_hotspots(signals: list[TriggerSignal]) -> list[HotspotCandidate]:
    """Group *signals* into HotspotCandidates using a sliding move-index window.

    Algorithm
    ---------
    1. Sort signals by move_index.
    2. Walk through them; start a new window whenever the gap between the
       current signal and the window's first signal exceeds HOTSPOT_WINDOW.
    3. For each window, pick the signal with the largest |winrate_delta| as
       the center; collect all unique trigger types and move indices.
    4. Return one HotspotCandidate per window, sorted by center_move_index.
    """
    if not signals:
        return []

    sorted_signals = sorted(signals, key=lambda s: s.move_index)
    windows: list[list[TriggerSignal]] = []
    current_window: list[TriggerSignal] = [sorted_signals[0]]

    for sig in sorted_signals[1:]:
        if sig.move_index - current_window[0].move_index <= HOTSPOT_WINDOW:
            current_window.append(sig)
        else:
            windows.append(current_window)
            current_window = [sig]
    windows.append(current_window)

    candidates: list[HotspotCandidate] = []
    for window in windows:
        center = max(window, key=lambda s: abs(s.winrate_delta))
        move_indices = sorted({s.move_index for s in window})
        # Preserve insertion order of trigger types as they first appear
        seen: set[str] = set()
        trigger_types = []
        for s in window:
            if s.trigger_type not in seen:
                seen.add(s.trigger_type)
                trigger_types.append(s.trigger_type)
        max_wr    = max(abs(s.winrate_delta) for s in window)
        max_score = max(abs(s.score_delta)   for s in window)
        capture_map: dict[int, CaptureGroupInfo] = {}
        for signal in window:
            for group in signal.captured_groups:
                capture_map[group.group_id] = group
        captured_groups = tuple(capture_map[group_id] for group_id in sorted(capture_map.keys()))
        max_captured_group_size = max((group.size for group in captured_groups), default=0)
        candidates.append(
            HotspotCandidate(
                center_move_index=center.move_index,
                move_indices=move_indices,
                trigger_types=trigger_types,
                max_winrate_delta=max_wr,
                max_score_delta=max_score,
                captured_groups=captured_groups,
                max_captured_group_size=max_captured_group_size,
            )
        )

    return sorted(candidates, key=lambda c: c.center_move_index)

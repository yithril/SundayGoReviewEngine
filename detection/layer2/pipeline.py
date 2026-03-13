from __future__ import annotations

"""
detection/layer2/pipeline.py
-----------------------------
Public API for Layer 2.  Receives Layer 1's HotspotCandidates and
classifies each into a named GameEvent.

v1: all classifiers are stubs — run_layer2() returns an empty list.
Real implementation: iterate each hotspot through the classifier registry;
collect non-None results, sort by move_start.
"""

from detection.layer2.classifiers import (
    classify_bad_direction_shift,
    classify_capture_sequence,
    classify_cut_defense_success,
    classify_good_direction_shift,
    classify_group_death,
    classify_group_saved,
    classify_invasion_settled,
    classify_ko_fight,
    classify_liberty_tactic,
    classify_large_territory_swing,
    classify_moyo_established,
    classify_opening_framework,
    classify_semeai,
    classify_shape_strength_or_liability,
    classify_tenuki_punished,
    classify_weak_group_crisis,
)
from detection.layer1.zones import classify_sector_9, parse_gtp_coord
from game.constants.thresholds import DIRECTION_EVENT_DEBOUNCE_WINDOW
from detection.types import GameEvent, HotspotCandidate

# Registry: each classifier is tried against every hotspot in order.
# A hotspot may match multiple classifiers (e.g. a ko fight that also
# involves a weak group); all matches are kept.
_CLASSIFIERS = [
    classify_capture_sequence,
    classify_cut_defense_success,
    classify_shape_strength_or_liability,
    classify_liberty_tactic,
    classify_group_death,
    classify_group_saved,
    classify_invasion_settled,
    classify_ko_fight,
    classify_semeai,
    classify_large_territory_swing,
    classify_opening_framework,
    classify_tenuki_punished,
    classify_weak_group_crisis,
    classify_moyo_established,
    classify_good_direction_shift,
    classify_bad_direction_shift,
]


def _move_color(game: dict, move_index: int) -> str:
    moves = game.get("moves", [])
    if 1 <= move_index <= len(moves):
        return str(moves[move_index - 1][0])
    return "B"


def _move_sector(game: dict, move_index: int) -> str:
    moves = game.get("moves", [])
    board_size = int(game.get("board_size", 19))
    if 1 <= move_index <= len(moves):
        move = str(moves[move_index - 1][1]) if len(moves[move_index - 1]) > 1 else "pass"
        return classify_sector_9(parse_gtp_coord(move, board_size), board_size)
    return "center"


def _suppress_repeated_direction_events(
    events: list[GameEvent],
    game: dict,
) -> list[GameEvent]:
    """Debounce repeated good/bad direction events during local fights."""
    kept: list[GameEvent] = []
    last_seen: dict[tuple[str, str, str], tuple[int, bool]] = {}

    for event in sorted(events, key=lambda e: e.center_move_index):
        if event.event_type not in {"good_direction_shift", "bad_direction_shift"}:
            kept.append(event)
            continue

        center = event.center_move_index
        zone = _move_sector(game, center)
        player = _move_color(game, center)
        key = (event.event_type, player, zone)
        has_local_fight = any(
            "local_fight" in hs.trigger_types
            for hs in event.hotspots
        )
        prev = last_seen.get(key)
        should_suppress = False
        if prev is not None:
            prev_center, prev_local_fight = prev
            close_in_time = (center - prev_center) <= DIRECTION_EVENT_DEBOUNCE_WINDOW
            if close_in_time and (has_local_fight or prev_local_fight):
                should_suppress = True

        if not should_suppress:
            kept.append(event)
            last_seen[key] = (center, has_local_fight)

    return kept


def run_layer2(
    hotspots: list[HotspotCandidate],
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str = "B",
) -> list[GameEvent]:
    """Classify HotspotCandidates into named GameEvents.

    Parameters
    ----------
    hotspots         : output of run_layer1()
    game             : parsed SGF dict
    katago_responses : turn_number → KataGo response dict

    Returns
    -------
    list[GameEvent] sorted by move_start.
    """
    events: list[GameEvent] = []

    for hotspot in hotspots:
        for classifier in _CLASSIFIERS:
            result = classifier(hotspot, game, katago_responses, reviewed_player_color)
            if result is not None:
                events.append(result)

    events = _suppress_repeated_direction_events(events, game)
    return sorted(events, key=lambda e: e.move_start)

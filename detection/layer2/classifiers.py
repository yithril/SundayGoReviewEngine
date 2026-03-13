from __future__ import annotations

"""
detection/layer2/classifiers.py
--------------------------------
One classifier function per GameEventType.  Each receives a HotspotCandidate
and the raw KataGo context; it returns a GameEvent if the hotspot matches that
event type, or None if it does not.

v1: all classifiers are stubs that return None.
Each docstring describes what the real implementation should look for so
each event type can be implemented independently without touching the others.
"""

from typing import Optional

from game.constants.phases import get_phase
from detection.types import GameEvent, HotspotCandidate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _score_swing_across(
    hotspot: HotspotCandidate,
    katago_responses: dict[int, dict],
) -> float:
    """Net score change (Black perspective) across hotspot move span."""
    indices = hotspot.move_indices
    if not indices:
        return 0.0
    start_resp = katago_responses.get(indices[0] - 1, {})
    end_resp   = katago_responses.get(indices[-1], {})
    start_score = start_resp.get("rootInfo", {}).get("scoreLead", 0.0)
    end_score   = end_resp.get("rootInfo", {}).get("scoreLead", 0.0)
    return float(end_score - start_score)


def _player_color_for_move(game: dict, move_index: int) -> str:
    moves = game.get("moves", [])
    if 1 <= move_index <= len(moves):
        entry = moves[move_index - 1]
        if entry and isinstance(entry, list):
            return str(entry[0])
    return "B"


def _score_swing_for_player(
    hotspot: HotspotCandidate,
    katago_responses: dict[int, dict],
    player_color: str,
) -> float:
    indices = hotspot.move_indices
    if not indices:
        return 0.0
    start_resp = katago_responses.get(indices[0] - 1, {})
    end_resp = katago_responses.get(indices[-1], {})
    start_score = float(start_resp.get("rootInfo", {}).get("scoreLead", 0.0))
    end_score = float(end_resp.get("rootInfo", {}).get("scoreLead", 0.0))
    black_delta = end_score - start_score
    return black_delta if player_color == "B" else -black_delta


def _winrate_swing_for_player(
    hotspot: HotspotCandidate,
    katago_responses: dict[int, dict],
    player_color: str,
) -> float:
    indices = hotspot.move_indices
    if not indices:
        return 0.0
    start_resp = katago_responses.get(indices[0] - 1, {})
    end_resp = katago_responses.get(indices[-1], {})
    start_wr = float(start_resp.get("rootInfo", {}).get("winrate", 0.5))
    end_wr = float(end_resp.get("rootInfo", {}).get("winrate", 0.5))
    black_delta = end_wr - start_wr
    return black_delta if player_color == "B" else -black_delta


def _event_from_hotspot(
    *,
    event_type: str,
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
    description_hint: str,
    forced_polarity: str | None = None,
) -> GameEvent:
    move_start = min(hotspot.move_indices) if hotspot.move_indices else hotspot.center_move_index
    move_end = max(hotspot.move_indices) if hotspot.move_indices else hotspot.center_move_index
    player_color = _player_color_for_move(game, hotspot.center_move_index)
    score_swing = _score_swing_for_player(hotspot, katago_responses, reviewed_player_color)
    winrate_swing = _winrate_swing_for_player(hotspot, katago_responses, reviewed_player_color)
    if forced_polarity is not None:
        polarity = forced_polarity
    elif score_swing > 0:
        polarity = "positive"
    elif score_swing < 0:
        polarity = "negative"
    else:
        polarity = "neutral"
    return GameEvent(
        event_type=event_type,  # type: ignore[arg-type]
        move_start=move_start,
        move_end=move_end,
        center_move_index=hotspot.center_move_index,
        hotspots=[hotspot],
        player_color=player_color,  # type: ignore[arg-type]
        phase=get_phase(hotspot.center_move_index),
        description_hint=description_hint,
        score_swing=score_swing,
        winrate_swing=winrate_swing,
        score_swing_abs=abs(score_swing),
        event_polarity=polarity,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# Classifier stubs — one per GameEventType
# ---------------------------------------------------------------------------

def classify_capture_sequence(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a sequence where stones were captured.

    Real implementation: check for 'capture' and 'atari_created' triggers
    in the hotspot, confirm stones_captured > 0 via board state, verify
    the score swing matches the stone value.
    """
    if "capture" not in hotspot.trigger_types:
        return None
    return _event_from_hotspot(
        event_type="capture_sequence",
        hotspot=hotspot,
        game=game,
        katago_responses=katago_responses,
        reviewed_player_color=reviewed_player_color,
        description_hint="Capture sequence impacted the local position.",
    )


def classify_group_death(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect when a player's group is killed.

    Real implementation (future pass): look for 'life_and_death_candidate'
    + 'weak_group_candidate' triggers, then confirm via per-group ownership
    trend channels (plumbed through Layer 1 facts) that ownership collapses
    from favorable to unfavorable over several moves.

    This classifier intentionally stays disabled in V1 while ownership-flip
    thresholds and stability windows are calibrated.
    """
    return None


def classify_group_saved(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect when a player successfully defends an endangered group.

    Real implementation: 'life_and_death_candidate' or 'weak_group_candidate'
    fired, followed by a positive score swing for the defender; ownership
    around the group stabilises.
    """
    return None


def classify_invasion_settled(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect an invasion or reduction that reached a settled outcome.

    Real implementation: 'invasion' or 'reduction' trigger, followed within
    HOTSPOT_WINDOW moves by either a large score swing (invasion succeeded)
    or by the invading group becoming weak (invasion failed).
    """
    return None


def classify_ko_fight(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a ko fight.

    Real implementation: repeated capture of the same point (ko point from
    BoardState), combined with tenuki moves for ko threats.  Check for
    'capture' triggers at an identical board coordinate across alternating moves.
    """
    return None


def classify_semeai(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a capturing race (semeai) between two adjacent groups.

    Real implementation: two groups with low self_liberties (both <= 4),
    adjacent to each other, with score swings correlating with liberty changes.
    """
    return None


def classify_large_territory_swing(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a large territory swing not attributed to a specific tactical event.

    Real implementation: 'score_swing' trigger with abs(score_delta) above a
    higher threshold (e.g. 8+ points), no 'capture' or 'life_and_death_candidate'
    co-trigger — pure strategic move with large territory impact.
    """
    return None


def classify_opening_framework(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a significant opening framework formation.

    Real implementation: hotspot in OPENING_1 or OPENING_2 phase, large
    ownership region established (moyo_formed trigger), positive score swing.
    The description should name the opening if recognisable (Chinese, Kobayashi,
    San-Rensei, etc.) — joseki library lookup goes here.
    """
    return None


def classify_tenuki_punished(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect when a tenuki was punished by the opponent.

    Real implementation: 'tenuki_after_forcing' trigger on player's move,
    followed within a few moves by a large negative score swing — the
    opponent exploited the ignored local issue.
    """
    return None


def classify_weak_group_crisis(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a prolonged crisis for a weak group.

    Real implementation: multiple consecutive 'weak_group_candidate' triggers
    across several moves in the same area, combined with a sustained negative
    ownership shift around that region.
    """
    return None


def classify_moyo_established(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect when a moyo is established (sustained, not just a single trigger).

    Real implementation: 'moyo_formation' trigger fires on at least 2 of the
    hotspot's move indices (moyo persisted across multiple moves), with
    moyo_cell_count above MOYO_MIN_CELLS throughout the span.
    """
    return None


def classify_cut_defense_success(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a successful local cut defense/connection result."""
    if "connection_attempt" not in hotspot.trigger_types:
        return None
    return _event_from_hotspot(
        event_type="cut_defense_success",
        hotspot=hotspot,
        game=game,
        katago_responses=katago_responses,
        reviewed_player_color=reviewed_player_color,
        description_hint="Connected stones to defend against cut pressure.",
    )


def classify_shape_strength_or_liability(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Classify shape candidate as positive strength or negative liability."""
    if "shape_candidate" not in hotspot.trigger_types:
        return None
    score_swing = _score_swing_for_player(hotspot, katago_responses, reviewed_player_color)
    event_type = "shape_strength" if score_swing >= 0 else "shape_liability"
    desc = (
        "Shape choice improved local efficiency."
        if event_type == "shape_strength"
        else "Shape choice reduced local efficiency."
    )
    return _event_from_hotspot(
        event_type=event_type,
        hotspot=hotspot,
        game=game,
        katago_responses=katago_responses,
        reviewed_player_color=reviewed_player_color,
        description_hint=desc,
    )


def classify_liberty_tactic(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Classify liberty-focused tactical outcomes from existing L1 signals."""
    has_positive = "atari_created" in hotspot.trigger_types
    has_negative = "self_atari_candidate" in hotspot.trigger_types
    if not (has_positive or has_negative):
        return None
    if has_negative and not has_positive:
        event_type = "liberty_tactic_failure"
        desc = "Liberty management error created tactical vulnerability."
    else:
        event_type = "liberty_tactic_success"
        desc = "Liberty tactic created pressure on nearby group."
    return _event_from_hotspot(
        event_type=event_type,
        hotspot=hotspot,
        game=game,
        katago_responses=katago_responses,
        reviewed_player_color=reviewed_player_color,
        description_hint=desc,
    )


def classify_good_direction_shift(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a move where direction aligns with preferred board area."""
    if "good_direction_of_play" not in hotspot.trigger_types:
        return None
    return _event_from_hotspot(
        event_type="good_direction_shift",
        hotspot=hotspot,
        game=game,
        katago_responses=katago_responses,
        reviewed_player_color=reviewed_player_color,
        description_hint="Shifted play into KataGo-preferred board area.",
        forced_polarity="positive",
    )


def classify_bad_direction_shift(
    hotspot: HotspotCandidate,
    game: dict,
    katago_responses: dict[int, dict],
    reviewed_player_color: str,
) -> Optional[GameEvent]:
    """Detect a move where direction diverges from preferred board area."""
    if "bad_direction_of_play" not in hotspot.trigger_types:
        return None
    return _event_from_hotspot(
        event_type="bad_direction_shift",
        hotspot=hotspot,
        game=game,
        katago_responses=katago_responses,
        reviewed_player_color=reviewed_player_color,
        description_hint="Played in opposite direction to KataGo-preferred area.",
        forced_polarity="negative",
    )

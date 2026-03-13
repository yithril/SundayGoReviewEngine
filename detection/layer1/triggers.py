from __future__ import annotations

"""
detection/layer1/triggers.py
-----------------------------
Step 2 of the Layer 1 pipeline: apply threshold rules to a MoveFacts
instance and emit zero or more TriggerSignals.

All numeric thresholds live in game/constants/thresholds.py so they can
be tuned without touching this file.  Phase-aware threshold tables will
slot in here in v2 — the phase is already available on each MoveFacts.
"""

from game.constants.thresholds import (
    ADJ_ENEMY_MOYO_FORMATION_EXACT,
    ADJ_FRIENDLY_MOYO_FORMATION_MIN,
    BAD_DIRECTION_MIN_TOP3_PRIOR_SUM,
    DMOYO_INVASION_MIN,
    DMOYO_REDUCTION_MAX_EXCLUSIVE,
    DMOYO_REDUCTION_MIN,
    DMOYO_MOYO_FORMATION_MAX,
    GOOD_DIRECTION_MIN_TOP3_PRIOR_SUM,
    HOTSPOT_WINDOW,          # noqa: F401 — imported for callers who need it
    OWN_HERE_INVASION_MAX,
    OWN_HERE_MOYO_FORMATION_MIN,
    OWN_HERE_REDUCTION_MAX,
    POLICY_RANK_THRESHOLD,
    SCORE_SWING_THRESHOLD,
    TENUKI_DISTANCE,
    WINRATE_SWING_THRESHOLD,
)
from game.constants.phases import GamePhase
from detection.layer1.zones import is_opposite_or_adjacent_opposite
from detection.layer1.zones import is_preferred_or_adjacent_preferred
from detection.types import FirstLayerTriggerType, MoveFacts, TriggerSignal


def _signal(
    facts: MoveFacts,
    trigger_type: FirstLayerTriggerType,
) -> TriggerSignal:
    """Convenience constructor so each check is a one-liner."""
    return TriggerSignal(
        move_index=facts.move_index,
        trigger_type=trigger_type,
        player_color=facts.player_color,
        score_delta=facts.score_delta,
        winrate_delta=facts.winrate_delta,
        captured_groups=facts.captured_groups,
        max_captured_group_size=facts.max_captured_group_size,
    )


def _direction_phase_active(phase: GamePhase) -> bool:
    return phase in {
        GamePhase.OPENING_2,
        GamePhase.EARLY_MIDDLE,
        GamePhase.MID_MIDDLE,
        GamePhase.LATE_MIDDLE,
    }


def emit_triggers(
    facts: MoveFacts,
) -> list[TriggerSignal]:
    """Apply all threshold rules to *facts* and return the fired triggers.

    Parameters
    ----------
    facts                : MoveFacts for the current move
    Rule-specific inputs such as dmoyo, own_here, and move_sector_9 are
    precomputed in collect_facts().
    """
    signals: list[TriggerSignal] = []

    # -- score_swing ----------------------------------------------------------
    if abs(facts.score_delta) > SCORE_SWING_THRESHOLD:
        signals.append(_signal(facts, "score_swing"))

    # -- policy_mismatch ------------------------------------------------------
    if facts.policy_rank > POLICY_RANK_THRESHOLD:
        signals.append(_signal(facts, "policy_mismatch"))

    # -- capture --------------------------------------------------------------
    # Board state stub: fires when stones_captured > 0.
    # Currently always 0; will fire once board state is implemented.
    if facts.stones_captured > 0:
        signals.append(_signal(facts, "capture"))

    # -- atari_created --------------------------------------------------------
    # Board state stub: fires when a neighbouring enemy group has exactly 1
    # liberty (we just put them in atari).
    if facts.enemy_liberties_nearby == 1:
        signals.append(_signal(facts, "atari_created"))

    # -- self_atari_candidate -------------------------------------------------
    # Board state stub: fires when the moved group's own liberty count is 1.
    if facts.self_liberties == 1:
        signals.append(_signal(facts, "self_atari_candidate"))

    # -- cut_created ----------------------------------------------------------
    if facts.cut_groups:
        signals.append(_signal(facts, "cut_created"))

    # -- connection_attempt ---------------------------------------------------
    if facts.connected_groups:
        signals.append(_signal(facts, "connection_attempt"))

    # -- shape_candidate ------------------------------------------------------
    # A suspicious shape: policy disagrees AND the stone is near friendly stones.
    if facts.policy_rank > 3 and facts.adjacent_friendly >= 2:
        signals.append(_signal(facts, "shape_candidate"))

    # -- local_fight ----------------------------------------------------------
    # Adjacent enemy stones with a notable win-rate swing.
    if (
        facts.adjacent_enemy >= 2
        and abs(facts.winrate_delta) > WINRATE_SWING_THRESHOLD
    ):
        signals.append(_signal(facts, "local_fight"))

    # -- tenuki_after_forcing -------------------------------------------------
    # Played far away while a local urgent issue was unresolved.
    if facts.distance_to_prev > TENUKI_DISTANCE and facts.urgent_local_existed:
        signals.append(_signal(facts, "tenuki_after_forcing"))

    # -- invasion -------------------------------------------------------------
    # Rule: dmoyo >= 10, own_here <= 0.20, and move is on side/center.
    is_side = facts.move_sector_9 in {"top", "bottom", "left", "right"}
    is_center = facts.move_sector_9 == "center"
    if (
        _direction_phase_active(facts.game_phase)
        and
        facts.dmoyo >= DMOYO_INVASION_MIN
        and facts.own_here <= OWN_HERE_INVASION_MAX
        and (is_side or is_center)
    ):
        signals.append(_signal(facts, "invasion"))

    # -- reduction ------------------------------------------------------------
    # Rule: 5 <= dmoyo < 10, own_here <= 0.30, and move is on side/center.
    if (
        _direction_phase_active(facts.game_phase)
        and
        facts.dmoyo >= DMOYO_REDUCTION_MIN
        and facts.dmoyo < DMOYO_REDUCTION_MAX_EXCLUSIVE
        and facts.own_here <= OWN_HERE_REDUCTION_MAX
        and (is_side or is_center)
    ):
        signals.append(_signal(facts, "reduction"))

    # -- bad_direction_of_play ------------------------------------------------
    # Played in an opposite (or adjacent-opposite) zone compared to KataGo's
    # top-3 weighted preferred zone.
    if (
        _direction_phase_active(facts.game_phase)
        and
        facts.preferred_top3_prior_sum >= BAD_DIRECTION_MIN_TOP3_PRIOR_SUM
        and is_opposite_or_adjacent_opposite(
            facts.move_sector_9,
            facts.preferred_move_sector_9,
        )
    ):
        signals.append(_signal(facts, "bad_direction_of_play"))

    # -- good_direction_of_play -----------------------------------------------
    # Played in a preferred or adjacent-preferred zone compared to KataGo's
    # top-3 weighted preferred zone.
    if (
        _direction_phase_active(facts.game_phase)
        and
        facts.preferred_top3_prior_sum >= GOOD_DIRECTION_MIN_TOP3_PRIOR_SUM
        and is_preferred_or_adjacent_preferred(
            facts.move_sector_9,
            facts.preferred_move_sector_9,
        )
    ):
        signals.append(_signal(facts, "good_direction_of_play"))

    # -- weak_group_candidate -------------------------------------------------
    # Board state stub: own group has very few liberties and wasn't a capture.
    if facts.self_liberties <= 2 and facts.self_liberties > 0 and facts.stones_captured == 0:
        signals.append(_signal(facts, "weak_group_candidate"))

    # -- life_and_death_candidate ---------------------------------------------
    # Large swing AND a weak group detected — high-value investigation target.
    score_swing_fired       = abs(facts.score_delta) > SCORE_SWING_THRESHOLD
    weak_group_fired        = (
        facts.self_liberties <= 2
        and facts.self_liberties > 0
        and facts.stones_captured == 0
    )
    if score_swing_fired and weak_group_fired:
        signals.append(_signal(facts, "life_and_death_candidate"))

    # -- moyo_formation -------------------------------------------------------
    # Rule: dmoyo <= 3, own_here >= 0.30, adjacent friendly >= 1, adjacent
    # enemy == 0, and move is on side/center.
    if (
        _direction_phase_active(facts.game_phase)
        and
        facts.dmoyo <= DMOYO_MOYO_FORMATION_MAX
        and facts.own_here >= OWN_HERE_MOYO_FORMATION_MIN
        and facts.adjacent_friendly >= ADJ_FRIENDLY_MOYO_FORMATION_MIN
        and facts.adjacent_enemy == ADJ_ENEMY_MOYO_FORMATION_EXACT
        and (is_side or is_center)
    ):
        signals.append(_signal(facts, "moyo_formation"))

    return signals

from __future__ import annotations

# ---------------------------------------------------------------------------
# Layer 1 trigger thresholds
# All numeric constants live here so they can be tuned without touching
# detection logic.  Phase-aware overrides will go here too (v2).
# ---------------------------------------------------------------------------

# score_swing: fires when |score_delta| exceeds this many points
SCORE_SWING_THRESHOLD: float = 3.0

# policy_mismatch: fires when the played move's rank in KataGo's policy
# exceeds this (0 = best move, higher = further from top suggestion)
POLICY_RANK_THRESHOLD: int = 5

# tenuki_after_forcing: fires when the Chebyshev board distance from the
# previous move exceeds this AND an urgent local issue existed
TENUKI_DISTANCE: int = 8

# moyo_formed: ownership map thresholds
MOYO_OWNERSHIP_THRESHOLD: float = 0.55   # per-cell ownership floor (player perspective)
MOYO_MIN_CELLS: int = 24                 # minimum qualifying cells to count as a moyo
MOYO_GROWTH_THRESHOLD: int = 8           # re-fire if moyo grows by at least this many cells

# invasion / reduction / moyo_formation rule thresholds (Layer 1)
# These directional heuristics are applied only in late opening + middle game.
# dmoyo = current moyo_cell_count - previous move's moyo_cell_count
DMOYO_INVASION_MIN: int = 10
OWN_HERE_INVASION_MAX: float = 0.20
DMOYO_REDUCTION_MIN: int = 5
DMOYO_REDUCTION_MAX_EXCLUSIVE: int = 10
OWN_HERE_REDUCTION_MAX: float = 0.30
DMOYO_MOYO_FORMATION_MAX: int = 3
OWN_HERE_MOYO_FORMATION_MIN: float = 0.30
ADJ_FRIENDLY_MOYO_FORMATION_MIN: int = 1
ADJ_ENEMY_MOYO_FORMATION_EXACT: int = 0

# bad/good direction: require top-3 preferred zone mass to be meaningful
BAD_DIRECTION_MIN_TOP3_PRIOR_SUM: float = 0.35
GOOD_DIRECTION_MIN_TOP3_PRIOR_SUM: float = 0.35

# Directional event debounce in Layer 2 (one event per local window)
DIRECTION_EVENT_DEBOUNCE_WINDOW: int = 10

# hotspot merging: signals within this many moves of each other are merged
HOTSPOT_WINDOW: int = 6

# winrate swing considered "large" for local_fight detection
WINRATE_SWING_THRESHOLD: float = 0.05

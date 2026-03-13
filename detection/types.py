from __future__ import annotations

"""
detection/types.py
------------------
Single source of truth for all data types shared across the three detection
layers.  No layer imports types from a sibling layer; everything flows through
here.

Import rules:
  - game/constants/* may be imported freely by all modules.
  - detection/types.py may be imported by any detection sub-module.
  - Layer N must NOT import from layer M (N != M).
"""

from dataclasses import dataclass, field
from typing import Literal

from game.constants.phases import GamePhase
from game.constants.ranks import RankBand  # noqa: F401  (re-exported for convenience)
from game.constants.skills import GoSkillId, SKILL_DISPLAY_NAMES

# ---------------------------------------------------------------------------
# Shared primitives
# ---------------------------------------------------------------------------

Color = Literal["B", "W"]

# ---------------------------------------------------------------------------
# Layer 1: Candidate Detection types
# ---------------------------------------------------------------------------

OpeningZone = Literal["corner", "side", "center"]
MoveSector9 = Literal[
    "upper_left",
    "top",
    "upper_right",
    "left",
    "center",
    "right",
    "lower_left",
    "bottom",
    "lower_right",
]


@dataclass(frozen=True)
class CaptureGroupInfo:
    """Captured group metadata emitted by Layer 1 capture candidates."""
    group_id: int
    size: int
    zone: MoveSector9


@dataclass
class OpeningInfo:
    """A recognised standard opening pattern detected at move 5 or 7."""
    name: str        # "kobayashi" | "sanrensei" | "high_chinese" | "low_chinese" | "mini_chinese"
    orientation: str  # "bottom" | "top" | "right" | "bottom-right" | "top-right"


@dataclass
class FirstMoveInfo:
    """The reviewed player's first move and its board zone."""
    move: str           # e.g. "Q4"
    zone: OpeningZone   # "corner" | "side" | "center"


FirstLayerTriggerType = Literal[
    "score_swing",
    "policy_mismatch",
    "capture",
    "atari_created",
    "self_atari_candidate",
    "cut_created",
    "connection_attempt",
    "shape_candidate",
    "local_fight",
    "tenuki_after_forcing",
    "invasion",
    "reduction",
    "bad_direction_of_play",
    "good_direction_of_play",
    "weak_group_candidate",
    "life_and_death_candidate",
    "moyo_formation",
]


@dataclass
class MoveFacts:
    """All cheap per-move facts collected in Layer 1, Step 1.

    Fields are grouped by their data source:
      - KataGo responses    : always populated
      - Coordinate arithmetic: always populated
      - Ownership map       : always populated (prefix-sum derived)
      - Board state         : stubbed with 0 / False; see TODO comments
      - Carry-forward       : derived from prior TriggerSignals
    """
    move_index: int
    move: str                       # e.g. "D4"  ("pass" for pass moves)
    player_color: Color
    game_phase: GamePhase           # from game.constants.phases.get_phase()

    # -- KataGo-derived -------------------------------------------------------
    score_delta: float              # score change from player's perspective
    winrate_delta: float            # win-rate change from player's perspective
    policy_rank: int                # rank of played move in KataGo policy (0 = best)
    policy_prob: float              # KataGo prior probability for the played move
    best_pv_length: int             # len(moveInfos[0].pv); 0 if pv not in response
    preferred_top3_prior_sum: float # total prior mass across top-3 KataGo suggestions

    # -- Ownership map (prefix-sum, O(1) after one-time table build) ----------
    entered_influence: bool         # move landed inside opponent's ownership territory
    moyo_cell_count: int            # qualifying cells in player's moyo zone this move
    own_here: float                 # ownership at played point from current player's perspective [0,1]
    dmoyo: int                      # moyo delta vs previous move's moyo_cell_count

    # -- Coordinate arithmetic ------------------------------------------------
    distance_to_prev: float         # Chebyshev distance to the previous move
    move_sector_9: MoveSector9      # 9-sector board location bucket for this move
    preferred_move_sector_9: MoveSector9   # top-3 KataGo weighted preferred zone

    # -- Board state ----------------------------------------------------------
    stones_captured: int            # count of enemy stones removed by this move
    self_liberties: int             # liberty count of the moved group after play
    enemy_liberties_nearby: int     # min liberties of any adjacent enemy group (1 = atari)
    adjacent_friendly: int          # same-color stones directly adjacent (4 neighbors), pre-play
    adjacent_enemy: int             # opponent stones directly adjacent (4 neighbors), pre-play
    connected_groups: bool          # move joined two or more previously separate friendly groups
    cut_groups: bool                # move is adjacent to two or more separate enemy groups
    nearby_friendly: int            # same-color stones within Chebyshev-2 radius, pre-play
    played_group_id: int            # persistent group ID of the played stone's resulting group
    friendly_group_ids_adjacent_pre: tuple[int, ...]   # persistent IDs of adjacent friendly groups (pre-play)
    enemy_group_ids_adjacent_pre: tuple[int, ...]      # persistent IDs of adjacent enemy groups (pre-play)
    groups_created: tuple[int, ...]                    # group IDs created on this move
    groups_captured: tuple[int, ...]                   # group IDs captured on this move
    groups_merged_into: dict[int, tuple[int, ...]]     # target group ID -> merged source IDs
    played_group_liberties_post: int                   # liberties of played group after play
    adjacent_enemy_liberties_post: dict[int, int]      # adjacent enemy group ID -> liberties after play
    alive_group_liberties: dict[int, int]              # all alive group IDs -> liberty counts
    alive_group_zone_9: dict[int, MoveSector9]         # all alive group IDs -> 9-sector zone
    captured_groups: tuple[CaptureGroupInfo, ...]      # captured group details (id/size/zone)
    max_captured_group_size: int                       # max size among captured groups (0 if none)
    alive_group_ownership_mean: dict[int, float]       # group_id -> mean ownership (black perspective)

    # -- Carry-forward from previous signals ----------------------------------
    urgent_local_existed: bool      # a local trigger fired within the last 4 moves


@dataclass
class TriggerSignal:
    """A single fired Layer 1 trigger for one move."""
    move_index: int
    trigger_type: FirstLayerTriggerType
    player_color: Color
    score_delta: float
    winrate_delta: float
    captured_groups: tuple[CaptureGroupInfo, ...] = ()
    max_captured_group_size: int = 0


@dataclass
class HotspotCandidate:
    """A cluster of TriggerSignals in a local move window, ready for Layer 2."""
    center_move_index: int
    move_indices: list[int]
    trigger_types: list[FirstLayerTriggerType]
    max_winrate_delta: float
    max_score_delta: float
    captured_groups: tuple[CaptureGroupInfo, ...] = ()
    max_captured_group_size: int = 0

# ---------------------------------------------------------------------------
# Layer 2: Event Classification types
# ---------------------------------------------------------------------------

GameEventType = Literal[
    "capture_sequence",
    "cut_defense_success",
    "shape_strength",
    "shape_liability",
    "liberty_tactic_success",
    "liberty_tactic_failure",
    "group_death",
    "group_saved",
    "invasion_settled",
    "ko_fight",
    "semeai",
    "large_territory_swing",
    "opening_framework",
    "tenuki_punished",
    "weak_group_crisis",
    "moyo_established",
    "good_direction_shift",
    "bad_direction_shift",
]


@dataclass
class GameEvent:
    """A named, classified game event produced by Layer 2.

    Spans one or more moves (move_start..move_end) and is anchored to the
    single most significant move (center_move_index).  Carries the source
    HotspotCandidates so Layer 3 can still access raw trigger context.
    """
    event_type: GameEventType
    move_start: int
    move_end: int
    center_move_index: int
    hotspots: list[HotspotCandidate]
    player_color: Color
    phase: GamePhase                # phase at center_move_index
    description_hint: str           # human-readable label for debugging / L3 prompt seed
    score_swing: float              # net score change across the event span
    winrate_swing: float            # net winrate change across the event span
    score_swing_abs: float          # abs(score_swing), precomputed for ranking
    event_polarity: Literal["positive", "negative", "neutral"]

# ---------------------------------------------------------------------------
# Layer 3: Narrative Engine types
# ---------------------------------------------------------------------------


@dataclass
class SkillMention:
    """A Go skill observed (or notably absent) in this game."""
    skill_id: GoSkillId             # must be a canonical GoSkillId from game/constants/skills.py
    points: int                     # 0–10


@dataclass
class KeyMomentOutput:
    """A single coaching observation linked to a board position."""
    explanation: str
    move_number: int | None         # 1-based; None for general observations


@dataclass
class NarrativeOutput:
    """The complete narrative payload returned by Layer 3 and consumed by
    review/builder.py.  Replaces the five separate stub function calls."""
    story: str
    skills_used: list[SkillMention] = field(default_factory=list)
    did_well: list[KeyMomentOutput] = field(default_factory=list)
    needs_improvement: list[KeyMomentOutput] = field(default_factory=list)
    match_highlights: list[KeyMomentOutput] = field(default_factory=list)
    opening_info: OpeningInfo | None = None
    first_move_info: FirstMoveInfo | None = None

    def to_report_fields(self) -> dict:
        """Serialize to the report dict shape expected by the frontend.

        This is the single source of truth for the NarrativeOutput wire
        format.  Field renames (e.g. skill_id → "name") and any future
        additions live here; builder.py never inspects the inner dataclasses.
        """
        result: dict = {
            "story": self.story,
            "skills_used": [
                {"name": SKILL_DISPLAY_NAMES[s.skill_id], "points": s.points}
                for s in self.skills_used
            ],
            "did_well": [
                {"explanation": m.explanation, "move_number": m.move_number}
                for m in self.did_well
            ],
            "needs_improvement": [
                {"explanation": m.explanation, "move_number": m.move_number}
                for m in self.needs_improvement
            ],
            "match_highlights": [
                {"explanation": m.explanation, "move_number": m.move_number}
                for m in self.match_highlights
            ],
        }
        if self.opening_info is not None:
            result["opening"] = {
                "name": self.opening_info.name,
                "orientation": self.opening_info.orientation,
            }
        if self.first_move_info is not None:
            result["first_move"] = {
                "move": self.first_move_info.move,
                "zone": self.first_move_info.zone,
            }
        return result

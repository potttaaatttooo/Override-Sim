"""Data model for M3 observation records (Revision 2.1, docs/plans/m3-observation-plan.md).

Frozen dataclasses mirror the field-by-field reference in
docs/design/07-observation-schema.md. As in `vexu_sim.sources`, closed vocabularies are
plain `frozenset[str]` constants rather than `Enum` classes -- these are data-layer
records parsed from YAML/CSV, not domain concepts consumed by pure scoring logic (that
style is `vexu_sim.model`'s, for MatchState). No validation lives here; `loader.py`
and `from_csv.py` are the only places that construct these from untrusted input and
enforce the REQ / REQ-IF / enum rules described in the schema doc.

`UNKNOWN = "unknown"` is the sentinel for "a required field whose real value the video
does not show" -- distinct from `None`, which means "not applicable to this record"
(the REQ-IF condition does not hold). See docs/design/07-observation-schema.md, "REQ vs
unknown vs null."
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

UNKNOWN = "unknown"

# --- Closed vocabularies ---------------------------------------------------------

PERIODS = frozenset({"autonomous", "driver"})
CONFIDENCE_LEVELS = frozenset({"certain", "probable", "uncertain"})

VIDEO_QUALITIES = frozenset({"good", "usable", "poor"})
CAMERA_TYPES = frozenset({"fixed_full_field", "broadcast_switched", "handheld", "mixed"})
SIZE_CLASSES = frozenset({"unknown_v5rc", "vexu_24", "vexu_15"})

# match.yaml metadata vocabularies (docs/plans/m3-observation-plan.md §C.1, §L.1).
ALLIANCES = frozenset({"red", "blue"})
AUTONOMOUS_BONUS_TO_VALUES = frozenset({"red", "blue", "tie", UNKNOWN})
# §L.1's ten selection_stratum values (strata 1-3 are M3B; 4-10 are M3C).
SELECTION_STRATA = frozenset(
    {"baseline_clean", "typical_broadcast", "poor_video", "high_throughput",
     "heavy_defense", "loader_heavy", "toggle_contested", "strong_autonomous",
     "failure_rich", "late_season"}
)
# LoaderVisit.objects_types list items -- unlike most object-type fields, no
# "unknown" here: an entry only appears in the list once the labeler is sure
# enough of the type to log it in the first place (§C.12, OPT field).
OBJECT_TYPES = frozenset({"pin", "cup"})

SNAPSHOT_CONTEXTS = frozenset({"autonomous_end", "match_end"})
SNAPSHOT_QUALITIES = frozenset({"good", "partial", "poor"})
GOAL_CONFIDENCE = CONFIDENCE_LEVELS

STACK_OBJECT_TYPES = frozenset({"pin", "cup", UNKNOWN})
CUP_FACES = frozenset({"opaque", "transparent", UNKNOWN})
NESTED_HALVES = frozenset({"a", "b", UNKNOWN})
PIN_COLORS = frozenset({"red", "blue", "yellow", UNKNOWN})
TOGGLE_ORIENTATIONS = frozenset({"red", "blue", "yellow", UNKNOWN})

# Only the four true Action types -- LoaderVisit is deliberately NOT here
# (Revision 2.1, correction A; see docs/plans/m3-observation-plan.md).
ACTION_TYPES = frozenset({"acquire", "place", "descore", "toggle"})

OUTCOMES = frozenset({"success", "fail", "abandoned", UNKNOWN})
FAILURE_MODES = frozenset(
    {"object_not_acquired", "dropped", "missed_target", "knocked_target_stack", "blocked",
     "object_stuck", "robot_incident", UNKNOWN}
)
CONTESTED_VALUES = frozenset(
    {"none", "opponent_contact", "opponent_block", "congestion_opponent",
     "congestion_partner", "field_element", UNKNOWN}
)
# GapClass -- six values including no_next_action (Revision 2.1, correction C).
GAP_CLASSES = frozenset({"transit", "mixed", "contested", "not_observed", "none", "no_next_action"})

ACQUIRE_SOURCES = frozenset({"floor", "loader", "goal_stack", "opponent_robot", UNKNOWN})
ACQUIRE_OBJECTS = frozenset({"pin", "cup", "pin_and_cup", UNKNOWN})
PLACE_DESCORE_OBJECTS = frozenset({"pin", "cup", UNKNOWN})
DESCORE_METHODS = frozenset({"extract", "topple", "obscure", UNKNOWN})
TOGGLE_METHODS = frozenset({"stopped_contact", "drive_by", UNKNOWN})

INCIDENT_TYPES = frozenset(
    {"tipped", "near_tip", "immobilized", "mechanism_stopped", "object_stuck",
     "disconnected", UNKNOWN}
)
RESOLUTIONS = frozenset({"self_recovered", "freed_by_contact", "assisted", "unresolved", UNKNOWN})

INTERACTION_TYPES = frozenset(
    {"sustained_contact", "path_denial", "immobilization", "mutual_congestion", UNKNOWN}
)

CHANGE_TYPES = frozenset(
    {"stack_toppled", "object_fell_from_stack", "object_added_unattributed",
     "object_displaced_from_goal", "toggle_changed", "object_dropped_in_transit",
     "object_taken_from_robot", UNKNOWN}
)
GOAL_AFFECTING_CHANGES = frozenset(
    {"stack_toppled", "object_fell_from_stack", "object_added_unattributed",
     "object_displaced_from_goal"}
)
TOGGLE_AFFECTING_CHANGES = frozenset({"toggle_changed"})
POSSESSION_AFFECTING_CHANGES = frozenset({"object_dropped_in_transit", "object_taken_from_robot"})

Number = Union[int, float]

# --- match.yaml --------------------------------------------------------------------


@dataclass(frozen=True)
class VideoMetadata:
    url: str
    retrieved: str
    quality: str
    camera: str
    period_offsets: dict[str, float]
    sync_check: dict[str, Any]
    timing_precision_s: float


@dataclass(frozen=True)
class RobotEntry:
    robot_ref: str
    alliance: str
    team: str
    size_class: str
    visual_key: str
    cycle_labeled: bool


@dataclass(frozen=True)
class OfficialResult:
    red_total: int
    blue_total: int
    autonomous_bonus_to: str
    awp: dict[str, bool]
    violations_autonomous: Union[str, list[str]]
    source_url: str
    retrieved: str


@dataclass(frozen=True)
class UnlabeledWindow:
    period: str
    t_start: float
    t_end: float
    reason: str


@dataclass(frozen=True)
class Coverage:
    cycle_labeled_alliance: str
    fully_labeled: bool
    unlabeled_windows: tuple[UnlabeledWindow, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class LabelingMeta:
    labeler: str
    label_date: str
    pass_id: int
    selection_stratum: str
    minutes_spent: int
    source_csv_sha256: Optional[str] = None


@dataclass(frozen=True)
class MatchObservation:
    schema_version: str
    match_key: str
    program: str
    event_name: str
    event_code: str
    match_id: str
    match_type: str
    date: str
    manual_version: str
    video: VideoMetadata
    roster: tuple[RobotEntry, ...]
    official_result: OfficialResult
    coverage: Coverage
    labeling: LabelingMeta


# --- snapshots.yaml ------------------------------------------------------------------


@dataclass(frozen=True)
class StackItem:
    object: str
    colors: Optional[list[str]] = None
    down_face: Optional[str] = None
    nested_half: Optional[str] = None


@dataclass(frozen=True)
class GoalSnapshot:
    stack: tuple[StackItem, ...]
    confidence: str


@dataclass(frozen=True)
class ToggleSnapshot:
    orientation: str
    seated: Union[bool, str]
    contacted_by_robot: Union[bool, str]
    confidence: str


@dataclass(frozen=True)
class RobotSnapshot:
    in_midfield: Union[bool, str]
    contacting_perimeter: Optional[Union[bool, str]]
    confidence: str = "certain"


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    context: str
    video_t: float
    quality: str
    goals: dict[str, GoalSnapshot]
    toggles: dict[str, ToggleSnapshot]
    robots: dict[str, RobotSnapshot]


# --- events.yaml: layer-2/3 records -------------------------------------------------


@dataclass(frozen=True)
class Action:
    """The four true Action types (`acquire`, `place`, `descore`, `toggle`).

    One flat dataclass rather than a subclass per type: the per-type fields
    (`source`/`object`/... for `acquire`, `target_goal_ref`/... for `place`, etc.) are
    REQ-IF `action_type`, exactly like every other conditional field in this schema,
    and a single shape keeps `loader.py`'s REQ-IF machinery uniform across all of
    them. `docs/design/07-observation-schema.md` documents which fields apply to
    which `action_type`.
    """

    record_type: str  # always "action"
    id: str
    action_type: str
    robot_ref: str
    period: str
    video_t_start: float
    video_t_end: Union[Number, str]  # numeric or "unknown" -- NEVER None (Revision 2.1, §E.3)
    region: str
    outcome: str
    contested: str
    retry_of: Optional[str]
    confidence: str
    gap_after: Optional[str] = None  # REQ-IF robot is cycle_labeled
    failure_mode: Optional[str] = None  # REQ-IF outcome != success
    contested_robot_ref: Optional[str] = None
    possession_id: Optional[str] = None  # REQ-IF action_type in {acquire, place}
    notes: Optional[str] = None
    # acquire
    source: Optional[str] = None
    object: Optional[str] = None
    object_colors: Optional[list[str]] = None
    loader_visit_id: Optional[str] = None
    # place / descore
    target_goal_ref: Optional[str] = None
    stack_height_before: Optional[Union[int, str]] = None
    stack_height_after: Optional[Union[int, str]] = None
    cup_down_face: Optional[str] = None
    destabilized_stack: Optional[Union[bool, str]] = None  # place only
    video_t_release: Optional[Union[Number, str]] = None  # place only, OPT
    # descore
    method: Optional[str] = None  # descore: extract/topple/obscure ; toggle: stopped_contact/drive_by
    objects_removed: Optional[Union[int, str]] = None  # REQ-IF method in {extract, topple}
    # toggle
    toggle_ref: Optional[str] = None
    state_before: Optional[str] = None
    state_after: Optional[str] = None
    seated_after: Optional[Union[bool, str]] = None


@dataclass(frozen=True)
class LoaderVisit:
    """A robot-activity interval/container, NOT an Action (Revision 2.1, correction A).

    No `outcome`, `failure_mode`, `retry_of`, or `gap_after` -- see
    docs/plans/m3-observation-plan.md §C.12.
    """

    record_type: str  # always "loader_visit"
    id: str
    robot_ref: str
    period: str
    video_t_enter: float
    video_t_exit: Optional[Union[Number, str]]  # null = still inside at period end
    loader_ref: str
    objects_acquired: Union[int, str]
    failed_grabs: Union[int, str]
    departs_possession_id: Optional[str]  # None = left empty-handed; may be "unknown"
    contested: str
    confidence: str
    objects_types: Optional[list[str]] = None
    video_t_first_object_available: Optional[Union[Number, str]] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class MidfieldOccupancy:
    record_type: str  # always "midfield_occupancy"
    id: str
    robot_ref: str
    period: str
    video_t_enter: Union[Number, str]
    video_t_exit: Optional[Union[Number, str]]  # null = still inside at period end
    contested_during: Union[bool, str]
    confidence: str
    exit_coincident_with_contact: Optional[Union[bool, str]] = None  # REQ-IF video_t_exit numeric
    notes: Optional[str] = None


@dataclass(frozen=True)
class Incident:
    record_type: str  # always "incident"
    id: str
    robot_ref: str
    period: str
    video_t_start: Union[Number, str]
    video_t_end: Optional[Union[Number, str]]  # null = unresolved at match end
    incident_type: str
    resolution: str
    confidence: str
    notes: Optional[str] = None


@dataclass(frozen=True)
class Interaction:
    """OPTIONAL through M3B (docs/plans/m3-observation-plan.md §C.11, §R.3)."""

    record_type: str  # always "interaction"
    id: str
    actor_robot_ref: str
    subject_robot_ref: str
    video_t_start: Union[Number, str]
    video_t_end: Union[Number, str]
    period: str
    interaction_type: str
    confidence: str
    subject_region: Optional[str] = None
    notes: Optional[str] = None


@dataclass(frozen=True)
class StateChange:
    """The un-attempted-change channel -- the schema's one genuinely instantaneous
    record type: a single `video_t`, no interval (§C.4)."""

    record_type: str  # always "state_change"
    id: str
    period: str
    video_t: float
    change: str
    attributed_to: Optional[str]  # robot_ref, or None = no robot involved
    confidence: str
    target_goal_ref: Optional[str] = None
    stack_height_before: Optional[Union[int, str]] = None
    stack_height_after: Optional[Union[int, str]] = None
    toggle_ref: Optional[str] = None
    state_after: Optional[str] = None
    seated_after: Optional[Union[bool, str]] = None
    possession_id: Optional[str] = None
    object: Optional[str] = None
    caused_by_action: Optional[str] = None
    notes: Optional[str] = None


EventRecord = Union[Action, LoaderVisit, MidfieldOccupancy, Incident, Interaction, StateChange]

RECORD_TYPE_CLASSES: dict[str, type] = {
    "action": Action,
    "loader_visit": LoaderVisit,
    "midfield_occupancy": MidfieldOccupancy,
    "incident": Incident,
    "interaction": Interaction,
    "state_change": StateChange,
}


@dataclass(frozen=True)
class LoadedMatch:
    """One fully loaded and validated match: metadata, both snapshots, and every
    layer-2/3 event record. Returned by `loader.load_match_observation`."""

    match: MatchObservation
    snapshots: tuple[Snapshot, ...]
    events: tuple[EventRecord, ...]
    warnings: tuple[str, ...] = field(default_factory=tuple)

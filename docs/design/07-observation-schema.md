# Observation schema (M3A)

Normative technical reference for `src/vexu_sim/observations/`. Implements the
approved M3 design in `docs/plans/m3-observation-plan.md` (Revision 2.1) -- that
document remains the planning rationale and handoff; this document is the concise
reference a future labeler or a future milestone (M4+) reads to know exactly what a
field means, whether it is required, and how it validates. If this document and the
plan ever appear to disagree, the plan's Revision 2.1 corrections table (§ "Corrections
applied in Revision 2.1") is the tiebreaker, and the disagreement is a bug in this
document to fix, not a reason to re-derive the schema.

M3A ships this schema and its tooling with **zero real labeled matches**. Manual
video review and labeling begin in M3B.

## Scope

`src/vexu_sim/observations/` reads three stable public APIs and modifies nothing:
`vexu_sim.sources.validate_empirical_program` (program legality),
`vexu_sim.rules.RuleBundle.period_seconds()` (period lengths, never hardcoded), and
canonical Goal/Toggle/Quadrant ids via `observations/refs.py`, which itself reads
`vexu_sim.field_setup`. `refs.py` is also the one place the genuinely **M3-local**
labeling vocabulary is declared -- Loader ids and the four Load-Zone region ids -- since
no rule datum names them.

This package never compiles a snapshot into a `MatchState` and never calls the
scorer. `<SC2>`/`<SC3>` Placed/Scored adjudication is explicitly **not** a labeling
task -- see §O below and `docs/plans/m3-observation-plan.md` §H.3. That compiler is
M4's job.

## REQ / REQ-IF / OPT / DER, and `unknown` vs `null`

- **`REQ`** -- the key must be present in the record.
- **`REQ-IF <condition>`** -- the key must be present exactly when the stated
  condition holds, and **must be absent** when it does not. The validator
  (`loader.py`) checks both directions: a present-when-forbidden field is as much an
  error as a missing-when-required one.
- **`OPT`** -- may be present or absent freely.
- **`DER`** -- derived; never stored in an observation record. Listed here so a
  future M5 consumer knows the quantity exists and so this schema knows not to
  duplicate it.
- **`REQ` does not mean "known."** `unknown` (the literal string `"unknown"`,
  `models.UNKNOWN`) is a legal value for any REQ field unless stated otherwise --
  it means "the video does not show this." `null`/absent means "not applicable to
  this record" -- a REQ-IF condition that does not hold. These are different facts,
  and the loader enforces the distinction: a REQ field may never be `null` when its
  condition holds, and a field marked "REQ-IF absent otherwise" must genuinely be
  absent (not `unknown`) when the condition does not hold.
- **`REQ` also means the *key* must be present, even when `null` is itself the
  legal value.** A handful of fields are REQ but legitimately `null`:
  `LoaderVisit.video_t_exit`/`departs_possession_id`, `MidfieldOccupancy.
  video_t_exit`, `Incident.video_t_end`, `Action.retry_of`, and
  `StateChange.attributed_to`, plus two REQ list/collection fields where an empty
  collection is itself a real observed fact rather than an omission --
  `Coverage.unlabeled_windows` and `GoalSnapshot.stack`. For every one of these, the
  loader (`loader.py`'s parsers) distinguishes "the key is present with value
  `null`/`[]`" from "the key is absent entirely" and rejects the latter as a
  structural authoring error -- an omitted key is never silently treated as if the
  author had written the legal `null`/empty value. `events.source.csv` cannot spell
  "explicit null" differently from "blank cell," so for exactly these
  (`record_type`, field) pairs a blank CSV cell is interpreted as the legal null
  value rather than dropped as not-applicable -- see `08-labeling-protocol.md`'s
  "Cell conventions."

## Record families

Eight record types across three files per labeled match directory
(`data/observations/<program>/<match_key>/`):

| # | Record | File | Cardinality | Python type |
|---|---|---|---|---|
| 1 | Match metadata | `match.yaml` | 1 | `MatchObservation` |
| 2 | Snapshot | `snapshots.yaml` | 2 | `Snapshot` |
| 3 | Action (`acquire`\|`place`\|`descore`\|`toggle`) | `events.yaml` | many | `Action` |
| 4 | LoaderVisit | `events.yaml` | 0+ | `LoaderVisit` |
| 5 | MidfieldOccupancy | `events.yaml` | 0+ | `MidfieldOccupancy` |
| 6 | Incident | `events.yaml` | 0+ | `Incident` |
| 7 | Interaction (OPTIONAL through M3B) | `events.yaml` | 0+ | `Interaction` |
| 8 | StateChange | `events.yaml` | 0+ | `StateChange` |

**`LoaderVisit` is not an Action.** Only `acquire`, `place`, `descore`, and `toggle`
are `action_type` values. A `loader_visit` is a robot-activity interval/container --
time spent inside a Load Zone -- with no `outcome`, `failure_mode`, `retry_of`, or
`gap_after`: a zero-object visit (`objects_acquired: 0`) is data, not a failed
action. An `acquire{source: loader}` may reference its containing visit via
`loader_visit_id`; there is no reverse `within_action` link.

## Temporal semantics

All timestamps are **video seconds** (float, 0.1s resolution); `match.video.
period_offsets` maps each period's `t=0`. Match-clock time and `is_endgame` are
**DER**, computed from `RuleBundle.period_seconds()` -- never a hardcoded 15/105/
30/90/10.

**Action endpoints (Revision 2.1, the load-bearing rule of this schema):**
`video_t_start` is always a numeric float. `video_t_end` is **numeric or the literal
string `"unknown"` -- NEVER `null`.** All four Action types are interval
observations with two real boundaries (see "Action ontology" below); none is
genuinely instantaneous. `duration` is **DER**, computed only when both endpoints
are numeric -- an `unknown` end leaves duration undefined, not zero. When both
endpoints are numeric, `video_t_end` must be strictly greater than `video_t_start`
(equality is rejected as indistinguishable from an unmodeled zero-length
measurement).

**`null`/open-ended semantics are reserved for record types where "still ongoing"
is itself the observed fact**, not a labeling gap: `LoaderVisit.video_t_exit`,
`MidfieldOccupancy.video_t_exit`, and `Incident.video_t_end` may be `null`, meaning
"still open when the Period/Match ended." None of these three record types is an
Action.

**`StateChange`** is the schema's one genuinely instantaneous record: a single
`video_t`, no interval at all.

**Overlapping actions** are permitted and not required to be annotated (a robot may
intake a Cup while driving to place a Pin). The validator reports overlaps as a
**warning** in the QC surface, never an error; an OPT `concurrent: true` hint may be
set but is not enforced.

## Spatial abstraction: Region

Nine regions plus `unknown`, read from `observations.refs.region_vocabulary()`:
`quadrant_<id>` for each of the four canonical Quadrant ids `field_setup` builds,
`midfield`, and four **M3-local** Load Zone regions (`load_zone_red_1`,
`load_zone_red_2`, `load_zone_blue_1`, `load_zone_blue_2` -- declared in `refs.py`
since no rule datum names individual Load Zones). No coordinates, no distances; an
Action's sole spatial fact is its `region` plus whichever object it references
(`target_goal_ref`, `toggle_ref`, `loader_ref`).

## `gap_after` (`GapClass`)

Six values: `transit`, `mixed`, `contested`, `not_observed`, `none`,
`no_next_action`. REQ-IF the acting robot's `roster[].cycle_labeled` is true;
otherwise the field must be absent. "Next Action" is defined deterministically as
the next Action **for the same robot, in the same period**, ordered by
`video_t_start` -- a `loader_visit` is never itself a "next Action" for this
purpose, since it is not an Action. `no_next_action` means no later Action exists
for that robot in that period. Two pieces of machinery cooperate:
`loader.canonicalize_no_next_action` **recomputes and overwrites** the
chronologically-last cycle-labeled Action of each (robot, period) group to
`"no_next_action"` -- run automatically by the CSV import path
(`from_csv.import_events_csv`/`import_match_from_csv`) before validation, so a
labeler never has to know mid-session which Action will turn out to be terminal,
and every non-terminal Action's `gap_after` is left untouched. `loader.
_validate_no_next_action` then **validates** (never silently corrects) that every
terminal Action says `"no_next_action"` and no non-terminal one does -- this is
what a hand-authored `events.yaml` (already canonical, produced by the importer) is
checked against on every load via `load_match_observation`, and what rejects a
non-terminal Action mislabeled `"no_next_action"`. **Only `gap_after == "transit"`
intervals are eligible as future M5 travel-time samples.**

## Possession episodes

**No persistent global Pin/Cup identity.** `possession_id` (`"<robot_ref>#<n>"`,
monotonically increasing per robot) names a contiguous **possession episode**, not
an object. `<SG6>`'s possession limit (≤1 Pin + ≤1 Cup) is what makes this work:
within one open episode, `object: pin` / `object: cup` is sufficient to identify
which held object a `place` or a possession-affecting `StateChange` refers to.

- **Opening:** an `acquire` while the robot holds nothing opens a fresh
  `possession_id`.
- **Extending:** an `acquire` of the *other* object type while one is already held
  reuses the currently open id. `acquire{object: pin_and_cup}` opens an episode
  already containing both.
- **Multiple placements from one episode:** two `place` records share the
  `possession_id` and differ in `object`.
- **Closing:** when the robot's held set becomes empty -- via `place`(s), or a
  possession-affecting `StateChange` (`object_dropped_in_transit`,
  `object_taken_from_robot`). An episode still open at the end of the labeled
  record stream is legal (the robot ended holding something) and is reported, not
  rejected.
- **`descore` carries no `possession_id`.** If a robot ends up holding a removed
  object, that is a separate `acquire{source: goal_stack}` opening its own episode.
- **`LoaderVisit` is a container, not a possession.** It links to the episode the
  robot *departs* the Load Zone holding via `departs_possession_id`; it has no
  `possession_id` field of its own.

**Validation:** episodes are tracked per robot, chronologically, across the whole
match (not just within one period). Referencing a `possession_id` other than the
robot's currently-open one (when one is open, and the reference is not opening a
fresh episode) is an **error** -- episodes must be per-robot and non-interleaved.
Two specific cases are **warnings**, not errors, because they may be a genuine
`<SG6>` violation the labeler correctly observed rather than a labeling mistake:
acquiring an object type already held in the open episode, and a `place` whose
`object` is not present in the currently open episode's held set.

**Id integrity**, enforced whenever an episode opens (an `acquire` while the robot
holds nothing): the id must match `<robot_ref>#<n>` exactly, `n` must be a positive
integer, `robot_ref` must equal the acting robot (an id cannot be opened for a
*different* robot), and `n` must be strictly greater than every suffix that robot
has ever used before -- episode numbers move monotonically forward and a closed
episode's id can never be reused for a new one. `LoaderVisit.departs_possession_id`,
when it names a concrete id (not `null`/`unknown`), is checked the same way: the
robot-id prefix must match the visit's own `robot_ref`, and the id must actually
have been opened by that robot at some point in the match.

`possession_contents`, `possession_duration`, and `cycle_time` are **DER**, never
stored.

## Confidence and `unknown`

Three per-record levels (`certain`, `probable`, `uncertain`) -- see the plan §C.8
for the operational definitions M5 uses to decide inclusion in a default fit.
`confidence` is orthogonal to `unknown`: a `certain` record may still contain
`unknown` field values.

## Field reference by record type

### `MatchObservation` (`match.yaml`)

| Field | Type | Req |
|---|---|---|
| `schema_version` | str | REQ |
| `match_key` | str | REQ |
| `program` | `v5rc \| vexu` | REQ (never `both` -- `validate_empirical_program`) |
| `event_name`, `event_code`, `match_id`, `match_type`, `date` | str | REQ |
| `manual_version` | str | REQ |
| `video` | `VideoMetadata` | REQ |
| `roster` | tuple[`RobotEntry`, ...] | REQ |
| `official_result` | `OfficialResult` | REQ |
| `coverage` | `Coverage` | REQ |
| `labeling` | `LabelingMeta` | REQ |

`VideoMetadata`: `url`, `retrieved`, `quality` (`good|usable|poor`), `camera`
(`fixed_full_field|broadcast_switched|handheld|mixed`), `period_offsets`
(`{period: video_t of t=0}`), `sync_check`, `timing_precision_s` -- all REQ.

`RobotEntry`: `robot_ref`, `alliance`, `team`, `size_class`, `visual_key`,
`cycle_labeled` -- all REQ. **`size_class ∈ {unknown_v5rc, vexu_24, vexu_15}`, and a
`v5rc` record's robots must all be `unknown_v5rc`** -- inventing a VEX U size class
on V5RC data is the single most dangerous transfer error this schema can prevent
(`docs/plans/m3-observation-plan.md` §J.1). A `vexu` record's robots must be
`vexu_24` or `vexu_15` (not `unknown_v5rc`).

`OfficialResult`: `red_total`, `blue_total`, `autonomous_bonus_to`, `awp`,
`violations_autonomous`, `source_url`, `retrieved` -- all REQ, transcribed from the
published record, never judged from video.

`Coverage`: `cycle_labeled_alliance`, `fully_labeled`, `unlabeled_windows` (list,
may be `[]`) -- all REQ.

`LabelingMeta`: `labeler`, `label_date`, `pass_id`, `selection_stratum`,
`minutes_spent` REQ; `source_csv_sha256` REQ-IF events were imported via the CSV
pipeline, else `null`.

### `Snapshot` (`snapshots.yaml`, exactly one `autonomous_end` + one `match_end`)

`snapshot_id`, `context` (`autonomous_end|match_end`), `video_t`, `quality`
(`good|partial|poor`) -- all REQ. `goals`, `toggles`, `robots` are REQ maps that
must contain **every** canonical Goal id, canonical Toggle id, and rostered
`robot_ref` respectively.

`GoalSnapshot.stack` is an ordered, bottom-up list of `StackItem` -- **physical**
stacking as seen, not `<SC2>` Placed adjudication (deliberately not a labeling
task; see §O). `StackItem.object` (`pin|cup|unknown`) REQ; `colors` REQ-IF
`object == pin`; `down_face` (`opaque|transparent|unknown`) REQ-IF `object == cup`;
`nested_half` (`a|b|unknown`) OPT.

`ToggleSnapshot`: `orientation` (`red|blue|yellow|unknown`), `seated` (bool or
`"unknown"`), `contacted_by_robot` (bool or `"unknown"`), `confidence` -- all REQ.

`RobotSnapshot`: `in_midfield` (bool or `"unknown"`) REQ; `contacting_perimeter`
REQ-IF `context == autonomous_end`, OPT (commonly absent) at `match_end`.

**Deliberately excluded:** loose floor Pins/Cups -- the scorer never reads them.

### `Action` (`events.yaml`, `record_type: action`)

Common core (all four `action_type`s): `id`, `action_type`, `robot_ref`, `period`,
`video_t_start`, `video_t_end`, `region`, `outcome`, `contested`, `retry_of`,
`confidence` -- REQ. `gap_after` REQ-IF `cycle_labeled`. `failure_mode` REQ-IF
`outcome != success`. `contested_robot_ref` OPT. `possession_id` REQ-IF
`action_type ∈ {acquire, place}`, else must be absent. `notes` OPT.

**`acquire`**: `source` (`floor|loader|goal_stack|opponent_robot|unknown`) REQ;
`object` (`pin|cup|pin_and_cup|unknown`) REQ; `object_colors` OPT;
`loader_visit_id` OPT, must resolve to a `LoaderVisit` id (never an Action id) when
present.

**`place`**: `target_goal_ref` (a canonical Goal id) REQ; `object`
(`pin|cup|unknown`) REQ; `stack_height_before`/`stack_height_after` (int or
`"unknown"`) REQ, **physical** counts; `cup_down_face` REQ-IF `object == cup`;
`destabilized_stack` (bool or `"unknown"`) REQ; `video_t_release` OPT.

**`descore`**: `target_goal_ref` REQ; `method`
(`extract|topple|obscure|unknown`) REQ; `objects_removed` REQ-IF
`method ∈ {extract, topple}`; `stack_height_before`/`stack_height_after` REQ;
`cup_down_face` REQ-IF `method == obscure`. **No `object` field** -- a descore
never records what type it removed. `descore{method: obscure}` **increases**
physical depth (a Cup placed opaque-down over an opposing scored half) -- the
reconciliation ledger uses each record's own observed `after - before`, never an
assumed sign, precisely so this case is handled without a special case.

**`toggle`**: `toggle_ref` (a canonical Toggle id) REQ; `state_before`/
`state_after` (`red|blue|yellow|unknown`) REQ -- `state_after` is read only after
the robot separates and the Toggle settles (`<SC4>`); `seated_after` REQ; `method`
(`stopped_contact|drive_by|unknown`) REQ.

### `LoaderVisit` (`record_type: loader_visit`)

`id`, `robot_ref`, `period`, `video_t_enter` REQ (numeric). `video_t_exit` REQ,
numeric, `"unknown"`, or `null` (still inside at period end). `loader_ref` REQ, one
of the four **M3-local** Loader ids. `objects_acquired`, `failed_grabs` REQ
(int or `"unknown"`; `0` is legal and meaningful). `objects_types` OPT.
`departs_possession_id` REQ (a possession id, `null` if left empty-handed, or
`"unknown"`). `video_t_first_object_available` OPT. `contested` REQ (same enum as
Action's). `confidence` REQ. **No `outcome`, `failure_mode`, `retry_of`,
`gap_after`, `possession_id`, or `region`** -- none has observable meaning for a
container interval.

### `MidfieldOccupancy` (`record_type: midfield_occupancy`)

`id`, `robot_ref`, `period`, `video_t_enter` REQ. `video_t_exit` REQ (numeric,
`"unknown"`, or `null` -- still inside at period end). `exit_coincident_with_contact`
REQ-IF `video_t_exit` is not `null`, else must be absent. `contested_during` REQ.
`confidence` REQ. **No `outcome`, `failure_mode`, `region`, `possession_id`, or
`gap_after`.**

### `Incident` (`record_type: incident`)

`id`, `robot_ref`, `period`, `video_t_start` REQ. `video_t_end` REQ (numeric,
`"unknown"`, or `null` -- unresolved at match end). `incident_type`
(`tipped|near_tip|immobilized|mechanism_stopped|object_stuck|disconnected|unknown`)
REQ -- observable outcomes, never diagnosed causes; never "pinned" (collides with
"Pin" the Scoring Object). `resolution`
(`self_recovered|freed_by_contact|assisted|unresolved|unknown`) REQ. `confidence`
REQ.

### `Interaction` (`record_type: interaction`, OPTIONAL through M3B)

`id`, `actor_robot_ref`, `subject_robot_ref`, `video_t_start`, `video_t_end`,
`period`, `interaction_type`
(`sustained_contact|path_denial|immobilization|mutual_congestion|unknown`),
`confidence` REQ. `subject_region` OPT (regions are only labeled for
cycle-labeled robots).

### `StateChange` (`record_type: state_change`)

The un-attempted-change channel; the one genuinely instantaneous record type. `id`,
`period`, `video_t`, `change`, `attributed_to`, `confidence` REQ. `change` is one of
three groups, and the group determines which further fields apply:

- **Goal-affecting** (`stack_toppled|object_fell_from_stack|
  object_added_unattributed|object_displaced_from_goal`): `target_goal_ref`,
  `stack_height_before`, `stack_height_after` REQ-IF, absent otherwise.
- **Toggle-affecting** (`toggle_changed`): `toggle_ref`, `state_after`,
  `seated_after` REQ-IF, absent otherwise.
- **Possession-affecting** (`object_dropped_in_transit|object_taken_from_robot`):
  `possession_id`, `object` REQ-IF, absent otherwise. Closes the named episode.

`attributed_to` is a robot_ref, `null` (no robot involved -- settling, gravity), or
`"unknown"` -- **who was in contact, never why.** `caused_by_action` OPT, links a
side effect back to the Action that produced it.

## Validation summary (enforced by `observations/loader.py`)

- `program` never `both` (delegates to `vexu_sim.sources.validate_empirical_program`).
- `v5rc` robots are always `unknown_v5rc`; `vexu` robots are `vexu_24`/`vexu_15`.
- Every enum field checked against its closed vocabulary in `models.py`.
- Every REQ key present (including the REQ-but-legally-`null` fields listed above --
  a missing key is rejected even where `null` itself is the legal value); every
  REQ-IF condition checked in both directions.
- Every event record id is unique **across all record types**, checked first (a
  duplicate id would make every later `retry_of`/`loader_visit_id`/
  `caused_by_action` resolution ambiguous).
- Action `video_t_end` numeric or `"unknown"`, never `null`; `video_t_end >
  video_t_start` when both numeric.
- `robot_ref`, `retry_of`, `caused_by_action`, `loader_visit_id`,
  `contested_robot_ref`, `actor_robot_ref`/`subject_robot_ref` all resolve;
  `retry_of` chains are acyclic; `loader_visit_id` resolves to a `LoaderVisit`, not
  an Action; a loader-linked `acquire` must agree with its `LoaderVisit` on
  `robot_ref` and `period`.
- `target_goal_ref`/`toggle_ref` are canonical ids from `field_setup` (via
  `refs.py`); `loader_ref`/`region` are from the declared M3-local vocabulary.
- Both snapshots present, each containing every canonical Goal/Toggle and every
  rostered robot.
- `gap_after` present iff the robot is `cycle_labeled`; `no_next_action`
  recomputed deterministically at CSV-import time and, on every load, validated
  against chronological Action order -- see "`gap_after`" above.
- Possession episodes per-robot, non-interleaved, with id-format/ownership/
  monotonic integrity enforced (see "Possession episodes" above);
  `LoaderVisit.departs_possession_id` cross-checked against the referenced robot's
  actually-opened episodes. Duplicate-type acquisition and `place.object`
  inconsistency are warnings, not errors; other interleaving/id-integrity failures
  are errors.
- Event timestamps checked against `RuleBundle.period_seconds()` (a warning, not an
  error, given video timing imprecision).
- `events.source.csv` provenance, when loading a match directory
  (`load_match_observation`/`validate_csv_provenance`): a committed CSV whose bytes
  no longer match the stamped `source_csv_sha256`, a committed CSV with no hash
  stamped, and a stamped hash with no CSV to verify it against are all errors.
- Overlapping actions, a still-open possession episode at match end, and an event
  inside an `unlabeled_window` are warnings, surfaced in the QC report, never
  errors.

The validator never adjudicates a game rule (Placed/Scored/Owned) -- that
boundary belongs to `vexu_sim.scoring`, consumed only from M4 onward.

## Reconciliation inputs (see `docs/plans/m3-observation-plan.md` §H.2 for the full
design; implemented in `observations/reconcile.py`)

Three required channels. Goal depth and Toggle orientation are evaluated only at
`match_end` (the score-anchor instant); Midfield occupancy is evaluated at **both**
snapshot instants, since `<VUG5>` makes Midfield occupancy score-relevant at the
Autonomous boundary for VEX U too:

1. **Goal net depth**: `predicted_depth(G) = starting_depth(G) + Σ(after − before)`
   over every `place`/`descore`/goal-affecting `StateChange` touching `G`, compared
   to the `match_end` snapshot's physical stack length. Any contributing record
   with a non-numeric endpoint makes the channel `indeterminate` for that Goal.
2. **Toggle final orientation**: the last labeled `state_after` (from `toggle`
   Actions and toggle-affecting `StateChange`s, or the starting orientation if none)
   compared against the `match_end` snapshot's `orientation` -- never effective
   color.
3. **Midfield occupancy**: whether a `MidfieldOccupancy` episode is open at the
   `autonomous_end`/`match_end` instant, compared against
   `snapshot.robots[ref].in_midfield`. A `MidfieldOccupancy` record's own `period`
   bounds which snapshot it can cover: an autonomous-period episode with a `null`
   (still-open) exit closes at the autonomous/driver boundary and is never treated
   as covering `match_end`, and symmetrically a driver-period episode never covers
   `autonomous_end` -- occupancy records are matched to a snapshot by `period`, not
   by comparing absolute video timestamps alone.

One OPTIONAL best-effort channel: **Goal composition** -- the starting
type composition plus every determinate `object`-tagged net addition/removal,
compared to the snapshot's stack-item type multiset. Computed only when the depth
channel is determinate for that Goal and every contributing record's `object` is
known (a `descore`, which never records `object`, makes any Goal it touches
non-comparable on this channel even when the depth channel is fine).

Reconciliation never writes back to an observation and never runs the scorer; a
non-zero delta or a mismatch is reported, never corrected.

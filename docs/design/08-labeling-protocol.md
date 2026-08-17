# Labeling protocol (M3A)

The human procedure for turning real Override match video into the records
described in `docs/design/07-observation-schema.md`. This is a design/procedure
document, not an ADR (`docs/plans/m3-observation-plan.md` decided against one for
this milestone). It is amended after every QC disagreement (M3B/M3C); the schema
reference revises less often, only at the M3B checkpoint. **No real match has been
labeled under this protocol yet -- M3A closes with zero labeled matches; labeling
begins in M3B.**

## Per-match workflow

Seven steps, front-loading the highest-value, most reliable records so an
interrupted session still yields something usable:

| # | Step | Output |
|---|---|---|
| 0 | **Eligibility.** Official score published and retrievable; video covers the full match including the post-match settle. | go/no-go |
| 1 | **Metadata + roster**, including `visual_key` per robot, written *before* watching for events. | `match.yaml` |
| 2 | **Sync.** Fill `video.period_offsets`; verify with one independent `sync_check` pair. | offsets |
| 3 | **Snapshots first** -- `match_end` (after the `<SC1>` 5-second settle, where the broadcast dwells), then `autonomous_end`. | `snapshots.yaml` |
| 4 | **Score-critical pass, all 4 robots, 1x playback.** `place`, `descore`, `toggle`, `midfield_occupancy`, un-attributed `state_change`. | `events.source.csv` (partial) |
| 5 | **Cycle pass, one robot at a time -- the 2 robots of the cycle-labeled Alliance only.** `acquire`, `loader_visit`, `region`, `gap_after`, `possession_id` chaining. Incidents/interactions logged as noticed. | `events.source.csv` (complete) |
| 6 | **Import + QC.** Run the importer (refuses to emit on any error) and record `unlabeled_windows`, `minutes_spent`, `timing_precision_s`. | `events.yaml` |
| 7 | **Reconciliation.** Run all three channels; record the report. **Never edit a snapshot to make it balance.** | QC report |

Estimated ~88 minutes per match at first, expected to settle near 50-65 once
familiar with the sheet -- tracked via `labeling.minutes_spent` because "is this
protocol affordable" is one of M3B's actual research questions.

**Why the cycle pass covers only one Alliance's two robots:** it halves the
dominant labeling cost, a 2-robot V5RC Alliance is the closest structural analogue
to a VEX U team, and it is the only configuration where partner congestion
(`contested: congestion_partner`) is observable. All four robots are still covered
by the score-critical pass, so match reconstruction (M4) is unaffected.

## Match metadata (`match.yaml`)

Hand-authored YAML, written before any event labeling. `roster[].visual_key` is
written first, before watching for events -- robot mis-attribution is the most
common labeling error, and writing the discriminator first (e.g. "tall black tower,
orange wheels") reduces it and makes a re-label pass comparable. See
`docs/design/07-observation-schema.md` for every field's requirement level; see the
schema doc's worked `match.yaml` example, and
`tests/fixtures/observations/synth_match/match.yaml` for a complete synthetic
instance exercising every REQ field (not real match data).

## Video synchronization

Fill `video.period_offsets` (`{"autonomous": <video_t of auton t=0>, "driver":
<video_t of driver t=0>}`) by reading the on-screen match clock at the moment each
period starts. Verify with one independent `sync_check` pair: pick any later moment,
read the on-screen clock, and confirm `video_t - period_offset` matches. This is
cheap insurance against the single most corrupting labeling error -- a mis-synced
offset silently shifts every timestamp in the match, and repairing it later is a
metadata edit only because the offset is a single point of truth (§E.1 of the plan).

## Snapshots

Label `match_end` first (right after the `<SC1>` 5-second post-match settle, the
moment broadcasts reliably dwell on the field), then `autonomous_end` (often
`partial` quality -- action is still live). Record **physical stacking as seen**,
bottom-up, for every Goal -- not `<SC2>`/`<SC3>` Placed/Scored adjudication, which
is never a labeling task (see "What must not be labeled" below). Every Goal,
Toggle, and rostered robot must appear in both snapshots, even when empty/neutral/
unknown. Loose floor Pins/Cups are never recorded.

## Event labeling and the `events.source.csv` workflow

```
match.yaml        hand-authored YAML   (once per match)
snapshots.yaml     hand-authored YAML   (twice per match, nested and ragged)
events.source.csv  spreadsheet          (40-120 flat, repetitive rows)
    |
    | deterministic importer (vexu_sim.observations.from_csv)
    v
events.yaml        canonical YAML (importer output; never hand-edited)
```

`events.source.csv` is committed alongside `events.yaml` as the human-authored
provenance artifact; `match.labeling.source_csv_sha256` is set from the importer's
computed hash and must be re-verifiable by re-hashing the committed file (a
mismatch is a validation error, not a warning). `events.yaml` remains canonical for
every downstream reader -- no loader in this package ever reads the CSV directly.

**One CSV, one `record_type` column** -- not one sheet per record type. The
labeler works a single chronological timeline; switching sheets mid-match invites
mis-ordering. Unused columns for a given row's `record_type` are just empty cells.

### Spreadsheet column order

Exactly the order `vexu_sim.observations.from_csv.CSV_COLUMNS` declares (the
importer is the source of truth; this table documents it for the labeler):

```
record_type, id, robot_ref, period, action_type,
video_t_start, video_t_end, video_t, video_t_enter, video_t_exit,
region, outcome, failure_mode, contested, contested_robot_ref,
gap_after, retry_of, possession_id,
source, object, object_colors, loader_visit_id,
target_goal_ref, stack_height_before, stack_height_after, cup_down_face,
destabilized_stack, video_t_release,
method, objects_removed,
toggle_ref, state_before, state_after, seated_after,
loader_ref, objects_acquired, objects_types, failed_grabs,
departs_possession_id, video_t_first_object_available,
contested_during, exit_coincident_with_contact,
incident_type, resolution,
actor_robot_ref, subject_robot_ref, interaction_type, subject_region,
change, attributed_to, caused_by_action,
confidence, notes
```

Grouped core -> per-type blocks (Action common core, then `acquire`, `place`,
`descore`, `toggle` fields, then `LoaderVisit`, `MidfieldOccupancy`, `Incident`,
`Interaction`, `StateChange` fields, then the trailing `confidence`/`notes` shared
by everything) so a labeler working one record type at a time only has to look at
one contiguous band of columns. Freeze the header row and the `record_type`/`id`/
`robot_ref`/`period` columns when working the sheet.

### Cell conventions the importer enforces

- Empty cell = absent (not applicable to this `record_type`/condition).
- The literal text `unknown` (case-insensitive) = the `unknown` sentinel, for any
  field where it is legal -- kept distinct from an empty cell.
- Numeric columns accept a plain number or `unknown`; anything else is a hard
  import error (no silent coercion).
- Boolean columns accept `true`/`false` (or `yes`/`no`/`1`/`0`) or `unknown`.
- List columns (`object_colors`, `objects_types`) use `|` as the separator, e.g.
  `red|yellow`.
- A column the importer does not recognize is a hard error -- catches a typo'd
  header before it silently drops a field.

The importer never writes partial output: if any row fails to parse, or the fully
assembled event set fails validation against `match.yaml`/`snapshots.yaml`/the
`RuleBundle`, `events.yaml` is not written at all.

## Action boundary definitions

See `docs/plans/m3-observation-plan.md` §D for the full reasoning; the operative
boundaries:

- **`acquire`**: start = first contact between the robot and the target object; end
  = the object translating with the robot for ≈0.5s / one clear motion (success),
  or the robot breaking off (failure/abandon). Approach is not part of this
  action -- it is the preceding gap, classified by the *previous* record's
  `gap_after`.
- **`place`**: start = the last transition from transit motion to a stop/slow
  maneuver adjacent to the target Goal -- **the weakest boundary in the
  ontology**; M3B measures pass-to-pass agreement on it specifically, with a
  stated fallback (redefine start as first contact between the carried object and
  the Goal/stack) if agreement is poor. End = the object at rest, manipulator
  separated.
- **`descore`**: defined by *effect*, never apparent intent. Start = first contact
  with the target stack; completion = an object removed from its Placed position,
  the stack toppled, or a Cup placed opaque-down over an already-stacked half.
  A robot that topples a stack while placing its *own* object is
  `place{destabilized_stack: true}` plus a `state_change` -- not a `descore`.
- **`toggle`**: start = first contact; `state_after` is read only once the robot
  separates **and the Toggle settles** (`<SC4>`) -- reading it during contact is
  always wrong, not a labeler judgement call.
- **No `align` action type.** Alignment overhead is folded into `place` and
  recovered statistically in M5 (regression on depth/Goal class), plus the OPT
  `video_t_release` split when visible -- splitting it out as its own event
  produces a field with poor pass-to-pass agreement, per the plan's D.6 analysis.

## `gap_after` classification

Fill while already watching that robot (during the cycle pass, step 5) -- it costs
one enum per Action for the two cycle-labeled robots, not a separate pass. Classify
the interval from an Action's end to the **same robot's next Action in the same
period**, ordered by `video_t_start`:

- `transit` -- drives essentially continuously to the next Action: no stop longer
  than ~1s, no opponent interaction, no visible searching, nothing else attempted.
  **Only this value is eligible for M5 travel-time fitting later** -- and even a
  clean `transit` gap includes some disengage/approach tail, a known upward bias,
  not something to try to trim by eye.
- `mixed` -- anything else observed in the gap: waiting, searching, hovering,
  idling, unrelated repositioning.
- `contested` -- the gap contained an opponent interaction that impeded movement
  (normally paired with an `interaction` record).
- `not_observed` -- a camera cut or occlusion covers part of the gap.
- `none` -- the Actions abut or overlap; no positive gap to classify.
- `no_next_action` -- this was the robot's last labeled Action of the period. Do
  not try to determine this while labeling mid-session -- **the importer
  recomputes it deterministically** from the finished, ordered per-robot,
  per-period Action list and will reject a value that disagrees with the data. If
  unsure whether an Action will turn out to be the robot's last one of the period,
  label the honest gap classification for what is actually visible and let the
  importer settle `no_next_action` on its own for genuinely terminal Actions.

## `LoaderVisit` handling

Label the interval a robot spends inside a Load Zone as its own
`record_type: loader_visit` row -- start = first entry into the Load Zone region
(purely positional, no intent judgement), end = leaving it (or leave `video_t_exit`
empty if still inside at period end). `objects_acquired: 0` is a legitimate,
informative row (a pass-through or an unproductive wait), not a failure to be
forced into Action-shaped success/fail semantics -- this is exactly why
`LoaderVisit` is not an Action. When individual grabs inside the visit are clearly
visible (`video.quality == good`), link each nested `acquire{source: loader}` row
to its containing visit via `loader_visit_id`; this is never required, and
visit-level throughput (`objects_acquired`) is available even when it isn't done.
Record `video_t_first_object_available` only when the human Loader interaction is
separately visible from the robot's own delay -- when it isn't, `loader_visit`
duration is a joint human+robot quantity, and it must not be attributed to the
robot alone in any downstream analysis.

## Possession episodes

Assign `possession_id` as `<robot_ref>#<n>`, incrementing per robot as episodes
open. Open a fresh id on an `acquire` while the robot holds nothing; reuse the
currently open id when acquiring the *other* object type (extending the episode);
close it (stop referencing that id) once the robot's held set is empty, whether
via `place`(s) or a possession-affecting `state_change`. A `descore` never carries
a `possession_id`; if the robot ends up holding what it just removed, log that as
a separate `acquire{source: goal_stack}`. If in doubt about whether an episode is
still open, check the previous record's outcome for that robot rather than
guessing -- the importer will flag inconsistencies (duplicate-type acquisition,
`place.object` not in the open episode) as warnings for review, not silently
accept them.

## Uncertainty

Use exactly four mechanisms, and never guess in place of one of them:

1. **`confidence`** (`certain`/`probable`/`uncertain`) per record -- would a second
   viewing fill every required field identically (`certain`), does ≥1 field rest
   on partial visibility (`probable`), or could a competent labeler reasonably
   disagree the event happened at all (`uncertain`, excluded from the M5 default
   fit)?
2. **`unknown`** per field -- the video does not show this particular value.
3. **`null`/absent** -- not applicable to this record (a REQ-IF condition does not
   hold), never a stand-in for "I don't know."
4. **`coverage.unlabeled_windows`** -- for a whole window the labeler cannot cover
   at all (camera on the drive team, etc.), rather than silently thinning the
   record density in that window.

Below `uncertain` confidence, do not record the event; let the window fall into
`unlabeled_windows` instead, so absence of evidence stays visible.

## The M3B pilot workflow (not started by M3A)

M3B labels three matches -- one per video-quality stratum (`baseline_clean`,
`typical_broadcast`, `poor_video`) -- runs reconciliation on all three, and holds a
schema-revision checkpoint: any field that proves unlabelable in practice is
removed or demoted to OPTIONAL, with the reason recorded, `schema_version` bumped,
and the three matches re-labeled if the change is not backward compatible. Specific
questions M3B must answer: is the `place` start boundary usable, is `gap_after`
reproducible, is Cup `down_face` readable often enough for a tight `<SC3>` score
band, and did the three matches collectively reach the corpus-level breadth
preference (floor acquisition, Loader interaction, Pin/Cup placement, Toggle
interaction, Midfield occupancy, at least one failure/retry, contested activity)?
M3A does not source, watch, or label any of this -- see "Strict non-goals," below.

## QC procedures (run in M3C, not M3A)

Either a single-labeler blinded re-label (2 matches, ≥7 days later, no access to
the first pass) or, if multiple labelers are available, independent labeling of
the same 2 matches followed by a joint adjudication pass that produces a resolved
file **and** a protocol clarification for every disagreement -- the clarification
is the actual deliverable, not the raw agreement number. Metrics: event
recall/precision/F1 per `action_type` (`|Δt_start| ≤ 1.0s` match), `place`
start-boundary agreement specifically, `gap_after` agreement (overall and on the
`transit` subset), outcome/failure_mode agreement, timing agreement (calibrates
`timing_precision_s` empirically), snapshot agreement (the check with actual
ground truth, via Gate V2), and reconciliation-channel agreement. Thresholds are
provisional until M3B establishes a baseline; a field that misses badly gets cut
or redefined, not labeled harder, and every such change (including the bad
numbers) is written into this document.

## What must NOT be labeled

1. Driver intent, strategy quality, decision quality.
2. Mechanical root cause -- outcomes only (`dropped`), never diagnoses
   (never "insufficient intake compression").
3. Exact velocity, coordinates, distances, 3D stack geometry.
4. Capability claims -- there is no `capable`/`incapable` field anywhere. A
   non-attempt is not evidence of incapacity; capability is a query over records,
   run in M7.
5. Persistent global object identity -- possession episodes only (§ above).
6. Every traversal -- gaps are *classified* (`gap_after`), never labeled as their
   own action records.
7. Every robot contact -- only contact meeting a `contested`/`interaction`
   definition.
8. Interference delay magnitude -- derived by contrast in M5, never observed.
9. Subjective interference character -- "aggressive," "dirty," "clean," or any
   field naming a delay magnitude.
10. An intended autonomous routine -- video cannot establish intent; autonomous is
    covered entirely by `period: autonomous` on ordinary records plus the
    `autonomous_end` snapshot.
11. **`<SC2>`/`<SC3>` Placed/Scored adjudication.** Record physical stacking as
    seen; whether it counts as Placed/Scored is M4's job via the existing scorer.
12. Loose floor Pins/Cups in snapshots.
13. Referee/violation adjudication from video -- violations come only from the
    published official record.
14. Anything the labeler would have to guess. `unknown` is always available and is
    always the correct answer when the video does not show it.

## Non-goals for this document

This protocol governs *how a human labels*, not what the schema *means* -- see
`docs/design/07-observation-schema.md` for field-by-field semantics, and
`docs/plans/m3-observation-plan.md` for the full design rationale, alternatives
considered, and the pilot-corpus/QC design this document summarizes procedurally.

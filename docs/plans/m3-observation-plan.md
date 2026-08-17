# M3 — Observation Schema and Manual Match-Labeling Protocol (Revision 2.1)

> **STATUS: APPROVED PLANNING BASELINE**
> **IMPLEMENTATION HAS NOT STARTED**

This document is the definitive, approved planning baseline for M3, preserved as a project
handoff. No `src/vexu_sim/observations/` package, no labeled matches, and no schema documents
under `docs/design/` exist yet. Nothing in this file has been implemented. Revision 2.1 folds in
the final approved M3A corrections directly (§B–§R below; see "Corrections applied in Revision
2.1" immediately following) rather than leaving them as a note superseding the body text, so a
fresh implementation session has exactly one consistent source of truth.

---

## Context

M0–M2 built the rules-first foundation: cited rule bundles (`data/rules/override/v1.1/`), a
deterministic scorer over a static `MatchState` (`src/vexu_sim/scoring/`), and the official
starting Field states (`src/vexu_sim/field_setup/`). Every fact so far traces to the Game Manual
or an official Q&A ruling. Nothing in the repo has yet touched reality.

M3 is the hinge. It defines how real Override match video becomes structured data, and everything
empirical downstream inherits its shape: M4 reconstruction, M5 parameter estimation, M6 the
discrete-event simulator, M7 capability vectors, M8 Monte Carlo, M9 the architecture answer. A
schema mistake here is not a bug — it is a corpus that has to be re-labeled by hand.

Two forces pull against each other and the whole design is the resolution between them:
**analytical completeness** (M5 needs enough to fit distributions; M4 needs enough to reproduce a
score) and **labeling cost/reliability** (a 2-minute match must not take 90 minutes, and a field a
human cannot read consistently from broadcast video is worse than no field, because it silently
poisons a fitted parameter).

The immediate corpus is V5RC Override video, because VEX U video is scarce. The target is VEX U.
The schema must therefore make the V5RC→VEX U transfer question *visible in the data* rather than
letting it dissolve.

**Decisions in force:** three-layer architecture · snapshot-authoritative with event→snapshot
reconciliation as QC · cycle detail for one alliance's two robots · spreadsheet-authored events ·
pilot target 8 matches, committing only to the first 3 before the schema checkpoint · M3 includes
models/validator/importer code · `08-labeling-protocol.md` is a design/procedure doc · no ADR for
the reconstruction choice · `video_t_release` optional but strongly encouraged during the pilot ·
`loader_visit` is a robot-activity record, not an Action · `events.source.csv` is committed
alongside `events.yaml` · `interaction` stays OPTIONAL through M3B, reconsidered at the checkpoint.

---

## Corrections applied in Revision 2.1

Final approved M3A corrections, incorporated throughout §A–§R below (not merely noted here).
Recorded so the reasoning is not lost.

| # | Change |
|---|---|
| **A · LoaderVisit is not an Action** | `loader_visit` is no longer an `action_type`. The true Action types are only `acquire`, `place`, `descore`, `toggle` — each has a real attempt/outcome. `loader_visit` is its own layer-2 robot-activity **interval/container** record type (§B, §C.12): time spent inside a Load Zone, with no `outcome`, `failure_mode`, `retry_of`, or `gap_after` — a zero-object visit is data, not a failed action. The old `within_action` link from a nested `acquire{source: loader}` to its containing visit is replaced by an explicit `loader_visit_id` reference on the `acquire` record. |
| **B · Action end-time semantics** | The four Action types are interval observations with two real boundaries (§D). `video_t_end` is now `<number> \| "unknown"` — **never `null`**. Duration is DERIVED only when both endpoints are numeric; an `unknown` end leaves duration undefined, not zero (§E.3). `null`/open-ended semantics are reserved for record types where "still ongoing" is itself the observed fact: `MidfieldOccupancy.video_t_exit`, `Incident.video_t_end`, and `LoaderVisit.video_t_exit`. `StateChange` remains the schema's one genuinely instantaneous record (a single `video_t`, no interval at all) and is unaffected. |
| **C · `gap_after` terminal semantics** | `GapClass` gains a sixth value, `no_next_action`: no later Action exists for this robot in this Period, so there is nothing to classify a gap *to*. "Next Action" is defined deterministically as the next Action for the same robot **and same period**, ordered by `video_t_start` (§F.2). `gap_after` is therefore always present on a cycle-labeled robot's Action — never merely absent for a terminal one. Only `transit` is eligible for M5 travel-time fitting. |
| **D · M3B pilot breadth** | Added a corpus-level **sourcing preference** to §L.1, layered on top of (not replacing) the three video-quality strata: across the three M3B matches collectively, sourcing should prefer, where practical, coverage of floor acquisition, Loader interaction, Pin placement, Cup placement/stacking, Toggle interaction, Midfield occupancy, at least one failure or retry, and contested activity. Not a requirement that every behavior appear in every match — the M3B checkpoint should test ontology breadth as well as camera-quality robustness. |
| **E · Remaining decisions settled** | §R is now a closed decisions log, not an open-questions list: M3B step 0 is match sourcing; `events.source.csv` **is** committed alongside `events.yaml` as the human-authored provenance artifact, with `source_csv_sha256` verifiable against the committed file; `interaction` stays OPTIONAL through M3B and is reconsidered at the M3B checkpoint. |

---

## Corrections applied in Revision 2

Recorded so the reasoning is not lost and the Revision 1 mistakes are not re-introduced.

| # | Change |
|---|---|
| **1 · Traversal** | Retracted "every positive gap is a traversal." Added a single REQUIRED enum `gap_after` on each action of a cycle-labeled robot, classifying the interval to that robot's next action (Revision 2.1 added a sixth value, `no_next_action`, for a robot's period-terminal action — see the Revision 2.1 table below). **Only `transit` gaps become M5 travel-time samples.** Retracted the v1 claim that derived traversal is free and "the largest cost saving" — it costs one enum per action, and even a clean `transit` gap still contains disengagement and approach tails, which §I now states as a known upward bias rather than hiding. |
| **2 · Possession** | `possession_id` now names a **possession episode**, not an object. `<SG6>` bounds an episode to ≤1 Pin + ≤1 Cup, so `(possession_id, object)` uniquely identifies a held object without global identity — this is what makes `pin_and_cup` and multi-placement work. Two placements from one episode share the id and differ in `object`. **`loader_visit` no longer carries `possession_id`** (it is a container, not a carried object); it carries `departs_possession_id` instead. `descore` carries no possession id at all. |
| **3 · Object loss** | A drop with no placement attempt is no longer a failed `place`. Added `state_change.change ∈ {object_dropped_in_transit, object_taken_from_robot}` carrying `attributed_to` + `possession_id` + `object`; it closes the episode. Removed `object_lost_in_transit` from `failure_mode` (`dropped` now means *dropped during an attempted placement*, only). Reacquisition opens a new episode and the schema makes no claim it is the same physical object. |
| **4 · Autonomous** | **Removed `autonomous_routine_completed` entirely.** Video cannot establish intended routine. Autonomous is covered by `period: autonomous` on ordinary records plus the `autonomous_end` snapshot. A team-supplied intended routine would be a separate future record type, never inferred. |
| **5 · Midfield** | **Removed `midfield_hold` as an action type** — `outcome`/`failure_mode`/`possession_id`/`region` do not apply to an occupancy interval, and `outcome: success` for "was still there" was forcing attempt semantics onto a state. Replaced with a `midfield_occupancy` **state-interval record type** with no outcome field: enter/exit times, `exit_coincident_with_contact` (observable, no causal claim), `contested_during`. Endgame transition timing is derived. |
| **6 · Reconciliation** | Expanded from Goal-depth-only to **three channels** — Goal net depth, Toggle final orientation, Midfield occupancy at both scoring boundaries — plus an OPTIONAL best-effort Goal *composition* channel needing no persistent tracking. **Fixed the descore sign error:** the ledger sums observed `stack_height_after − stack_height_before` per record, so `descore{method: obscure}` correctly contributes **+1**. Unknown endpoints mark a channel `indeterminate` instead of being assumed. |
| **7 · Dependencies** | Fixed the v1 contradiction. `observations` READS three stable public APIs and modifies nothing: `validate_empirical_program`, `RuleBundle.period_seconds()`, and `build_*_starting_state(bundle).match_state` for canonical Goal/Toggle/Quadrant ids. Added `observations/refs.py` as the single place these are pulled in — and the single place the genuinely **M3-local** vocabulary (Loader ids, Load-Zone region ids) is declared, flagged as such because no rule datum names them. |
| **8 · Authoring** | Endorsed the `match.yaml` + `snapshots.yaml` hand-authored / `events.csv` → importer → `events.yaml` workflow, with the reason stated: snapshots are nested and ragged and hostile to a flat CSV, while events are flat, repetitive and high-volume. One CSV with a `record_type` column, not one per type. Importer is deterministic, refuses to emit on any validation error, and stamps `source_csv_sha256`. |
| **9 · Execution split** | Restructured into **M3A** (schema + tooling, closes with no real matches), **M3B** (3-match pilot + schema checkpoint), **M3C** (5 more + QC). The ≥7-day re-label delay lives entirely in M3C and blocks nothing before it. |
| **10 · Decisions** | Pilot target 8, committing 3 · M3 includes code · protocol doc stays a design doc · no ADR · sourcing is M3B step 0 · `video_t_release` optional but encouraged. |

### Issues found in the internal-consistency pass

| Finding | Resolution |
|---|---|
| **Stack height ≠ Placed count.** `<SC2>` / Figure SC2-2: a Pin resting on an already-occupied Cup half is physically on the stack but is *not Placed*. v1 blurred these. | Snapshots and all `stack_height_*` fields are explicitly **physical** counts. `<SC2>` adjudication is declared **not a labeling task** — it is M4's compiler. |
| **The depth ledger cannot see visibility changes.** A Cup rotated in place, or a half becoming hidden without a depth change, is score-relevant and invisible to a net-depth sum. | Stated as an explicit known limit of reconciliation, and the reason the snapshot stays authoritative. |
| **Intent-flavored boundaries.** v1's `loader_visit` start said "with an apparent intent to load"; `place` start said "goal-directed positioning." | `loader_visit` is now purely positional. `place`'s start is redefined positionally and flagged as the ontology's weakest boundary, with a specific agreement target in M3B. |
| **`descore` named by intent.** | Redefined purely by effect; a robot toppling a stack during its own placement is `place{destabilized_stack: true}` + `state_change`, not a `descore`. |
| **Required fields that don't apply.** | Introduced explicit **conditional requirements** (`REQ-IF`) throughout, enforced by the validator in both directions. |
| **REQ vs `unknown` ambiguity.** | Global convention: **REQ means the key must be present; `unknown` is a legal value unless stated otherwise.** |
| **Duplicated `contested` row** on the old `midfield_hold`; **`autonomous_routine_completed`** appeared in one section but not the roster table. | Both gone with the records that carried them. |
| **VEX U endgame has no value in the rule bundle.** `periods.yaml` defines `endgame_seconds` only under `v5rc:`. | Endgame derivation is V5RC-only; for VEX U it evaluates to `unknown` rather than assuming 10 s. A `verify` item, not an assumption. |
| **`interaction.subject_region`** was REQ-ish but regions are only labeled for cycle-labeled robots. | Demoted to OPT. |

---

## A. Observation philosophy and granularity

### A.1 Three layers

The roadmap's flat "action event" sketch is the right vocabulary and the wrong shape: not every
score change is caused by a labeled robot action (an opponent shoulders a stack over; a Pin settles
out ten seconds later), and not every action changes the score (traversal, failed acquisitions,
Loader visits). Three layers, with different jobs, different failure modes, different cost:

| Layer | Records | Answers | Failure mode if wrong |
|---|---|---|---|
| **1. Boundary state** | `snapshot` ×2 | What was the Field at the end of Autonomous and end of Match? | Breaks score reconstruction (Gate V2) |
| **2. Robot activity** | `action`, `loader_visit`, `midfield_occupancy`, `incident`, `interaction` | What did each robot do/experience, when, for how long, with what outcome? | Adds noise/bias to a fitted parameter (M5) |
| **3. Un-attempted change** | `state_change` | What changed that no robot *attempted*? | Breaks event→snapshot reconciliation |

Layer 3 is "no attempt was made," not "no robot was involved" — a drop in transit and an opponent
knocking a stack both live here and both name a robot, without claiming intent.

### A.2 Actions carry their own effects; `state_change` is the exception channel

A successful `place` records what it did (target Goal, object, physical depth before/after); no
paired `state_change` is written. `state_change` covers only changes no labeled action attempted.
This halves record count and sharpens the semantics of both types.

### A.3 Granularity rule

**One record per attempted unit of work whose duration or success a robot could plausibly be
better or worse at.** If two labelers would draw the boundary differently, or the quantity is not
something a mechanism can be good at, it does not get its own record. This is what kills `align`
(§D.6) and what removed `midfield_hold` from the action family (§C.6).

### A.4 Raw, not derived

Nothing derived is stored — no averages, no rates, no "cycle time." Derived quantities are listed
as **DER** so M5 knows they exist and M3 knows not to store them.

---

## B. Record types

Eight record types, three files per labeled match.

| # | Record | File | Cardinality | Layer |
|---|---|---|---|---|
| 1 | `match` (metadata, roster, coverage, official result) | `match.yaml` | 1 | metadata |
| 2 | `snapshot` | `snapshots.yaml` | 2 | 1 |
| 3 | `action` — 4 types: `acquire`, `place`, `descore`, `toggle` | `events.yaml` | ~30–100 | 2 |
| 4 | `loader_visit` (interval/container, no outcome; §C.12) | `events.yaml` | 0–20 | 2 |
| 5 | `midfield_occupancy` (state interval, no outcome) | `events.yaml` | 0–12 | 2 |
| 6 | `incident` | `events.yaml` | 0–8 | 2 |
| 7 | `interaction` (OPTIONAL) | `events.yaml` | 0–10 | 2 |
| 8 | `state_change` | `events.yaml` | 0–15 | 3 |

`loader_visit`, `midfield_occupancy`, `incident` and `interaction` are separate from `action`
because an action is *something a robot attempted*: a Load Zone visit and an occupancy interval
have no success criterion (a zero-object visit is data, not a failure), a tip-over is not an
attempt, and a two-robot engagement has two subjects. Folding any of them in would overload
`robot_ref` and force `outcome`/`failure_mode`/`retry_of`/`gap_after` onto records where none has
observable meaning.

---

## C. Field schema

**Conventions.**
- **Req**: `REQ` (key must be present) · `REQ-IF <cond>` (required only under a stated condition; the validator enforces both directions) · `OPT` · `DER` (derived, never stored) · `DEF` (deferred).
- **`REQ` does not mean "known."** `unknown` is a legal value for any REQ field unless stated otherwise. `null`/absent means *not applicable to this record*. These are different facts and validation enforces the distinction; a required enum may never be `null` when its condition holds.
- **Action interval endpoints are numeric-or-`unknown`, never `null`** (§E.3). `null` is reserved
  for record types where "still ongoing" is itself the observed fact — `MidfieldOccupancy`,
  `Incident`, and `LoaderVisit` — not for `acquire`/`place`/`descore`/`toggle`.
- **Video**: `Y` reliably readable from ordinary event/broadcast footage · `P` partial, frequently `unknown` · `N` usually not (nothing `N` is REQ).
- All times are **video seconds** (float, 0.1 s). Match-clock time is DER (§E.1).

### C.1 `match` — `match.yaml` (hand-authored)

```yaml
schema_version: "m3.0"
match_key: "v5rc/2026-11-14_bay-area-signature_q041"
program: v5rc
event_name: "Bay Area Signature Event"
event_code: "RE-V5RC-26-1234"
match_id: "Q41"
match_type: qualification
date: 2026-11-14
manual_version: "1.1"

video:
  url: "https://www.youtube.com/watch?v=..."
  retrieved: 2026-11-20
  quality: good                    # good | usable | poor
  camera: fixed_full_field         # fixed_full_field | broadcast_switched | handheld | mixed
  period_offsets: {autonomous: 412.3, driver: 441.8}
  sync_check: {video_t: 500.0, observed_field_clock: "1:03"}
  timing_precision_s: 0.3

roster:
  - {robot_ref: r_red_a,  alliance: red,  team: "1234A", size_class: unknown_v5rc,
     visual_key: "tall black tower, orange wheels", cycle_labeled: true}
  - {robot_ref: r_red_b,  alliance: red,  team: "5678B", size_class: unknown_v5rc,
     visual_key: "low wide chassis, green banner", cycle_labeled: true}
  - {robot_ref: r_blue_a, alliance: blue, team: "9012C", size_class: unknown_v5rc,
     visual_key: "white, front intake ramp", cycle_labeled: false}
  - {robot_ref: r_blue_b, alliance: blue, team: "3456D", size_class: unknown_v5rc,
     visual_key: "red bumper, tall arm", cycle_labeled: false}

official_result:                   # transcribed from the published record, never judged from video
  red_total: 128
  blue_total: 96
  autonomous_bonus_to: red         # red | blue | tie | unknown
  awp: {red: false, blue: false}
  violations_autonomous: []        # [] | [red] | [blue] | [red, blue] | unknown
  source_url: "https://www.robotevents.com/..."
  retrieved: 2026-11-20

coverage:
  cycle_labeled_alliance: red
  fully_labeled: true
  unlabeled_windows:
    - {period: driver, t_start: 63.0, t_end: 68.5, reason: "camera on drive team"}

labeling:
  labeler: "nn"
  label_date: 2026-11-21
  pass_id: 1
  selection_stratum: heavy_defense
  minutes_spent: 47
  source_csv_sha256: "…"           # set by the importer; ties events.yaml to the authored sheet
```

| Field | Type / values | Req | Definition, when recorded, why | Video |
|---|---|---|---|---|
| `schema_version` | string | REQ | Which schema revision this file was labeled under. The M3B checkpoint **will** revise the schema; without this, pre- and post-revision records mix silently. | — |
| `match_key` | string | REQ | Unique; also the directory path. | — |
| `program` | `v5rc \| vexu` | REQ | Never `both`; validated via `validate_empirical_program()`. | — |
| `manual_version` | string | REQ | Which `RuleBundle` governs. Rules change mid-season; a fit spanning a rule change is unattributable without it. | — |
| `video.quality` | `good \| usable \| poor` | REQ | `good` = full field visible most of the time, ≥720p, few cuts. Drives M5 weighting and §L stratification. | Y |
| `video.camera` | enum | REQ | Broadcast switching dominates `unknown` timings; lets M5 test whether timing distributions differ by camera type. | Y |
| `video.period_offsets` | map period→float | REQ | Video second of each period's `t=0`. Single point of truth for video→match-clock conversion; one edit repairs a mis-synced file (§E.1). | Y |
| `video.sync_check` | object | REQ | One independent (video_t, on-screen clock) pair. Catches the offset error that would otherwise corrupt every timestamp. | Y |
| `video.timing_precision_s` | float | REQ | Honest bound on achievable timing accuracy. **M5 may not fit a distribution tighter than this.** | — |
| `roster[].team` | string \| `unknown` | REQ | Cross-match identity key; lets M5 pool a robot across matches and stops one team's mechanism from becoming the population. | Y |
| `roster[].size_class` | `unknown_v5rc \| vexu_24 \| vexu_15` | REQ | **A V5RC robot is always `unknown_v5rc`.** Validator rejects a VEX U class on a `v5rc` record. V5RC has no 15" class; inventing one is the single most dangerous transfer error available (§J.1). | — |
| `roster[].visual_key` | string | REQ | How the labeler tells this robot apart, written **before** event labeling. Robot mis-attribution is the most common labeling error; writing the discriminator first reduces it and makes a re-label pass comparable. | Y |
| `roster[].cycle_labeled` | bool | REQ | Whether layer-2 cycle detail was labeled for this robot. Distinguishes "did not attempt" from "not labeled" — without it, attempt counts are uninterpretable (§C.10). Also gates whether `gap_after` is required. | — |
| `official_result.*` | ints / enums | REQ | Transcribed, never judged. The Gate V2 target. `violations_autonomous` feeds `MatchState.autonomous_violations`; if unpublished, `unknown`, and the auton-bonus half of reconstruction is marked non-verifiable rather than guessed. | — |
| `coverage.unlabeled_windows` | list (may be `[]`) | REQ | Explicit holes. M5 divides counts by *labeled* time, not match time. | Y |
| `labeling.pass_id` | int | REQ | 1 = first pass; 2 = blinded re-label (§M). | — |
| `labeling.selection_stratum` | enum (§L.1) | REQ | Why this match entered the corpus — records the sampling bias explicitly, which matters because M5 fits from a *purposive*, not random, corpus. | — |
| `labeling.minutes_spent` | int | REQ | "Is this protocol affordable" is one of M3B's actual research questions. | — |
| `labeling.source_csv_sha256` | string \| null | REQ-IF events were imported | Ties the canonical YAML to the authored sheet; lets a re-import be verified byte-for-byte. | — |

### C.2 `snapshot` — `snapshots.yaml` (hand-authored)

Two per match. The score-reconstruction anchor, and authoritative over the event stream.

```yaml
- snapshot_id: s_match_end
  context: match_end               # autonomous_end | match_end
  video_t: 561.5
  quality: good                    # good | partial | poor
  goals:
    g_alliance_red_1: {stack: [], confidence: certain}
    g_neutral_short_red_1:
      stack:                       # bottom-up, PHYSICAL stacking (not Placed adjudication)
        - {object: pin, colors: [red, yellow], nested_half: unknown}
        - {object: cup, down_face: opaque}
        - {object: pin, colors: [yellow, yellow], nested_half: a}
      confidence: probable
    g_midfield: {stack: [{object: pin, colors: [yellow, yellow]}], confidence: certain}
    # … all 9 Goals present, always
  toggles:
    t_red_1: {orientation: red, seated: true, contacted_by_robot: false, confidence: certain}
    # … all 4 Toggles present, always
  robots:
    r_red_a: {in_midfield: true, contacting_perimeter: false, confidence: certain}
    # … every rostered robot present, always
```

| Field | Type / values | Req | Definition, when recorded, why | Video |
|---|---|---|---|---|
| `context` | `autonomous_end \| match_end` | REQ | Maps 1:1 onto the existing `ScoringContext`. `match_end` is read **after** the `<SC1>` 5-second settle — exactly when broadcasts dwell on the field, the most reliably observable moment in the video. | Y |
| `quality` | `good \| partial \| poor` | REQ | Whether the whole field was legible at that instant. `autonomous_end` is often `partial`. | Y |
| `goals.<id>.stack` | ordered list, bottom-up | REQ | **Physical stacking as seen.** Goal ids are exactly the nine `field_setup` builds. Empty list = empty Goal. A stack list is what a human can read off a frame; the `rests_on`/`occupant` slot graph is what the scorer needs — M4 owns that compiler. | Y/P |
| — | | | **`<SC2>` capacity adjudication is NOT a labeling task.** A Pin resting on an already-occupied Cup half (Figure SC2-2) is physically on the stack and is *not Placed*. The labeler records what is physically there; deciding what counts as Placed is M4's job, using the existing scorer. Every `stack_height_*` field in this schema is likewise a **physical object count**. | | |
| `stack[].object` | `pin \| cup \| unknown` | REQ | | Y |
| `stack[].colors` | `[color, color]` | REQ-IF `object == pin` | The Pin's half colors; each may be `unknown`. Determines 5 vs 10 points and Ownership (`<SC3>`/`<SC5>`). | Y/P |
| `stack[].down_face` | `opaque \| transparent \| unknown` | REQ-IF `object == cup` | Which face points down onto the half beneath. **This single field is the entire `<SC3>` visibility mechanic.** Gray vs clear is readable in decent video; `unknown` is common in poor video and drives the §H.2 score band. | P |
| `stack[].nested_half` | `a \| b \| unknown` | OPT | Which half is nested downward. Only matters when the Pin's halves differ in color *and* the slot below is opaque. `unknown` is the normal value; requiring it would force guessing on nearly every item. | P |
| `goals.<id>.confidence` | `certain \| probable \| uncertain` | REQ | Per Goal — the labeler reads a whole stack at once. | — |
| `toggles.<id>.orientation` | `red \| blue \| yellow \| unknown` | REQ | Toggle ids from `field_setup` (`t_red_1` …). Reconciliation compares against **orientation**, not effective color (§H.2). | Y |
| `toggles.<id>.seated` | bool \| `unknown` | REQ | `<SC4>`a — an unseated Toggle reads neutral regardless of orientation, so it changes the score. | P |
| `toggles.<id>.contacted_by_robot` | bool \| `unknown` | REQ | `<SC4>`b — must be read at the scoring instant. | Y |
| `robots.<ref>.in_midfield` | bool \| `unknown` | REQ | 8 points per robot at `match_end` (`<SC6>`) plus Midfield yellow Ownership (`<SC5>`b). One of the highest-leverage fields in the file. | Y |
| `robots.<ref>.contacting_perimeter` | bool \| `unknown` | REQ-IF `context == autonomous_end`; OPT at `match_end` | Only the Autonomous Win Point reads it (`<SC8>`/`<VUG6>`). | P |

**Deliberately excluded:** loose floor Pins/Cups. The scorer never reads them (`is_pin_placed`
requires a chain grounded at a Goal), and counting 30+ scattered objects is expensive and
unreliable. A recorded exclusion, not an oversight.

### C.3 `action` — common core

Applies to actions only (`acquire`, `place`, `descore`, `toggle`). `loader_visit` is **not** an
Action — it is its own robot-activity interval/container record type; see §C.12. The other
layer-2 record types have their own, smaller cores.

| Field | Type / values | Req | Definition, when recorded, why | Video |
|---|---|---|---|---|
| `record_type` | `action` | REQ | Discriminator. | — |
| `id` | unique string | REQ | e.g. `a_017`. Referenced by `retry_of`, `caused_by_action`. | — |
| `action_type` | `acquire \| place \| descore \| toggle` | REQ | §D. | Y |
| `robot_ref` | roster ref | REQ | | Y |
| `period` | `autonomous \| driver` | REQ | The answer to "don't duplicate the ontology for autonomous" — the same records carry a period. | Y |
| `video_t_start` | float | REQ | Type-specific boundary, defined per type in §D — never left to labeler taste. | Y |
| `video_t_end` | float \| `unknown` | REQ | **Numeric or `unknown` — never `null`.** All four Action types are interval observations with real start/completion boundaries (§D); none is genuinely instantaneous, so the old `null`-as-instantaneous case is retracted for Actions (§E.3). `duration` is DERIVED only when both endpoints are numeric; `unknown` leaves it undefined, not zero. `t_end == t_start` (when both numeric) is rejected. | Y |
| `region` | region enum (§F.1) | REQ | The sole spatial fact stored. | Y |
| `gap_after` | `transit \| mixed \| contested \| not_observed \| none \| no_next_action` | REQ-IF the robot is `cycle_labeled`; else absent | Classifies the interval from this action's end to the same robot's **next Action in the same period** (defined deterministically by `video_t_start` order, §F.2). `no_next_action` is used when no later Action exists — added in Revision 2.1 so a period-terminal Action is never merely missing this field. Only `transit` gaps are eligible as M5 travel-time samples. | Y/P |
| `outcome` | `success \| fail \| abandoned \| unknown` | REQ | `success` = the type's completion criterion (§D) met. `fail` = attempted, not met. `abandoned` = broke off before the criterion could be evaluated, and departed. There is deliberately **no `interrupted`** — that requires inferring cause; `contested` carries opponent involvement without claiming causation. | Y/P |
| `failure_mode` | enum (§G.1) | REQ-IF `outcome != success` | **Outcome-shaped, never cause-shaped.** | Y/P |
| `contested` | `none \| opponent_contact \| opponent_block \| congestion_opponent \| congestion_partner \| field_element \| unknown` | REQ | §G.2. Lets M5 stratify clean vs contested rather than pretending a delay magnitude is observable. | Y/P |
| `contested_robot_ref` | roster ref \| null | OPT | Which robot, when `contested != none` and identifiable. | Y |
| `possession_id` | string | REQ-IF `action_type ∈ {acquire, place}`; **absent otherwise** | Episode id, not an object id (§C.7). | Y |
| `retry_of` | action id \| null | REQ | Set when this repeats an attempt at the same target after a failure (§E.5). | Y |
| `confidence` | `certain \| probable \| uncertain` | REQ | §C.8. Per record, not per field. | — |
| `notes` | string | OPT | Never parsed; read during QC and schema revision. | — |
| `duration`, `match_clock_t`, `is_endgame`, `possession_contents`, `cycle_time` | — | **DER** | Never stored (§E.1, §E.2, §C.7). | — |

**`acquire`**

| Field | Type / values | Req | Definition / why | Video |
|---|---|---|---|---|
| `source` | `floor \| loader \| goal_stack \| opponent_robot \| unknown` | REQ | The architecture-relevant distinction: floor and Loader acquisition are different mechanisms with different VEX U value (§I). | Y |
| `object` | `pin \| cup \| pin_and_cup \| unknown` | REQ | `pin_and_cup` = both in one motion, legal under `<SG6>`. **Whether Loaders present *nested* Pin/Cup combinations is a `verify` item for M3B, not an asserted rule fact** — the enum value exists so the labeler can record it if seen. | Y/P |
| `object_colors` | `[color, color]` \| `unknown` | OPT | Rarely worth chasing mid-cycle. | P |
| `loader_visit_id` | `loader_visit` id \| null | OPT; only meaningful when `source == loader` | Links this grab to its containing `loader_visit` record (§C.12) when video permits — **replaces the old `within_action` relationship** (Revision 2.1). Never required: visit-level throughput is available from `loader_visit.objects_acquired` even when individual grabs aren't nested. | Y/P |

**`place`**

| Field | Type / values | Req | Definition / why | Video |
|---|---|---|---|---|
| `target_goal_ref` | one of the 9 `field_setup` goal ids | REQ | The three Goal classes (Alliance / neutral short / neutral tall) are the scoring-capability axes. | Y |
| `object` | `pin \| cup \| unknown` | REQ | Must match an object held in `possession_id` (validator warns if not). Cup placements are structural, not scoring — separating them is what makes stacking capability measurable. | Y |
| `stack_height_before` / `stack_height_after` | int \| `unknown` | REQ | **Physical** object count on that Goal. Their difference is this record's net effect in the reconciliation ledger (§H.2) — the ledger never assumes ±1. | Y/P |
| `cup_down_face` | `opaque \| transparent \| unknown` | REQ-IF `object == cup` | Ties to `<SC3>`; a deliberate opaque-down placement is a de-scoring-adjacent tactic worth measuring. | P |
| `destabilized_stack` | bool \| `unknown` | REQ | Did the target stack visibly shift/topple. Reliability evidence for tall stacking. If it toppled, also write a `state_change`. | Y |
| `video_t_release` | float \| `unknown` | OPT (**strongly encouraged in the pilot whenever visible**) | Moment the object leaves the robot. Splits pre-release positioning from post-release retreat — a more reliably visible split than "alignment" (§D.6), and impossible to backfill without re-watching every placement. | P |

**`descore`** — defined by effect, not intent (§D.4).

| Field | Type / values | Req | Definition / why | Video |
|---|---|---|---|---|
| `target_goal_ref` | goal id | REQ | | Y |
| `method` | `extract \| topple \| obscure \| unknown` | REQ | Three physically distinct capabilities, all observable without inferring purpose. **`obscure` (placing a Cup opaque-down over an opposing scored half) *increases* physical depth** — which is why the ledger uses observed before/after, not an assumed subtraction. | Y |
| `objects_removed` | int \| `unknown` | REQ-IF `method ∈ {extract, topple}`; else absent | | Y/P |
| `stack_height_before` / `stack_height_after` | int \| `unknown` | REQ | Physical counts; their signed difference is this record's net ledger effect. | Y/P |
| `cup_down_face` | `opaque \| transparent \| unknown` | REQ-IF `method == obscure` | | P |

`descore` carries **no `possession_id`.** If the robot ends up holding a removed object, that is a
separate `acquire{source: goal_stack}` opening an episode — which is where the possession belongs.

**`toggle`**

| Field | Type / values | Req | Definition / why | Video |
|---|---|---|---|---|
| `toggle_ref` | `t_red_1 \| t_red_2 \| t_blue_1 \| t_blue_2` | REQ | From `field_setup`. | Y |
| `state_before` / `state_after` | `red \| blue \| yellow \| unknown` | REQ | **`state_after` is read only after the robot separates and the Toggle settles** — `<SC4>` makes a contacted or unseated Toggle read neutral, so reading it during contact is always wrong. A rules-derived labeling instruction, not a convention. | Y |
| `seated_after` | bool \| `unknown` | REQ | | P |
| `method` | `stopped_contact \| drive_by \| unknown` | REQ | Drive-by capability saves real cycle time and is directly observable (did the robot stop?). | Y |

### C.4 `state_change` — the un-attempted-change channel

```yaml
- record_type: state_change
  id: sc_003
  period: driver
  video_t: 78.4
  change: stack_toppled
  target_goal_ref: g_neutral_short_blue_1
  stack_height_before: 4
  stack_height_after: 1
  attributed_to: r_red_a           # WHO was in contact — never WHY
  caused_by_action: null
  confidence: probable

- record_type: state_change         # object loss, independent of placement intent
  id: sc_004
  period: driver
  video_t: 91.2
  change: object_dropped_in_transit
  attributed_to: r_red_b
  possession_id: "r_red_b#12"
  object: pin
  confidence: certain
```

| Field | Type / values | Req | Definition / why | Video |
|---|---|---|---|---|
| `change` | `stack_toppled \| object_fell_from_stack \| object_added_unattributed \| object_displaced_from_goal \| toggle_changed \| object_dropped_in_transit \| object_taken_from_robot \| unknown` | REQ | Grouped into **goal-affecting** (first four), **toggle-affecting**, and **possession-affecting** (last two). | Y |
| `target_goal_ref`, `stack_height_before`, `stack_height_after` | | REQ-IF goal-affecting; absent otherwise | Signed difference is the ledger effect. | P |
| `toggle_ref`, `state_after`, `seated_after` | | REQ-IF toggle-affecting; absent otherwise | | Y/P |
| `attributed_to` | roster ref \| `null` \| `unknown` | REQ | **Which robot was in contact / which robot lost the object — not why.** `null` = no robot involved (settling, gravity). Never an intent claim. | Y/P |
| `possession_id`, `object` | | REQ-IF possession-affecting; absent otherwise | Closes the episode named. Reacquisition opens a **new** episode; the schema makes no claim it is the same physical object. | Y |
| `caused_by_action` | action id \| null | OPT | For side effects of a labeled action (a `place` that also toppled a neighbouring stack). | Y |

### C.5 `incident` — reliability

```yaml
- record_type: incident
  id: i_004
  robot_ref: r_blue_b
  period: driver
  video_t_start: 80.1
  video_t_end: 92.6                # null if unresolved at match end
  incident_type: mechanism_stopped
  resolution: unresolved
  confidence: certain
  notes: "Intake stopped rotating; robot kept driving."
```

`incident_type`: `tipped | near_tip | immobilized | mechanism_stopped | object_stuck |
disconnected | unknown` — **observable outcomes, never diagnosed causes.** `object_stuck` replaces
"jam" and is defined as *an object visibly lodged in/on the robot while the robot continues
attempting to move it*. `immobilized` covers being held by an opponent — **the schema never uses
the word "pinned," because "Pin" is a Scoring Object in Override** and the collision would be a
permanent source of confusion in labels and code alike.

`resolution`: `self_recovered | freed_by_contact | assisted | unresolved | unknown`. Recovery time
is `t_end − t_start`.

**No `recover` action type** (a deliberate departure from the roadmap sketch): recovery is fully
described by the incident interval plus `retry_of` chains on subsequent actions. A `recover` action
would need the labeler to decide when "recovering" ends and "playing" resumes — an unreliable
boundary that buys nothing the interval doesn't already give.

### C.6 `midfield_occupancy` — a state interval, not an action

```yaml
- record_type: midfield_occupancy
  id: m_002
  robot_ref: r_red_a
  period: driver
  video_t_enter: 96.4
  video_t_exit: null               # null = still inside when the period ended
  exit_coincident_with_contact: unknown
  contested_during: true
  confidence: certain
```

| Field | Type / values | Req | Definition / why | Video |
|---|---|---|---|---|
| `video_t_enter` | float \| `unknown` | REQ | Robot first fully inside the Midfield (`field.yaml: zones.midfield` — bounded by the inner edges of the white tape square). | Y |
| `video_t_exit` | float \| `null` \| `unknown` | REQ | `null` = still inside at period end — which is exactly the score-relevant case (`<SC6>`, `<SC5>`b). | Y |
| `exit_coincident_with_contact` | `true \| false \| unknown` | REQ-IF `video_t_exit` is a number; absent otherwise | **Purely observational** — the exit coincided with sustained contact from another robot. Deliberately *not* `displaced_by_opponent`, which would be a causal claim. Displacement is inferred in M5 from this flag plus co-occurring `interaction` records, never labeled. | Y |
| `contested_during` | `true \| false \| unknown` | REQ | Was an opposing robot also in or contesting the Midfield during the episode. | Y |

**No `outcome`, no `failure_mode`, no `region`, no `possession_id`, no `gap_after`** — none has an
observable meaning for an occupancy interval, which is precisely why this is not an `action`.

REQ for any episode overlapping a period boundary or the Endgame window; OPT for earlier transient
entries. **Endgame transition timing is DERIVED**: `video_t_enter` of the episode open at match end
versus the rule-derived endgame boundary (§E.2).

### C.7 Possession episodes — the lightweight identity answer

**No persistent global object identity.** Pins within a colour combination are visually identical,
there are up to 63 Pins and 56 Cups, and tracking them through a 2-minute scramble across camera
cuts is not something a human does reliably. The scorer needs *stack composition*, not object
histories; every M5 parameter is a duration, a count, or a rate.

**What replaces it — the possession episode.**

- `possession_id` = `<robot_ref>#<n>`, monotonically increasing per robot. It names an **episode**:
  a contiguous interval during which that robot holds at least one Scoring Object.
- **`<SG6>` bounds an episode to ≤1 Pin and ≤1 Cup** (possession limit, unmodified for VEX U per
  `02-game-model.md`). This is the fact that makes the whole design work: within one episode,
  `object: pin` / `object: cup` is *sufficient* to identify which held object an event refers to.
- **Opening:** an `acquire` while the robot holds nothing opens a new id.
- **Extending:** an `acquire` while the robot already holds the *other* object type reuses the
  current id. `acquire{object: pin_and_cup}` opens an episode already containing both.
- **Multiple placements from one episode:** they share the `possession_id` and differ in `object` —
  `place{p#7, object: cup}` then `place{p#7, object: pin}`. Unambiguous, by `<SG6>`.
- **Closing:** when the robot holds nothing — via `place`(s), or a possession-affecting
  `state_change` (§C.4). An episode may close partially (Cup placed, Pin still held); it is closed
  when its last object leaves.
- **Containers do not carry it:** `loader_visit` uses `departs_possession_id`; `descore` carries
  nothing.

**Validation:** ids are per-robot and non-interleaved; an `acquire` of an object type already held
in the open episode is a **warning** (either a labeling error or a real `<SG6>` violation — the
validator does not adjudicate rules); a `place` whose `object` is not in the open episode is a
warning; an episode still open at match end is legal (the robot ended holding something).

**DERIVED, never stored:** `possession_contents`, `possession_duration`, and `cycle_time`
(`last place.video_t_end − first acquire.video_t_start` over one episode).

**CV note:** a tracker would produce global ids and could populate `possession_id` trivially, so
this choice does not block later CV — it declines to demand CV-grade output from a human.

### C.8 Confidence and ambiguity

Three levels, per record, with operational definitions — not a 1–10 score, which would be
unanchored and inconsistent between passes.

| Level | Definition | Effect on M5 |
|---|---|---|
| `certain` | Seen unambiguously; the labeler would fill every required field identically on a second viewing. | In the default fit. |
| `probable` | The event clearly happened, but ≥1 field rests on partial visibility. | In the default fit; every parameter is **also refit without `probable`** as a published robustness check, reporting `n_certain` / `n_probable`. |
| `uncertain` | The labeler believes it happened but a competent labeler could reasonably disagree that it happened at all. | **Excluded** from the default fit; sensitivity analysis only. Recorded so it is not lost. |

Below `uncertain`, nothing is recorded — the window goes into `coverage.unlabeled_windows`, so
absence of evidence stays visible. `confidence` is orthogonal to `unknown`: a `certain` record can
contain `unknown` fields (sure a place happened, unable to read the depth).

### C.9 Autonomous — no routine inference

No separate ontology: `period: autonomous` on the same records. There is **no
`autonomous_routine_completed` field** — video cannot establish what routine a robot was *intended*
to run, and a "partial/complete" judgement would be an intent inference wearing a factual label.

Autonomous is therefore covered by exactly three things already in the schema:
1. Ordinary action/incident/state_change/occupancy records with `period: autonomous`, and their
   outcomes — which is where navigation failure and object-interaction failure actually show up.
2. The `autonomous_end` snapshot (Autonomous Bonus and AWP inputs).
3. `official_result.autonomous_bonus_to` / `.awp` / `.violations_autonomous`, transcribed.

If an intended routine ever becomes known from an independent source (a team telling us), it would
be a **separate future record type compared against these observations** — never inferred from
video, and out of scope for M3.

One program asymmetry that makes the `autonomous_end` snapshot matter even for V5RC: `<VUG5>`
includes Midfield-dependent scoring at the Autonomous boundary for VEX U while `<SC7>` excludes it
for V5RC (qna:3188). So `in_midfield` must be captured at `autonomous_end` even where it does not
affect the V5RC bonus — otherwise the corpus cannot support the VEX U comparison later.

### C.10 Capability evidence — what is deliberately NOT a field

There is **no `capable` field anywhere.** A capability is a *query over records*, run in M7:

| Capability | Query |
|---|---|
| Floor Pin / Cup acquisition | `acquire{source: floor, object: …}` |
| Loader Pin / Cup acquisition | `acquire{source: loader, object: …}` (optionally linked to its `loader_visit` via `loader_visit_id`), or `loader_visit.objects_types` when grabs aren't individually nested |
| Nested Pin+Cup handling | `acquire{object: pin_and_cup}` |
| Short Goal scoring | `place{target_goal_ref ∈ alliance ∪ neutral_short}` |
| Tall Goal scoring | `place{target_goal_ref = g_midfield}` — note there is exactly **one** neutral tall Goal (`field.yaml: goals.breakdown.neutral_tall: 1`), so "tall Goal" and "Midfield Goal" scoring are the same capability |
| Stacking | `place{stack_height_before ≥ 1}`, by depth |
| Toggle interaction | `toggle`, by `method` |
| De-scoring | `descore`, by `method` |
| Defensive interaction | `interaction{actor_robot_ref = R}` |
| Midfield / endgame | `midfield_occupancy` |
| Autonomous | records with `period: autonomous` |
| Recovery / reliability | `incident` + `outcome` / `retry_of` rates |

Two consequences the protocol enforces:
- **A non-attempt is not evidence of incapacity.** Zero `place{g_midfield}` may mean the robot
  cannot reach a tall Goal, or that strategy never called for it. M3 records attempts; M7 does the
  inference, and `cycle_labeled` + `unlabeled_windows` are what make the distinction computable.
- **Therefore every labeled match is labeled end-to-end** for its in-scope robots. Partial labeling
  makes attempt counts uninterpretable — which is why `fully_labeled` is required.

### C.11 `interaction` — sustained engagements (OPTIONAL)

For interference **not contained within a single action**: sustained defense, blocked transit
spanning several actions, an opponent holding a robot against the perimeter.

`actor_robot_ref`, `subject_robot_ref`, `video_t_start`, `video_t_end`, `period`, `confidence` all
REQ; `interaction_type ∈ {sustained_contact, path_denial, immobilization, mutual_congestion,
unknown}` REQ; `subject_region` **OPT** (regions are only labeled for cycle-labeled robots).
`mutual_congestion` asserts no actor/subject asymmetry.

**Never recorded:** a delay magnitude, "aggression," or whether the defense was good. Interference
cost is *derived in M5* by contrasting contested and uncontested distributions of the same action
type — never observed, because causality is not visible in video.

**Decided:** `interaction` stays OPTIONAL through M3B. Its status — including whether
`heavy_defense` (M3C, stratum 5, §L.1) requires promoting it to REQUIRED — is reconsidered at the
M3B schema-revision checkpoint (§Q), with actual pilot counts in hand rather than a guess made now.

### C.12 `loader_visit` — a robot-activity interval, not an Action

```yaml
- record_type: loader_visit
  id: lv_005
  robot_ref: r_red_a
  period: driver
  video_t_enter: 118.2
  video_t_exit: 124.6              # null = still in the Load Zone when the period ended
  loader_ref: loader_red_1
  objects_acquired: 2
  objects_types: [pin, cup]
  failed_grabs: 1
  departs_possession_id: "r_red_a#9"
  video_t_first_object_available: unknown
  contested: none
  confidence: certain
```

A `loader_visit` is an interval a robot spends inside a Load Zone — a **container**, not an
attempt. It carries no `outcome`, `failure_mode`, `retry_of`, or `gap_after`: a zero-object visit
(`objects_acquired: 0`) is a legitimate, informative record (a pass-through, or a wait that
produced nothing), not a failed action forcing an artificial success/fail judgement onto an
interval — see §A.3's granularity rule. This is why `loader_visit` is not in the `action` family
in this revision (Revision 2.1, correction A); its start/end boundaries are unchanged from earlier
revisions and are defined in §D.2.

| Field | Type / values | Req | Definition / why | Video |
|---|---|---|---|---|
| `id` | unique string | REQ | e.g. `lv_005`. Referenced by an `acquire`'s `loader_visit_id` (§C.3). | — |
| `robot_ref` | roster ref | REQ | | Y |
| `period` | `autonomous \| driver` | REQ | | Y |
| `video_t_enter` | float | REQ | The robot first enters the Load Zone region — purely positional, no intent test (§D.2). | Y |
| `video_t_exit` | float \| `null` \| `unknown` | REQ | The robot leaves the Load Zone region. `null` = still inside when the Period ended — the same open-ended pattern as `MidfieldOccupancy.video_t_exit` and `Incident.video_t_end` (§E.3), because a Load Zone visit is an interval/container record, not an Action. | Y |
| `loader_ref` | `loader_red_1 \| loader_red_2 \| loader_blue_1 \| loader_blue_2` | REQ | Four Loaders, two per Alliance (`field.yaml: inventory.loaders`). **M3-local vocabulary** — the rules give the count, not names (§P). | Y |
| `objects_acquired` | int \| `unknown` | REQ | Objects the robot left holding. Visit ÷ objects is the throughput number VEX U cares about. `0` is legal and meaningful. | Y |
| `objects_types` | list of `pin`/`cup` | OPT | | P |
| `failed_grabs` | int \| `unknown` | REQ | Visibly failed grabs within the visit — cheaper and more reliable than timing each. Individual grabs may additionally be linked via a nested `acquire{source: loader}` record's `loader_visit_id`. | P |
| `departs_possession_id` | possession id \| `null` \| `unknown` | REQ | The episode the robot departed the Load Zone holding — `null` when it left empty-handed, and it may name an episode *opened before* the visit (robot arrived holding a Pin, left holding Pin+Cup). A container links to an episode; it does not claim to be one (§C.7). | Y |
| `video_t_first_object_available` | float \| `unknown` | OPT | When a Match Load first became visibly available. **The only field separating human-Loader delay from robot delay**, and frequently `unknown` (robot occludes the Loader). When `unknown`, visit duration is a *joint* human+robot quantity and §I forbids attributing it to the robot. | P |
| `contested` | same enum as Action `contested` (§C.3) | REQ | Whether another robot's presence at/around the Loader affected this visit — relevant to the `loader_heavy` stratum's queueing question (§L.1). | Y/P |
| `confidence` | `certain \| probable \| uncertain` | REQ | §C.8. | — |
| `notes` | string | OPT | | — |

**No `outcome`, no `failure_mode`, no `retry_of`, no `gap_after`, no `possession_id`, no
`region`.** `region` is redundant here — `loader_ref` already identifies the specific Load Zone.
`gap_after` in particular has no meaning: it is defined on **Actions**, classifying the gap to the
robot's *next Action*, and a `loader_visit` is not one and is never itself a "next Action."

---

## D. Action ontology — boundaries

Each of the four true Action types (`acquire`, `place`, `descore`, `toggle`) states **start**,
**completion criterion**, and **end** explicitly, because these three sentences are where
agreement is actually won or lost. **There is deliberately no D.2 in this revision:**
`loader_visit` is not an Action (Revision 2.1, correction A), so its boundary definition lives with
its record type at §C.12 rather than here; the numbering gap (D.1, D.3, D.4, D.5, D.6) is kept
exactly as-is so every existing `§D.n` cross-reference in this document stays correct.

### D.1 `acquire`
- **Start:** first contact between the robot (any part, including an intake) and the target object.
- **Completion (success):** **the object translates with the robot** — it moves with robot motion
  for a visible moment (≈0.5 s or one clear robot movement) without further repositioning.
- **End:** completion, or the moment the robot breaks off.
- **Approach is not part of this action.** It is the preceding gap, classified by `gap_after` on
  the previous record (§F.2). This is the answer to "should acquisition distinguish approach /
  contact / control": the three-phase split collapses to two boundaries, because an `approach`
  start boundary ("when did the robot begin approaching *this* object?") requires reading intent.
- **Failed acquisition:** contacted, never controlled → `outcome: fail`.
- **Loss after control:** the `acquire` stays `success`; the loss is a possession-affecting
  `state_change` (§C.4) or, if a placement was attempted, `place{failure_mode: dropped}`.

*(`loader_visit`'s boundaries — purely positional, no intent test: start is the robot first
entering the Load Zone region, end is the robot leaving it — are defined with the rest of its
schema at §C.12, since it is not an Action. Individual grabs may be linked via a nested
`acquire{source: loader}` record's `loader_visit_id` — never REQUIRED, RECOMMENDED when
`video.quality == good`, giving visit-level throughput from every match and per-grab timing only
from the good ones. Human vs robot delay is separable only where
`video_t_first_object_available` is legible; otherwise the schema records a joint quantity and §I
forbids attributing it to the robot.)*

### D.3 `place`
- **Start:** the last transition of the robot's drive base from transit motion to a stop or slow
  maneuver adjacent to the target Goal. **This is the weakest boundary in the ontology** — it has
  no sharp visual discontinuity — and M3B measures pass-to-pass agreement on it specifically
  (§M.3). If agreement is poor, the fallback is to redefine `video_t_start` as first contact
  between the carried object and the Goal/stack, accepting that alignment time then moves into the
  preceding gap.
- **Completion (success):** the object comes to rest nested on the Goal/stack and remains as the
  robot withdraws.
- **End:** manipulator separates and the object is at rest.
- **Goal vs stack** is DERIVED from `stack_height_before == 0` — not a field, not a second type.

### D.4 `descore` — defined by effect, not intent
Any action whose effect is the removal, toppling, or opaque-obscuring of already-stacked objects on
a Goal, **regardless of apparent purpose**. Start: first contact with the target stack.
Completion: ≥1 object removed from its Placed position, or the stack toppled, or a Cup placed
opaque-down over an already-stacked half. End: robot separates.

**Boundary with `place`:** a robot that topples a stack while making its own placement is
`place{destabilized_stack: true}` plus a `state_change`, **not** a `descore`. The discriminator is
observable — was the robot depositing an object it carried into that Goal, or acting on objects
already there.

### D.5 `toggle`
Start: first contact. Completion: post-settle orientation differs from `state_before`. End: robot
separates **and the Toggle settles** — `state_after` is read only then, per `<SC4>`. Repeats chain
via `retry_of`.

### D.6 `align` — NOT an action type

**Two reasonable designs exist.** (a) Split `align` out as its own required event, giving a
directly measured overhead. (b) Fold it into `place` and recover the overhead statistically.

**Recommend (b).** In ordinary footage a robot translates, extends and aligns simultaneously; the
boundary has no visible discontinuity, so (a) produces a field with poor pass-to-pass agreement —
and a noisy split of a duration is worse than an honest unsplit duration, because it manufactures
two bad numbers from one good one. Alignment overhead is instead recovered in M5 as the dependence
of `place` duration on `stack_height_before` and Goal class, plus the optional `video_t_release`
split, which has a genuinely visible boundary. If M3B shows `video_t_release` is reliably readable,
promoting it to REQ is a one-line change requiring no re-labeling around it.

---

## E. Temporal and overlap semantics

### E.1 Video seconds stored, match clock derived
Timestamps are **video seconds**; `video.period_offsets` maps each period's `t=0`. Match-clock time
is DER. Two reasons: the labeler reads video time off the player (transcription, not conversion),
and a mis-synced offset is repaired by one metadata edit instead of re-labeling every record.
`video.sync_check` exists to catch that error before it propagates.

**Two clocks (period + t), not one:** the real match has a non-constant pause between Autonomous
and Driver Controlled; a single continuous clock would bake that pause into every driver timestamp.
The `(period, t)` pair is exact — and it *is* the `period` field the autonomous question asks for,
which is why no separate autonomous ontology is needed.

Resolution 0.1 s; accuracy bounded by `video.timing_precision_s`.

### E.2 Endgame is derived — and is V5RC-only for now
`is_endgame` = `period == driver and match_clock_t ≥ driver_period_seconds − endgame_seconds`,
reading both from the `RuleBundle` — **no rule number hardcoded, none hand-labeled.**

**Consistency finding:** `periods.yaml` defines `endgame_seconds` only under the `v5rc:` key, and
`vexu.yaml` does not override it. For a VEX U match `is_endgame` therefore evaluates to `unknown`
rather than assuming 10 s. This is a `verify` item (re-read Section 6 / `<VUT>` for a VEX U Endgame
definition) — **not an assumption, and not an `open` question until steps 1–2 of the rule-gap
workflow have been done.** It does not block M3, whose corpus is V5RC.

### E.3 Action endpoints: numeric or `unknown`, never `null` (Revision 2.1)
Every Action (`acquire`, `place`, `descore`, `toggle`) is an interval observation with two real
boundaries defined in §D — none of the four is genuinely instantaneous once its start/completion
criteria are read literally (even a fast `toggle` flip has a contact-to-settle duration).
`video_t_end` is therefore `<number> | "unknown"` — **never `null`** — and `duration` is DERIVED
only when both endpoints are numeric; an `unknown` end leaves duration undefined, not zero.
`t_end == t_start` (when both are numeric) is rejected, because it would be indistinguishable from
a genuine zero-length measurement this schema does not model.

`null`/open-ended semantics are reserved for record types where "still ongoing" is itself the
observed fact, not a labeling gap: `MidfieldOccupancy.video_t_exit` (§C.6, still in the Midfield
when the Period ended), `Incident.video_t_end` (§C.5, unresolved at match end), and
`LoaderVisit.video_t_exit` (§C.12, still in the Load Zone when the Period ended — `loader_visit` is
an interval/container record, not an Action, so it follows this pattern rather than §D's). Neither
of these is "instantaneous"; both are genuinely open at one end and both use `null` to say so.

`StateChange` remains the schema's one genuinely instantaneous record type — a single `video_t`,
no start/end pair at all (§C.4) — and is unaffected by this section.

### E.4 Overlapping actions
Permitted and **not required to be annotated** — a robot may intake a Cup while driving to place a
Pin, and forcing a concurrency judgement onto every record to serve a rare case is bad economics.
Consequences belong to the analysis layer: M5 must not sum overlapping durations as sequential
work, and a `gap_after` of `none` covers the overlap case. An OPT `concurrent: true` hint may be
set; the validator reports overlaps in the QC report but never rejects them.

### E.5 Retries — precise definition
`B` is a retry of `A` iff: same `robot_ref`, same `action_type`, same target (`target_goal_ref` /
`toggle_ref` / same object for `acquire`), `A.outcome ∈ {fail, abandoned}`, no intervening
successful action of that type on that target by that robot, and `B` begins without the robot
completing an unrelated cycle in between. Chains are linear and acyclic; M5 walks them.

### E.6 Abandonment vs failure
`fail` = attempted, criterion not met. `abandoned` = broke off before the criterion could be
evaluated, and departed. Both observable. No `interrupted` — see §C.3.

---

## F. Spatial abstraction

### F.1 Region vocabulary
Nine regions plus `unknown`:

`quadrant_red_1` · `quadrant_red_2` · `quadrant_blue_1` · `quadrant_blue_2` · `midfield` ·
`load_zone_red_1` · `load_zone_red_2` · `load_zone_blue_1` · `load_zone_blue_2` · `unknown`

1. **Mostly not invented.** Quadrant, Midfield and Load Zone are defined in `field.yaml: zones`
   with manual citations, and the four Quadrant ids already exist in `field_setup`.
   **Honest caveat:** the *four individual* Load-Zone ids and the region-name spellings are
   **M3-local labeling vocabulary** — the rules give the Load Zone concept and the count of four
   Loaders, not four names. Declared as such in `observations/refs.py` (§P), not passed off as
   rule-derived.
2. **Reliably labelable.** Tape lines are visible; "which Quadrant" is a glance, not a judgement.
3. **Replaceable.** Any finer M6 model coarsens onto these regions, so M3 labels stay valid. No
   coordinates, no distances, no velocities.

Sub-Quadrant precision is expressed by **referencing the object** (`target_goal_ref`, `toggle_ref`,
`loader_ref`), which is the spatial fact that matters and is already in the model.

### F.2 Traversal — DERIVED from *classified* gaps

**Revision 1 was wrong** to treat every positive inter-action gap as a traversal duration. Gaps
routinely contain waiting for a Loader, searching for an object, hovering while a partner clears a
Goal, idling on defense, or repositioning unrelated to the next task. Fitting a travel-time
distribution over all of them would produce a number that is not travel time.

**Mechanism — one enum, filled while already watching that robot.** Every Action of a cycle-labeled
robot carries `gap_after`, classifying the interval to that robot's **next Action**. "Next Action"
is defined deterministically: the next Action for the *same robot*, in the *same period*, ordered
by `video_t_start`. (A `loader_visit` is not an Action — §C.12 — and is never itself a "next
Action" for this purpose, though time spent inside one is exactly the kind of thing a `mixed` gap
around it would describe.)

| Value | Definition |
|---|---|
| `transit` | A later Action exists, and the robot drives essentially continuously from where it finished to where it begins that Action: no stop longer than ~1 s, no opponent interaction, no visible searching or hesitation, no other task attempted. |
| `mixed` | A later Action exists, and the gap contains anything else observed — waiting, searching, hovering, idling, repositioning unrelated to the next Action. |
| `contested` | A later Action exists, and the gap contained an opponent interaction that impeded movement (normally paired with an `interaction` record). |
| `not_observed` | A later Action exists, but a camera cut or occlusion covers part of the gap. |
| `none` | A later Action exists, but the Actions abut or overlap — no positive gap to classify. |
| `no_next_action` | **Added in Revision 2.1.** No later Action exists for this robot in this Period — this was that robot's last labeled Action of the Period, so there is nothing to classify a gap *to*. |

**Only `gap_after: transit` intervals are eligible as M5 travel-time samples.** Everything else is
retained (it is real data about where time goes, or in `no_next_action`'s case, about where the
robot's labeled activity for the Period ended) but excluded from the travel distribution.

**`gap_after` is always present on a cycle-labeled robot's Action — never merely absent for a
terminal one.** The REQ-IF condition is unchanged ("the robot is `cycle_labeled`," §C.3); what
Revision 2.1 fixed is that a robot's period-terminal Action previously had no defined value to put
there, which made a genuinely-last Action indistinguishable from a validation gap. Because "is
there a next Action" is a data fact rather than a judgement, the importer/loader recomputes
`no_next_action` deterministically from the ordered per-robot, per-period Action list at import
time and treats a manually entered value that disagrees as an error (§K.2, §P) — the labeler does
not have to know mid-session whether an Action will turn out to be the robot's last one.

**Cost:** one enum per Action for two robots per match — a few dozen cells, filled during the pass
in which the labeler already knows both endpoints. Not free, but far below labeling traversal
actions everywhere.

**Honest limit, stated rather than hidden:** even a clean `transit` gap includes the tail of
disengaging from the previous action and the head of approaching the next. Derived traversal is
therefore a **slight over-estimate of pure travel**, and §I records it as a known upward bias. This
replaces revision 1's claim that derived traversal was free and clean, which the raw observations
did not justify.

Field-side transitions, Quadrant transitions, Loader→Goal and Goal→Goal trips, and Midfield
crossings are all derivable from the region sequence, and none of them is labeled.

---

## G. Failure, interference, uncertainty

### G.1 `failure_mode` — outcome-shaped only
`object_not_acquired` · `dropped` · `missed_target` · `knocked_target_stack` · `blocked` ·
`object_stuck` · `robot_incident` · `unknown`

**A labeler records what failed to happen, never why the mechanism failed.** "Did not retain the
Pin" is an observation; "insufficient intake compression" is a diagnosis and is forbidden.
`robot_incident` cross-links to an `incident` record.

`object_lost_in_transit` was removed in Revision 2 — a drop with no placement attempt is now a
possession-affecting `state_change` (§C.4). `dropped` now means, only, *dropped during an attempted
placement*.

### G.2 The separated interference concepts

| Concept | Where | Definition |
|---|---|---|
| Direct defensive contact | `contested: opponent_contact` (+ `interaction{sustained_contact}` if sustained) | Sustained physical contact by an opponent, not incidental to both pursuing the same object. |
| Blocking / path denial | `contested: opponent_block` (+ `interaction{path_denial}`) | Opponent in the path **without contact**; subject visibly reroutes or stops. |
| Congestion (opponent) | `contested: congestion_opponent` | Two or more robots contending for the same object/Goal/region; no directional claim. |
| Congestion (partner) | `contested: congestion_partner` | Same, with an alliance partner. **Observable in V5RC** and the closest available analogue to VEX U two-robot coordination (§J.4) — which is why it is a separate value rather than lumped in. |
| Field-element obstruction | `contested: field_element` | Goal/Toggle/perimeter/Loader geometry impeded the robot. |
| Immobilization | `incident{immobilized}` | The robot cannot move. Never called "pinning" (§C.5). |

**Interference is an attribute AND a record, with a rule for which:** attribute (`contested`) when
contained within one action; standalone (`interaction`) only when it spans multiple actions or
occurs while the subject is doing nothing labelable. Never both for the same episode.

**Forbidden vocabulary:** "aggressive," "dirty," "intentional," and any field naming a delay
magnitude.

### G.3 Uncertainty
Four distinct mechanisms for four kinds of not-knowing, none requiring a guess: `confidence` per
record (§C.8), `unknown` per field, `null`/absent for not-applicable, and
`coverage.unlabeled_windows` for whole windows.

---

## H. Match-reconstruction coverage

### H.1 What each record buys

| Purpose | Records |
|---|---|
| **Score reconstruction only** | `snapshot` ×2, `official_result`, `roster` |
| **Parameter estimation only** | `acquire`, `loader_visit`, `toggle`, `incident`, `interaction`, classified gaps |
| **Both** | `place`, `descore`, `midfield_occupancy`, `state_change` |

### H.2 Snapshots authoritative; reconciliation is QC

The snapshot is the score anchor. Reconciliation is a **labeling-completeness signal only** and
never a score source. It runs at a level that needs no scoring and no `MatchState` compiler, so it
stays inside M3's boundary. Three required channels plus one optional:

**1. Goal net depth (fixed sign handling).** For each of the 9 Goals:

```
predicted_depth(G) = starting_depth(G, from field_setup)
                   + Σ over every record touching G of
                       (record.stack_height_after − record.stack_height_before)

delta(G) = predicted_depth(G) − snapshot(match_end).goals[G] physical stack length
```

Every record that touches a Goal — `place`, `descore` (all methods), goal-affecting
`state_change` — contributes its **own observed signed difference**. Nothing is assumed to be ±1.
This is the fix for the `descore{method: obscure}` case: obscuring adds a Cup, so its observed
`after − before` is **+1**, and the ledger gets it right without a special case. If either endpoint
of any contributing record is `unknown`, that Goal's channel is `indeterminate`, not assumed.

**2. Toggle final orientation.** The last labeled `state_after` before the snapshot instant (from
`toggle` actions and toggle-affecting `state_change`s) versus `snapshot.toggles[id].orientation`.
Compared against **orientation**, not effective colour — `<SC4>` makes a contacted or unseated
Toggle *read* neutral without its orientation changing, so comparing effective colour would
manufacture false mismatches.

**3. Midfield occupancy at both scoring boundaries.** Which robots have a `midfield_occupancy`
episode open at the `autonomous_end` and `match_end` instants versus
`snapshot.robots[ref].in_midfield`. This channel is why `midfield_occupancy` exists as a record
type rather than living only in the snapshot.

**4. Goal composition (OPTIONAL, best-effort).** Where a Goal's depth channel is fully determinate
and every contributing record recorded `object`, compare the **multiset of object types** added
(counts of `pin` / `cup`) against the snapshot's stack composition. Type-level only — no persistent
object tracking, no identity claim.

Each channel reports `match | mismatch(value) | indeterminate(reason)` per Goal/Toggle/robot.

**Known limits, stated rather than papered over:**
- **A depth ledger cannot see visibility changes.** A Cup rotated in place, or a half becoming
  hidden without a depth change, is score-relevant and invisible to every channel above. This is a
  central reason the snapshot — not the ledger — is authoritative.
- **Physical depth ≠ Placed count** (`<SC2>`, Figure SC2-2). The ledger reconciles physical
  objects; placement adjudication is M4's.

**A non-zero delta is recorded, never corrected.** It does not license editing the snapshot, and it
explicitly does not license inventing events until the number balances. Balancing pressure is
exactly how a "reconstructed" corpus quietly becomes a fitted one, which is what the four-store
separation exists to prevent.

**Occlusion → a score band, not a guess.** Where a snapshot field is `unknown` (most often a Cup's
`down_face`, which drives `<SC3>` visibility), M4 reconstructs a **min/max score band** by
enumerating the unknowns. Gate V2 then reads: the official score lies inside the band, and the band
is exact (`min == max`) on a stated fraction of matches — an honest treatment of occlusion and a
stronger test than a point estimate that happened to land.

### H.3 The minimum M3 must capture for M4
1. `match_end` snapshot: all 9 Goals' stacks, all 4 Toggles, all robots' `in_midfield`.
2. `autonomous_end` snapshot: same, plus `contacting_perimeter`.
3. `official_result`: totals, auton bonus recipient, AWP, autonomous violations.
4. `manual_version`, so M4 loads the right `RuleBundle`.
5. Enough `place` / `descore` / `state_change` / `midfield_occupancy` records for §H.2 to compute.

M3 verifies **presence and internal consistency** of these. M3 scores nothing — compiling stack
lists into `rests_on`/`occupant` graphs and running the scorer is M4/Gate V2, and keeping that line
sharp is what stops M3 from quietly editing the scoring engine.

---

## I. Observations → future empirical parameters

M3 assigns **no `transfer_class` values** — that is set in M5 with the fitted parameter. The right
column is expected reasoning, not a classification.

| M5 parameter | Direct observations | Principal confounders | Expected V5RC→VEX U reasoning |
|---|---|---|---|
| **Pin acquisition duration** | `acquire{object: pin, source: floor}` bounds, `outcome`, `contested`, `confidence` | No coordinates ⇒ reachability unmodeled, variance inflated; mechanism-specific; congestion | Duration is mechanism-level and plausibly transfers. But VEX U starts with **0 loose floor Pins vs V5RC's 32** — the *rate* is program-specific even where the *duration* transfers. |
| **Cup acquisition duration** | `acquire{object: cup}` | Same | Sharper: VEX U starts with **0 on-Field Cups vs V5RC's 36**; all VEX U Cups arrive via Loaders. |
| **Nested Pin+Cup handling** | `acquire{object: pin_and_cup}` | Rare, small n; bounded by `<SG6>` | Mechanism-level, likely transferable — but whether Loaders present *nested* combinations is an open `verify` item, not an assumption. |
| **Loader interaction / cycle** | `loader_visit` bounds, `objects_acquired`, `failed_grabs`, `departs_possession_id`, `video_t_first_object_available` | Human Loader skill; queueing; robot occludes the Loader ⇒ human/robot split usually unavailable | **Program-specific.** `<SG11>`c restricts V5RC loads to Driver Controlled; `<VUG4>` allows both periods and `<VUG7>` extends Load Zone protection to both; VEX U has 26 vs 22 Match Load Pins. Where the availability time is unknown, M5 must publish a **joint human+robot** quantity. |
| **Scoring interaction duration** | `place` bounds by Goal class and `stack_height_before` | Reach/height; contested; depth often `unknown` on tall stacks; **the `place` start boundary is the ontology's weakest** (§D.3) | Duration plausibly transfers per mechanism class; the Goal *mix* is strategy- and program-specific. |
| **Alignment overhead** | Regression of `place` duration on depth and Goal class; OPT `video_t_release` split | Confounded with reach and approach speed; not separately observable in most footage | Uncertain. M5 should publish it as a derived contrast with caveats, not as a measured primitive. |
| **Stacking duration & reliability** | `place{stack_height_before ≥ 1}`, `destabilized_stack`, `outcome` by depth | **`unknown` depth correlates with depth** — non-random missingness M5 must handle, not ignore | Likely direct at mechanism level; the 24"/15" split makes depth-vs-height the central architecture question. |
| **Toggle duration & reliability** | `toggle` bounds, `method`, `state_before/after`, `seated_after` | `<SC4>` settling; drive-by vs stopped conflated when `method` is `unknown` | **Strongest transfer candidate** — Toggle hardware and `<SC4>` are identical across programs and the interaction is short and self-contained. |
| **Traversal duration** | DERIVED from `gap_after == transit` gaps with region endpoints (§F.2) | Coarse regions; **`transit` gaps still include disengage/approach tails ⇒ known upward bias**; the `transit` classification is itself a labeler judgement whose agreement M3B measures | **Size-class-specific, and V5RC provides no 15"-class data at all** (§J.1). Region topology is shared, so the region-pair *structure* transfers; the speeds do not. |
| **Failure probability** | `outcome` counts by type × context | Failures near occlusion are under-counted (recall bias); the `fail`/`abandoned` boundary | Mechanism-level; uncertain. Stratify by `confidence` and `video.quality` to expose the bias. |
| **Retry probability & cost** | `retry_of` chains; retry vs first-attempt duration | Same | Same. |
| **Object-loss rate in transport** | `state_change{object_dropped_in_transit}` per possession episode | Drops off-camera are missed entirely | Mechanism-level (retention); plausibly transferable. **New in Revision 2** — v1 could not measure this at all, because transport drops were miscoded as failed placements. |
| **Recovery time** | `incident` bounds, `resolution` | Small n; severity unmeasured | Uncertain. Report a range, not a distribution, until n supports one. |
| **Defensive / interference delay** | `contested` + `interaction` + `gap_after == contested` | **Selection bias: defense targets effective robots**, so contested actions are not a random sample. Causality unobservable. | **Program-specific** — V5RC 2v2 vs VEX U 1v1-with-two-robots changes defensive economics entirely. Derive as a contrast, never label a delay. |
| **Congestion delay** | `contested: congestion_opponent` / `congestion_partner` | As above; partner congestion depends on alliance coordination, not a robot property | Uncertain. V5RC partner congestion is the only available proxy for VEX U coordination (§J.4). |
| **Autonomous action success** | Records with `period: autonomous`; `autonomous_end` snapshot | Auton routines are match- and alliance-specific, not robot-general; small n per team; **intended routine is unknown by design** (§C.9) | **Program-specific.** 30 s vs 15 s, Match Loads during VEX U auton (`<VUG4>`), different bonus/AWP rules (`<VUG5>`/`<VUG6>`). |
| **Midfield / endgame transition & robustness** | `midfield_occupancy` enter/exit, `exit_coincident_with_contact`, `contested_during`; region of the preceding action | V5RC Endgame is the last 10 s and **VEX U's has no bundle value yet** (§E.2); displacement is contested by definition | **Program-specific on strategy**, possibly direct on the travel component. `<VUG5>` makes Midfield occupancy matter at the Autonomous boundary in VEX U — V5RC data cannot inform that. |

---

## J. V5RC → VEX U transfer

1. **V5RC contains no 15"-class data whatsoever** — the largest single transfer gap in the project.
   Enforced: `size_class` on a V5RC robot is always `unknown_v5rc`; the validator rejects a VEX U
   class on a `v5rc` record. Never infer size class from apparent dimensions.
2. **The starting Field differs radically** (V5RC 32 loose Pins + 36 Cups; VEX U 0 and 0). Rate
   parameters cannot transfer; durations may.
3. **Match Load timing and volume differ** (`<SG11>`c vs `<VUG4>`; 22 vs 26 Pins; `<VUG7>`). Loader
   and autonomous behaviour do not transfer.
4. **2v2 alliance ≠ 1v1 two-robot team.** Defensive and congestion economics do not transfer — but
   V5RC **partner** congestion is the closest available analogue to VEX U two-robot coordination,
   which is why `congestion_partner` is a distinct value rather than lumped with opponent
   congestion. That separation is what makes the V5RC corpus informative about the VEX U
   coordination question at all.
5. **Objects and Toggles are physically identical across programs** — object-interaction mechanics
   are the best transfer candidates, and Toggle interaction the best of those.
6. **`<SG2>` remains unresolved** (`docs/open-questions.md` #1). If the 24" robot truly has zero
   horizontal expansion headroom, wide-intake acquisition times measured on V5RC robots may not be
   achievable on a VEX U 24" robot at all. M5 must not assume the transfer while that is open.

---

## K. Manual labeling workflow

### K.1 Per-match passes

Front-loads the highest-value, most reliable records so an interrupted session still yields
something usable, and avoids the biggest reliability killer: tracking four robots at once.

| # | Step | Output | Est. |
|---|---|---|---|
| 0 | **Eligibility.** Official score published and retrievable; video covers the full match including the post-match settle. A match without a verifiable official score cannot enter the corpus — Gate V2 is defined against it. | go/no-go | 3 min |
| 1 | **Metadata + roster**, including `visual_key` per robot, **before watching for events**. | `match.yaml` | 8 min |
| 2 | **Sync.** Fill `period_offsets`; verify with one independent `sync_check` pair. | offsets | 4 min |
| 3 | **Snapshots first** — `match_end` (after the `<SC1>` settle, where the broadcast dwells), then `autonomous_end`. Doing these first means an aborted session still produces a Gate-V2-usable record. | `snapshots.yaml` | 12 min |
| 4 | **Score-critical pass, all 4 robots, 1× playback.** `place`, `descore`, `toggle`, `midfield_occupancy`, un-attributed `state_change`. | `events.csv` (partial) | 20 min |
| 5 | **Cycle pass, one robot at a time — the 2 robots of the cycle-labeled alliance only.** `acquire`, `loader_visit`, `region`, `gap_after`, `possession_id` chaining. Incidents and interactions logged as noticed, not as a separate pass. | `events.csv` (complete) | 28 min |
| 6 | **Import + QC.** Run the importer (refuses to emit on any error) and the validator; record `unlabeled_windows`, `minutes_spent`, `timing_precision_s`. | `events.yaml` | 8 min |
| 7 | **Reconciliation.** Run all three channels; record the report. **Do not correct snapshots to make it balance.** | QC report | 5 min |

**≈ 88 min per match at first, expected to settle near 50–65.** Stated openly because "is this
protocol affordable" is one of M3B's actual questions — which is why `minutes_spent` is REQUIRED.

**Why the cycle pass covers one alliance's two robots:** it halves the dominant cost; a 2-robot
V5RC alliance is the closest structural analogue to a VEX U team; and it is the only configuration
in which partner congestion is observable. All four robots are still covered by the score-critical
pass, so reconstruction is unaffected.

### K.2 Authoring format

```
match.yaml       hand-authored YAML   (once per match, nested, ~40 lines)
snapshots.yaml   hand-authored YAML   (twice per match, nested and ragged)
events.csv       spreadsheet          (40–120 flat, repetitive rows)
   └─ deterministic validated importer ─→ events.yaml   (canonical)
```

**Why this split and not all-CSV:** a snapshot is a nested, ragged structure — 9 Goals each holding
a variable-length ordered stack of heterogeneous items. Flattening that into a CSV needs either
one row per stack item with parent keys (error-prone ordering, easy to corrupt) or wide
`slot_1_object, slot_1_colors, …` columns (mostly empty, capped arbitrarily). Both are worse than
typing 30 lines of YAML twice. Events are the opposite: flat, repetitive, high-volume, heavy on
column defaults — the CSV sweet spot.

**One CSV with a `record_type` column, not one per record type.** The labeler works a single
chronological timeline; switching sheets mid-match breaks the flow and invites mis-ordering. Unused
columns are just empty cells; the importer dispatches on `record_type` and enforces the `REQ-IF`
conditional requirements per type. The sheet is wide (~35 columns) — mitigated by a documented
column order (core → per-type groups) and frozen panes, both specified in the protocol doc.

**Importer contract:** deterministic (same CSV → byte-identical YAML, stable key order); **refuses
to emit on any validation error** rather than writing partial output; stamps
`labeling.source_csv_sha256` into `match.yaml` so the canonical YAML is traceable to the sheet it
came from. The importer also **recomputes `gap_after: no_next_action` deterministically** from the
ordered per-robot, per-period Action list rather than trusting whatever the labeler entered for a
robot's chronologically-last Action of a period, and treats a manually entered value that disagrees
as a validation error (§F.2) — "is there a next Action" is a data fact, not a judgement, once the
whole sheet is in.

**Decided (Revision 2.1): `events.source.csv` is committed** alongside the canonical
`events.yaml`, one per labeled match (§N). It is the actual human-authored provenance artifact —
committing it costs nothing and is what makes `source_csv_sha256` verifiable by a future reader
(re-hash the committed file; a mismatch is a validation error, not a warning). This does not make
it canonical: `events.yaml` remains the record of truth for every downstream reader, and no loader
in this package ever reads the CSV directly.

**No materially better low-complexity design was found.** The one alternative worth naming is a
tiny structured text format for events (one line per record, `key=value` pairs) that would avoid a
wide sheet — but it loses spreadsheet ergonomics (fill-down, column defaults, sorting by time) for
no gain in expressiveness, so the CSV wins. No UI is built in M3.

---

## L. Pilot corpus

### L.1 Stratified purposive sampling
The pilot's purpose is to **stress the ontology**, not to estimate a Worlds model. Sampling the
best robots would produce a corpus where every action succeeds and half the schema is never
exercised.

| # | `selection_stratum` | Why | Phase |
|---|---|---|---|
| 1 | `baseline_clean` | Fixed camera, full field, mid-level teams. Establishes the **ceiling** on labeling reliability — everything else is measured against it. | M3B |
| 2 | `typical_broadcast` | Switched broadcast with cuts and zooms. The realistic case. | M3B |
| 3 | `poor_video` | Bad angle/resolution/occlusion. **Deliberately included** — cutting this stratum is how a schema quietly becomes unusable, and it is the only real test of the `unknown` machinery. | M3B |
| 4 | `high_throughput` | Fast cycles, deep stacks. Stresses record volume and depth readability. | M3C |
| 5 | `heavy_defense` | Stresses `contested`, `interaction`, `immobilized`, `gap_after: contested`. | M3C |
| 6 | `loader_heavy` | Stresses `loader_visit`, `departs_possession_id`, the human/robot separability question. | M3C |
| 7 | `toggle_contested` | Repeated flips; stresses `retry_of` and `<SC4>` settling. | M3C |
| 8 | `strong_autonomous` | Stresses auton labeling and the `autonomous_end` snapshot / AWP. | M3C |
| 9–10 | `failure_rich`, `late_season` | Stretch only if per-match time lands at the low end. | M3C |

**M3B's three are strata 1–3 deliberately:** their *defining* axis of variation is video quality,
not strategy — the schema checkpoint needs to know first whether the ontology is labelable at all
across the quality range, since behavioral breadth is worth little if the fields themselves do not
survive a bad camera angle. This is the primary selection axis, not the only thing that matters
when choosing among otherwise-eligible candidates within each stratum — see the breadth preference
immediately below, which is a secondary criterion layered on top of it.

**Corpus-level breadth preference (Revision 2.1, correction D) — not a per-match requirement.**
Across the three M3B matches collectively — not necessarily within any single one — sourcing should
prefer, where practical, a combination that exercises: floor acquisition, Loader interaction, Pin
placement, Cup placement/stacking, Toggle interaction, Midfield occupancy, at least one failure or
retry, and contested activity. This is layered on top of, not a replacement for, the three
video-quality strata above and the hard inclusion criteria below — it exists so the M3B schema
checkpoint tests ontology **breadth** as well as camera-quality robustness; three clean matches
that never exercise `descore` or `toggle` would validate the wrong thing. If a behavior cannot be
found within three matches without sacrificing a quality stratum, it is deferred to M3C rather than
forcing a fourth M3B match.

### L.2 Hard inclusion criteria
- **Published, retrievable official score** — non-negotiable.
- Video covers the full match including the post-match settle.
- Across the corpus: **≥3 distinct events**, **≥8 distinct teams**, so one team's mechanism cannot
  dominate the fitted parameters. Both recorded and checkable.

### L.3 Size
**8 matches target**, but only the first 3 are committed before the M3B checkpoint (§Q).

---

## M. Consistency / quality control

Both branches specified; the branch is chosen at M3C execution time. **All of §M lives in M3C** —
nothing here blocks M3A or M3B.

### M.1 Single labeler — blinded re-label
2 matches (~25%), deliberately one `baseline_clean` and one `poor_video` (agreement on easy footage
tells you nothing about the protocol's real limits). Re-labeled from scratch **≥7 days later**
without opening the first pass; written with `pass_id: 2` under `…/relabel/`.

### M.2 Multiple labelers — inter-labeler agreement
Same 2 matches, labeled independently, same metrics, then a **joint adjudication pass** producing
(a) a resolved file and (b) **a protocol clarification for every disagreement** — the clarification
is the actual deliverable; the agreement number is just what triggers writing it.

### M.3 Metrics that matter

| Metric | Definition | Why |
|---|---|---|
| **Event recall / precision / F1** per `action_type` | Match on same `robot_ref`, same `action_type`, `\|Δt_start\| ≤ 1.0 s` | A field cannot be fit if the *event* isn't reproducibly detected. |
| **`place` start-boundary agreement** | Median `\|Δt_start\|` on matched `place` records specifically | §D.3 flags this as the ontology's weakest boundary; this metric decides whether the fallback definition is adopted. |
| **`gap_after` agreement** | Raw % agreement on the gap class, and on the `transit` subset specifically | The entire travel-time parameter rests on this one enum being reproducible. |
| **Outcome agreement** | Raw % on `outcome` and `failure_mode` | Reliability estimates are architecture-critical. |
| **Timing agreement** | Median and p90 of `\|Δt_start\|`, `\|Δduration\|` | Calibrates `timing_precision_s` empirically and floors any duration distribution M5 may claim. |
| **Snapshot agreement** | Do both passes' snapshots agree, and reconstruct to the official score? | **The most important check** — Gate V2's input, and the only one with ground truth. |
| **Reconciliation-channel agreement** | Do both passes produce similar per-channel results? | Distinguishes "the labeler missed events" from "the schema cannot capture this." |

**Deliberately not required:** κ, ICC, bootstrapped CIs. n is far too small for them to mean
anything.

### M.4 Thresholds — provisional by design
Aim: F1 ≥ 0.85 on `place`/`acquire`; ≥0.90 raw agreement on `outcome`; ≥0.85 on `gap_after`; median
`|Δt_start|` ≤ 0.5 s; exact snapshot-score agreement across passes. **Provisional until M3B
establishes a baseline.** If a field misses badly, the response is to **cut or redefine it, not to
try harder** — and every miss and resulting change is written into the protocol doc, including the
bad numbers.

---

## N. On-disk format

```
data/observations/
  README.md                              # updated: points at 07-observation-schema.md
  v5rc/
    2026-11-14_bay-area-signature_q041/
      match.yaml                         # hand-authored
      snapshots.yaml                     # hand-authored
      events.yaml                        # importer output (canonical)
      events.source.csv                  # human-authored provenance artifact; committed, not canonical (§K.2, §R)
      relabel/                           # pass_id: 2, M3C only
  qc/
    reconciliation-<match_key>.md
    relabel-agreement-<yyyy-mm>.md
```

Program directory makes the never-`both` rule structural, not merely validated. YAML matches every
other data file in the repo and adds no dependency. Three files because the layers have different
authorship moments and very different edit frequencies. **Append-only** per
`05-data-provenance-and-validation.md`: corrections are new passes or explicit amendments with a
note, never silent edits.

---

## O. What must NOT be labeled

1. Driver intent, strategy quality, decision quality.
2. Mechanical root cause — outcomes only (`dropped`), never diagnoses.
3. Exact velocity, coordinates, distances, 3D stack geometry.
4. Capability claims. No `capable`/`incapable` field. A non-attempt is not evidence.
5. Persistent global object identity (§C.7). Possession episodes only.
6. Every traversal — gaps are *classified*, not labeled as actions (§F.2).
7. Every robot contact — only contact meeting a `contested`/`interaction` definition.
8. Interference delay magnitude — derived by contrast in M5, never observed.
9. Subjective interference character — "aggressive," "dirty," "clean."
10. **An intended autonomous routine** (§C.9).
11. **Placed/Scored adjudication** — the labeler records physical stacking; `<SC2>`/`<SC3>` are
    M4's job via the existing scorer (§C.2).
12. Loose floor Pins/Cups in snapshots — the scorer never reads them.
13. Referee/violation adjudication from video — violations come from the published record.
14. Anything the labeler would have to guess. `unknown` is always available and is always the
    correct answer when the video does not show it.

---

## P. Files and dependencies (planned, not yet created)

**Docs (new)**
- `docs/design/07-observation-schema.md` — normative ontology and field reference (§A–§H, §N, §O).
- `docs/design/08-labeling-protocol.md` — procedure: workflow, boundary definitions, CSV column
  layout, do-not-label list, pilot selection, QC procedures and results. A design/procedure
  document, not an ADR; **no ADR is created for the reconstruction-anchor choice.**

Two documents because a schema *reference* and a *procedure* have different readers and different
revision cadences (the schema revises once at the M3B checkpoint; the protocol is amended after
every QC disagreement).

**Code (new — `src/vexu_sim/observations/`)**
- `__init__.py` — public exports, mirroring the `sources`/`rules`/`field_setup` package style.
- `models.py` — frozen dataclasses + enums: `MatchObservation`, `VideoMetadata`, `RobotEntry`,
  `OfficialResult`, `Coverage`, `Snapshot`, `GoalSnapshot`, `StackItem`, `ToggleSnapshot`,
  `RobotSnapshot`, `Action`, `LoaderVisit`, `MidfieldOccupancy`, `StateChange`, `Interaction`,
  `Incident`, plus `ActionType` (now `acquire | place | descore | toggle` — no `loader_visit`,
  Revision 2.1), `Region`, `GapClass` (now six values, including `no_next_action`), `Outcome`,
  `FailureMode`, `Contested`, `Confidence`, `IncidentType`, `ChangeType`. `LoaderVisit` is a
  top-level dataclass, not a variant nested in `Action`'s per-type details.
- `refs.py` — **the single boundary with existing packages.** Derives canonical ids from the public
  APIs below, and is the one place the genuinely M3-local vocabulary (Loader ids, Load-Zone region
  ids) is declared and marked as such.
- `loader.py` — `load_match_observation(path, *, rule_bundle)`, `load_all_observations(...)`,
  `ObservationValidationError`. Validation lives here, following `rules/loader.py`'s pattern (split
  out `validate.py` only if it exceeds ~250 lines).
- `reconcile.py` — the three-channel reconciliation (§H.2) and its report. Separate because M4 will
  extend it and it must never be confused with scoring.
- `from_csv.py` — the deterministic validated CSV→YAML importer (§K.2).

**Dependency resolution.** `observations` **reads** three stable public APIs and **modifies
nothing**:

| Needed | Read from | Why not duplicated |
|---|---|---|
| Program tag legality | `vexu_sim.sources.validate_empirical_program` | Already the single enforcement point for never-`both`. |
| Period bounds; endgame boundary | `vexu_sim.rules.RuleBundle.period_seconds()` and `periods.yaml` via the bundle | Timing values are versioned, cited rule data. Restating 15/105/30/90/10 inside `observations` would put a rule number in a non-rule store — exactly what `CLAUDE.md` forbids, and it would silently diverge at the next manual version. |
| Canonical Goal / Toggle / Quadrant ids | `vexu_sim.field_setup.build_v5rc_starting_state(bundle).match_state` → `.goals[*].id`, `.toggles[*].id`, `.quadrants[*].id` | These ids are already constructed in exactly one place. A hand-copied list in `observations` would drift the first time a Goal id changes. |
| Loader ids; Load-Zone region ids | **Declared in `refs.py` as M3-local** | No rule datum names them — `field.yaml` gives the Loader *count* (4) and the Load Zone *concept*, not names. Declared honestly as labeling vocabulary rather than passed off as rule-derived. |

`load_match_observation` takes an already-loaded `RuleBundle`, matching how `field_setup` takes one
— the caller owns rule loading, `observations` never reaches into `data/rules/` itself. **No
modifications to `model/`, `scoring/`, `field_setup/`, `rules/`, `sources/`. No new dependencies.**

**Validation the loader enforces** (each gets a test):
- `program` via `validate_empirical_program()` — rejects `both`.
- `size_class == unknown_v5rc` whenever `program == v5rc`.
- Every enum legal; **every `REQ-IF` condition checked in both directions** (present when required,
  absent when not applicable) — this is the rule that catches "required fields that don't apply."
- Action `video_t_end` is a number or `unknown`; `null` is rejected for `acquire`/`place`/`descore`/
  `toggle` (§E.3). `video_t_end > video_t_start` when both are numeric; equality rejected.
  `LoaderVisit.video_t_exit`, `MidfieldOccupancy.video_t_exit`, and `Incident.video_t_end` may be
  `null` (open-ended), since none of the three is an Action.
- `gap_after` present iff the robot is `cycle_labeled` (including `no_next_action` on that robot's
  chronologically-last Action of the Period). The loader recomputes `no_next_action` deterministically
  from the ordered per-robot, per-period Action list and treats a manually entered value that
  disagrees as an error, since "is there a next Action" is a data fact, not a judgement (§F.2).
- Every `robot_ref`, `retry_of`, `caused_by_action`, `loader_visit_id`, `departs_possession_id`
  resolves; `retry_of` acyclic; `loader_visit_id` resolves to a `LoaderVisit`, never to an `Action`.
- Possession episodes: per-robot, non-interleaved; `place.object` present in the open episode
  (warning); duplicate object type in one episode (warning, `<SG6>`); `possession_id` never appears
  on `LoaderVisit` (it has no such field) or on `descore` (present in the schema but always absent)
  — a value on either is an error.
- `target_goal_ref` / `toggle_ref` among the ids `field_setup` actually builds; `loader_ref` /
  `region` among `refs.py`'s declared vocabulary.
- Both snapshots present; all 9 Goals, 4 Toggles and every rostered robot present in each.
- `gap_after` present iff the robot is `cycle_labeled`.
- Events inside period bounds read from the `RuleBundle`.
- **Warnings, not errors** (surfaced in the QC report): overlapping actions; non-zero reconciliation
  delta; an event inside an `unlabeled_window`; an episode still open at match end.

**Tests (new)**
- `tests/fixtures/observations/` — a small **synthetic** match (2 robots, ~15–18 events, both
  snapshots, one deliberate `pin_and_cup` episode with two placements, one transport drop, one
  `descore{obscure}`, one `loader_visit` with `objects_acquired: 0` to prove a pass-through is not
  a failure, one `acquire{source: loader}` linked via `loader_visit_id`, and at least one robot's
  period-terminal Action carrying `gap_after: no_next_action`) so the suite never depends on the
  pilot corpus existing.
- `tests/test_observations.py` — one test per validation rule, plus reconciliation-math tests
  (especially the `obscure` +1 case), importer determinism, and a test that every committed pilot
  match loads and validates.

**Updated at the end of M3:** `data/observations/README.md`, `CLAUDE.md`, `README.md`,
`docs/roadmap.md`.

---

## Q. Execution split and acceptance criteria

### M3A — Schema + tooling (no real matches required)
1. `07-observation-schema.md` and `08-labeling-protocol.md` exist; every enum and field in
   `models.py` appears in 07 with definition, requirement level, and video-reliability rating.
2. `observations` package implemented per §P; **reads** the three public APIs, modifies nothing, no
   new dependencies.
3. Validator rejects every invalid case in §P, with a test each; `REQ-IF` checked both directions.
4. `reconcile.py` implements all three required channels; a unit test covers
   `descore{method: obscure}` contributing **+1**, and a test covers `unknown` endpoints producing
   `indeterminate` rather than an assumed value.
5. Importer is deterministic and refuses to emit on error; round-trip test on the synthetic fixture.
6. `LoaderVisit` is implemented and validated as its own record type, never as an `Action` variant;
   `acquire.loader_visit_id` resolves to it. `GapClass` includes `no_next_action`, and the
   loader/importer derives it deterministically from the ordered per-robot, per-period Action list
   rather than trusting a manually entered value (§F.2). Action `video_t_end` accepts only a number
   or `unknown` — never `null` — and a test confirms the importer rejects `null` there while still
   accepting it for `LoaderVisit.video_t_exit`, `MidfieldOccupancy.video_t_exit`, and
   `Incident.video_t_end`.
7. `pytest` green. **M3A closes with zero labeled matches.**

### M3B — Three-match pilot + schema checkpoint
0. **Match sourcing** — strata 1–3 (`baseline_clean`, `typical_broadcast`, `poor_video`), each with
   a published, retrievable official score. Its own time budget (§R.1).
1. Three matches labeled end-to-end, `fully_labeled` or with explicit `unlabeled_windows`, all
   loading and validating.
2. Reconciliation run on all three; per-channel report committed to `data/observations/qc/`.
   **Non-zero deltas are reported, not fixed by editing labels.**
3. `minutes_spent` and per-field `unknown` rates recorded and reviewed — the affordability answer.
4. **Schema-revision checkpoint.** Any field that proved unlabelable is removed or demoted to
   OPTIONAL, with the reason recorded; `schema_version` bumped; the three matches re-labeled under
   the revised schema if the change is not backward-compatible.
5. Specific questions M3B must answer: is the `place` start boundary usable (§D.3)? Is `gap_after`
   reproducible (§F.2)? Is `down_face` readable often enough for the score band to be tight (§H.2)?
   Do Loaders present nested Pin/Cup combinations (`verify` item, §C.3)? Did the three matches
   collectively reach the §L.1 breadth preference, and if not, which behaviors are deferred to
   M3C?

### M3C — Expanded pilot + QC
1. Five further matches (strata 4–8) after the schema stabilizes; **8 total**.
2. Corpus spans ≥3 events and ≥8 teams.
3. QC procedure (§M) run on 2 matches — single-labeler blinded re-label (**≥7-day delay, entirely
   inside M3C**) or multi-labeler agreement, whichever applies. All metrics computed and written
   into `08-labeling-protocol.md`, **including numbers that came out badly.**
4. Coverage check: every match's two snapshots contain everything §H.3 requires, verified
   structurally. **M3 scores nothing** — that boundary is what keeps M4/Gate V2 an independent test.
5. Any rule ambiguity surfaced during labeling goes through `CLAUDE.md`'s rule-gap workflow —
   manual first, both Q&A systems second — and only genuine `open` items reach
   `docs/open-questions.md`.
6. `CLAUDE.md` / `README.md` / `docs/roadmap.md` updated to mark M3 complete.

**CV future-proofing** (evaluated, not designed for): the schema is structured enough that a
detector could populate the same format — typed, timestamped, region-tagged records against stable
Goal/Toggle ids; `confidence` maps onto detector scores; `possession_id` is what a tracker
produces. Two places where manual reliability was chosen over CV convenience, deliberately: **no
persistent object ids** and **no coordinates**. Both are additive later — a CV pipeline can emit
richer data into a superset schema without invalidating a single hand-labeled record.

---

## R. Decisions log

Every item below was open in an earlier revision and is now settled (Revision 2.1, correction E).
Kept here as a record of what was decided and why, not as a checklist — **there are no remaining
"decision needed before M3A" items.**

1. **Match sourcing.** M3B begins with match sourcing as its own Step 0 (§Q, M3B item 0) — there is
   no assumption that candidate V5RC Override videos are already in hand. `poor_video` in
   particular needs deliberate searching, not whatever is on the front page.
2. **`events.source.csv` is committed** alongside the canonical `events.yaml`, one per labeled
   match (§N, §K.2). It is the human-authored provenance artifact; `events.yaml` remains canonical
   for every downstream reader. `labeling.source_csv_sha256` (§C.1) must be verifiable by re-hashing
   the committed CSV — a mismatch is a validation error, not a warning.
3. **`interaction` stays OPTIONAL through M3B** (§C.11). Its status — including whether
   `heavy_defense` (M3C, stratum 5, §L.1) requires promoting it to REQUIRED — is reconsidered at the
   M3B schema-revision checkpoint (§Q), with actual pilot counts in hand rather than a guess made
   now.

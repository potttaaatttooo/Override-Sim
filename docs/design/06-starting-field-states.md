# Starting Field states (M2)

Formal description of the official V5RC and VEX U starting Field configurations implemented in
`src/vexu_sim/field_setup/`. See `02-game-model.md` for the game rules and `03-state-and-scoring.md`
for the `MatchState`/scoring model this builds on. This document also records the verification task
`docs/roadmap.md` set for M2: "Determine exactly how the VEX U starting field differs from the V5RC
starting field and whether Figure VEXU-1 plus the Section 6 modifications fully define the VEX U
starting layout."

## Scope: structure, not simulation

`field_setup.build_v5rc_starting_state()` / `build_vexu_starting_state()` each return a
`StartingFieldState` -- a `MatchState` at `ScoringContext.START` (everything physically on the Field,
including Robots and their Preloads) plus the off-field Match Load inventory (`match_load_pins`,
`match_load_cups`) that is not on the Field until a Drive Team Member introduces it (`<SG11>`/`<VUG4>`).
Nothing here advances time, applies an action, or derives one snapshot from another -- consistent with
`03-state-and-scoring.md`'s "static scoring, not simulation" scope.

## Sources used

- Field Overview (p.8) and `data/rules/override/v1.1/field.yaml`: the V5RC aggregate Pin/Cup inventory
  by color combination and category (predetermined / preload / match load).
- Section 6 "Rule Modifications: Field Setup" (p.72) and `data/rules/override/v1.1/vexu.yaml`
  `field_setup`: the VEX U field layout and Match Load deltas.
- Appendix B Glossary: `Goal`, `Toggle`, `Quadrant`, `Match Load`, `Preload` entries -- structural
  facts (9 Goals: 2 red/2 blue Alliance, 4 neutral-short, 1 neutral-tall Midfield; 4 Toggles, one per
  Quadrant) and the "22 Pins, 11 per Alliance / 20 Cups, 10 per Alliance" Match Load total.
- Appendix B Figure Q-1: Quadrant labels ("Red 1", "Red 2", "Blue 1", "Blue 2"), reused as this
  project's Quadrant IDs.
- Appendix A "Scoring Object Locations" (dimensioned drawing, page A12): which Goals start with a Pin
  Placed. Unlike Figure FO-2 in the manual body -- which carries an explicit illustrative disclaimer
  ("Some figures may highlight or change the appearance of certain Field Elements and Scoring Objects
  to emphasize or clarify intent," Field Overview p.8) -- Appendix A is the dimensioned, non-illustrative
  drawing the Field Overview page itself points to for "exact Field dimensions, a full Field bill of
  materials, and exact details of Field construction." It was read at 300+ DPI, quadrant by quadrant,
  cross-checking each icon against the Pin/Cup/Goal/Toggle specification drawings' icon legend (solid
  color = a Pin's visible half color; a black/gray octagonal "gear" ring = a neutral Goal; a red or blue
  gear ring = an Alliance Goal; a 4-armed pinwheel = a Toggle; small plain-circle markers sitting exactly
  on tape-line intersections = AprilTag fiducials, confirmed against the separate "AprilTag
  Numbering/Locations" drawing, not Scoring Objects).
- Appendix A "Toggle Assembly - Starting Orientation" (page A15): an assembly drawing stating, for both
  Alliances' Toggles, "Yellow facing up and into the field, [Alliance color] facing out of the field" --
  the only place in the manual that states Toggle starting orientation in so many words.
- Figures VEXU-1 (overhead) and VEXU-2 (side view): the VEX U starting layout, cross-checked against the
  Section 6 field-setup bullet text.
- Both official Q&A systems (V5RC: 34 entries, `https://events.vex.com/faqs/51/pdf`; VURC: 3 entries,
  `https://events.vex.com/faqs/52/pdf`; both retrieved 2026-08-14) were searched for "starting",
  "predetermined", "configuration", "Toggle", "preload", and the relevant Figure numbers. Neither
  addresses starting Field configuration, predetermined Pin/Cup placement, or Toggle starting
  orientation -- consistent with the manual and Appendix A already fully answering these questions
  without needing a ruling.

## The M2 verification task, resolved

**Does Figure VEXU-1 plus the Section 6 modifications fully define the VEX U starting layout?** Yes.
Section 6's "Modified Field layout" bullet ("Only the Midfield Goal should begin the Match with a
yellow/yellow Pin Placed in it") is a complete, unambiguous statement once cross-checked against Figure
VEXU-1: every non-Midfield Goal shows the same "empty" icon used throughout Appendix A, and the Field
shows no Cup icon anywhere (VEX U's Cup total -- 20, all Match Loads -- is confirmed by
`vexu.yaml: field_setup.match_loads`, and is smaller than V5RC's 56 precisely because VEX U has no
on-Field predetermined Cups at all). Quadrant/Goal/Toggle *structure* and Toggle starting orientation are
unmodified by Section 6 (neither is listed in `overrides_base_rule_ids`), so both programs share the
same `_build_quadrants_goals_toggles()` helper in `field_setup/starting_state.py`.

## V5RC starting configuration

- **Goals**: all 4 Alliance Goals (2 red, 2 blue) start **empty**. All 4 neutral-short Goals and the
  Midfield Goal each start with **one yellow/yellow Pin Placed directly on the Goal** (no Cup involved)
  -- 5 Pins total, all unowned at kickoff since every Toggle starts neutral.
- **Toggles**: all 4 start seated, orientation yellow, uncontacted -- `effective_color == YELLOW`
  (neutral) for every Toggle at kickoff.
- **Remaining on-Field Pins**: the Field Overview's predetermined counts (4 red/blue, 8 red/yellow, 8
  blue/yellow, 17 yellow/yellow = 37 total) include the 5 Pins above; the other 32 are on the Field but
  **not Placed on any Goal** (`goal=None`) -- see "Deliberately not represented" below.
- **On-Field Cups**: all 36 predetermined Cups (24 start gray-side-up, 12 clear-side-up) are on the
  Field but not nested to anything (`goal`/`occupant` concepts don't apply to a Cup that isn't stacked).
- **Preloads**: 4 Robots, each holding one Preload Pin (`<SG5>`) -- red-Alliance Robots preload
  red/yellow, blue-Alliance Robots preload blue/yellow. On the Field (held by a Robot), not Placed.
- **Match Loads** (off-Field, in the Loader): 10 red/yellow + 1 yellow/yellow Pins and 10 Cups for red;
  10 blue/yellow + 1 yellow/yellow Pins and 10 Cups for blue -- 22 Pins / 20 Cups total, matching the
  Glossary's "Match Load" entry ("22 Pins, 11 per Alliance, ... 20 Cups, 10 per Alliance").
- **Totals check**: on-Field/held (41 Pins, 36 Cups) + Match Loads (22 Pins, 20 Cups) = 63 Pins / 56
  Cups, reproducing the Field Overview's own totals exactly (`test_v5rc_total_inventory_matches_field_overview`).

## VEX U starting configuration

- **Goals**: all 8 non-Midfield Goals start **empty**. The Midfield Goal starts with **one yellow/yellow
  Pin Placed** -- the only Pin on the Field at kickoff besides Preloads.
- **Toggles**: identical starting orientation to V5RC (unmodified by Section 6).
- **On-Field Cups**: **none**.
- **Preloads**: 4 Robots (one 24" + one 15" per side, `<VUR1>`), each holding one Preload Pin -- `<SG5>`
  is not in `vexu.yaml`'s `overrides_base_rule_ids`, so it applies unmodified; combined with `<VUR1>`'s
  2-Robots-per-Team this yields the same 2 red/yellow + 2 blue/yellow Preload pattern as V5RC.
- **Match Loads**: per `vexu.yaml: field_setup.match_loads` -- red: 10 Cups, 10 red/yellow Pins, 3
  yellow/yellow Pins; blue: 10 Cups, 10 blue/yellow Pins, 3 yellow/yellow Pins (26 Pins / 20 Cups total).
  VEX U's manual does not state a combined Pin/Cup total the way V5RC's Field Overview does; the derived
  total (5 on-Field/held + 26 Match Load = 31 Pins; 0 on-Field + 20 Match Load = 20 Cups) is a
  consequence of already-cited facts, not a new source claim.

## Exact V5RC vs. VEX U differences

| | V5RC | VEX U |
|---|---|---|
| Alliance Goals at start | empty (both programs) | empty (both programs) |
| Neutral-short Goals at start | 1 yellow/yellow Pin each | empty |
| Midfield Goal at start | 1 yellow/yellow Pin | 1 yellow/yellow Pin |
| On-Field loose (unplaced) Pins | 32 | 0 |
| On-Field Cups | 36 | 0 |
| Match Load Pins | 22 (11/Alliance) | 26 (13/Alliance) |
| Match Load Cups | 20 (10/Alliance) | 20 (10/Alliance) |
| Match Load availability | Driver Controlled Period only (`<SG11>c`) | both periods (`<VUG4>`) |
| Preloads | 2 red/yellow + 2 blue/yellow (1/Robot, 4 Robots) | 2 red/yellow + 2 blue/yellow (1/Robot, 4 Robots) |

## Deliberately not represented

- **Exact floor position of V5RC's 32 unplaced on-Field Pins (and all 36 on-Field Cups).** Appendix A's
  "Scoring Object Locations" drawing precisely dimensions only objects at fixed Goal/Toggle mount
  points; the Field Overview text gives a count and color-combination breakdown for the rest, not a
  location, and Figure FO-2 (the only figure that shows more objects scattered around the Field) is
  explicitly marked illustrative. Modeling an exact per-Goal stack topology for these Pins/Cups would
  mean inventing placements no official source states -- prohibited by CLAUDE.md's rule-gap workflow.
  This does not block M4 (match reconstruction), which will use real observed match states, not a
  synthetic fully-detailed V5RC kickoff stack.
- **Coordinates**, per `03-state-and-scoring.md`'s existing scope boundary -- unchanged by M2.
- **Cup gray/clear starting-orientation**, per-object. `field.yaml` records the aggregate counts (24
  gray-up, 12 clear-up) for provenance, but no current scoring predicate reads which face of an unplaced
  Cup is up, so no `Cup` field was added for it (see "Model change," below).

## Model change: `Pin.goal` becomes `Optional[Goal]`

The only core-model change M2 required: `Pin.goal` was mandatory (every fixture built so far represented
an already-Placed Pin). Representing a Pin that is on the Field but not yet Placed on any particular
Goal's stack -- a loose predetermined Pin, or a Preload held by a Robot -- needed a way to say "this Pin
has no grounding Goal yet." `Pin.goal: Optional[Goal] = None` is the smallest change that allows this: no
scoring function reads `pin.goal` unless `is_pin_placed(pin)` is already true (via `rests_on`/`occupant`,
which is unaffected), so `goal=None` on an unplaced Pin is inert to every existing M0/M1 test and
scoring path. `ScoringContext.START` was added alongside it (also purely descriptive, unread by
`scoring.py`) so a starting-state snapshot doesn't have to misuse `AUTONOMOUS_END`/`MATCH_END`.

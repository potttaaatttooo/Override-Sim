# State and scoring (M1)

Formal description of the state model and scoring engine implemented in `src/vexu_sim/model/`
and `src/vexu_sim/scoring/`. See `02-game-model.md` for the game rules this evaluates and
`data/rules/override/v1.1/` for the cited rule data. Rule-defined numeric/boolean thresholds (e.g.
Autonomous Win Point Pins-Scored/qualifying-Goals counts) are not hardcoded in scoring code -- they
are read at runtime from the versioned, cited `RuleBundle` via its `AWPRequirements`
(`awp_requirements`) accessor and similar effective/composed accessors (see "Program dispatch"
below). `scoring.yaml`/`vexu.yaml` still carry the original plain-English `conditions` lists
alongside the structured `requirements` data, so both a human and the scorer can verify the same
rule the same way.

## Scope: static scoring, not simulation

`MatchState` is one fully-formed snapshot of the Field at a single instant -- the end of the
Autonomous Period, or the end of the Match. It is not a live/mutable simulation state; nothing in
`model/` or `scoring/` advances time, applies an action, or derives one snapshot from another.
Two different snapshots (an autonomous-end one and a match-end one) are constructed independently
by the caller (test fixture, and eventually a labeled observation in M4) and scored independently;
`autonomous_bonus()` output from the first is threaded into `score_breakdown()` for the second.

## What is deliberately not represented

- **Coordinates.** No (x, y, z), no field dimensions, no distances. Every spatial fact the rules
  actually require (which Quadrant a Goal is in, which side of the Autonomous Line that is,
  whether a Robot is in the Midfield or touching the Perimeter) is represented as a direct typed
  fact or relationship, not derived from geometry.
- **Drivetrain motion, path planning, collision geometry, travel-time modeling.** Nothing moves.
- **Stochastic behavior.** No RNG anywhere in `model/` or `scoring/`.
- **The physical stacking process.** `MatchState` records the *result* of stacking (who is nested
  in what, right now) as given/observed data, the same way a human labeler or a test fixture would
  record it -- it does not simulate a Robot placing a Pin, and it does not defensively re-derive or
  validate physical plausibility (e.g. that a Cup can't float without something under it). Trust
  the input, matching this project's general style of trusting internal/constructed data.
- **Violations beyond the pass/fail flag `SC7`/`SC8`/`VUG6` need.** `MatchState.autonomous_violations`
  is a `frozenset[Alliance]` of which Alliance(s) committed a Violation during the Autonomous
  Period -- enough to drive the Autonomous Bonus swap (`<SC7>c/d`) and Autonomous Win Point
  disqualification (`<SC8>`/`<VUG6>`: "no Violations during the Autonomous Period"). No Violation
  taxonomy, Major/Minor distinction, or point-deduction ledger is modeled; scoring never deducts
  Violation points itself (Referees do that per `<SC1>e`).

## The Placed -> Scored -> Owned chain, as data

The atomic scoring unit is a Pin *half* (`02-game-model.md`). The model mirrors the manual's own
recursive language for `<SC2>` directly, using explicit nesting relationships rather than a
generic "stack list," because the rule text ("nested with a Goal, or with a Cup that is nested
with another Placed Pin") and the Figure SC2-2 capacity edge case are both about a specific
nesting relationship between two adjacent objects, not about stack order or geometry.

### The stack/slot representation

- A **`Goal`** provides exactly one nesting slot (`occupant: Occupant | None`) -- "Each Goal ...
  contains a maximum of one Pin half" (`<SC2>a.ii`).
- A **`Cup`** provides exactly two nesting slots, one per half (`opaque.occupant`,
  `transparent.occupant`), matching "each half of a Cup ... contains a maximum of one Pin half."
- Each **`Pin`** half (`PinHalf.rests_on`) points at the single slot (a `Goal` or a `CupHalf`) it
  is *attempting* to nest into. This is the physical claim.
- Each slot's `occupant` field (an `Occupant(pin, half)` pair) is the single *adjudicated* fact of
  which Pin half actually holds that slot's one-half capacity -- set once, as given/observed data.

Separating the claim (`rests_on`) from the adjudicated fact (`occupant`) is what lets the model
represent Figure SC2-2 directly: a second Pin half can have `rests_on` pointing at an already-full
slot (its `occupant` names a *different* Pin half). `is_pin_placed` only counts a half as actually
nesting when both agree; when they disagree, that half simply isn't Placed via that slot -- exactly
the manual's "the Pin resting on top is not considered Placed" outcome, without needing a separate
"reject" code path.

- **`Pin.goal`** is a direct reference to the Goal the Pin's stack is built on (its Quadrant, and
  therefore Toggle and Autonomous-Line side, follow from that Goal). This is recorded directly
  rather than derived by walking the nesting chain down through intermediate Cups: nothing in the
  rules needs the intermediate chain itself, only which Goal grounds it, and re-deriving it via
  traversal would be exactly the kind of physics-flavored computation this milestone avoids.
  `Pin.goal` is `Optional` (M2, `docs/design/06-starting-field-states.md`): `None` for a Pin that
  is on the Field but not yet Placed on any Goal's stack -- a loose predetermined starting Pin, or
  a Preload held by a Robot. No scoring function reads `pin.goal` unless `is_pin_placed(pin)` is
  already true via `rests_on`/`occupant`, so this is inert to every Placed-pin code path.

### Placed (`<SC2>`)

`is_pin_placed(pin)`: true if some half's `rests_on` slot exists and its `occupant` names that
same `(pin, half)`, and that slot is either a `Goal` directly, or a `CupHalf` whose owning `Cup` is
itself Placed (recursive, grounded at a `Goal`).

`is_cup_placed(cup)`: true if either of the Cup's two slots has an `occupant` whose Pin is itself
Placed.

### Scored / visibility (`<SC3>`)

`is_half_visible(pin, half)`: false only when that half's adjudicated slot is a `CupHalf` with
`kind == "opaque"` -- "nested" is defined (`<SC2>` red box) as one Pin half breaking the plane of a
Cup's opening, which is exactly the `rests_on`/`occupant` relationship above; visibility is a
property of *which* slot a half occupies, already captured by the same relationship used for
Placed. No separate "hidden" flag is needed.

### Owned (`<SC5>`) and Toggle state (`<SC4>`)

- **`Toggle.effective_color`**: the Toggle's recorded `orientation` (`red`/`blue`/`yellow`) if
  `seated` and not `contacted_by_robot`; otherwise `yellow` (the manual's own default-to-neutral
  rule, `<SC4>`). `contacted_by_robot` is the one Robot-Toggle interaction the rules require at
  scoring time; there is no general Robot/Toggle contact history.
- **`Quadrant.alliance_side`**: red or blue, matching "each Quadrant is described as red or blue
  based on the Alliance-colored Goal it includes" (`field.yaml: zones.quadrant`, Field Overview
  p.8). A yellow Pin's owner in a Quadrant is whichever Alliance the Quadrant's Toggle is
  `effective_color`-set to (`<SC5>a`).
- A yellow Pin in the Midfield Goal (`Goal.quadrant is None`) is owned by whichever Alliance has
  more Robots `in_midfield` in this snapshot (`<SC5>b`), or unowned on a tie.

### Autonomous Line side, for the Autonomous Win Point (`<SC8>`/`<VUG6>`) -- PROVISIONAL

`<SC8>`/`<VUG6>` exclude "Pins Scored in Quadrants on the opposing side of the Autonomous Line"
from the pin/goal thresholds. The manual does not spell out, in so many words, which two of the
four Quadrants are "your side" -- but Figure FO-1 places the red Alliance Station and both red
Quadrants (by alliance-Goal color) on one half of the field and blue's on the other, and Quadrants
are already defined as red/blue by the Alliance-colored Goal they contain (Field Overview, p.8).
This model therefore treats **"your side of the Autonomous Line" as "Quadrants whose
`alliance_side` matches your Alliance"** -- i.e. the same red/blue Quadrant coloring already cited
elsewhere, not a new fact. This is a spatial-encoding judgment call, not a literal manual quote, and
it drives real AWP scoring behavior (`AWPRequirements.excludes_opposing_side_of_autonomous_line`,
see below), so it is recorded as **PROVISIONAL** in `docs/open-questions.md` (#2), not merely as a
manual-review note, until an official ruling confirms or corrects it.

Similarly, `<VUG6>`.4 ("At least one (1) Robot is within the Midfield") does not restate "for your
Alliance" the way conditions 1-2 do. This model reads it as continuing to refer to the achieving
Alliance's own Robots (`AWPRequirements.requires_robot_in_midfield`, checked against only that
Alliance's Robots), consistent with the rest of the same checklist and with VEX U's Alliance
redefinition (Section 6: "Alliance" = a Team's own two Robots) -- also **PROVISIONAL**, recorded in
`docs/open-questions.md` (#3).

## MatchState

```
MatchState:
  program: "v5rc" | "vexu"
  scoring_context: START | AUTONOMOUS_END | MATCH_END   # which instant this snapshot represents
  goals: list[Goal]
  pins: list[Pin]
  cups: list[Cup]
  quadrants: list[Quadrant]
  toggles: list[Toggle]
  robots: list[Robot]
  autonomous_violations: frozenset[Alliance]
```

`Robot` carries only the predicates the rules need: `alliance`, `program`, `in_midfield`,
`contacting_perimeter`. No position, no size, no capability.

## Scoring function contracts

All functions in `src/vexu_sim/scoring/` are pure: `(MatchState, RuleBundle) -> value` (or a
subset of that signature when one input is unused), with no RNG, I/O, LLM/web calls, or mutation
of their inputs. The same inputs always produce the same output.

- `is_pin_placed(pin) -> bool`
- `is_cup_placed(cup) -> bool`
- `is_half_visible(pin, half) -> bool`
- `yellow_pin_owner(pin, match_state) -> Alliance | None`
- `half_owner(pin, half, match_state) -> Alliance | None` -- combines Placed + visible + color/Owned
  into "which Alliance (if any) this half is Scored for."
- `midfield_robot_counts(match_state) -> dict[Alliance, int]`
- `autonomous_bonus(match_state, rule_bundle) -> dict[Alliance, int]` -- call with an
  `AUTONOMOUS_END` snapshot. Applies the V5RC/VEX U Midfield-inclusion difference via
  `rule_bundle.autonomous_bonus_includes_midfield`, and the Violation swap/cancel rule.
- `autonomous_win_point(match_state, alliance, rule_bundle) -> bool` -- call with an
  `AUTONOMOUS_END` snapshot. Reads every threshold from `rule_bundle.awp_requirements`
  (`AWPRequirements`); contains no rule-version-specific literal values itself.
- `score_breakdown(match_state, rule_bundle, autonomous_bonus_points) -> ScoreBreakdown` -- call
  with a `MATCH_END` snapshot; takes the already-computed `autonomous_bonus()` result as input
  rather than recomputing it, since that value is fixed at the Autonomous/Driver boundary
  (`<SC7>`) and the Match-end snapshot cannot re-derive it.

## Program dispatch

Scoring functions read `rule_bundle.point_values`, `rule_bundle.autonomous_bonus_includes_midfield`,
and `rule_bundle.program` -- the effective/composed accessors on `RuleBundle` (see
`rules/models.py`) -- and never inspect `rule_bundle.data["vexu_overlay"]` directly or branch on
"is this key present in the overlay." Autonomous Win Point thresholds (min Pins Scored, min
qualifying Goals, min Pins per qualifying Goal, and the perimeter-contact / opposing-side /
Robot-in-Midfield booleans) are read from `rule_bundle.awp_requirements` -- a structured
`AWPRequirements` view over the `requirements` block newly added to
`autonomous_win_point_criteria_v5rc` (scoring.yaml) and `autonomous_win_point_criteria`
(vexu.yaml), each still covered by that block's existing `sources` citation (`<SC8>`/`<VUG6>`) and
still accompanied by the original plain-English `conditions` list. `scoring.py` contains no
literal `7`, `3`, `12`, or `4` for these thresholds; changing a value in the YAML changes scoring
output without touching `scoring.py`.

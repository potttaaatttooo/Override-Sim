# Game model: Override (2026-2027 season)

Formal description of the game this project scores and (eventually) simulates. Every claim below
cites the Game Manual v1.1 or an official Q&A ruling; see `data/rules/override/v1.1/` for the
machine-readable, individually-cited version of this same information. This document is prose for
humans; the YAML files are the source of truth a program reads.

## Entities

- **Pin** — a Scoring Object with two halves, each colored red, blue, or yellow. Four color
  combinations exist: red/blue (starts predetermined only), red/yellow, blue/yellow,
  yellow/yellow. (Glossary, p.B8; Field Overview, p.8.)
- **Cup** — a Scoring Object with an opaque half and a transparent half. Scores zero points
  directly; it is purely structural — it extends a stack so more Pins can be `Placed`, and its
  *opaque* half can hide a Pin half so that half stops counting as `Scored`. (`<SC2>a.i`, p.14;
  `<SC3>`, p.15.)
- **Goal** — one of 9 locations where Pins/Cups are stacked: 4 Alliance-colored (2 red, 2 blue)
  and 5 neutral (4 short in the Quadrants, 1 tall in the Midfield). (Glossary, p.B5; Field
  Overview, p.8.)
- **Toggle** — one of 4 triangular Field Elements, one per Quadrant, that can be set to red, blue,
  or neutral (yellow) and thereby controls Ownership of yellow Pins in that Quadrant.
  (`<SC4>`/`<SC5>`, p.15-16.)
- **Loader** — one of 4 locations (two per Alliance) where Drive Team Members introduce Match
  Load Scoring Objects during the Match. (`<SG11>`, p.24.)
- **Quadrant** — one of 4 triangular Field areas, each containing 2 Goals and 1 Toggle. (Glossary,
  p.B9.)
- **Midfield** — the central square area; Robots contest it, especially in the final 10-second
  Endgame. (Glossary, p.B7.)
- **Load Zone** — the protected volume around each Loader. (Glossary, p.B6.)

## The Placed → Scored → Owned chain

This is the core of the scoring model, and the atomic scoring unit is a **Pin half**, not a whole
Pin — confirmed by the manual's own worked example (p.17): one stack of Pins under a red Toggle
scores Red 45 / Blue 5, which only makes sense if each half is scored independently.

1. **Placed** (`<SC2>`) — a Pin is Placed if it nests with a Goal, or with a Cup that nests with
   another Placed Pin; each Goal/Cup-half holds a maximum of one Pin half. A Cup is Placed if it
   nests with a Placed Pin. Robot contact does not negate Placed status. A Pin resting on a Cup
   half that *already* holds a Pin half is **not** Placed (Figure SC2-2) — capacity is a hard
   per-slot constraint, not a counter.
2. **Scored** (`<SC3>`) — each half of a Placed Pin is independently Scored if it remains fully
   visible (not nested inside a Cup's *opaque* half). Red/blue halves score for their Alliance
   automatically; yellow halves score only if `Owned`.
3. **Owned** (`<SC5>`) — a yellow Pin is Owned by whichever Alliance's color the Quadrant's Toggle
   is set to (or, in the Midfield, by whichever Alliance has more robots there at the relevant
   end-of-period moment — see the auton-boundary note below).

## Point values (`data/rules/override/v1.1/scoring.yaml: point_values`)

| Item | Points |
|---|---|
| Scored red/blue Pin half | 5 |
| Scored yellow Pin half (Owned) | 10 |
| Robot ending in Midfield | 8 |
| Autonomous Bonus | 12 (6 each on a tie) |

## Periods

V5RC: 15s Autonomous, 105s (1:45) Driver Controlled, Endgame = last 10s. VEX U: 30s Autonomous,
90s Driver Controlled (`<VUT4>`/`<VUT5>`, p.78). `<SC1>`'s 5-second scoring grace period applies
only at the END of the Match, not at the Autonomous/Driver boundary — confirmed by qna:3188.

## Autonomous Bonus and Autonomous Win Point

The Autonomous Bonus (12 pts, 6/6 on tie) goes to whichever Alliance has more points at the end of
the Autonomous Period. **Critically, for V5RC this excludes Midfield-position-dependent scoring**
(Robots ending in Midfield, Midfield yellow Pin ownership) because those statuses are, by
definition, evaluated only at the end of the *Match* — the Autonomous Period is not the end of the
Match (`<SC6>`, `<SC7>`, confirmed verbatim by qna:3188). VEX U is the exception: `<VUG5>`
explicitly makes these scoring methods active at the end of the Autonomous Period as well as at
the end of the Match — also confirmed by qna:3188's holding, in the same ruling.

The Autonomous Win Point (`<SC8>` for V5RC, `<VUG6>` for VEX U — see below) is a separate
pass/fail bonus requiring Pin/Goal thresholds and no Robot contacting the Field Perimeter.

## VEX U deltas (Section 6)

- **Format**: 1v1, not 2-team Alliances. Each Team fields two Robots — one ≤24×24×24", one
  ≤15×15×15" (`<VUR1>`, `<VUT1>`, p.78-79).
- **"Alliance" is redefined** for VEX U as "a grouping of two (2) Robots from the same Team" —
  i.e. a Team's own pair, not two Teams (Section 6, VURC Definitions, p.71). This single
  redefinition is why V5RC's Alliance-scoped statistics (Win Points, Autonomous Points, Strength
  of Schedule Points, and the `<T13>` ranking tiebreaker order) apply directly to VEX U's 1v1
  format without needing separate rules: "your Alliance" already means "your own two Robots."
- **Timing**: 30s Autonomous, 90s Driver Controlled, immediately following (`<VUT4>`/`<VUT5>`).
- **Field setup**: only the Midfield Goal starts with a Pin Placed; extra yellow/yellow Match
  Loads (`Rule Modifications: Field Setup`, p.72).
- **Match Loads available during both periods** (`<VUG4>`), not just Driver Controlled as in V5RC
  — and cover both Pins and Cups, confirmed by qna:3134.
- **Autonomous Bonus includes Midfield-dependent scoring** at the Autonomous Period boundary
  (`<VUG5>`, confirmed by qna:3188 — see above).
- **Autonomous Win Point criteria are harder and different**: 12 Pins Scored (not 7), 4 Goals with
  ≥2 Pins Scored each (not 3), plus a new requirement that ≥1 Robot be in the Midfield
  (`<VUG6>`, p.75).
- **Load Zone protection applies during both periods**, not just Driver Controlled (`<VUG7>`).

## Inherited rules with surprising consequences

Rules that are *not* modified for VEX U but produce non-obvious results when combined with VEX U's
other deltas:

- **`<SG2>` horizontal expansion (24"×24" cap) is not listed as modified in Section 6.** Taken
  literally, the 24" robot — which already starts at the cap — has zero legal horizontal
  expansion headroom for the entire Match, while the 15" robot retains 9" of headroom per axis.
  This is architecturally consequential (it bears directly on whether wide intake/manipulation
  mechanisms belong on the 24" or 15" robot) and was **not** resolved by either official Q&A
  system as of 2026-08-14 (34 V5RC entries and 3 VURC entries, all checked). Tracked as `open` in
  `docs/open-questions.md`.
- **`<SG3>` vertical expansion (50" cap) is likewise unmodified** but produces no surprising
  interaction — recorded here for completeness, not because it's ambiguous.
- **`<SG6>` possession limit (1 Pin + 1 Cup) is unmodified**, and combined with VEX U's two-robot
  format, doubles a Team's simultaneous carrying capacity relative to a single V5RC robot without
  changing per-robot throughput at all — a capability-modeling input, not a rule question.

## Win conditions

A Match's winner is whichever Alliance (V5RC) or Team (VEX U) has the higher final score, which is
the sum of Scored Pin-half points, Robot-ending-in-Midfield points, and the Autonomous Bonus,
minus any point effects of Violations. Ties, tiebreakers, and elimination-bracket structure are
Tournament Rules (Section 5/`<T13>`-`<T19>`) and are out of scope for the scoring engine — they
govern event outcomes, not match scores.

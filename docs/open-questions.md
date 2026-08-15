# Open questions

Genuinely unresolved rule ambiguities only — items that survived the rule-gap workflow in
`CLAUDE.md` (re-read the manual, search both official Q&A systems, then classify) without being
answered. Do not add an item here without having done that first; do not silently resolve a
genuine ambiguity either. See `docs/design/02-game-model.md`, "Inherited rules with surprising
consequences," for the reasoning behind #1.

## 1. Does `<SG2>` (24"×24" horizontal expansion cap) apply unmodified in VEX U?

**Why it matters:** Section 6 does not list `<SG2>` among the rules it modifies. Taken literally,
the 24" robot — which starts at the cap — has zero legal horizontal expansion for the entire
Match, while the 15" robot retains 9" of headroom per axis. This is architecturally consequential:
it bears directly on whether wide intake/manipulation mechanisms should go on the 24" or 15"
robot, which is exactly the kind of question this project exists to answer.

**Checked:** Full manual re-read of Section 6 (Rule Modifications: Robot, p.79-84) — `<SG2>` is
not listed. Full V5RC Override Q&A checked (34 entries, `https://events.vex.com/faqs/51/pdf`,
retrieved 2026-08-14) — no entry addresses `<SG2>` in a VEX U context. Full VURC Override Q&A
checked (3 entries, `https://events.vex.com/faqs/52/pdf`, retrieved 2026-08-14) — no entry
addresses this either.

**Current working assumption:** None adopted. `data/rules/override/v1.1/robot_limits.yaml`
records the V5RC rule as-is and flags this applicability question in a `vexu_applicability` note
rather than guessing an answer; `vexu.yaml` lists `SG2a` in `overrides_base_rule_ids` to keep it
tracked even though no VEX U-specific value has been recorded.

**Resolution path:** Submit a question to the official VURC Q&A system, or wait for a future
manual version (v2.0+) to clarify. Re-check both Q&A systems before each new manual version is
added (see `data/rules/CHANGELOG.md`).

## 2. Which Quadrants are "the opposing side of the Autonomous Line" for `<SC8>`/`<VUG6>`?

**Exact question:** `<SC8>` (V5RC) and `<VUG6>` (VEX U) both exclude "Pins Scored in Quadrants on
the opposing side of the Autonomous Line" (and "Goals in Quadrants on the opposing side of the
Autonomous Line") from the Autonomous Win Point's Pins-Scored and qualifying-Goals thresholds.
Neither rule, nor the Glossary's "Autonomous Line" entry, states in so many words which two of the
Field's four Quadrants count as "your side" for a given Alliance.

**Why it matters:** This directly gates Autonomous Win Point scoring for both programs -- it
decides which Goals' scored Pins count toward the 7-Pin/3-Goal (V5RC) or 12-Pin/4-Goal (VEX U)
thresholds. Scored incorrectly, an Alliance's AWP could be wrongly granted or wrongly denied.

**Checked:** Full re-read of `<SC8>` (p.18), `<VUG6>` (p.75), the Glossary's Autonomous Line and
Quadrant entries (p.B2, p.B9), and the Field Overview (p.8). Figure FO-1 (p.9) shows the two
diagonal Autonomous Line tapes forming an X that divides the Field into the same four triangular
Quadrants already defined elsewhere, with the red Alliance Station and both red-colored Quadrants
on one half of the Field and blue's on the other. No sentence anywhere states "your side" in terms
of Quadrant color. Full V5RC Override Q&A checked (34 entries, `https://events.vex.com/faqs/51/pdf`,
retrieved 2026-08-14) -- no entry addresses this. Full VURC Override Q&A checked (3 entries,
`https://events.vex.com/faqs/52/pdf`, retrieved 2026-08-14) -- no entry addresses this either.

**Current implementation behavior -- PROVISIONAL, not confirmed official truth:**
`AWPRequirements.excludes_opposing_side_of_autonomous_line` (`src/vexu_sim/rules/models.py`,
consumed by `autonomous_win_point()` in `src/vexu_sim/scoring/scoring.py`) treats "your side" as
"Quadrants whose `alliance_side` matches your Alliance" -- i.e. the same red/blue Quadrant coloring
already cited in `field.yaml: zones.quadrant` (Field Overview, p.8), inferred from Figure FO-1's
layout rather than quoted from a rule. This is recorded in `data/rules/override/v1.1/scoring.yaml`
and `vexu.yaml` (`requirements` block comments) as PROVISIONAL. It is a reasonable reading with no
plausible alternative found, but it is an inference, not an official ruling, and it drives real AWP
scoring output. Do not treat AWP results computed under this assumption as validated against an
official source until a ruling confirms or corrects it.

**Resolution path:** Submit a question to the official V5RC and/or VURC Q&A system asking which
Quadrants count as "your side" of the Autonomous Line. Re-check both Q&A systems before each new
manual version is added.

## 3. Whose Robot satisfies `<VUG6>`.4 ("At least one (1) Robot is within the Midfield")?

**Exact question:** `<VUG6>`'s four Autonomous Win Point conditions for VEX U are: (1) "At least
twelve (12) Pins Scored for your Alliance", (2) "At least four (4) Goals each contain at least two
(2) Pins Scored for your Alliance", (3) "Neither Robot is contacting the Field Perimeter", (4) "At
least one (1) Robot is within the Midfield." Conditions 1-2 explicitly say "for your Alliance";
condition 4 does not say whose Robot must be in the Midfield.

**Why it matters:** This gates the fourth VEX U Autonomous Win Point requirement. Read one way (any
Robot on the Field, either Team's), a Team could earn this condition off the *opposing* Team's
Robot being in the Midfield -- which would be a strange design given conditions 1-3 all constrain
the achieving Team. Read the other way (one of the achieving Team's own two Robots), it is
consistent with the rest of the checklist. The two readings can disagree on whether the AWP is
earned.

**Checked:** Full re-read of `<VUG6>` (p.75) and Section 6's redefinition of "Alliance" as "a
grouping of two (2) Robots from the same Team" (VURC Definitions, p.71). Full V5RC Override Q&A
checked (34 entries, `https://events.vex.com/faqs/51/pdf`, retrieved 2026-08-14) -- no entry
addresses this (V5RC has no equivalent condition; `<SC8>` has only three conditions). Full VURC
Override Q&A checked (3 entries, `https://events.vex.com/faqs/52/pdf`, retrieved 2026-08-14) -- no
entry addresses this either.

**Current implementation behavior -- PROVISIONAL, not confirmed official truth:**
`AWPRequirements.requires_robot_in_midfield` (`src/vexu_sim/rules/models.py`, consumed by
`autonomous_win_point()` in `src/vexu_sim/scoring/scoring.py`) is checked only against the
achieving Alliance's own Robots (`match_state.robots` filtered to that Alliance), not the whole
Field. This is recorded in `data/rules/override/v1.1/vexu.yaml` (`requirements` block comment) as
PROVISIONAL. It is the reading consistent with the surrounding checklist and VEX U's Alliance
redefinition, but it is an inference, not an official ruling.

**Resolution path:** Submit a question to the official VURC Q&A system asking whose Robot
`<VUG6>`.4 refers to. Re-check the VURC Q&A before each new manual version is added.

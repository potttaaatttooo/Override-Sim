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

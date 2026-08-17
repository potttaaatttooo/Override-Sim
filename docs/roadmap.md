# Roadmap

Each milestone is sized for one or two short, focused sessions — see `CLAUDE.md` "Session
hygiene." Empirical work (M3-M5) precedes stochastic behavior modeling (M6+), so there are no
entrenched guessed priors to unlearn later.

- **M0 — Rules foundation.** *(Session A — complete)* Repo scaffolding, `CLAUDE.md`, design docs
  01/02/05 (+ 04 stub), the source/provenance model, the Override v1.1 rule bundle (base + VEX U
  overlay) with per-datum citations, the loader/validator, and tests. No CLI — deferred until a
  real human-facing workflow needs one.
- **M1 — Deterministic scoring.** *(Session B — complete)* MatchState dataclasses (only the
  rule-required location predicates — no coordinates, no zone graph) + pure scoring functions +
  golden tests against the manual's own worked examples (p.17) and rule edge cases. → **Gate V1**
- **M2 — Initial field states.** *(complete)* V5RC and VEX U starting configurations encoded in
  `src/vexu_sim/field_setup/` from Appendix A ("Scoring Object Locations," "Toggle Assembly -
  Starting Orientation") and Figures FO-2/VEXU-1/VEXU-2; the VEX U-vs-V5RC layout question is
  resolved in `docs/design/06-starting-field-states.md`. Inventory-sum and per-color-combination
  tests in `tests/test_starting_state.py`.
- **M3 — Observation schema and labeling protocol.** Split into **M3A** (*complete*: observation
  schema + tooling -- record types, field-by-field schema, validator, CSV→YAML importer, synthetic
  fixtures/tests, `docs/design/07-observation-schema.md` + `08-labeling-protocol.md` — closed with
  zero real matches), **M3B** (*next*: a 3-match pilot corpus across
  `baseline_clean`/`typical_broadcast`/`poor_video` video quality, reconciliation, and a
  schema-revision checkpoint), and **M3C** (5 more matches to reach an 8-match pilot, plus QC —
  **if multiple labelers are available, an inter-labeler agreement check on a shared subset; if
  there is only one labeler, a blinded re-label consistency check instead**). Full design in
  `docs/plans/m3-observation-plan.md`. No computer vision at this stage.
- **M4 — Match reconstruction.** Replay each labeled match's action sequence through `model` +
  `scoring` and compare against the officially published final score. → **Gate V2.** Validates the
  state model and scorer against reality using zero simulation.
- **M5 — Empirical parameter estimation.** Fit distributions from the labeled corpus for:
  acquisition time, Loader cycle time, scoring/alignment time, Toggle interaction time, traversal
  time, stack interaction time, failure/retry probability, defensive delay, congestion effects.
  Statistical methods only. Every parameter tagged `program` + `transfer_class`. Train/held-out
  split established here.
- **M6 — Spatial interface + single-robot DES.** Introduce the replaceable spatial/travel model
  behind its interface (region-based to start), plus a single-robot discrete-event loop driven by
  measured parameters. Determinism test: same seed → byte-identical event log. → **Gate V3**
- **M7 — Two robots + capabilities.** 24"/15" pairing, coordination policy, capability vectors;
  simulate a VEX U Robot Skills Match end to end. Skills comparison used as corroboration only.
- **M8 — Head-to-head + Monte Carlo.** Opponent model, full 1v1 match sim, batch harness, run
  manifests, win probability. → **Gate V4**
- **M9 — Architecture comparison.** Systematic sweeps over duplicate / specialize-24 /
  specialize-15 / omit per capability. First milestone that actually answers the decision
  question.
- **M10+ — Deferred.** Season-meta and Worlds opponent forecasting, autonomous strategy
  optimization, automatic video analysis, UI.

## Observation schema (M3)

The detailed schema — record types, field-by-field reference, temporal/spatial semantics,
possession episodes, reconciliation design, parameter traceability, labeling workflow, pilot
selection, and QC protocol — lives in `docs/plans/m3-observation-plan.md`, not here, so there is
exactly one schema to keep in sync. Summary of the execution split:

- **M3A** *(complete)* — observation schema + tooling: normative schema docs, `src/vexu_sim/
  observations/` (models, validator, reconciliation, CSV→YAML importer), synthetic fixtures/tests.
  Closed with zero real matches.
- **M3B** — a 3-match pilot corpus (`baseline_clean` / `typical_broadcast` / `poor_video`),
  reconciliation run on all three, and a schema-revision checkpoint.
- **M3C** — 5 more matches (8 total), corpus-breadth strata, and QC (single-labeler re-label or
  multi-labeler agreement).

## Adding a new manual version

Its own small milestone, whenever VEX releases one (v2.0 expected released 2026-09-03, effective
2026-09-10): copy the PDF into `docs/manuals/`, add a manifest record to
`data/sources/manuals.yaml` (with independent `released`/`effective` dates), copy the previous
rules directory under `data/rules/override/`, apply only the changed entries (cross-reference the
manual's own changelog against `data/rules/CHANGELOG.md`), mark any Q&A rulings the new manual
incorporates as `superseded` in their source record, re-run tests, and record any newly-surfaced
open questions.

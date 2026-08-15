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
- **M2 — Initial field states.** *(next)* Encode V5RC and VEX U starting configurations from
  Appendix A and Figures FO-2/VEXU-1; resolve whether the VEX U on-field layout otherwise matches
  V5RC's Figure FO-2 (a manual-reading task, not an open question); inventory-sum tests.
- **M3 — Observation schema and labeling protocol.** Define the label vocabulary (see sketch
  below) and labeling protocol; hand-label a pilot set of 5-10 real V5RC Override matches. **If
  multiple labelers are available, run an inter-labeler agreement check on a shared subset. If
  there is only one labeler, run a re-label consistency check instead** — the same labeler
  re-labels a shared subset after a delay, and agreement between the two passes stands in for
  inter-labeler agreement. No computer vision at this stage.
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

## Observation schema sketch (M3)

One record per labeled action event — labeler-friendly, coarse, no coordinates:

`match_id`, `program`, `event`, `date`, `video_url`, `video_timestamp`, `robot_ref`,
`robot_size_class`, `action_type` (`acquire_pin` | `acquire_cup` | `retrieve_from_loader` |
`traverse` | `align` | `place` | `flip_toggle` | `contest_midfield` | `recover`), `t_start`,
`t_end`, `from_region`, `to_region`, `outcome` (`success` | `fail` | `abandoned`), `retry_of`,
`interference` (`none` | `defensive_contact` | `congestion` | `field_element`), `notes`, `labeler`,
`label_date`, `confidence`.

Every M5 parameter maps onto exactly one `action_type` or one derived field
(`failure/retry` ← `outcome` + `retry_of`; `defensive delay` and `congestion` ← `interference`).

## Adding a new manual version

Its own small milestone, whenever VEX releases one (v2.0 expected released 2026-09-03, effective
2026-09-10): copy the PDF into `docs/manuals/`, add a manifest record to
`data/sources/manuals.yaml` (with independent `released`/`effective` dates), copy the previous
rules directory under `data/rules/override/`, apply only the changed entries (cross-reference the
manual's own changelog against `data/rules/CHANGELOG.md`), mark any Q&A rulings the new manual
incorporates as `superseded` in their source record, re-run tests, and record any newly-surfaced
open questions.

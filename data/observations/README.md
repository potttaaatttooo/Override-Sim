# Observations

Raw labeled match data (hand-labeled from real match video) -- what we saw, not what we assumed
or measured from it. **Still empty: M3A (schema + tooling) is complete, but M3B/M3C (real match
labeling) have not started.** Every future match directory here is `<program>/<match_key>/`
holding `match.yaml`, `snapshots.yaml`, `events.yaml`, and `events.source.csv` -- see
`docs/design/07-observation-schema.md` for the normative field-by-field schema and
`docs/design/08-labeling-protocol.md` for the human labeling procedure. Loading, validation,
reconciliation, and the CSV importer are implemented in `src/vexu_sim/observations/`, tested only
against the synthetic fixture in `tests/fixtures/observations/synth_match/` -- no real observation
has been added yet. Every record carries `program: v5rc | vexu` (never `both`), enforced by
`vexu_sim.sources.validate_empirical_program`.

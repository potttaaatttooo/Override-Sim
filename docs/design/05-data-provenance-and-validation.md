# Data provenance and validation

## The source model

Two source types back every rule datum in `data/rules/`:

- **`manual`** — a versioned Game Manual PDF, committed to `docs/manuals/`, recorded in
  `data/sources/manuals.yaml`. Fields: `id`, `source_type`, `program` (`v5rc | vexu | both`),
  `manual_version`, `released`, `effective`, `sha256`, `source_url`, `retrieved`, `local_path`.
  **`released` and `effective` are independent fields** — a manual can be published before it
  governs play (v1.1: released 2026-08-06, effective 2026-08-13; v2.0: released 2026-09-03,
  effective 2026-09-10). Bundle/event applicability is always by `effective` date.
- **`q_and_a`** — an official ruling from the V5RC or VURC Q&A system, recorded one file per
  ruling under `data/sources/qna/<qna_id>.yaml`, retrieved **verbatim** (never written from
  memory or paraphrased) with `question` and `holding` fields. Fields: `id`, `source_type`,
  `program`, `qna_id`, `title`, `source_url`, `pdf_export_url`, `answered`, `retrieved`,
  `applies_to_manual_versions`, `rule_ids`, `status` (`active | superseded | withdrawn`),
  `superseded_by`.

Q&A rulings are rule provenance, not simulation assumptions — they live in `data/sources/`
alongside manuals and are cited by rule data exactly the same way (`{ref: "qna:3188"}`).

Known upcoming manual versions after v1.1: v2.0 (released 2026-09-03, effective 2026-09-10), then
v2.1, v2.2, v3.0, v4.0. Adding one is its own small milestone: copy the PDF, add a manifest
record, copy the previous rules directory, apply only the changed entries (cross-referenced via
`data/rules/CHANGELOG.md`), mark any Q&A rulings the new manual incorporates as `superseded`,
re-run tests, record any new open questions.

### `program` differs by record kind

| Record kind | Allowed `program` |
|---|---|
| Source records (`data/sources/`) | `v5rc` \| `vexu` \| `both` |
| Rule bundles (`data/rules/`) | `v5rc` \| `vexu` |
| Observations, parameters, matches | `v5rc` \| `vexu` — **never `both`** |

`both` exists because the combined Game Manual, and some Q&A rulings (e.g. qna:3188), genuinely
govern two programs in one document. It must never appear on empirical data: an observation, a
fitted parameter, or a match always came from exactly one program, and `both` would erase the
V5RC-to-VEX-U transfer question a parameter's `transfer_class` field exists to track.

## The four data stores

| Store | Answers | Mutable? |
|---|---|---|
| `data/rules/` | What do official sources assert? | Immutable per manual version |
| `data/assumptions/` | What structural choice did we make where sources say nothing? | Can change; tracked with `status` |
| `data/parameters/` | What did we measure? | Refit as more observations arrive |
| `data/observations/` | What did we see in a real match? | Append-only |

Never mixed in one file. When validation fails, the fix order is **assumptions first, parameters
second, rules never** — a rule only changes when an official source says so.

## Run manifests

Every simulation batch (once simulation exists, M6+) records `rules_version`,
`assumption_set_id`, `parameter_set_id`, `seed`, `code_git_sha`, and the count of parameters used
whose `transfer_class` is `uncertain`. A result that cannot name all of these is not a result.

## Validation — five staged gates

Aggregate score agreement is never sufficient on its own — a too-slow cycle time offset by a
too-high success rate can reproduce the right final score while being wrong about everything
underneath it (compensating errors).

| Gate | What is checked | Milestone |
|---|---|---|
| **V1** | Deterministic scoring reproduces the manual's own worked examples (p.17) exactly, plus rule edge cases (Figure SC2-2, etc.). | M1 |
| **V2** | Match reconstruction — replaying a real match's labeled action sequence through the state model and scorer reproduces its officially published final score, for N real matches. No simulation involved. | M4 |
| **V3** | Component-level distributions — simulated action durations and success rates match labeled observations *per action type*, on a held-out split, not just in aggregate. | M6 |
| **V4** | Aggregate score/margin distributions match real event results, out of sample. | M8 |
| **V5** | Skills results — corroboration only. Never sufficient on its own. | M7+ |

Parameters are fit on a training split and validated on a held-out split. Every tuning action is
recorded as an assumption status change, so "we adjusted until it matched" is always visible in
the project's history rather than silently baked into a number.

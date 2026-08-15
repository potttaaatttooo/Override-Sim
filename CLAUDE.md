# VEX U Override Decision-Support & Simulation Tool

## Purpose

This project answers: which combination of capabilities across a VEX U team's 24" robot and 15"
robot is most likely to remain competitive at late-season events and at the World Championship?
It is built rules-first (rules → deterministic scoring → observation → measurement → simulation),
not simulation-first, so that every conclusion is traceable back to an official source or a real
observation.

## Hard constraints

- Official sources are the current Game Manual **and** official V5RC/VEX U Q&A rulings. Neither
  alone is sufficient.
- Four data stores, never mixed in one file: `data/rules/` (what sources assert),
  `data/assumptions/` (what we chose to model), `data/parameters/` (what we measured),
  `data/observations/` (what we saw).
- Rules are versioned by Game Manual version. Every run records which version it used.
- Scoring is deterministic and never calls an LLM.
- Simulations (once they exist) reproduce exactly from a seed.
- Discrete-event simulation, not rigid-body physics.
- Robots are capability vectors, not CAD.
- A VEX U architecture is a coordinated 24" + 15" robot pair.
- No ML where deterministic or statistical methods suffice.
- No vision, video, optimization, or UI until the validation gates in
  `docs/design/05-data-provenance-and-validation.md` pass.

## The rule-gap workflow

Never invent a rule. When something is unclear:
1. Re-read the current manual, including Appendix B (glossary) and Section 6 (VEX U).
2. Search the official Override Q&A (both the V5RC Q&A and the separate VURC Q&A).
3. Classify the item: `rule` (answered, just under-read), `qna` (an official ruling answers it),
   `verify` (needs a specific manual-reading task, scheduled as one), `parameter` (not a rule
   question, a quantity to measure), or `open` (genuinely unresolved after 1-2).
4. Only `open` items go in `docs/open-questions.md`. Never silently resolve a genuine ambiguity,
   and never file something as `open` without having done 1-2 first.

## Layout

```
CLAUDE.md, README.md, pyproject.toml       project root
docs/manuals/                              official Game Manual PDFs, committed verbatim
docs/design/                               principles, game model, state/scoring, provenance+validation
docs/decisions/                            ADRs -- on demand only, see decisions/README.md
docs/open-questions.md                     genuinely unresolved rule ambiguities
docs/roadmap.md                            milestone plan
data/sources/                              WHO SAYS SO -- manual + Q&A source records
data/rules/override/v<version>/            WHAT THE RULES SAY -- versioned, cited, base+VEX U overlay
data/assumptions/                          WHAT WE CHOSE TO MODEL -- empty until simulation work
data/parameters/                           WHAT WE MEASURED -- empty until estimation work
data/observations/                         WHAT WE SAW -- empty until labeling work
src/vexu_sim/sources/                      load source records, resolve citations, supersede checks
src/vexu_sim/rules/                        load + compose + validate rule bundles. No game logic.
tests/                                     pytest; fixtures/scoring/ for golden scoring cases
```

## Provenance convention

Every rule datum carries a `sources` (list) or `source` (single) key with `{ref: "<source id>",
...}` citations resolving into `data/sources/`. Rule IDs are quoted verbatim (`SC3`, `SG6`,
`VUG5`, `VUR1b`), never paraphrased into a field name.

## Program tagging

Every record carries a `program`. Source records (manuals, Q&A) may be `v5rc | vexu | both` --
the Game Manual genuinely governs both in one document. Rule bundles, observations, parameters,
and matches are `v5rc | vexu` and **never `both`**: an empirical record always came from exactly
one program, and letting it claim `both` would erase the V5RC-to-VEX-U transfer question that a
parameter's (future) `transfer_class` field exists to track.

## Current milestone

**Session A (M0) complete: rules foundation and provenance.** `src/vexu_sim/sources` and
`src/vexu_sim/rules` load, compose, and validate the Override v1.1 rule bundle (base + VEX U
overlay) against official sources.

**Session B (M1) complete: deterministic scoring.** `src/vexu_sim/model` and `src/vexu_sim/scoring`
implement MatchState + pure scoring functions, validated against the manual's own worked examples
(p.17) and rule edge cases (Figure SC2-2, etc.). Gate V1 is implemented. No CLI or simulation exist
yet.

**Next: M2 — Initial field states.** Encode V5RC and VEX U starting configurations from Appendix A
and Figures FO-2/VEXU-1; inventory-sum tests.

## Commands

```bash
pip install -e ".[dev]"
pytest
```

## Session hygiene

One milestone per session. Don't refactor outside the current milestone. Prefer adding a test
over adding a feature. Ask before adding a dependency (currently: `pyyaml` + `pytest` only). No
subagents, no background workflows.

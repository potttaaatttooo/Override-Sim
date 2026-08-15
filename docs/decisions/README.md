# Architecture Decision Records

ADRs are written **only** for major architectural decisions that are likely to be revisited, or
whose rationale would otherwise be lost. Not for ordinary choices — those are documented inline
(a code comment or a line in the relevant design doc) or not at all.

None exist yet. A Session A example of something that would warrant one, if revisited: the choice
not to deep-merge the VEX U overlay onto the base rule bundle (`src/vexu_sim/rules/loader.py`),
keeping `vexu_overlay` as a separate top-level key instead. That rationale is currently recorded
as a docstring in `RuleBundle` rather than a standalone ADR — promote it here only if a future
session actually reconsiders it.

When you do write one: `NNNN-short-title.md`, numbered sequentially, with Context / Decision /
Consequences sections.

"""The single boundary between `observations` and the rest of the project.

Derives canonical Goal/Toggle/Quadrant ids from `vexu_sim.field_setup`'s public
`build_v5rc_starting_state`/`build_vexu_starting_state` instead of hand-copying a
second list (docs/plans/m3-observation-plan.md §P) -- so a Goal id change upstream
cannot silently drift out of sync with this package.

This is also the one place the genuinely M3-local labeling vocabulary is declared:
Loader ids and the four individual Load-Zone region ids. No rule datum names them --
`field.yaml` gives the Loader *count* (4) and the Load Zone *concept*, not names (§F.1,
§P) -- so they are declared here, honestly, as labeling vocabulary rather than passed
off as rule-derived.
"""

from __future__ import annotations

from vexu_sim.field_setup import build_v5rc_starting_state, build_vexu_starting_state
from vexu_sim.rules import RuleBundle

# M3-local: the rules give the Loader count (4, field.yaml: inventory.loaders.total)
# and the Load Zone concept, not these four names.
LOADER_REFS: frozenset[str] = frozenset(
    {"loader_red_1", "loader_red_2", "loader_blue_1", "loader_blue_2"}
)

# M3-local region spellings for the four Load Zones -- one per Loader.
LOAD_ZONE_REGIONS: frozenset[str] = frozenset(
    {"load_zone_red_1", "load_zone_red_2", "load_zone_blue_1", "load_zone_blue_2"}
)

MIDFIELD_REGION = "midfield"
UNKNOWN_REGION = "unknown"


def _starting_state(rule_bundle: RuleBundle):
    if rule_bundle.program == "v5rc":
        return build_v5rc_starting_state(rule_bundle)
    if rule_bundle.program == "vexu":
        return build_vexu_starting_state(rule_bundle)
    raise ValueError(f"unknown program {rule_bundle.program!r}")


def canonical_goal_ids(rule_bundle: RuleBundle) -> frozenset[str]:
    """The 9 canonical Goal ids `field_setup` actually builds for this program."""
    return frozenset(g.id for g in _starting_state(rule_bundle).match_state.goals)


def canonical_toggle_ids(rule_bundle: RuleBundle) -> frozenset[str]:
    """The 4 canonical Toggle ids `field_setup` actually builds for this program."""
    return frozenset(t.id for t in _starting_state(rule_bundle).match_state.toggles)


def canonical_quadrant_ids(rule_bundle: RuleBundle) -> frozenset[str]:
    """The 4 canonical Quadrant ids (e.g. "red_1") `field_setup` actually builds."""
    return frozenset(q.id for q in _starting_state(rule_bundle).match_state.quadrants)


def region_vocabulary(rule_bundle: RuleBundle) -> frozenset[str]:
    """The full §F.1 Region vocabulary for `Action.region`: one `quadrant_<id>` region
    per canonical Quadrant, the Midfield, the four M3-local Load Zone regions, and
    `unknown`."""
    quadrant_regions = frozenset(f"quadrant_{qid}" for qid in canonical_quadrant_ids(rule_bundle))
    return quadrant_regions | LOAD_ZONE_REGIONS | frozenset({MIDFIELD_REGION, UNKNOWN_REGION})


def loader_refs() -> frozenset[str]:
    return LOADER_REFS

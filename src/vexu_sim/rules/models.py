"""Data model for a composed, validated rule bundle.

A RuleBundle holds no game logic (see CLAUDE.md) -- it is loaded, cited data. Game-logic
consumers (scoring, field_setup) read the effective/composed accessors below
(`point_values`, `autonomous_bonus_includes_midfield`, `awp_requirements`,
`period_seconds`, `match_load_inventory`) rather than `.data` directly, so they never
need to know whether a value came from the base bundle or the VEX U overlay. `.data`
itself remains available for provenance-oriented tooling and tests (e.g. citation
checks) that are about the rule data, not about scoring a Match.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class AWPRequirements:
    """The effective, program-specific Autonomous Win Point requirements (<SC8> for
    V5RC, <VUG6> for VEX U) -- structured restatements of the `conditions` prose in
    scoring.yaml/vexu.yaml so the scorer never hardcodes a rule-version-specific
    number. See RuleBundle.awp_requirements.
    """

    min_pins_scored: int
    min_qualifying_goals: int
    min_pins_per_qualifying_goal: int
    excludes_opposing_side_of_autonomous_line: bool
    perimeter_contact_forbidden: bool
    requires_robot_in_midfield: bool


@dataclass(frozen=True)
class MatchLoadInventory:
    """The effective per-Alliance Match Load (off-Field, held in the Loader) Pin/Cup
    counts at kickoff -- <SG11> (V5RC) / <VUG4> (VEX U). Structured so a consumer
    (e.g. `field_setup`) never needs to know whether this data lives in the base
    `field.yaml` inventory or the `vexu.yaml` overlay's `field_setup.match_loads`
    block -- see RuleBundle.match_load_inventory. "Own-color" Pins are red/yellow for
    the red Alliance, blue/yellow for blue.
    """

    red_cups: int
    red_own_color_yellow_pins: int
    red_yellow_yellow_pins: int
    blue_cups: int
    blue_own_color_yellow_pins: int
    blue_yellow_yellow_pins: int


@dataclass(frozen=True)
class RuleBundle:
    """A composed rule bundle for one manual version and one program.

    `data` holds one key per base rule file (meta, periods, scoring, field,
    robot_limits) for program="v5rc". For program="vexu", `data` additionally holds a
    "vexu_overlay" key with the raw contents of vexu.yaml -- the base sections are NOT
    deep-merged with the overlay. `data` (including `vexu_overlay`) is preserved
    verbatim for provenance and is fine to inspect directly in tests or tooling that
    is *about* the rule data itself. Game-logic consumers (scoring, field_setup)
    should instead use the effective/composed accessors below (`point_values`,
    `autonomous_bonus_includes_midfield`, `awp_requirements`, `period_seconds`,
    `match_load_inventory`), none of which require the caller to know whether a
    value came from the base bundle or the VEX U overlay. This keeps composition
    simple (no generic deep-merge machinery) while still making "what changed"
    explicit via `overridden_rule_ids`.
    """

    manual_version: str
    program: str
    data: dict[str, Any]
    overridden_rule_ids: list[str] = field(default_factory=list)

    @property
    def point_values(self) -> dict[str, Any]:
        """Point values are identical for both programs -- no VEX U override exists."""
        return self.data["scoring"]["point_values"]

    @property
    def autonomous_bonus_includes_midfield(self) -> bool:
        """Whether Midfield-position-dependent scoring (Robots ending in the Midfield,
        Ownership of yellow Pins in the Midfield) counts toward the Autonomous Bonus.

        False for V5RC (<SC7>a: excluded, those statuses are only evaluated at the end
        of the Match) and True for VEX U (<VUG5>: included at the end of the Autonomous
        Period too), per qna:3188. This is the effective/composed view scoring code
        should consult instead of branching on `self.program` or inspecting
        `vexu_overlay` directly.
        """
        return self.program == "vexu"

    @property
    def awp_requirements(self) -> AWPRequirements:
        """The effective Autonomous Win Point requirements for this program (<SC8>
        for V5RC, <VUG6> for VEX U), without the caller needing to know whether the
        structured `requirements` data lives in the base scoring.yaml or the
        vexu.yaml overlay. Two of VEX U's fields are PROVISIONAL interpretations --
        see docs/open-questions.md #2 and #3, and the comments on `requirements` in
        vexu.yaml.
        """
        if self.program == "vexu":
            raw = self.data["vexu_overlay"]["autonomous_win_point_criteria"]["requirements"]
        else:
            raw = self.data["scoring"]["autonomous_win_point_criteria_v5rc"]["requirements"]
        return AWPRequirements(**raw)

    def period_seconds(self, period: str) -> int:
        """The effective, program-specific length (in seconds) of `period`
        ("autonomous" or "driver_controlled"), without the caller needing to know
        whether the value lives in the base periods.yaml or the vexu.yaml overlay.
        """
        key = f"{period}_period_seconds"
        if self.program == "vexu":
            return self.data["vexu_overlay"]["periods"][key]["value"]
        return self.data["periods"]["v5rc"][key]["value"]

    @property
    def match_load_inventory(self) -> MatchLoadInventory:
        """The effective Match Load Pin/Cup counts for this program (<SG11> for
        V5RC, <VUG4> for VEX U), without the caller needing to know whether the
        counts live in the base field.yaml inventory or the vexu.yaml overlay's
        field_setup.match_loads block. See MatchLoadInventory.
        """
        if self.program == "vexu":
            match_loads = self.data["vexu_overlay"]["field_setup"]["match_loads"]
            red = match_loads["red_alliance"]
            blue = match_loads["blue_alliance"]
            return MatchLoadInventory(
                red_cups=red["cups"],
                red_own_color_yellow_pins=red["red_yellow_pins"],
                red_yellow_yellow_pins=red["yellow_yellow_pins"],
                blue_cups=blue["cups"],
                blue_own_color_yellow_pins=blue["blue_yellow_pins"],
                blue_yellow_yellow_pins=blue["yellow_yellow_pins"],
            )
        inventory = self.data["field"]["inventory"]
        pins = inventory["pins"]["breakdown"]
        cups = inventory["cups"]["breakdown"]
        # Glossary "Match Load" entry (p.B6): "22 Pins, 11 per Alliance" -- the 2
        # yellow_yellow_match_loads split evenly, 1 per Alliance.
        yellow_yellow_each = pins["yellow_yellow_match_loads"] // 2
        return MatchLoadInventory(
            red_cups=cups["match_loads_red"],
            red_own_color_yellow_pins=pins["red_yellow_match_loads"],
            red_yellow_yellow_pins=yellow_yellow_each,
            blue_cups=cups["match_loads_blue"],
            blue_own_color_yellow_pins=pins["blue_yellow_match_loads"],
            blue_yellow_yellow_pins=yellow_yellow_each,
        )

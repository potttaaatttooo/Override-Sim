"""Data model for a composed, validated rule bundle.

A RuleBundle holds no game logic (see CLAUDE.md) -- it is loaded, cited data. Session B's
scoring module reads a RuleBundle's `.data` to get point values and criteria text.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RuleBundle:
    """A composed rule bundle for one manual version and one program.

    `data` holds one key per base rule file (meta, periods, scoring, field,
    robot_limits) for program="v5rc". For program="vexu", `data` additionally holds a
    "vexu_overlay" key with the raw contents of vexu.yaml -- the base sections are NOT
    deep-merged with the overlay; Session B's scoring code consults vexu_overlay first
    for VEX U matches. This keeps composition simple (no generic deep-merge machinery)
    while still making "what changed" explicit via `overridden_rule_ids`.
    """

    manual_version: str
    program: str
    data: dict[str, Any]
    overridden_rule_ids: list[str] = field(default_factory=list)

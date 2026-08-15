"""Data model for official source records (Game Manual versions, official Q&A rulings).

Sources are the WHO-SAYS-SO layer described in CLAUDE.md and docs/design/05-data-provenance-
and-validation.md: every datum in data/rules/ must resolve to at least one of these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Sources (manuals, Q&A rulings) may cover both programs in one document/ruling.
# Rule bundles, observations, parameters, and matches must NOT use "both" -- see
# CLAUDE.md "Program tagging" and validate_empirical_program() in loader.py.
VALID_SOURCE_PROGRAMS = frozenset({"v5rc", "vexu", "both"})

VALID_SOURCE_TYPES = frozenset({"manual", "q_and_a"})

VALID_STATUSES = frozenset({"active", "superseded", "withdrawn"})


@dataclass(frozen=True)
class Source:
    """A single official source record: a Game Manual version or a Q&A ruling."""

    id: str
    source_type: str
    program: str
    status: str
    applies_to_manual_versions: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

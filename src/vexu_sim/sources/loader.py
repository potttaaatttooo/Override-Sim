"""Load official source records and resolve rule-data citations against them.

See docs/design/05-data-provenance-and-validation.md for the source model this implements.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .models import (
    VALID_SOURCE_PROGRAMS,
    VALID_SOURCE_TYPES,
    VALID_STATUSES,
    Source,
)

# Observation, parameter, and match records always come from exactly one program.
# "both" is reserved for source records (manuals, Q&A rulings) that genuinely cover
# more than one program in a single document -- see CLAUDE.md "Program tagging".
EMPIRICAL_PROGRAMS = frozenset({"v5rc", "vexu"})


class SourceValidationError(Exception):
    """Raised when a source record or a citation referencing one is invalid."""


class SourceRegistry:
    """Loaded official sources, keyed by id, with citation resolution."""

    def __init__(self, sources: dict[str, Source]) -> None:
        self._sources = sources

    def __contains__(self, source_id: str) -> bool:
        return source_id in self._sources

    def get(self, source_id: str) -> Source:
        try:
            return self._sources[source_id]
        except KeyError:
            raise SourceValidationError(f"unknown source id: {source_id!r}") from None

    def resolve(self, ref: dict[str, Any], *, manual_version: str | None = None) -> Source:
        """Resolve a rule-data citation of the form {"ref": "<source id>", ...}.

        Raises SourceValidationError if the source does not exist, is not active
        (superseded/withdrawn sources cannot back new-looking rule data), or -- when
        manual_version is given -- does not declare applicability to that manual version.
        """
        source_id = ref.get("ref")
        if not source_id:
            raise SourceValidationError(f"citation is missing 'ref': {ref!r}")
        source = self.get(source_id)
        if source.status != "active":
            raise SourceValidationError(
                f"source {source_id!r} is {source.status!r}, not active; "
                f"a superseded or withdrawn source cannot back a citation ({ref!r})"
            )
        if (
            manual_version is not None
            and source.applies_to_manual_versions
            and manual_version not in source.applies_to_manual_versions
        ):
            raise SourceValidationError(
                f"source {source_id!r} does not declare applicability to manual version "
                f"{manual_version!r} (applies to {source.applies_to_manual_versions!r})"
            )
        return source


def validate_empirical_program(program: str) -> None:
    """Validate a program tag for observation/parameter/match records.

    These record kinds never use "both": an empirical record always came from exactly
    one program, and "both" would erase the V5RC-to-VEX-U transfer question that the
    (future) `transfer_class` field on parameters exists to track. No observation/
    parameter/match module exists yet (that's Session B+), but the schema commitment
    is tested now so it can't drift before those modules are written.
    """
    if program not in EMPIRICAL_PROGRAMS:
        raise SourceValidationError(
            f"empirical (observation/parameter/match) program tag must be one of "
            f"{sorted(EMPIRICAL_PROGRAMS)} -- never 'both' -- got {program!r}"
        )


def _validate_source_record(record: dict[str, Any]) -> None:
    record_id = record.get("id")
    if not record_id:
        raise SourceValidationError(f"source record missing 'id': {record!r}")

    source_type = record.get("source_type")
    if source_type not in VALID_SOURCE_TYPES:
        raise SourceValidationError(
            f"source {record_id!r} has invalid source_type {source_type!r}; "
            f"must be one of {sorted(VALID_SOURCE_TYPES)}"
        )

    program = record.get("program")
    if program not in VALID_SOURCE_PROGRAMS:
        raise SourceValidationError(
            f"source {record_id!r} has invalid program {program!r}; "
            f"must be one of {sorted(VALID_SOURCE_PROGRAMS)}"
        )

    status = record.get("status", "active")
    if status not in VALID_STATUSES:
        raise SourceValidationError(
            f"source {record_id!r} has invalid status {status!r}; "
            f"must be one of {sorted(VALID_STATUSES)}"
        )


def load_sources(data_root: Path) -> SourceRegistry:
    """Load all source records under <data_root>/sources/."""
    sources_dir = data_root / "sources"
    sources: dict[str, Source] = {}

    manuals_path = sources_dir / "manuals.yaml"
    with manuals_path.open(encoding="utf-8") as f:
        manual_records = yaml.safe_load(f) or []
    for record in manual_records:
        _validate_source_record(record)
        sources[record["id"]] = Source(
            id=record["id"],
            source_type=record["source_type"],
            program=record["program"],
            status="active",  # manuals don't carry a status field; they're always active
            applies_to_manual_versions=[record["manual_version"]],
            raw=record,
        )

    qna_dir = sources_dir / "qna"
    if qna_dir.is_dir():
        for path in sorted(qna_dir.glob("*.yaml")):
            with path.open(encoding="utf-8") as f:
                record = yaml.safe_load(f)
            _validate_source_record(record)
            sources[record["id"]] = Source(
                id=record["id"],
                source_type=record["source_type"],
                program=record["program"],
                status=record.get("status", "active"),
                applies_to_manual_versions=record.get("applies_to_manual_versions", []),
                raw=record,
            )

    return SourceRegistry(sources)

"""The deterministic, validated events.source.csv -> events.yaml importer (§K.2).

`events.source.csv` is the human-authored provenance artifact (spreadsheet-authored,
committed alongside the canonical YAML); `events.yaml` is canonical for every
downstream reader -- no loader in this package ever reads the CSV directly (§R.2).

Contract (docs/plans/m3-observation-plan.md §K.2, §P):
- deterministic: identical CSV bytes -> byte-identical YAML, stable key order.
- refuses to emit any YAML if validation fails -- never writes partial output.
- rejects invalid enum values, invalid timestamps, and REQ-IF violations by routing
  every row through the same `parse_event`/`validate_observation_set` pipeline
  `loader.py` uses to load a hand-authored events.yaml, so the two paths can never
  silently diverge in what they accept.
- never silently coerces a malformed value: an unparseable number/boolean is a hard
  error, not a best-effort guess.

Column order (documented verbatim in docs/design/08-labeling-protocol.md) is fixed at
`CSV_COLUMNS` below -- one CSV, one `record_type` column, not one sheet per type.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path
from typing import Any, Optional

import yaml
from dataclasses import asdict

from vexu_sim.rules import RuleBundle

from .loader import ObservationValidationError, parse_event, validate_observation_set
from .models import UNKNOWN, MatchObservation, Snapshot

# One CSV, one record_type column, per §K.2. Fields with the same name are
# deliberately shared across record types where the plan's own field tables reuse a
# name (e.g. `video_t_start`/`video_t_end` for Action/Incident/Interaction,
# `video_t_enter` for LoaderVisit/MidfieldOccupancy, `method` for descore/toggle).
CSV_COLUMNS: tuple[str, ...] = (
    "record_type", "id", "robot_ref", "period", "action_type",
    "video_t_start", "video_t_end", "video_t", "video_t_enter", "video_t_exit",
    "region", "outcome", "failure_mode", "contested", "contested_robot_ref",
    "gap_after", "retry_of", "possession_id",
    "source", "object", "object_colors", "loader_visit_id",
    "target_goal_ref", "stack_height_before", "stack_height_after", "cup_down_face",
    "destabilized_stack", "video_t_release",
    "method", "objects_removed",
    "toggle_ref", "state_before", "state_after", "seated_after",
    "loader_ref", "objects_acquired", "objects_types", "failed_grabs",
    "departs_possession_id", "video_t_first_object_available",
    "contested_during", "exit_coincident_with_contact",
    "incident_type", "resolution",
    "actor_robot_ref", "subject_robot_ref", "interaction_type", "subject_region",
    "change", "attributed_to", "caused_by_action",
    "confidence", "notes",
)

NUMERIC_FIELDS = frozenset(
    {"video_t_start", "video_t_end", "video_t", "video_t_enter", "video_t_exit",
     "video_t_release", "stack_height_before", "stack_height_after", "objects_removed",
     "objects_acquired", "failed_grabs", "video_t_first_object_available"}
)
BOOL_FIELDS = frozenset(
    {"destabilized_stack", "seated_after", "contested_during", "exit_coincident_with_contact"}
)
LIST_FIELDS = frozenset({"object_colors", "objects_types"})


def _coerce_cell(field_name: str, raw: Optional[str]) -> Any:
    if raw is None:
        return None
    value = raw.strip()
    if value == "":
        return None
    if value.lower() == UNKNOWN:
        return UNKNOWN
    if field_name in NUMERIC_FIELDS:
        try:
            return int(value) if "." not in value else float(value)
        except ValueError:
            raise ObservationValidationError(
                f"column {field_name!r}: {value!r} is not a valid number or 'unknown'"
            ) from None
    if field_name in BOOL_FIELDS:
        low = value.lower()
        if low in ("true", "yes", "1"):
            return True
        if low in ("false", "no", "0"):
            return False
        raise ObservationValidationError(
            f"column {field_name!r}: {value!r} is not a valid boolean, or 'unknown'"
        )
    if field_name in LIST_FIELDS:
        return [item.strip() for item in value.split("|") if item.strip()]
    return value


def _coerce_row(row: dict[str, Optional[str]], row_number: int) -> dict[str, Any]:
    coerced: dict[str, Any] = {}
    for field_name in CSV_COLUMNS:
        try:
            value = _coerce_cell(field_name, row.get(field_name))
        except ObservationValidationError as exc:
            raise ObservationValidationError(f"row {row_number}: {exc}") from exc
        if value is not None:
            coerced[field_name] = value
    return coerced


def compute_csv_sha256(csv_path: Path) -> str:
    return hashlib.sha256(csv_path.read_bytes()).hexdigest()


def read_events_csv(csv_path: Path) -> list[Any]:
    """Parse events.source.csv into typed event records (Action/LoaderVisit/...),
    without validating them against the rest of the match yet. Raises
    ObservationValidationError on the first malformed row (invalid enum, invalid
    number, unknown record_type) -- never silently coerces or skips a row."""
    events = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        unknown_columns = set(reader.fieldnames or []) - set(CSV_COLUMNS)
        if unknown_columns:
            raise ObservationValidationError(
                f"events.source.csv has unrecognized column(s): {sorted(unknown_columns)}"
            )
        for row_number, row in enumerate(reader, start=2):  # header is row 1
            coerced = _coerce_row(row, row_number)
            if not coerced.get("record_type"):
                raise ObservationValidationError(f"row {row_number}: missing record_type")
            try:
                events.append(parse_event(coerced))
            except ObservationValidationError as exc:
                raise ObservationValidationError(f"row {row_number}: {exc}") from exc
    return events


def import_events_csv(
    csv_path: Path,
    *,
    match: MatchObservation,
    snapshots: tuple[Snapshot, ...],
    rule_bundle: RuleBundle,
) -> tuple[tuple[Any, ...], tuple[str, ...], str]:
    """Parse and fully validate events.source.csv against `match`/`snapshots`/
    `rule_bundle`. Returns (events, warnings, source_csv_sha256). Raises
    ObservationValidationError -- refusing to produce anything an emitter could write
    -- if any row is malformed or the resulting event set fails validation."""
    events = tuple(read_events_csv(csv_path))
    errors, warnings = validate_observation_set(match, snapshots, events, rule_bundle)
    if errors:
        raise ObservationValidationError(
            f"{csv_path}: {len(errors)} validation error(s) -- refusing to emit events.yaml:\n  - "
            + "\n  - ".join(errors)
        )
    sha256 = compute_csv_sha256(csv_path)
    return events, tuple(warnings), sha256


def verify_csv_sha256(csv_path: Path, expected: Optional[str]) -> None:
    """Re-hash the committed CSV and compare against `match.labeling.source_csv_sha256`
    -- a mismatch is a validation error, not a warning (§R.2)."""
    if expected is None:
        return
    actual = compute_csv_sha256(csv_path)
    if actual != expected:
        raise ObservationValidationError(
            f"{csv_path}: source_csv_sha256 mismatch -- expected {expected}, computed {actual}"
        )


def events_to_yaml_docs(events: tuple[Any, ...]) -> list[dict[str, Any]]:
    """Convert parsed event dataclasses to plain dicts in a stable, declaration-order
    key ordering (dataclasses.asdict preserves field-definition order, which is fixed
    by the code, not by input order) -- this is what makes the importer deterministic."""
    return [asdict(e) for e in events]


def write_events_yaml(events: tuple[Any, ...], output_path: Path) -> None:
    """Write canonical events.yaml. Same `events` tuple always serializes to the same
    bytes: stable per-record key order (declaration order) and `sort_keys=False`."""
    docs = events_to_yaml_docs(events)
    text = yaml.safe_dump(docs, sort_keys=False, default_flow_style=False, allow_unicode=True)
    output_path.write_text(text, encoding="utf-8", newline="\n")

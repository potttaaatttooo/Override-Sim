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
- recomputes `gap_after: no_next_action` deterministically (§F.2) rather than
  trusting the sheet -- see `loader.canonicalize_no_next_action`.
- computes and stamps `match.labeling.source_csv_sha256` (§R.2) via
  `import_match_from_csv`, the one safe high-level import path.

Column order (documented verbatim in docs/design/08-labeling-protocol.md) is fixed at
`CSV_COLUMNS` below -- one CSV, one `record_type` column, not one sheet per type.
"""

from __future__ import annotations

import csv
import re
from dataclasses import asdict, replace as _dc_replace
from pathlib import Path
from typing import Any, Optional

import yaml

from vexu_sim.rules import RuleBundle

from .hashing import HashMismatchError
from .hashing import compute_csv_sha256 as _compute_csv_sha256
from .hashing import verify_csv_sha256 as _hash_verify_csv_sha256
from .loader import (
    ObservationValidationError,
    canonicalize_no_next_action,
    parse_event,
    parse_match,
    parse_snapshot,
    validate_observation_set,
)
from .models import UNKNOWN, LoadedMatch, MatchObservation, Snapshot

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

# Fields that are REQUIRED for a given record_type but legally `null` (§07-
# observation-schema.md's REQ-vs-null distinction): a CSV cell has no way to spell
# "explicit null" differently from "blank/not applicable", so for exactly these
# (record_type, field) pairs a blank cell is interpreted as an explicit null rather
# than an absent key -- every other blank cell means "not applicable" and is
# dropped, matching REQ-IF absence. `video_t_end`/`video_t_exit` are shared column
# names across record types with different rules (Action's `video_t_end` must
# never be null -- a blank there should stay absent, surfacing a clear "missing
# required key" error), so this is keyed by record_type, not by column alone.
REQ_NULLABLE_FIELDS_BY_RECORD_TYPE: dict[str, frozenset[str]] = {
    "action": frozenset({"retry_of"}),
    "loader_visit": frozenset({"video_t_exit", "departs_possession_id"}),
    "midfield_occupancy": frozenset({"video_t_exit"}),
    "incident": frozenset({"video_t_end"}),
    "state_change": frozenset({"attributed_to"}),
}


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
    record_type = (row.get("record_type") or "").strip()
    retain_as_null = REQ_NULLABLE_FIELDS_BY_RECORD_TYPE.get(record_type, frozenset())
    coerced: dict[str, Any] = {}
    for field_name in CSV_COLUMNS:
        try:
            value = _coerce_cell(field_name, row.get(field_name))
        except ObservationValidationError as exc:
            raise ObservationValidationError(f"row {row_number}: {exc}") from exc
        if value is not None or field_name in retain_as_null:
            coerced[field_name] = value
    return coerced


def compute_csv_sha256(csv_path: Path) -> str:
    return _compute_csv_sha256(csv_path)


def verify_csv_sha256(csv_path: Path, expected: Optional[str]) -> None:
    """Re-hash the committed CSV and compare against `match.labeling.source_csv_sha256`
    -- a mismatch is a validation error, not a warning (§R.2)."""
    try:
        _hash_verify_csv_sha256(csv_path, expected)
    except HashMismatchError as exc:
        raise ObservationValidationError(str(exc)) from exc


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
    """Parse, canonicalize, and fully validate events.source.csv against
    `match`/`snapshots`/`rule_bundle`. Returns (events, warnings, source_csv_sha256).
    Raises ObservationValidationError -- refusing to produce anything an emitter
    could write -- if any row is malformed or the resulting event set fails
    validation. `gap_after: no_next_action` is recomputed deterministically before
    validation runs (§F.2) -- see `loader.canonicalize_no_next_action`."""
    events = tuple(read_events_csv(csv_path))
    events = canonicalize_no_next_action(events, match)
    errors, warnings = validate_observation_set(match, snapshots, events, rule_bundle)
    if errors:
        raise ObservationValidationError(
            f"{csv_path}: {len(errors)} validation error(s) -- refusing to emit events.yaml:\n  - "
            + "\n  - ".join(errors)
        )
    sha256 = compute_csv_sha256(csv_path)
    return events, tuple(warnings), sha256


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


# --- one safe high-level import path (§ "Complete CSV provenance workflow") ----------

_SHA256_VALUE_PATTERN = re.compile(
    r'(source_csv_sha256:\s*)(null|~|"[0-9a-f]{64}"|\'[0-9a-f]{64}\'|[0-9a-f]{64})'
)


def _stamp_source_csv_sha256(match_yaml_text: str, sha256: str) -> str:
    """Rewrite `labeling.source_csv_sha256`'s value in `match_yaml_text` to `sha256`,
    leaving every other byte of the hand-authored file untouched. Raises
    ObservationValidationError if the key can't be found -- match.yaml must declare
    the key explicitly (even as `null`) rather than have it synthesized."""
    new_text, count = _SHA256_VALUE_PATTERN.subn(rf'\g<1>"{sha256}"', match_yaml_text, count=1)
    if count == 0:
        raise ObservationValidationError(
            "match.yaml: could not find a 'source_csv_sha256:' key to stamp -- it must be "
            "declared explicitly (e.g. 'source_csv_sha256: null') before import"
        )
    return new_text


def import_match_from_csv(match_dir: Path, *, rule_bundle: RuleBundle) -> LoadedMatch:
    """The one safe high-level import path (§R.2): read `match.yaml` + `snapshots.yaml`
    + `events.source.csv` from `match_dir`, canonicalize/validate the complete
    observation set, refuse on any error, then -- only once everything is known
    good -- write the deterministic `events.yaml` and stamp/verify
    `match.labeling.source_csv_sha256` in `match.yaml`.

    - If `source_csv_sha256` is already stamped and matches the committed CSV,
      `match.yaml` is left untouched.
    - If it is already stamped and does NOT match, this raises
      ObservationValidationError and writes nothing at all (events.yaml included).
    - If it is unset (`null`), this rewrites just that one value in `match.yaml`
      (byte-identical everywhere else) once validation has already passed.
    """
    match_path = match_dir / "match.yaml"
    snapshots_path = match_dir / "snapshots.yaml"
    csv_path = match_dir / "events.source.csv"
    events_path = match_dir / "events.yaml"

    match_yaml_text = match_path.read_text(encoding="utf-8")
    match = parse_match(yaml.safe_load(match_yaml_text))
    snapshots = tuple(parse_snapshot(s) for s in (yaml.safe_load(snapshots_path.read_text(encoding="utf-8")) or []))

    events, warnings, computed_sha256 = import_events_csv(
        csv_path, match=match, snapshots=snapshots, rule_bundle=rule_bundle
    )

    # Provenance: a previously-stamped hash must still match this CSV. (A missing
    # hash is fine here -- that's exactly the "not yet stamped" case this function
    # exists to fix; validate_csv_provenance would otherwise flag it as an error for
    # the *read* path, but stamping it is precisely this function's job.)
    stored_sha256 = match.labeling.source_csv_sha256
    if stored_sha256 is not None:
        verify_csv_sha256(csv_path, stored_sha256)

    write_events_yaml(events, events_path)

    if stored_sha256 != computed_sha256:
        new_text = _stamp_source_csv_sha256(match_yaml_text, computed_sha256)
        match_path.write_text(new_text, encoding="utf-8")
        match = _dc_replace(match, labeling=_dc_replace(match.labeling, source_csv_sha256=computed_sha256))

    return LoadedMatch(match=match, snapshots=snapshots, events=events, warnings=warnings)

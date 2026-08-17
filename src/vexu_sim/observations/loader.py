"""Load and validate a labeled match: match.yaml + snapshots.yaml + events.yaml.

Follows `rules/loader.py`'s pattern: load raw YAML, parse into the frozen dataclasses
in `models.py`, then validate. Validation here enforces docs/design/07-observation-
schema.md's REQ / REQ-IF / enum / reference rules; it never adjudicates a game rule
(<SC2>/<SC3> Placed/Scored adjudication is explicitly M4's job, not this loader's --
see docs/plans/m3-observation-plan.md §O.11).

`observations` reads three stable public APIs and modifies nothing (§P):
`vexu_sim.sources.validate_empirical_program`, `RuleBundle.period_seconds()`, and the
canonical Goal/Toggle/Quadrant ids via `refs.py` (which itself reads `field_setup`).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml

from vexu_sim.rules import RuleBundle
from vexu_sim.sources import SourceValidationError, validate_empirical_program

from . import refs
from .models import (
    ACQUIRE_OBJECTS,
    ACQUIRE_SOURCES,
    ACTION_TYPES,
    CAMERA_TYPES,
    CHANGE_TYPES,
    CONFIDENCE_LEVELS,
    CONTESTED_VALUES,
    CUP_FACES,
    DESCORE_METHODS,
    FAILURE_MODES,
    GAP_CLASSES,
    GOAL_AFFECTING_CHANGES,
    INCIDENT_TYPES,
    INTERACTION_TYPES,
    NESTED_HALVES,
    OUTCOMES,
    PERIODS,
    PIN_COLORS,
    PLACE_DESCORE_OBJECTS,
    POSSESSION_AFFECTING_CHANGES,
    RESOLUTIONS,
    SIZE_CLASSES,
    SNAPSHOT_CONTEXTS,
    SNAPSHOT_QUALITIES,
    STACK_OBJECT_TYPES,
    TOGGLE_AFFECTING_CHANGES,
    TOGGLE_METHODS,
    TOGGLE_ORIENTATIONS,
    UNKNOWN,
    VIDEO_QUALITIES,
    Action,
    Coverage,
    GoalSnapshot,
    Incident,
    Interaction,
    LabelingMeta,
    LoadedMatch,
    LoaderVisit,
    MatchObservation,
    MidfieldOccupancy,
    OfficialResult,
    RobotEntry,
    RobotSnapshot,
    Snapshot,
    StackItem,
    StateChange,
    ToggleSnapshot,
    UnlabeledWindow,
    VideoMetadata,
)


class ObservationValidationError(Exception):
    """Raised when a match/snapshots/events file is malformed or fails a schema rule."""


def _req(d: dict, key: str, ctx: str) -> Any:
    if key not in d:
        raise ObservationValidationError(f"{ctx}: missing required key {key!r}")
    return d[key]


def _check_enum(value: Any, allowed: frozenset, ctx: str, field_name: str) -> None:
    if value not in allowed:
        raise ObservationValidationError(
            f"{ctx}: {field_name}={value!r} is not one of {sorted(allowed)}"
        )


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check_numeric_or_unknown(value: Any, ctx: str, field_name: str, *, allow_null: bool = False) -> None:
    if allow_null and value is None:
        return
    if value == UNKNOWN:
        return
    if _is_number(value):
        return
    raise ObservationValidationError(
        f"{ctx}: {field_name}={value!r} must be numeric, {UNKNOWN!r}"
        + (" or null" if allow_null else "")
    )


def _check_bool_or_unknown(value: Any, ctx: str, field_name: str, *, allow_null: bool = False) -> None:
    if allow_null and value is None:
        return
    if value == UNKNOWN or isinstance(value, bool):
        return
    raise ObservationValidationError(
        f"{ctx}: {field_name}={value!r} must be a bool, {UNKNOWN!r}"
        + (" or null" if allow_null else "")
    )


# --- match.yaml parsing --------------------------------------------------------------


def _parse_video(raw: dict) -> VideoMetadata:
    ctx = "match.video"
    return VideoMetadata(
        url=_req(raw, "url", ctx),
        retrieved=_req(raw, "retrieved", ctx),
        quality=_req(raw, "quality", ctx),
        camera=_req(raw, "camera", ctx),
        period_offsets=dict(_req(raw, "period_offsets", ctx)),
        sync_check=dict(_req(raw, "sync_check", ctx)),
        timing_precision_s=_req(raw, "timing_precision_s", ctx),
    )


def _parse_roster_entry(raw: dict) -> RobotEntry:
    ctx = f"match.roster[{raw.get('robot_ref')!r}]"
    return RobotEntry(
        robot_ref=_req(raw, "robot_ref", ctx),
        alliance=_req(raw, "alliance", ctx),
        team=_req(raw, "team", ctx),
        size_class=_req(raw, "size_class", ctx),
        visual_key=_req(raw, "visual_key", ctx),
        cycle_labeled=_req(raw, "cycle_labeled", ctx),
    )


def _parse_official_result(raw: dict) -> OfficialResult:
    ctx = "match.official_result"
    return OfficialResult(
        red_total=_req(raw, "red_total", ctx),
        blue_total=_req(raw, "blue_total", ctx),
        autonomous_bonus_to=_req(raw, "autonomous_bonus_to", ctx),
        awp=dict(_req(raw, "awp", ctx)),
        violations_autonomous=_req(raw, "violations_autonomous", ctx),
        source_url=_req(raw, "source_url", ctx),
        retrieved=_req(raw, "retrieved", ctx),
    )


def _parse_coverage(raw: dict) -> Coverage:
    ctx = "match.coverage"
    windows = tuple(
        UnlabeledWindow(
            period=w["period"], t_start=w["t_start"], t_end=w["t_end"], reason=w["reason"]
        )
        for w in raw.get("unlabeled_windows", [])
    )
    return Coverage(
        cycle_labeled_alliance=_req(raw, "cycle_labeled_alliance", ctx),
        fully_labeled=_req(raw, "fully_labeled", ctx),
        unlabeled_windows=windows,
    )


def _parse_labeling(raw: dict) -> LabelingMeta:
    ctx = "match.labeling"
    return LabelingMeta(
        labeler=_req(raw, "labeler", ctx),
        label_date=_req(raw, "label_date", ctx),
        pass_id=_req(raw, "pass_id", ctx),
        selection_stratum=_req(raw, "selection_stratum", ctx),
        minutes_spent=_req(raw, "minutes_spent", ctx),
        source_csv_sha256=raw.get("source_csv_sha256"),
    )


def parse_match(raw: dict) -> MatchObservation:
    ctx = "match"
    return MatchObservation(
        schema_version=_req(raw, "schema_version", ctx),
        match_key=_req(raw, "match_key", ctx),
        program=_req(raw, "program", ctx),
        event_name=_req(raw, "event_name", ctx),
        event_code=_req(raw, "event_code", ctx),
        match_id=_req(raw, "match_id", ctx),
        match_type=_req(raw, "match_type", ctx),
        date=str(_req(raw, "date", ctx)),
        manual_version=str(_req(raw, "manual_version", ctx)),
        video=_parse_video(_req(raw, "video", ctx)),
        roster=tuple(_parse_roster_entry(r) for r in _req(raw, "roster", ctx)),
        official_result=_parse_official_result(_req(raw, "official_result", ctx)),
        coverage=_parse_coverage(_req(raw, "coverage", ctx)),
        labeling=_parse_labeling(_req(raw, "labeling", ctx)),
    )


# --- snapshots.yaml parsing -----------------------------------------------------------


def _parse_stack_item(raw: dict, ctx: str) -> StackItem:
    return StackItem(
        object=_req(raw, "object", ctx),
        colors=raw.get("colors"),
        down_face=raw.get("down_face"),
        nested_half=raw.get("nested_half"),
    )


def _parse_goal_snapshot(raw: dict, ctx: str) -> GoalSnapshot:
    stack = tuple(_parse_stack_item(item, f"{ctx}.stack") for item in raw.get("stack", []))
    return GoalSnapshot(stack=stack, confidence=_req(raw, "confidence", ctx))


def _parse_toggle_snapshot(raw: dict, ctx: str) -> ToggleSnapshot:
    return ToggleSnapshot(
        orientation=_req(raw, "orientation", ctx),
        seated=_req(raw, "seated", ctx),
        contacted_by_robot=_req(raw, "contacted_by_robot", ctx),
        confidence=_req(raw, "confidence", ctx),
    )


def _parse_robot_snapshot(raw: dict, ctx: str) -> RobotSnapshot:
    return RobotSnapshot(
        in_midfield=_req(raw, "in_midfield", ctx),
        contacting_perimeter=raw.get("contacting_perimeter"),
        confidence=raw.get("confidence", "certain"),
    )


def parse_snapshot(raw: dict) -> Snapshot:
    ctx = f"snapshot[{raw.get('snapshot_id')!r}]"
    goals = {gid: _parse_goal_snapshot(g, f"{ctx}.goals.{gid}") for gid, g in _req(raw, "goals", ctx).items()}
    toggles = {
        tid: _parse_toggle_snapshot(t, f"{ctx}.toggles.{tid}") for tid, t in _req(raw, "toggles", ctx).items()
    }
    robots = {
        rref: _parse_robot_snapshot(r, f"{ctx}.robots.{rref}") for rref, r in _req(raw, "robots", ctx).items()
    }
    return Snapshot(
        snapshot_id=_req(raw, "snapshot_id", ctx),
        context=_req(raw, "context", ctx),
        video_t=_req(raw, "video_t", ctx),
        quality=_req(raw, "quality", ctx),
        goals=goals,
        toggles=toggles,
        robots=robots,
    )


# --- events.yaml parsing ---------------------------------------------------------------


def _parse_action(raw: dict) -> Action:
    ctx = f"action[{raw.get('id')!r}]"
    return Action(
        record_type="action",
        id=_req(raw, "id", ctx),
        action_type=_req(raw, "action_type", ctx),
        robot_ref=_req(raw, "robot_ref", ctx),
        period=_req(raw, "period", ctx),
        video_t_start=_req(raw, "video_t_start", ctx),
        video_t_end=_req(raw, "video_t_end", ctx),
        region=_req(raw, "region", ctx),
        outcome=_req(raw, "outcome", ctx),
        contested=_req(raw, "contested", ctx),
        retry_of=raw.get("retry_of"),
        confidence=_req(raw, "confidence", ctx),
        gap_after=raw.get("gap_after"),
        failure_mode=raw.get("failure_mode"),
        contested_robot_ref=raw.get("contested_robot_ref"),
        possession_id=raw.get("possession_id"),
        notes=raw.get("notes"),
        source=raw.get("source"),
        object=raw.get("object"),
        object_colors=raw.get("object_colors"),
        loader_visit_id=raw.get("loader_visit_id"),
        target_goal_ref=raw.get("target_goal_ref"),
        stack_height_before=raw.get("stack_height_before"),
        stack_height_after=raw.get("stack_height_after"),
        cup_down_face=raw.get("cup_down_face"),
        destabilized_stack=raw.get("destabilized_stack"),
        video_t_release=raw.get("video_t_release"),
        method=raw.get("method"),
        objects_removed=raw.get("objects_removed"),
        toggle_ref=raw.get("toggle_ref"),
        state_before=raw.get("state_before"),
        state_after=raw.get("state_after"),
        seated_after=raw.get("seated_after"),
    )


def _parse_loader_visit(raw: dict) -> LoaderVisit:
    ctx = f"loader_visit[{raw.get('id')!r}]"
    return LoaderVisit(
        record_type="loader_visit",
        id=_req(raw, "id", ctx),
        robot_ref=_req(raw, "robot_ref", ctx),
        period=_req(raw, "period", ctx),
        video_t_enter=_req(raw, "video_t_enter", ctx),
        video_t_exit=raw.get("video_t_exit"),
        loader_ref=_req(raw, "loader_ref", ctx),
        objects_acquired=_req(raw, "objects_acquired", ctx),
        failed_grabs=_req(raw, "failed_grabs", ctx),
        departs_possession_id=raw.get("departs_possession_id"),
        contested=_req(raw, "contested", ctx),
        confidence=_req(raw, "confidence", ctx),
        objects_types=raw.get("objects_types"),
        video_t_first_object_available=raw.get("video_t_first_object_available"),
        notes=raw.get("notes"),
    )


def _parse_midfield_occupancy(raw: dict) -> MidfieldOccupancy:
    ctx = f"midfield_occupancy[{raw.get('id')!r}]"
    return MidfieldOccupancy(
        record_type="midfield_occupancy",
        id=_req(raw, "id", ctx),
        robot_ref=_req(raw, "robot_ref", ctx),
        period=_req(raw, "period", ctx),
        video_t_enter=_req(raw, "video_t_enter", ctx),
        video_t_exit=raw.get("video_t_exit"),
        contested_during=_req(raw, "contested_during", ctx),
        confidence=_req(raw, "confidence", ctx),
        exit_coincident_with_contact=raw.get("exit_coincident_with_contact"),
        notes=raw.get("notes"),
    )


def _parse_incident(raw: dict) -> Incident:
    ctx = f"incident[{raw.get('id')!r}]"
    return Incident(
        record_type="incident",
        id=_req(raw, "id", ctx),
        robot_ref=_req(raw, "robot_ref", ctx),
        period=_req(raw, "period", ctx),
        video_t_start=_req(raw, "video_t_start", ctx),
        video_t_end=raw.get("video_t_end"),
        incident_type=_req(raw, "incident_type", ctx),
        resolution=_req(raw, "resolution", ctx),
        confidence=_req(raw, "confidence", ctx),
        notes=raw.get("notes"),
    )


def _parse_interaction(raw: dict) -> Interaction:
    ctx = f"interaction[{raw.get('id')!r}]"
    return Interaction(
        record_type="interaction",
        id=_req(raw, "id", ctx),
        actor_robot_ref=_req(raw, "actor_robot_ref", ctx),
        subject_robot_ref=_req(raw, "subject_robot_ref", ctx),
        video_t_start=_req(raw, "video_t_start", ctx),
        video_t_end=_req(raw, "video_t_end", ctx),
        period=_req(raw, "period", ctx),
        interaction_type=_req(raw, "interaction_type", ctx),
        confidence=_req(raw, "confidence", ctx),
        subject_region=raw.get("subject_region"),
        notes=raw.get("notes"),
    )


def _parse_state_change(raw: dict) -> StateChange:
    ctx = f"state_change[{raw.get('id')!r}]"
    return StateChange(
        record_type="state_change",
        id=_req(raw, "id", ctx),
        period=_req(raw, "period", ctx),
        video_t=_req(raw, "video_t", ctx),
        change=_req(raw, "change", ctx),
        attributed_to=raw.get("attributed_to"),
        confidence=_req(raw, "confidence", ctx),
        target_goal_ref=raw.get("target_goal_ref"),
        stack_height_before=raw.get("stack_height_before"),
        stack_height_after=raw.get("stack_height_after"),
        toggle_ref=raw.get("toggle_ref"),
        state_after=raw.get("state_after"),
        seated_after=raw.get("seated_after"),
        possession_id=raw.get("possession_id"),
        object=raw.get("object"),
        caused_by_action=raw.get("caused_by_action"),
        notes=raw.get("notes"),
    )


_EVENT_PARSERS = {
    "action": _parse_action,
    "loader_visit": _parse_loader_visit,
    "midfield_occupancy": _parse_midfield_occupancy,
    "incident": _parse_incident,
    "interaction": _parse_interaction,
    "state_change": _parse_state_change,
}


def parse_event(raw: dict) -> Any:
    record_type = raw.get("record_type")
    parser = _EVENT_PARSERS.get(record_type)
    if parser is None:
        raise ObservationValidationError(
            f"event record has unknown record_type {record_type!r}; must be one of "
            f"{sorted(_EVENT_PARSERS)}"
        )
    return parser(raw)


# --- validation ------------------------------------------------------------------------


def _validate_match(match: MatchObservation, errors: list[str]) -> None:
    try:
        validate_empirical_program(match.program)
    except SourceValidationError as exc:
        errors.append(str(exc))
        return

    for r in match.roster:
        if match.program == "v5rc" and r.size_class != "unknown_v5rc":
            errors.append(
                f"roster[{r.robot_ref!r}]: a v5rc robot must have size_class 'unknown_v5rc', "
                f"got {r.size_class!r} -- V5RC has no 15\"/24\" class (§J.1)"
            )
        if match.program == "vexu" and r.size_class not in ("vexu_24", "vexu_15"):
            errors.append(
                f"roster[{r.robot_ref!r}]: a vexu robot must have size_class 'vexu_24' or "
                f"'vexu_15', got {r.size_class!r}"
            )
        if r.size_class not in SIZE_CLASSES:
            errors.append(f"roster[{r.robot_ref!r}]: invalid size_class {r.size_class!r}")

    if match.video.quality not in VIDEO_QUALITIES:
        errors.append(f"match.video.quality={match.video.quality!r} invalid")
    if match.video.camera not in CAMERA_TYPES:
        errors.append(f"match.video.camera={match.video.camera!r} invalid")


def _robot_refs(match: MatchObservation) -> frozenset[str]:
    return frozenset(r.robot_ref for r in match.roster)


def _cycle_labeled_refs(match: MatchObservation) -> frozenset[str]:
    return frozenset(r.robot_ref for r in match.roster if r.cycle_labeled)


def _validate_snapshots(
    match: MatchObservation,
    snapshots: tuple[Snapshot, ...],
    goal_ids: frozenset[str],
    toggle_ids: frozenset[str],
    errors: list[str],
) -> None:
    contexts = [s.context for s in snapshots]
    for required_context in SNAPSHOT_CONTEXTS:
        if contexts.count(required_context) != 1:
            errors.append(
                f"snapshots: exactly one snapshot with context={required_context!r} is required, "
                f"found {contexts.count(required_context)}"
            )

    robot_refs = _robot_refs(match)
    for snap in snapshots:
        if snap.context not in SNAPSHOT_CONTEXTS:
            errors.append(f"snapshot[{snap.snapshot_id!r}]: invalid context {snap.context!r}")
        if snap.quality not in SNAPSHOT_QUALITIES:
            errors.append(f"snapshot[{snap.snapshot_id!r}]: invalid quality {snap.quality!r}")

        missing_goals = goal_ids - snap.goals.keys()
        if missing_goals:
            errors.append(f"snapshot[{snap.snapshot_id!r}]: missing Goals {sorted(missing_goals)}")
        missing_toggles = toggle_ids - snap.toggles.keys()
        if missing_toggles:
            errors.append(f"snapshot[{snap.snapshot_id!r}]: missing Toggles {sorted(missing_toggles)}")
        missing_robots = robot_refs - snap.robots.keys()
        if missing_robots:
            errors.append(f"snapshot[{snap.snapshot_id!r}]: missing robots {sorted(missing_robots)}")

        for gid, goal in snap.goals.items():
            if goal.confidence not in CONFIDENCE_LEVELS:
                errors.append(f"snapshot[{snap.snapshot_id!r}].goals[{gid!r}]: invalid confidence")
            for item in goal.stack:
                if item.object not in STACK_OBJECT_TYPES:
                    errors.append(f"snapshot[{snap.snapshot_id!r}].goals[{gid!r}]: invalid stack object")
                if item.object == "pin" and not item.colors:
                    errors.append(
                        f"snapshot[{snap.snapshot_id!r}].goals[{gid!r}]: pin stack item missing 'colors'"
                    )
                if item.object == "cup" and item.down_face is None:
                    errors.append(
                        f"snapshot[{snap.snapshot_id!r}].goals[{gid!r}]: cup stack item missing 'down_face'"
                    )
                if item.down_face is not None and item.down_face not in CUP_FACES:
                    errors.append(f"snapshot[{snap.snapshot_id!r}].goals[{gid!r}]: invalid down_face")
                if item.nested_half is not None and item.nested_half not in NESTED_HALVES:
                    errors.append(f"snapshot[{snap.snapshot_id!r}].goals[{gid!r}]: invalid nested_half")

        for tid, toggle in snap.toggles.items():
            if toggle.orientation not in TOGGLE_ORIENTATIONS:
                errors.append(f"snapshot[{snap.snapshot_id!r}].toggles[{tid!r}]: invalid orientation")
            _check_bool_or_unknown(toggle.seated, f"snapshot.toggles[{tid!r}]", "seated")
            _check_bool_or_unknown(toggle.contacted_by_robot, f"snapshot.toggles[{tid!r}]", "contacted_by_robot")

        for rref, robot in snap.robots.items():
            _check_bool_or_unknown(robot.in_midfield, f"snapshot.robots[{rref!r}]", "in_midfield")
            if snap.context == "autonomous_end" and robot.contacting_perimeter is None:
                errors.append(
                    f"snapshot[{snap.snapshot_id!r}].robots[{rref!r}]: contacting_perimeter is "
                    f"REQ-IF context == autonomous_end"
                )
            if robot.contacting_perimeter is not None:
                _check_bool_or_unknown(
                    robot.contacting_perimeter, f"snapshot.robots[{rref!r}]", "contacting_perimeter"
                )


def _all_event_ids(events: tuple) -> frozenset[str]:
    return frozenset(e.id for e in events)


def _actions(events: tuple) -> list[Action]:
    return [e for e in events if isinstance(e, Action)]


def _loader_visits(events: tuple) -> list[LoaderVisit]:
    return [e for e in events if isinstance(e, LoaderVisit)]


def _validate_action(
    action: Action,
    match: MatchObservation,
    robot_refs: frozenset[str],
    goal_ids: frozenset[str],
    toggle_ids: frozenset[str],
    regions: frozenset[str],
    loader_visit_ids: frozenset[str],
    errors: list[str],
    warnings: list[str],
) -> None:
    ctx = f"action[{action.id!r}]"

    if action.action_type not in ACTION_TYPES:
        errors.append(f"{ctx}: invalid action_type {action.action_type!r}")
        return
    if action.robot_ref not in robot_refs:
        errors.append(f"{ctx}: robot_ref {action.robot_ref!r} does not resolve to a rostered robot")
    if action.period not in PERIODS:
        errors.append(f"{ctx}: invalid period {action.period!r}")
    if action.region not in regions:
        errors.append(f"{ctx}: region {action.region!r} not in the declared region vocabulary")
    if action.outcome not in OUTCOMES:
        errors.append(f"{ctx}: invalid outcome {action.outcome!r}")
    if action.contested not in CONTESTED_VALUES:
        errors.append(f"{ctx}: invalid contested {action.contested!r}")
    if action.confidence not in CONFIDENCE_LEVELS:
        errors.append(f"{ctx}: invalid confidence {action.confidence!r}")
    if action.contested_robot_ref is not None and action.contested_robot_ref not in robot_refs:
        errors.append(f"{ctx}: contested_robot_ref {action.contested_robot_ref!r} does not resolve")

    # video_t_end: numeric or "unknown", NEVER null (§E.3).
    if action.video_t_end is None:
        errors.append(f"{ctx}: video_t_end may never be null for an Action (Revision 2.1, §E.3)")
    else:
        _check_numeric_or_unknown(action.video_t_end, ctx, "video_t_end")
        if _is_number(action.video_t_end) and _is_number(action.video_t_start):
            if action.video_t_end <= action.video_t_start:
                errors.append(
                    f"{ctx}: video_t_end ({action.video_t_end}) must be strictly greater than "
                    f"video_t_start ({action.video_t_start})"
                )

    # outcome / failure_mode REQ-IF
    if action.outcome != "success":
        if action.failure_mode is None:
            errors.append(f"{ctx}: failure_mode is REQ-IF outcome != success")
        elif action.failure_mode not in FAILURE_MODES:
            errors.append(f"{ctx}: invalid failure_mode {action.failure_mode!r}")
    elif action.failure_mode is not None:
        errors.append(f"{ctx}: failure_mode must be absent when outcome == success")

    # gap_after REQ-IF cycle_labeled
    robot_entry = next((r for r in match.roster if r.robot_ref == action.robot_ref), None)
    if robot_entry is not None:
        if robot_entry.cycle_labeled:
            if action.gap_after is None:
                errors.append(f"{ctx}: gap_after is REQ-IF robot {action.robot_ref!r} is cycle_labeled")
            elif action.gap_after not in GAP_CLASSES:
                errors.append(f"{ctx}: invalid gap_after {action.gap_after!r}")
        elif action.gap_after is not None:
            errors.append(
                f"{ctx}: gap_after must be absent -- robot {action.robot_ref!r} is not cycle_labeled"
            )

    # possession_id REQ-IF action_type in {acquire, place}
    if action.action_type in ("acquire", "place"):
        if action.possession_id is None:
            errors.append(f"{ctx}: possession_id is REQ-IF action_type in {{acquire, place}}")
    elif action.possession_id is not None:
        errors.append(f"{ctx}: possession_id must be absent for action_type={action.action_type!r}")

    # --- per action_type field checks ---
    if action.action_type == "acquire":
        if action.source not in ACQUIRE_SOURCES:
            errors.append(f"{ctx}: invalid source {action.source!r}")
        if action.object not in ACQUIRE_OBJECTS:
            errors.append(f"{ctx}: invalid object {action.object!r}")
        if action.loader_visit_id is not None and action.loader_visit_id not in loader_visit_ids:
            errors.append(
                f"{ctx}: loader_visit_id {action.loader_visit_id!r} does not resolve to a LoaderVisit"
            )
        for absent_field in ("target_goal_ref", "method", "toggle_ref"):
            if getattr(action, absent_field) is not None:
                errors.append(f"{ctx}: {absent_field} must be absent for action_type='acquire'")

    elif action.action_type == "place":
        if action.target_goal_ref not in goal_ids:
            errors.append(f"{ctx}: target_goal_ref {action.target_goal_ref!r} not a canonical Goal id")
        if action.object not in PLACE_DESCORE_OBJECTS:
            errors.append(f"{ctx}: invalid object {action.object!r}")
        if action.stack_height_before is None:
            errors.append(f"{ctx}: stack_height_before is REQ for action_type='place'")
        else:
            _check_numeric_or_unknown(action.stack_height_before, ctx, "stack_height_before")
        if action.stack_height_after is None:
            errors.append(f"{ctx}: stack_height_after is REQ for action_type='place'")
        else:
            _check_numeric_or_unknown(action.stack_height_after, ctx, "stack_height_after")
        if action.object == "cup" and action.cup_down_face is None:
            errors.append(f"{ctx}: cup_down_face is REQ-IF object == 'cup'")
        if action.object != "cup" and action.cup_down_face is not None:
            errors.append(f"{ctx}: cup_down_face must be absent when object != 'cup'")
        if action.destabilized_stack is None:
            errors.append(f"{ctx}: destabilized_stack is REQ for action_type='place'")
        else:
            _check_bool_or_unknown(action.destabilized_stack, ctx, "destabilized_stack")
        if action.video_t_release is not None:
            _check_numeric_or_unknown(action.video_t_release, ctx, "video_t_release")

    elif action.action_type == "descore":
        if action.target_goal_ref not in goal_ids:
            errors.append(f"{ctx}: target_goal_ref {action.target_goal_ref!r} not a canonical Goal id")
        if action.method not in DESCORE_METHODS:
            errors.append(f"{ctx}: invalid method {action.method!r}")
        if action.method in ("extract", "topple"):
            if action.objects_removed is None:
                errors.append(f"{ctx}: objects_removed is REQ-IF method in {{extract, topple}}")
            else:
                _check_numeric_or_unknown(action.objects_removed, ctx, "objects_removed")
        elif action.objects_removed is not None:
            errors.append(f"{ctx}: objects_removed must be absent for method={action.method!r}")
        if action.stack_height_before is None:
            errors.append(f"{ctx}: stack_height_before is REQ for action_type='descore'")
        else:
            _check_numeric_or_unknown(action.stack_height_before, ctx, "stack_height_before")
        if action.stack_height_after is None:
            errors.append(f"{ctx}: stack_height_after is REQ for action_type='descore'")
        else:
            _check_numeric_or_unknown(action.stack_height_after, ctx, "stack_height_after")
        if action.method == "obscure" and action.cup_down_face is None:
            errors.append(f"{ctx}: cup_down_face is REQ-IF method == 'obscure'")
        if action.method != "obscure" and action.cup_down_face is not None:
            errors.append(f"{ctx}: cup_down_face must be absent unless method == 'obscure'")
        if action.object is not None:
            errors.append(f"{ctx}: object must be absent for action_type='descore'")

    elif action.action_type == "toggle":
        if action.toggle_ref not in toggle_ids:
            errors.append(f"{ctx}: toggle_ref {action.toggle_ref!r} not a canonical Toggle id")
        if action.state_before not in PIN_COLORS:
            errors.append(f"{ctx}: invalid state_before {action.state_before!r}")
        if action.state_after not in PIN_COLORS:
            errors.append(f"{ctx}: invalid state_after {action.state_after!r}")
        if action.seated_after is None:
            errors.append(f"{ctx}: seated_after is REQ for action_type='toggle'")
        else:
            _check_bool_or_unknown(action.seated_after, ctx, "seated_after")
        if action.method not in TOGGLE_METHODS:
            errors.append(f"{ctx}: invalid method {action.method!r}")


def _validate_retry_chains(actions: list[Action], errors: list[str]) -> None:
    action_by_id = {a.id: a for a in actions}
    for action in actions:
        if action.retry_of is None:
            continue
        if action.retry_of not in action_by_id:
            errors.append(f"action[{action.id!r}]: retry_of {action.retry_of!r} does not resolve to an Action")
            continue
        seen = {action.id}
        current = action
        while current.retry_of is not None:
            if current.retry_of in seen:
                errors.append(f"action[{action.id!r}]: retry_of chain is cyclic")
                break
            seen.add(current.retry_of)
            current = action_by_id.get(current.retry_of)
            if current is None:
                break


def _validate_no_next_action(actions: list[Action], match: MatchObservation, errors: list[str]) -> None:
    by_robot_period: dict[tuple[str, str], list[Action]] = {}
    for a in actions:
        by_robot_period.setdefault((a.robot_ref, a.period), []).append(a)

    for (robot_ref, period), group in by_robot_period.items():
        robot_entry = next((r for r in match.roster if r.robot_ref == robot_ref), None)
        if robot_entry is None or not robot_entry.cycle_labeled:
            continue
        ordered = sorted(group, key=lambda a: a.video_t_start)
        for i, action in enumerate(ordered):
            has_next = i < len(ordered) - 1
            if has_next and action.gap_after == "no_next_action":
                errors.append(
                    f"action[{action.id!r}]: gap_after='no_next_action' but a later Action exists "
                    f"for robot {robot_ref!r} in period {period!r} (§F.2 -- recomputed deterministically)"
                )
            if not has_next and action.gap_after is not None and action.gap_after != "no_next_action":
                errors.append(
                    f"action[{action.id!r}]: this is robot {robot_ref!r}'s last labeled Action of "
                    f"period {period!r}; gap_after must be 'no_next_action', got {action.gap_after!r}"
                )


def _validate_loader_visit(
    lv: LoaderVisit, robot_refs: frozenset[str], regions_unused: frozenset[str], errors: list[str]
) -> None:
    ctx = f"loader_visit[{lv.id!r}]"
    if lv.robot_ref not in robot_refs:
        errors.append(f"{ctx}: robot_ref {lv.robot_ref!r} does not resolve to a rostered robot")
    if lv.period not in PERIODS:
        errors.append(f"{ctx}: invalid period {lv.period!r}")
    if lv.loader_ref not in refs.loader_refs():
        errors.append(f"{ctx}: loader_ref {lv.loader_ref!r} not in the declared Loader vocabulary")
    if lv.contested not in CONTESTED_VALUES:
        errors.append(f"{ctx}: invalid contested {lv.contested!r}")
    if lv.confidence not in CONFIDENCE_LEVELS:
        errors.append(f"{ctx}: invalid confidence {lv.confidence!r}")
    _check_numeric_or_unknown(lv.video_t_exit, ctx, "video_t_exit", allow_null=True)
    _check_numeric_or_unknown(lv.objects_acquired, ctx, "objects_acquired")
    _check_numeric_or_unknown(lv.failed_grabs, ctx, "failed_grabs")
    if lv.video_t_first_object_available is not None:
        _check_numeric_or_unknown(lv.video_t_first_object_available, ctx, "video_t_first_object_available")


def _validate_midfield_occupancy(mo: MidfieldOccupancy, robot_refs: frozenset[str], errors: list[str]) -> None:
    ctx = f"midfield_occupancy[{mo.id!r}]"
    if mo.robot_ref not in robot_refs:
        errors.append(f"{ctx}: robot_ref {mo.robot_ref!r} does not resolve to a rostered robot")
    if mo.period not in PERIODS:
        errors.append(f"{ctx}: invalid period {mo.period!r}")
    if mo.confidence not in CONFIDENCE_LEVELS:
        errors.append(f"{ctx}: invalid confidence {mo.confidence!r}")
    _check_numeric_or_unknown(mo.video_t_enter, ctx, "video_t_enter")
    _check_numeric_or_unknown(mo.video_t_exit, ctx, "video_t_exit", allow_null=True)
    _check_bool_or_unknown(mo.contested_during, ctx, "contested_during")
    if _is_number(mo.video_t_exit) or mo.video_t_exit == UNKNOWN:
        if mo.exit_coincident_with_contact is None:
            errors.append(f"{ctx}: exit_coincident_with_contact is REQ-IF video_t_exit is not null")
        else:
            _check_bool_or_unknown(mo.exit_coincident_with_contact, ctx, "exit_coincident_with_contact")
    elif mo.exit_coincident_with_contact is not None:
        errors.append(f"{ctx}: exit_coincident_with_contact must be absent when video_t_exit is null")


def _validate_incident(inc: Incident, robot_refs: frozenset[str], errors: list[str]) -> None:
    ctx = f"incident[{inc.id!r}]"
    if inc.robot_ref not in robot_refs:
        errors.append(f"{ctx}: robot_ref {inc.robot_ref!r} does not resolve to a rostered robot")
    if inc.period not in PERIODS:
        errors.append(f"{ctx}: invalid period {inc.period!r}")
    if inc.incident_type not in INCIDENT_TYPES:
        errors.append(f"{ctx}: invalid incident_type {inc.incident_type!r}")
    if inc.resolution not in RESOLUTIONS:
        errors.append(f"{ctx}: invalid resolution {inc.resolution!r}")
    if inc.confidence not in CONFIDENCE_LEVELS:
        errors.append(f"{ctx}: invalid confidence {inc.confidence!r}")
    _check_numeric_or_unknown(inc.video_t_start, ctx, "video_t_start")
    _check_numeric_or_unknown(inc.video_t_end, ctx, "video_t_end", allow_null=True)


def _validate_interaction(ia: Interaction, robot_refs: frozenset[str], errors: list[str]) -> None:
    ctx = f"interaction[{ia.id!r}]"
    if ia.actor_robot_ref not in robot_refs:
        errors.append(f"{ctx}: actor_robot_ref {ia.actor_robot_ref!r} does not resolve")
    if ia.subject_robot_ref not in robot_refs:
        errors.append(f"{ctx}: subject_robot_ref {ia.subject_robot_ref!r} does not resolve")
    if ia.period not in PERIODS:
        errors.append(f"{ctx}: invalid period {ia.period!r}")
    if ia.interaction_type not in INTERACTION_TYPES:
        errors.append(f"{ctx}: invalid interaction_type {ia.interaction_type!r}")
    if ia.confidence not in CONFIDENCE_LEVELS:
        errors.append(f"{ctx}: invalid confidence {ia.confidence!r}")
    _check_numeric_or_unknown(ia.video_t_start, ctx, "video_t_start")
    _check_numeric_or_unknown(ia.video_t_end, ctx, "video_t_end")


def _validate_state_change(
    sc: StateChange, robot_refs: frozenset[str], goal_ids: frozenset[str], toggle_ids: frozenset[str],
    errors: list[str],
) -> None:
    ctx = f"state_change[{sc.id!r}]"
    if sc.period not in PERIODS:
        errors.append(f"{ctx}: invalid period {sc.period!r}")
    if sc.change not in CHANGE_TYPES:
        errors.append(f"{ctx}: invalid change {sc.change!r}")
    if sc.confidence not in CONFIDENCE_LEVELS:
        errors.append(f"{ctx}: invalid confidence {sc.confidence!r}")
    if sc.attributed_to is not None and sc.attributed_to != UNKNOWN and sc.attributed_to not in robot_refs:
        errors.append(f"{ctx}: attributed_to {sc.attributed_to!r} does not resolve to a rostered robot")

    is_goal_affecting = sc.change in GOAL_AFFECTING_CHANGES
    is_toggle_affecting = sc.change in TOGGLE_AFFECTING_CHANGES
    is_possession_affecting = sc.change in POSSESSION_AFFECTING_CHANGES

    if is_goal_affecting:
        if sc.target_goal_ref not in goal_ids:
            errors.append(f"{ctx}: target_goal_ref {sc.target_goal_ref!r} not a canonical Goal id")
        if sc.stack_height_before is None or sc.stack_height_after is None:
            errors.append(f"{ctx}: stack_height_before/after are REQ-IF change is goal-affecting")
        else:
            _check_numeric_or_unknown(sc.stack_height_before, ctx, "stack_height_before")
            _check_numeric_or_unknown(sc.stack_height_after, ctx, "stack_height_after")
    else:
        for absent_field in ("target_goal_ref", "stack_height_before", "stack_height_after"):
            if getattr(sc, absent_field) is not None:
                errors.append(f"{ctx}: {absent_field} must be absent unless change is goal-affecting")

    if is_toggle_affecting:
        if sc.toggle_ref not in toggle_ids:
            errors.append(f"{ctx}: toggle_ref {sc.toggle_ref!r} not a canonical Toggle id")
        if sc.state_after is None:
            errors.append(f"{ctx}: state_after is REQ-IF change is toggle-affecting")
        if sc.seated_after is None:
            errors.append(f"{ctx}: seated_after is REQ-IF change is toggle-affecting")
    else:
        for absent_field in ("toggle_ref", "state_after", "seated_after"):
            if getattr(sc, absent_field) is not None:
                errors.append(f"{ctx}: {absent_field} must be absent unless change is toggle-affecting")

    if is_possession_affecting:
        if sc.possession_id is None:
            errors.append(f"{ctx}: possession_id is REQ-IF change is possession-affecting")
        if sc.object is None:
            errors.append(f"{ctx}: object is REQ-IF change is possession-affecting")
    else:
        if sc.possession_id is not None:
            errors.append(f"{ctx}: possession_id must be absent unless change is possession-affecting")
        if sc.object is not None:
            errors.append(f"{ctx}: object must be absent unless change is possession-affecting")

    if sc.caused_by_action is not None:
        pass  # resolved centrally against the full action id set


def _validate_possession_episodes(
    events: tuple, match: MatchObservation, errors: list[str], warnings: list[str]
) -> None:
    """Per-robot possession-episode tracking (§C.7). Not interleaved: at most one
    open episode per robot at a time. Warnings (not errors) for the two cases the
    plan explicitly calls out as warnings; anything else that breaks the invariant
    (referencing a possession_id that is neither the currently open one nor a fresh
    one when opening) is an error."""
    by_robot: dict[str, list] = {}
    for e in events:
        if isinstance(e, Action) and e.action_type in ("acquire", "place"):
            by_robot.setdefault(e.robot_ref, []).append(("action", e.video_t_start, e))
        elif isinstance(e, StateChange) and e.change in POSSESSION_AFFECTING_CHANGES:
            robot = e.attributed_to
            if robot and robot != UNKNOWN:
                by_robot.setdefault(robot, []).append(("state_change", e.video_t, e))

    for robot_ref, items in by_robot.items():
        items.sort(key=lambda t: t[1])
        open_id: Optional[str] = None
        held: set[str] = set()
        used_ids: set[str] = set()
        for kind, _t, rec in items:
            if kind == "action" and rec.action_type == "acquire":
                types = {"pin", "cup"} if rec.object == "pin_and_cup" else (
                    {rec.object} if rec.object in ("pin", "cup") else set()
                )
                if open_id is None:
                    open_id = rec.possession_id
                    held = set(types)
                    if open_id:
                        used_ids.add(open_id)
                else:
                    if rec.possession_id != open_id:
                        errors.append(
                            f"action[{rec.id!r}]: possession_id {rec.possession_id!r} does not match "
                            f"robot {robot_ref!r}'s currently open episode {open_id!r} -- possession "
                            f"episodes must be per-robot and non-interleaved"
                        )
                    else:
                        if types & held:
                            warnings.append(
                                f"action[{rec.id!r}]: acquiring object type already held in open "
                                f"episode {open_id!r} (possible <SG6> violation or labeling error)"
                            )
                        held |= types
            elif kind == "action" and rec.action_type == "place":
                obj = rec.object
                if open_id is None or rec.possession_id != open_id or obj not in held:
                    warnings.append(
                        f"action[{rec.id!r}]: place.object {obj!r} is not consistent with robot "
                        f"{robot_ref!r}'s open possession episode ({open_id!r}, holding {sorted(held)})"
                    )
                held.discard(obj)
                if not held:
                    open_id = None
            elif kind == "state_change":
                if rec.object in held:
                    held.discard(rec.object)
                if not held:
                    open_id = None

        if open_id is not None:
            warnings.append(
                f"robot {robot_ref!r}: possession episode {open_id!r} is still open at the end of "
                f"the labeled record stream (legal -- the robot ended holding something)"
            )


def _validate_period_bounds(
    events: tuple, match: MatchObservation, rule_bundle: RuleBundle, warnings: list[str]
) -> None:
    """Soft check that event timestamps fall inside the period's rule-defined length,
    read from RuleBundle rather than a hardcoded value (§E.2). Video timing carries
    real imprecision, so a violation is a warning, not an error."""
    period_key = {"autonomous": "autonomous", "driver": "driver_controlled"}
    for period_name, offset in match.video.period_offsets.items():
        rule_period = period_key.get(period_name)
        if rule_period is None:
            continue
        try:
            length = rule_bundle.period_seconds(rule_period)
        except (KeyError, TypeError):
            continue  # e.g. VEX U endgame_seconds gap -- not this function's concern
        for e in events:
            if getattr(e, "period", None) != period_name:
                continue
            t = getattr(e, "video_t_start", None) or getattr(e, "video_t", None) or getattr(
                e, "video_t_enter", None
            )
            if not _is_number(t):
                continue
            match_clock_t = t - offset
            if match_clock_t < -0.5 or match_clock_t > length + 0.5:
                warnings.append(
                    f"{e.record_type}[{e.id!r}]: video_t implies match-clock time {match_clock_t:.1f}s, "
                    f"outside period {period_name!r}'s {length}s bound"
                )


def validate_observation_set(
    match: MatchObservation,
    snapshots: tuple[Snapshot, ...],
    events: tuple,
    rule_bundle: RuleBundle,
) -> tuple[list[str], list[str]]:
    """Validate a fully parsed match. Returns (errors, warnings); never raises."""
    errors: list[str] = []
    warnings: list[str] = []

    _validate_match(match, errors)

    goal_ids = refs.canonical_goal_ids(rule_bundle)
    toggle_ids = refs.canonical_toggle_ids(rule_bundle)
    regions = refs.region_vocabulary(rule_bundle)
    robot_refs = _robot_refs(match)

    _validate_snapshots(match, snapshots, goal_ids, toggle_ids, errors)

    actions = _actions(events)
    loader_visits = _loader_visits(events)
    loader_visit_ids = _all_event_ids(tuple(loader_visits))
    all_action_ids = _all_event_ids(tuple(actions))

    for a in actions:
        _validate_action(
            a, match, robot_refs, goal_ids, toggle_ids, regions, loader_visit_ids, errors, warnings
        )
        if a.retry_of is not None and a.retry_of not in all_action_ids:
            errors.append(f"action[{a.id!r}]: retry_of {a.retry_of!r} does not resolve to an Action")

    _validate_retry_chains(actions, errors)
    _validate_no_next_action(actions, match, errors)

    for lv in loader_visits:
        _validate_loader_visit(lv, robot_refs, regions, errors)

    for e in events:
        if isinstance(e, MidfieldOccupancy):
            _validate_midfield_occupancy(e, robot_refs, errors)
        elif isinstance(e, Incident):
            _validate_incident(e, robot_refs, errors)
        elif isinstance(e, Interaction):
            _validate_interaction(e, robot_refs, errors)
        elif isinstance(e, StateChange):
            _validate_state_change(e, robot_refs, goal_ids, toggle_ids, errors)
            if e.caused_by_action is not None and e.caused_by_action not in all_action_ids:
                errors.append(
                    f"state_change[{e.id!r}]: caused_by_action {e.caused_by_action!r} does not "
                    f"resolve to an Action"
                )

    _validate_possession_episodes(events, match, errors, warnings)
    _validate_period_bounds(events, match, rule_bundle, warnings)

    # overlapping actions -- permitted, warned (§E.4)
    by_robot: dict[str, list[Action]] = {}
    for a in actions:
        by_robot.setdefault(a.robot_ref, []).append(a)
    for robot_ref, group in by_robot.items():
        ordered = sorted(group, key=lambda a: a.video_t_start)
        for prev, nxt in zip(ordered, ordered[1:]):
            if _is_number(prev.video_t_end) and prev.video_t_end > nxt.video_t_start:
                warnings.append(
                    f"actions {prev.id!r} and {nxt.id!r} (robot {robot_ref!r}) overlap in time"
                )

    return errors, warnings


# --- top-level API -----------------------------------------------------------------


def load_match_observation(path: Path, *, rule_bundle: RuleBundle) -> LoadedMatch:
    """Load and validate one match directory (match.yaml + snapshots.yaml + events.yaml).

    Raises ObservationValidationError (with every error found, not just the first) if
    the match fails validation.
    """
    match_path = path / "match.yaml"
    snapshots_path = path / "snapshots.yaml"
    events_path = path / "events.yaml"

    with match_path.open(encoding="utf-8") as f:
        match = parse_match(yaml.safe_load(f))
    with snapshots_path.open(encoding="utf-8") as f:
        snapshots = tuple(parse_snapshot(s) for s in (yaml.safe_load(f) or []))
    with events_path.open(encoding="utf-8") as f:
        events = tuple(parse_event(e) for e in (yaml.safe_load(f) or []))

    errors, warnings = validate_observation_set(match, snapshots, events, rule_bundle)
    if errors:
        raise ObservationValidationError(
            f"{path}: {len(errors)} validation error(s):\n  - " + "\n  - ".join(errors)
        )

    return LoadedMatch(match=match, snapshots=snapshots, events=events, warnings=tuple(warnings))


def load_all_observations(observations_root: Path, *, rule_bundle: RuleBundle) -> list[LoadedMatch]:
    """Load every match directory under observations_root/<program>/*/match.yaml."""
    program_dir = observations_root / rule_bundle.program
    if not program_dir.is_dir():
        return []
    loaded = []
    for match_dir in sorted(program_dir.iterdir()):
        if (match_dir / "match.yaml").is_file():
            loaded.append(load_match_observation(match_dir, rule_bundle=rule_bundle))
    return loaded

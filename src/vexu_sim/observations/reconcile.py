"""M3's three required QC reconciliation channels, plus the optional best-effort
Goal-composition channel (docs/plans/m3-observation-plan.md §H.2).

Snapshots are authoritative. Reconciliation is a labeling-completeness *signal*,
never a score source and never a write path: nothing here edits an observation, and
nothing here compiles a Goal's stack into a `MatchState`/runs the scorer -- that
boundary belongs to M4 (§H.3). A non-zero delta is reported, never corrected.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from vexu_sim.field_setup import build_v5rc_starting_state, build_vexu_starting_state
from vexu_sim.rules import RuleBundle

from .models import (
    UNKNOWN,
    Action,
    GOAL_AFFECTING_CHANGES,
    MatchObservation,
    MidfieldOccupancy,
    Snapshot,
    StateChange,
    TOGGLE_AFFECTING_CHANGES,
)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


@dataclass(frozen=True)
class ChannelResult:
    status: str  # "match" | "mismatch" | "indeterminate"
    detail: str


@dataclass(frozen=True)
class ReconciliationReport:
    goal_depth: dict[str, ChannelResult]
    toggle_orientation: dict[str, ChannelResult]
    midfield_occupancy: dict[str, ChannelResult]  # key: "<robot_ref>@<context>"
    goal_composition: dict[str, ChannelResult]


def _starting_state(rule_bundle: RuleBundle):
    if rule_bundle.program == "v5rc":
        return build_v5rc_starting_state(rule_bundle)
    if rule_bundle.program == "vexu":
        return build_vexu_starting_state(rule_bundle)
    raise ValueError(f"unknown program {rule_bundle.program!r}")


def _starting_goal_depths(rule_bundle: RuleBundle) -> dict[str, int]:
    """Physical Pin+Cup count on each Goal at kickoff. Every M2 starting state has at
    most one Pin directly Placed per Goal and no Cups on a Goal, so counting Pins
    whose `.goal` names this Goal is exact for the current rule data; a future
    starting-state change that stacks a Cup at kickoff would need this extended."""
    state = _starting_state(rule_bundle).match_state
    depths = {g.id: 0 for g in state.goals}
    for pin in state.pins:
        if pin.goal is not None:
            depths[pin.goal.id] += 1
    return depths


def _match_end_snapshot(snapshots: tuple[Snapshot, ...]) -> Snapshot | None:
    for s in snapshots:
        if s.context == "match_end":
            return s
    return None


def _goal_touching_records(events: tuple) -> dict[str, list]:
    by_goal: dict[str, list] = {}
    for e in events:
        if isinstance(e, Action) and e.action_type in ("place", "descore"):
            if e.target_goal_ref:
                by_goal.setdefault(e.target_goal_ref, []).append(e)
        elif isinstance(e, StateChange) and e.change in GOAL_AFFECTING_CHANGES:
            if e.target_goal_ref:
                by_goal.setdefault(e.target_goal_ref, []).append(e)
    return by_goal


def reconcile_goal_depth(
    match: MatchObservation, snapshots: tuple[Snapshot, ...], events: tuple, rule_bundle: RuleBundle
) -> dict[str, ChannelResult]:
    """Channel 1: predicted_depth(G) = starting_depth(G) + sum(after - before) over
    every record touching G, compared against the match_end snapshot's physical
    stack length. Uses each record's own observed net effect -- never assumes place
    is +1 or descore is -1, so `descore{method: obscure}` (which adds a Cup)
    correctly contributes +1 through the same, unmodified formula."""
    starting_depths = _starting_goal_depths(rule_bundle)
    snap = _match_end_snapshot(snapshots)
    by_goal = _goal_touching_records(events)

    results: dict[str, ChannelResult] = {}
    for goal_id, start_depth in starting_depths.items():
        if snap is None:
            results[goal_id] = ChannelResult("indeterminate", "no match_end snapshot")
            continue
        records = by_goal.get(goal_id, [])
        net = 0
        indeterminate_reason = None
        for r in records:
            before, after = r.stack_height_before, r.stack_height_after
            if not (_is_number(before) and _is_number(after)):
                indeterminate_reason = f"{r.record_type}[{r.id}] has an unknown stack_height endpoint"
                break
            net += after - before
        if indeterminate_reason:
            results[goal_id] = ChannelResult("indeterminate", indeterminate_reason)
            continue
        predicted = start_depth + net
        actual = len(snap.goals[goal_id].stack) if goal_id in snap.goals else None
        if actual is None:
            results[goal_id] = ChannelResult("indeterminate", "goal missing from match_end snapshot")
        elif predicted == actual:
            results[goal_id] = ChannelResult("match", f"predicted={predicted} actual={actual}")
        else:
            results[goal_id] = ChannelResult(
                "mismatch", f"predicted={predicted} actual={actual} delta={actual - predicted}"
            )
    return results


def reconcile_toggle_orientation(
    snapshots: tuple[Snapshot, ...], events: tuple, rule_bundle: RuleBundle
) -> dict[str, ChannelResult]:
    """Channel 2: the last labeled `state_after` (from `toggle` Actions and
    toggle-affecting `state_change`s) before the match_end instant, compared against
    the snapshot's **orientation** -- not effective color, since <SC4> makes a
    contacted/unseated Toggle read neutral without its orientation changing."""
    snap = _match_end_snapshot(snapshots)
    start_state = _starting_state(rule_bundle).match_state
    starting_orientation = {t.id: t.orientation.value for t in start_state.toggles}

    by_toggle: dict[str, list[tuple[float, str]]] = {}
    for e in events:
        if isinstance(e, Action) and e.action_type == "toggle" and e.toggle_ref:
            t = e.video_t_end if _is_number(e.video_t_end) else e.video_t_start
            by_toggle.setdefault(e.toggle_ref, []).append((t, e.state_after))
        elif isinstance(e, StateChange) and e.change in TOGGLE_AFFECTING_CHANGES and e.toggle_ref:
            by_toggle.setdefault(e.toggle_ref, []).append((e.video_t, e.state_after))

    results: dict[str, ChannelResult] = {}
    for toggle_id, start_orientation in starting_orientation.items():
        if snap is None:
            results[toggle_id] = ChannelResult("indeterminate", "no match_end snapshot")
            continue
        events_for_toggle = sorted(by_toggle.get(toggle_id, []), key=lambda p: p[0])
        if events_for_toggle:
            predicted = events_for_toggle[-1][1]
        else:
            predicted = start_orientation
        actual = snap.toggles[toggle_id].orientation if toggle_id in snap.toggles else None
        if predicted == UNKNOWN or actual is None or actual == UNKNOWN:
            results[toggle_id] = ChannelResult(
                "indeterminate", f"predicted={predicted!r} actual={actual!r}"
            )
        elif predicted == actual:
            results[toggle_id] = ChannelResult("match", f"orientation={actual!r}")
        else:
            results[toggle_id] = ChannelResult(
                "mismatch", f"predicted={predicted!r} actual={actual!r}"
            )
    return results


# A MidfieldOccupancy record's `video_t_exit: null` means "still open at the end of
# THAT RECORD'S OWN PERIOD" -- not open forever into a later period (§C.6). An
# autonomous-period episode can therefore only ever cover the autonomous_end
# instant, and a driver-period episode can only ever cover the match_end instant.
_SNAPSHOT_CONTEXT_TO_PERIOD = {"autonomous_end": "autonomous", "match_end": "driver"}


def reconcile_midfield_occupancy(
    match: MatchObservation, snapshots: tuple[Snapshot, ...], events: tuple
) -> dict[str, ChannelResult]:
    """Channel 3: which robots have a `midfield_occupancy` episode open at the
    `autonomous_end` / `match_end` instant, versus `snapshot.robots[ref].in_midfield`.
    Occupancy records are matched by their own `period` against the snapshot's
    corresponding period -- an autonomous-period episode with a null (still-open)
    exit is bounded by the autonomous/driver boundary, never carried into match_end."""
    occupancies = [e for e in events if isinstance(e, MidfieldOccupancy)]
    results: dict[str, ChannelResult] = {}
    for snap in snapshots:
        snapshot_period = _SNAPSHOT_CONTEXT_TO_PERIOD.get(snap.context)
        for r in match.roster:
            key = f"{r.robot_ref}@{snap.context}"
            actual = snap.robots[r.robot_ref].in_midfield if r.robot_ref in snap.robots else None
            if actual is None or actual == UNKNOWN:
                results[key] = ChannelResult("indeterminate", f"snapshot in_midfield={actual!r}")
                continue
            episodes = [
                o for o in occupancies if o.robot_ref == r.robot_ref and o.period == snapshot_period
            ]
            covered = False
            indeterminate_reason = None
            for o in episodes:
                enter = o.video_t_enter
                exitt = o.video_t_exit
                if not _is_number(enter):
                    indeterminate_reason = f"{o.id}: video_t_enter is {enter!r}"
                    continue
                still_open = exitt is None
                if not still_open and not _is_number(exitt):
                    indeterminate_reason = f"{o.id}: video_t_exit is {exitt!r}"
                    continue
                if enter <= snap.video_t and (still_open or exitt >= snap.video_t):
                    covered = True
            if covered:
                predicted = True
            elif indeterminate_reason is not None:
                results[key] = ChannelResult("indeterminate", indeterminate_reason)
                continue
            else:
                predicted = False
            if predicted == actual:
                results[key] = ChannelResult("match", f"in_midfield={actual!r}")
            else:
                results[key] = ChannelResult(
                    "mismatch", f"predicted={predicted!r} actual={actual!r}"
                )
    return results


def _starting_goal_composition(rule_bundle: RuleBundle) -> dict[str, Counter]:
    """Starting object-type composition per Goal -- every M2 starting state's placed
    objects are Pins (see `_starting_goal_depths`); no Goal starts holding a Cup."""
    return {goal_id: Counter({"pin": depth}) if depth else Counter()
            for goal_id, depth in _starting_goal_depths(rule_bundle).items()}


def reconcile_goal_composition(
    snapshots: tuple[Snapshot, ...],
    events: tuple,
    depth_channel: dict[str, ChannelResult],
    rule_bundle: RuleBundle,
) -> dict[str, ChannelResult]:
    """OPTIONAL best-effort channel: where the depth channel is fully determinate and
    every contributing record recorded `object`, compare the starting composition
    plus the multiset of object types added against the snapshot's stack
    composition. Type-level only -- no persistent object identity or count-of-a-
    specific-Pin claim."""
    snap = _match_end_snapshot(snapshots)
    by_goal = _goal_touching_records(events)
    starting_composition = _starting_goal_composition(rule_bundle)
    results: dict[str, ChannelResult] = {}
    for goal_id, channel in depth_channel.items():
        if channel.status == "indeterminate" or snap is None or goal_id not in snap.goals:
            continue
        records = by_goal.get(goal_id, [])
        predicted = Counter(starting_composition.get(goal_id, Counter()))
        determinate = True
        for r in records:
            before, after = r.stack_height_before, r.stack_height_after
            if not (_is_number(before) and _is_number(after)):
                determinate = False
                break
            delta = after - before
            if delta == 0:
                continue
            obj = getattr(r, "object", None)
            if obj is None or obj == UNKNOWN:
                determinate = False
                break
            predicted[obj] += delta
        if not determinate:
            continue
        if any(item.object == UNKNOWN for item in snap.goals[goal_id].stack):
            results[goal_id] = ChannelResult("indeterminate", "snapshot stack has an unknown object type")
            continue
        actual = Counter(item.object for item in snap.goals[goal_id].stack)
        predicted = Counter({k: v for k, v in predicted.items() if v})
        actual = Counter({k: v for k, v in actual.items() if v})
        if predicted == actual:
            results[goal_id] = ChannelResult("match", f"composition={dict(actual)}")
        else:
            results[goal_id] = ChannelResult(
                "mismatch", f"predicted={dict(predicted)} snapshot_composition={dict(actual)}"
            )
    return results


def reconcile(
    match: MatchObservation, snapshots: tuple[Snapshot, ...], events: tuple, rule_bundle: RuleBundle
) -> ReconciliationReport:
    """Run all three required channels plus the optional Goal-composition channel."""
    goal_depth = reconcile_goal_depth(match, snapshots, events, rule_bundle)
    toggle_orientation = reconcile_toggle_orientation(snapshots, events, rule_bundle)
    midfield_occupancy = reconcile_midfield_occupancy(match, snapshots, events)
    goal_composition = reconcile_goal_composition(snapshots, events, goal_depth, rule_bundle)
    return ReconciliationReport(
        goal_depth=goal_depth,
        toggle_orientation=toggle_orientation,
        midfield_occupancy=midfield_occupancy,
        goal_composition=goal_composition,
    )

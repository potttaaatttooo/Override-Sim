"""Pure deterministic scoring functions for static Override match states.

No RNG, I/O, LLM/web calls, or mutation of inputs anywhere in this module. The same
MatchState + effective RuleBundle always produces the same result. See
docs/design/03-state-and-scoring.md for the reasoning behind each function.

Autonomous Win Point thresholds (Pins Scored, qualifying Goals, etc.) are NOT
hardcoded here -- they are read from `rule_bundle.awp_requirements`, a structured,
versioned, cited view over scoring.yaml/vexu.yaml (see rules/models.py). Point
values (5/10/8/12) are likewise read from `rule_bundle.point_values`, never
hardcoded.
"""

from __future__ import annotations

from dataclasses import dataclass

from vexu_sim.model import (
    Alliance,
    Color,
    Cup,
    CupHalf,
    Goal,
    MatchState,
    Pin,
    PinHalf,
)
from vexu_sim.rules import RuleBundle


def _half(pin: Pin, label: str) -> PinHalf:
    return pin.half_a if label == "a" else pin.half_b


def is_pin_placed(pin: Pin) -> bool:
    """<SC2>a: a Pin is Placed if either half occupies the slot it rests on (a Goal,
    or a Cup half whose owning Cup is itself Placed)."""
    return _is_pin_placed(pin, frozenset())


def is_cup_placed(cup: Cup) -> bool:
    """<SC2>b: a Cup is Placed if either of its halves' adjudicated occupant is itself
    a Placed Pin."""
    return _is_cup_placed(cup, frozenset())


def _is_pin_placed(pin: Pin, visited_cups: frozenset[int]) -> bool:
    # `visited_cups` guards against the mutual recursion that Cup <-> Pin nesting
    # naturally produces: resolving whether Cup C is Placed may need to ask whether a
    # Pin nested in C's *other* half is Placed, and that Pin may itself be nested in C
    # (see Figure SC2-2 in docs/design/03-state-and-scoring.md) -- without this guard,
    # that pair re-derives each other's placement forever instead of finding the
    # independent Goal-grounded route.
    for label in ("a", "b"):
        half = _half(pin, label)
        target = half.rests_on
        if target is None:
            continue
        occupant = target.occupant
        if occupant is None or occupant.pin is not pin or occupant.half != label:
            # This half is resting on a slot but is not its adjudicated occupant --
            # the Figure SC2-2 capacity conflict: not Placed via this slot.
            continue
        if isinstance(target, Goal):
            return True
        if isinstance(target, CupHalf) and target.cup is not None and id(target.cup) not in visited_cups:
            if _is_cup_placed(target.cup, visited_cups | {id(target.cup)}):
                return True
    return False


def _is_cup_placed(cup: Cup, visited_cups: frozenset[int]) -> bool:
    for cup_half in (cup.opaque, cup.transparent):
        occupant = cup_half.occupant
        if occupant is not None and _is_pin_placed(occupant.pin, visited_cups):
            return True
    return False


def is_half_visible(pin: Pin, label: str) -> bool:
    """<SC3>: a half is visible unless its adjudicated slot is a Cup's opaque half."""
    half = _half(pin, label)
    target = half.rests_on
    if target is None:
        return True
    occupant = target.occupant
    if occupant is None or occupant.pin is not pin or occupant.half != label:
        return True  # not actually nested here; nothing hides it
    if isinstance(target, CupHalf):
        return target.kind != "opaque"
    return True


def midfield_robot_counts(match_state: MatchState) -> dict[Alliance, int]:
    counts = {Alliance.RED: 0, Alliance.BLUE: 0}
    for robot in match_state.robots:
        if robot.in_midfield:
            counts[robot.alliance] += 1
    return counts


def yellow_pin_owner(pin: Pin, match_state: MatchState) -> Alliance | None:
    """<SC5>: which Alliance (if any) Owns a yellow Pin Placed in `pin.goal`."""
    if pin.goal.quadrant is not None:
        toggle = match_state.toggle_for_quadrant(pin.goal.quadrant)
        color = toggle.effective_color
        if color == Color.RED:
            return Alliance.RED
        if color == Color.BLUE:
            return Alliance.BLUE
        return None
    counts = midfield_robot_counts(match_state)
    if counts[Alliance.RED] > counts[Alliance.BLUE]:
        return Alliance.RED
    if counts[Alliance.BLUE] > counts[Alliance.RED]:
        return Alliance.BLUE
    return None


def half_owner(pin: Pin, label: str, match_state: MatchState) -> Alliance | None:
    """Which Alliance (if any) this Pin half is Scored for: Placed + visible, and for
    yellow halves, Owned. Combines <SC2>/<SC3>/<SC5>."""
    if not is_pin_placed(pin):
        return None
    if not is_half_visible(pin, label):
        return None
    color = _half(pin, label).color
    if color == Color.RED:
        return Alliance.RED
    if color == Color.BLUE:
        return Alliance.BLUE
    return yellow_pin_owner(pin, match_state)


def _pin_half_points(color: Color, rule_bundle: RuleBundle) -> int:
    pv = rule_bundle.point_values
    if color == Color.YELLOW:
        return pv["scored_pin_half_yellow"]["points"]
    return pv["scored_pin_half_alliance_colored"]["points"]


def autonomous_bonus(match_state: MatchState, rule_bundle: RuleBundle) -> dict[Alliance, int]:
    """<SC7> (V5RC) / <VUG5> (VEX U): the Autonomous Bonus, evaluated on an
    AUTONOMOUS_END MatchState. Violations during the Autonomous Period award the
    bonus to the opponent, or cancel it if both Alliances violated (<SC7>c/d,
    <GG13>)."""
    pv = rule_bundle.point_values["autonomous_bonus"]
    bonus_points = pv["points"]
    tie_points = pv["tie_points_each"]

    violations = match_state.autonomous_violations
    if Alliance.RED in violations and Alliance.BLUE in violations:
        return {Alliance.RED: 0, Alliance.BLUE: 0}
    if Alliance.RED in violations:
        return {Alliance.RED: 0, Alliance.BLUE: bonus_points}
    if Alliance.BLUE in violations:
        return {Alliance.BLUE: 0, Alliance.RED: bonus_points}

    totals = {Alliance.RED: 0, Alliance.BLUE: 0}
    include_midfield = rule_bundle.autonomous_bonus_includes_midfield
    for pin in match_state.pins:
        for label in ("a", "b"):
            half = _half(pin, label)
            if half.color == Color.YELLOW and pin.goal.quadrant is None and not include_midfield:
                continue  # <SC7>a: Midfield yellow Pin Ownership excluded for V5RC
            owner = half_owner(pin, label, match_state)
            if owner is not None:
                totals[owner] += _pin_half_points(half.color, rule_bundle)
    if include_midfield:
        for robot in match_state.robots:
            if robot.in_midfield:
                totals[robot.alliance] += rule_bundle.point_values["robot_ending_in_midfield"]["points"]

    if totals[Alliance.RED] > totals[Alliance.BLUE]:
        return {Alliance.RED: bonus_points, Alliance.BLUE: 0}
    if totals[Alliance.BLUE] > totals[Alliance.RED]:
        return {Alliance.BLUE: bonus_points, Alliance.RED: 0}
    return {Alliance.RED: tie_points, Alliance.BLUE: tie_points}


def _pins_scored_for_alliance_in_goal(goal: Goal, alliance: Alliance, match_state: MatchState) -> int:
    return sum(
        1
        for pin in match_state.pins
        if pin.goal is goal
        for label in ("a", "b")
        if half_owner(pin, label, match_state) == alliance
    )


def autonomous_win_point(match_state: MatchState, alliance: Alliance, rule_bundle: RuleBundle) -> bool:
    """<SC8> (V5RC) / <VUG6> (VEX U): whether `alliance` earns the Autonomous Win
    Point, evaluated on an AUTONOMOUS_END MatchState. All numeric/boolean thresholds
    come from `rule_bundle.awp_requirements` -- this function contains no
    rule-version-specific literal values."""
    if alliance in match_state.autonomous_violations:
        return False

    requirements = rule_bundle.awp_requirements
    alliance_robots = [r for r in match_state.robots if r.alliance == alliance]

    if requirements.perimeter_contact_forbidden and any(r.contacting_perimeter for r in alliance_robots):
        return False

    if requirements.requires_robot_in_midfield and not any(r.in_midfield for r in alliance_robots):
        return False

    if requirements.excludes_opposing_side_of_autonomous_line:
        own_goals = [
            g for g in match_state.goals if g.quadrant is None or g.quadrant.alliance_side == alliance
        ]
    else:
        own_goals = list(match_state.goals)

    pins_scored = sum(_pins_scored_for_alliance_in_goal(g, alliance, match_state) for g in own_goals)
    goals_meeting_threshold = sum(
        1
        for g in own_goals
        if _pins_scored_for_alliance_in_goal(g, alliance, match_state) >= requirements.min_pins_per_qualifying_goal
    )

    return pins_scored >= requirements.min_pins_scored and goals_meeting_threshold >= requirements.min_qualifying_goals


@dataclass(frozen=True)
class ScoreBreakdown:
    pin_points: dict[Alliance, int]
    midfield_points: dict[Alliance, int]
    autonomous_bonus_points: dict[Alliance, int]
    total: dict[Alliance, int]


def score_breakdown(
    match_state: MatchState,
    rule_bundle: RuleBundle,
    autonomous_bonus_points: dict[Alliance, int],
) -> ScoreBreakdown:
    """Final match score, evaluated on a MATCH_END MatchState. `autonomous_bonus_points`
    is the already-computed autonomous_bonus() result from the corresponding
    AUTONOMOUS_END snapshot -- <SC7> fixes that value at the Autonomous/Driver
    boundary, so it is threaded in rather than recomputed here."""
    pin_points = {Alliance.RED: 0, Alliance.BLUE: 0}
    for pin in match_state.pins:
        for label in ("a", "b"):
            half = _half(pin, label)
            owner = half_owner(pin, label, match_state)
            if owner is not None:
                pin_points[owner] += _pin_half_points(half.color, rule_bundle)

    midfield_points = {Alliance.RED: 0, Alliance.BLUE: 0}
    midfield_value = rule_bundle.point_values["robot_ending_in_midfield"]["points"]
    for robot in match_state.robots:
        if robot.in_midfield:
            midfield_points[robot.alliance] += midfield_value

    total = {
        alliance: pin_points[alliance] + midfield_points[alliance] + autonomous_bonus_points.get(alliance, 0)
        for alliance in (Alliance.RED, Alliance.BLUE)
    }
    return ScoreBreakdown(
        pin_points=pin_points,
        midfield_points=midfield_points,
        autonomous_bonus_points=dict(autonomous_bonus_points),
        total=total,
    )

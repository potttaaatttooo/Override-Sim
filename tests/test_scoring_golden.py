"""Golden tests for deterministic scoring: the manual's own worked examples (p.17) and
the rule edge cases in docs/design/03-state-and-scoring.md. See CLAUDE.md's Gate V1.
"""

from __future__ import annotations

import copy
import dataclasses
from pathlib import Path

import pytest

from fixtures.scoring.builders import (
    make_cup,
    make_goal,
    make_pin,
    make_quadrant,
    make_robot,
    make_toggle,
    nest_half_on_cup_half,
    nest_half_on_goal,
    rest_half_on_cup_half_without_occupying,
)
from vexu_sim.model import (
    Alliance,
    Color,
    Goal,
    GoalType,
    MatchState,
    ScoringContext,
)
from vexu_sim.rules import load_rule_bundle
from vexu_sim.scoring import (
    autonomous_bonus,
    autonomous_win_point,
    half_owner,
    is_cup_placed,
    is_pin_placed,
    is_half_visible,
    score_breakdown,
    yellow_pin_owner,
)
from vexu_sim.sources import load_sources

DATA_ROOT = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def sources():
    return load_sources(DATA_ROOT)


@pytest.fixture(scope="module")
def v5rc_bundle(sources):
    return load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)


@pytest.fixture(scope="module")
def vexu_bundle(sources):
    return load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)


def _stack_of_scored_pins(base_goal: Goal, n: int, prefix: str):
    """A chain of `n` Pins on top of `base_goal`, each with its `half_a` nested such
    that it remains visible (Goal, or a Cup's transparent half) -- see
    docs/design/03-state-and-scoring.md. Returns (pins, cups)."""
    pins = []
    cups = []
    target = base_goal
    for i in range(n):
        pin = make_pin(f"{prefix}{i}", Color.RED, Color.BLUE, base_goal)
        if isinstance(target, Goal):
            nest_half_on_goal(pin, "a", target)
        else:
            nest_half_on_cup_half(pin, "a", target)
        pins.append(pin)
        if i < n - 1:
            cup = make_cup(f"{prefix}cup{i}")
            nest_half_on_cup_half(pin, "b", cup.opaque)  # unused/hidden, not counted
            cups.append(cup)
            target = cup.transparent  # keeps the next pin's half_a visible
    return pins, cups


# --- A. The manual's three-panel worked scoring example (p.17) -------------------


def _build_worked_example_state(toggle_orientation: Color) -> MatchState:
    quadrant = make_quadrant("q1", Alliance.RED)
    toggle = make_toggle("t1", quadrant, orientation=toggle_orientation)

    g1 = make_goal("g1", GoalType.ALLIANCE_RED, quadrant)
    g2 = make_goal("g2", GoalType.NEUTRAL_SHORT, quadrant)
    g3 = make_goal("g3", GoalType.NEUTRAL_SHORT, quadrant)
    g4 = make_goal("g4", GoalType.NEUTRAL_SHORT, quadrant)
    cup = make_cup("c1")

    p1 = make_pin("p1", Color.RED, Color.BLUE, g1)
    nest_half_on_goal(p1, "a", g1)  # red half visible; blue half exposed & visible

    p2 = make_pin("p2", Color.RED, Color.YELLOW, g2)
    nest_half_on_goal(p2, "a", g2)  # red half visible; yellow half exposed & visible

    p3 = make_pin("p3", Color.RED, Color.YELLOW, g3)
    nest_half_on_goal(p3, "a", g3)

    p4 = make_pin("p4", Color.YELLOW, Color.YELLOW, g4)
    nest_half_on_goal(p4, "a", g4)  # yellow half visible
    nest_half_on_cup_half(p4, "b", cup.opaque)  # yellow half hidden -- the "+0" item

    return MatchState(
        program="v5rc",
        scoring_context=ScoringContext.MATCH_END,
        goals=[g1, g2, g3, g4],
        pins=[p1, p2, p3, p4],
        cups=[cup],
        quadrants=[quadrant],
        toggles=[toggle],
        robots=[],
    )


@pytest.mark.parametrize(
    "toggle_orientation,expected_red,expected_blue",
    [
        (Color.YELLOW, 15, 5),
        (Color.BLUE, 15, 35),
        (Color.RED, 45, 5),
    ],
)
def test_worked_example_reproduces_manual_p17(
    v5rc_bundle, toggle_orientation, expected_red, expected_blue
):
    state = _build_worked_example_state(toggle_orientation)
    breakdown = score_breakdown(state, v5rc_bundle, {Alliance.RED: 0, Alliance.BLUE: 0})
    assert breakdown.total[Alliance.RED] == expected_red
    assert breakdown.total[Alliance.BLUE] == expected_blue


# --- B. SC2 edge case: capacity conflict (Figure SC2-2) --------------------------


def test_pin_resting_on_already_occupied_cup_half_is_not_placed():
    quadrant = make_quadrant("q1", Alliance.RED)
    goal = make_goal("g1", GoalType.NEUTRAL_SHORT, quadrant)
    cup = make_cup("c1")

    pin0 = make_pin("p0", Color.RED, Color.BLUE, goal)
    nest_half_on_goal(pin0, "a", goal)
    nest_half_on_cup_half(pin0, "b", cup.transparent)  # cup is Placed via pin0

    pin_a = make_pin("pa", Color.RED, Color.YELLOW, goal)
    nest_half_on_cup_half(pin_a, "a", cup.opaque)  # legitimately occupies the slot

    pin_b = make_pin("pb", Color.BLUE, Color.YELLOW, goal)
    rest_half_on_cup_half_without_occupying(pin_b, "a", cup.opaque)  # capacity conflict

    assert is_cup_placed(cup) is True
    assert is_pin_placed(pin_a) is True
    assert is_pin_placed(pin_b) is False


# --- C. Visibility: Placed but hidden inside an opaque Cup half is not Scored ----


def test_placed_pin_half_hidden_in_opaque_cup_is_not_scored(v5rc_bundle):
    quadrant = make_quadrant("q1", Alliance.RED)
    toggle = make_toggle("t1", quadrant, orientation=Color.RED)  # would own yellow if visible
    goal = make_goal("g1", GoalType.NEUTRAL_SHORT, quadrant)
    cup = make_cup("c1")

    pin = make_pin("p1", Color.RED, Color.YELLOW, goal)
    nest_half_on_goal(pin, "a", goal)  # red half: visible
    nest_half_on_cup_half(pin, "b", cup.opaque)  # yellow half: hidden

    state = MatchState(
        program="v5rc",
        scoring_context=ScoringContext.MATCH_END,
        goals=[goal],
        pins=[pin],
        cups=[cup],
        quadrants=[quadrant],
        toggles=[toggle],
        robots=[],
    )

    assert is_pin_placed(pin) is True
    assert is_half_visible(pin, "a") is True
    assert is_half_visible(pin, "b") is False
    assert half_owner(pin, "a", state) == Alliance.RED
    assert half_owner(pin, "b", state) is None  # hidden, despite a red Toggle that would own it


# --- D. Toggle interaction (SC4) --------------------------------------------------


def test_toggle_contacted_by_robot_defaults_to_neutral_yellow():
    quadrant = make_quadrant("q1", Alliance.RED)
    toggle = make_toggle("t1", quadrant, orientation=Color.RED, seated=True, contacted_by_robot=True)
    assert toggle.effective_color == Color.YELLOW


def test_toggle_not_fully_seated_defaults_to_neutral_yellow():
    quadrant = make_quadrant("q1", Alliance.RED)
    toggle = make_toggle("t1", quadrant, orientation=Color.RED, seated=False, contacted_by_robot=False)
    assert toggle.effective_color == Color.YELLOW


def test_toggle_seated_and_uncontacted_is_set_to_its_orientation():
    quadrant = make_quadrant("q1", Alliance.RED)
    toggle = make_toggle("t1", quadrant, orientation=Color.RED, seated=True, contacted_by_robot=False)
    assert toggle.effective_color == Color.RED


def test_robot_contact_on_toggle_prevents_yellow_pin_ownership():
    quadrant = make_quadrant("q1", Alliance.RED)
    toggle = make_toggle("t1", quadrant, orientation=Color.RED, seated=True, contacted_by_robot=True)
    goal = make_goal("g1", GoalType.NEUTRAL_SHORT, quadrant)
    pin = make_pin("p1", Color.YELLOW, Color.YELLOW, goal)
    nest_half_on_goal(pin, "a", goal)

    state = MatchState(
        program="v5rc",
        scoring_context=ScoringContext.MATCH_END,
        goals=[goal],
        pins=[pin],
        cups=[],
        quadrants=[quadrant],
        toggles=[toggle],
        robots=[],
    )
    assert yellow_pin_owner(pin, state) is None


# --- E. Midfield yellow Pin ownership (SC5b) --------------------------------------


@pytest.mark.parametrize(
    "red_robots,blue_robots,expected",
    [
        (2, 1, Alliance.RED),
        (1, 2, Alliance.BLUE),
        (1, 1, None),
    ],
)
def test_midfield_yellow_pin_ownership(red_robots, blue_robots, expected):
    midfield_goal = make_goal("midfield", GoalType.NEUTRAL_TALL, None)
    pin = make_pin("p1", Color.YELLOW, Color.YELLOW, midfield_goal)
    nest_half_on_goal(pin, "a", midfield_goal)

    robots = [make_robot(f"r{i}", Alliance.RED, "v5rc", in_midfield=True) for i in range(red_robots)]
    robots += [make_robot(f"b{i}", Alliance.BLUE, "v5rc", in_midfield=True) for i in range(blue_robots)]

    state = MatchState(
        program="v5rc",
        scoring_context=ScoringContext.MATCH_END,
        goals=[midfield_goal],
        pins=[pin],
        cups=[],
        quadrants=[],
        toggles=[],
        robots=robots,
    )
    assert yellow_pin_owner(pin, state) == expected


# --- F. Autonomous Bonus (SC7 / VUG5) ---------------------------------------------


def _build_bonus_state(program: str, red_pin_count: int, blue_pin_count: int, robots=()):
    quadrant = make_quadrant("q1", Alliance.RED)
    toggle = make_toggle("t1", quadrant, orientation=Color.YELLOW)  # neutral: yellow halves score 0
    goals = []
    pins = []
    for i in range(red_pin_count):
        g = make_goal(f"gr{i}", GoalType.NEUTRAL_SHORT, quadrant)
        pin = make_pin(f"pr{i}", Color.RED, Color.YELLOW, g)
        nest_half_on_goal(pin, "a", g)
        goals.append(g)
        pins.append(pin)
    for i in range(blue_pin_count):
        g = make_goal(f"gb{i}", GoalType.NEUTRAL_SHORT, quadrant)
        pin = make_pin(f"pb{i}", Color.BLUE, Color.YELLOW, g)
        nest_half_on_goal(pin, "a", g)
        goals.append(g)
        pins.append(pin)

    return MatchState(
        program=program,
        scoring_context=ScoringContext.AUTONOMOUS_END,
        goals=goals,
        pins=pins,
        cups=[],
        quadrants=[quadrant],
        toggles=[toggle],
        robots=list(robots),
    )


def test_autonomous_bonus_red_wins(v5rc_bundle):
    state = _build_bonus_state("v5rc", red_pin_count=2, blue_pin_count=1)
    bonus = autonomous_bonus(state, v5rc_bundle)
    assert bonus == {Alliance.RED: 12, Alliance.BLUE: 0}


def test_autonomous_bonus_blue_wins(v5rc_bundle):
    state = _build_bonus_state("v5rc", red_pin_count=1, blue_pin_count=2)
    bonus = autonomous_bonus(state, v5rc_bundle)
    assert bonus == {Alliance.BLUE: 12, Alliance.RED: 0}


def test_autonomous_bonus_tie(v5rc_bundle):
    state = _build_bonus_state("v5rc", red_pin_count=1, blue_pin_count=1)
    bonus = autonomous_bonus(state, v5rc_bundle)
    assert bonus == {Alliance.RED: 6, Alliance.BLUE: 6}


def test_autonomous_bonus_violation_awards_opponent(v5rc_bundle):
    state = _build_bonus_state("v5rc", red_pin_count=5, blue_pin_count=0)
    state.autonomous_violations = frozenset({Alliance.RED})
    bonus = autonomous_bonus(state, v5rc_bundle)
    assert bonus == {Alliance.RED: 0, Alliance.BLUE: 12}


def test_autonomous_bonus_both_violate_awards_neither(v5rc_bundle):
    state = _build_bonus_state("v5rc", red_pin_count=5, blue_pin_count=0)
    state.autonomous_violations = frozenset({Alliance.RED, Alliance.BLUE})
    bonus = autonomous_bonus(state, v5rc_bundle)
    assert bonus == {Alliance.RED: 0, Alliance.BLUE: 0}


def test_autonomous_bonus_v5rc_excludes_midfield_robot_points(v5rc_bundle):
    # Pin points tie (5 vs 5); a Robot ending in the Midfield would break the tie for
    # VEX U (<VUG5>) but must NOT for V5RC (<SC7>a, qna:3188) -- it stays a tie.
    robot = make_robot("r1", Alliance.RED, "v5rc", in_midfield=True)
    state = _build_bonus_state("v5rc", red_pin_count=1, blue_pin_count=1, robots=[robot])
    bonus = autonomous_bonus(state, v5rc_bundle)
    assert bonus == {Alliance.RED: 6, Alliance.BLUE: 6}


def test_autonomous_bonus_vexu_includes_midfield_robot_points(vexu_bundle):
    # Same pin points (tie 5/5); VEX U's <VUG5> includes the Midfield Robot point,
    # which breaks the tie in red's favor.
    robot = make_robot("r1", Alliance.RED, "vexu", in_midfield=True)
    state = _build_bonus_state("vexu", red_pin_count=1, blue_pin_count=1, robots=[robot])
    bonus = autonomous_bonus(state, vexu_bundle)
    assert bonus == {Alliance.RED: 12, Alliance.BLUE: 0}


# --- G. Autonomous Win Point (SC8 / VUG6) -----------------------------------------


def _build_awp_state(
    program: str,
    own_pins_per_goal: list[int],
    midfield_extra: int = 0,
    perimeter_contact: bool = False,
    midfield_robot: bool = False,
    violations: frozenset = frozenset(),
):
    quadrant = make_quadrant("qred", Alliance.RED)
    goals = []
    pins = []
    cups = []
    for gi, n in enumerate(own_pins_per_goal):
        goal = make_goal(f"g{gi}", GoalType.NEUTRAL_SHORT, quadrant)
        goals.append(goal)
        stack_pins, stack_cups = _stack_of_scored_pins(goal, n, f"g{gi}p")
        pins.extend(stack_pins)
        cups.extend(stack_cups)
    if midfield_extra:
        midfield_goal = make_goal("midfield", GoalType.NEUTRAL_TALL, None)
        goals.append(midfield_goal)
        stack_pins, stack_cups = _stack_of_scored_pins(midfield_goal, midfield_extra, "mf")
        pins.extend(stack_pins)
        cups.extend(stack_cups)

    robot = make_robot(
        "r1", Alliance.RED, program, in_midfield=midfield_robot, contacting_perimeter=perimeter_contact
    )
    return MatchState(
        program=program,
        scoring_context=ScoringContext.AUTONOMOUS_END,
        goals=goals,
        pins=pins,
        cups=cups,
        quadrants=[quadrant],
        toggles=[],
        robots=[robot],
        autonomous_violations=violations,
    )


def test_v5rc_awp_passes_when_all_criteria_met(v5rc_bundle):
    state = _build_awp_state("v5rc", own_pins_per_goal=[2, 2, 2, 1])  # 7 pins, 3 goals >=2
    assert autonomous_win_point(state, Alliance.RED, v5rc_bundle) is True


def test_v5rc_awp_fails_below_pin_threshold(v5rc_bundle):
    state = _build_awp_state("v5rc", own_pins_per_goal=[2, 2, 2])  # 6 pins < 7, but 3 goals >=2
    assert autonomous_win_point(state, Alliance.RED, v5rc_bundle) is False


def test_v5rc_awp_fails_below_goal_threshold(v5rc_bundle):
    state = _build_awp_state("v5rc", own_pins_per_goal=[2, 2, 1, 1, 1])  # 7 pins, only 2 goals >=2
    assert autonomous_win_point(state, Alliance.RED, v5rc_bundle) is False


def test_v5rc_awp_fails_on_perimeter_contact(v5rc_bundle):
    state = _build_awp_state("v5rc", own_pins_per_goal=[2, 2, 2, 1], perimeter_contact=True)
    assert autonomous_win_point(state, Alliance.RED, v5rc_bundle) is False


def test_v5rc_awp_fails_on_autonomous_violation(v5rc_bundle):
    state = _build_awp_state(
        "v5rc", own_pins_per_goal=[2, 2, 2, 1], violations=frozenset({Alliance.RED})
    )
    assert autonomous_win_point(state, Alliance.RED, v5rc_bundle) is False


def test_vexu_awp_passes_when_all_criteria_met(vexu_bundle):
    state = _build_awp_state(
        "vexu", own_pins_per_goal=[2, 2, 2, 2], midfield_extra=4, midfield_robot=True
    )  # 12 pins, 4 goals >=2, >=1 Robot in Midfield
    assert autonomous_win_point(state, Alliance.RED, vexu_bundle) is True


def test_vexu_awp_fails_below_pin_threshold(vexu_bundle):
    state = _build_awp_state("vexu", own_pins_per_goal=[2, 2, 2, 2], midfield_robot=True)  # 8 < 12
    assert autonomous_win_point(state, Alliance.RED, vexu_bundle) is False


def test_vexu_awp_fails_below_goal_threshold(vexu_bundle):
    state = _build_awp_state(
        "vexu", own_pins_per_goal=[2, 2, 2, 1, 1, 1, 1, 1, 1], midfield_robot=True
    )  # 12 pins, only 3 goals >=2
    assert autonomous_win_point(state, Alliance.RED, vexu_bundle) is False


def test_vexu_awp_fails_on_perimeter_contact(vexu_bundle):
    state = _build_awp_state(
        "vexu",
        own_pins_per_goal=[2, 2, 2, 2],
        midfield_extra=4,
        midfield_robot=True,
        perimeter_contact=True,
    )
    assert autonomous_win_point(state, Alliance.RED, vexu_bundle) is False


def test_vexu_awp_fails_without_robot_in_midfield(vexu_bundle):
    state = _build_awp_state(
        "vexu", own_pins_per_goal=[2, 2, 2, 2], midfield_extra=4, midfield_robot=False
    )
    assert autonomous_win_point(state, Alliance.RED, vexu_bundle) is False


def test_vexu_awp_fails_on_autonomous_violation(vexu_bundle):
    state = _build_awp_state(
        "vexu",
        own_pins_per_goal=[2, 2, 2, 2],
        midfield_extra=4,
        midfield_robot=True,
        violations=frozenset({Alliance.RED}),
    )
    assert autonomous_win_point(state, Alliance.RED, vexu_bundle) is False


# --- AWP requirements come from the rule bundle, not from scoring.py -------------


def test_awp_requirements_are_program_specific(v5rc_bundle, vexu_bundle):
    # scoring.py must consume rule_bundle.awp_requirements rather than knowing these
    # numbers itself -- see docs/design/03-state-and-scoring.md "Program dispatch".
    assert v5rc_bundle.awp_requirements != vexu_bundle.awp_requirements
    assert v5rc_bundle.awp_requirements.min_pins_scored == 7
    assert vexu_bundle.awp_requirements.min_pins_scored == 12


def _bundle_with_awp_requirements(rule_bundle, **overrides):
    """A RuleBundle identical to `rule_bundle` except with the given AWP requirement
    fields overridden in its (deep-copied) rule data -- used to prove scoring.py reads
    thresholds from rule data rather than hardcoding them."""
    data = copy.deepcopy(rule_bundle.data)
    if rule_bundle.program == "vexu":
        requirements = data["vexu_overlay"]["autonomous_win_point_criteria"]["requirements"]
    else:
        requirements = data["scoring"]["autonomous_win_point_criteria_v5rc"]["requirements"]
    requirements.update(overrides)
    return dataclasses.replace(rule_bundle, data=data)


def test_raising_v5rc_min_pins_scored_in_rule_data_flips_awp_result(v5rc_bundle):
    state = _build_awp_state("v5rc", own_pins_per_goal=[2, 2, 2, 1])  # 7 pins: passes as-is
    assert autonomous_win_point(state, Alliance.RED, v5rc_bundle) is True

    inflated = _bundle_with_awp_requirements(v5rc_bundle, min_pins_scored=100)
    assert autonomous_win_point(state, Alliance.RED, inflated) is False


def test_lowering_v5rc_min_qualifying_goals_in_rule_data_flips_awp_result(v5rc_bundle):
    state = _build_awp_state("v5rc", own_pins_per_goal=[2, 2, 1, 1, 1])  # fails as-is (2 goals >=2)
    assert autonomous_win_point(state, Alliance.RED, v5rc_bundle) is False

    relaxed = _bundle_with_awp_requirements(v5rc_bundle, min_qualifying_goals=2)
    assert autonomous_win_point(state, Alliance.RED, relaxed) is True


def test_toggling_vexu_requires_robot_in_midfield_in_rule_data_flips_awp_result(vexu_bundle):
    state = _build_awp_state(
        "vexu", own_pins_per_goal=[2, 2, 2, 2], midfield_extra=4, midfield_robot=False
    )
    assert autonomous_win_point(state, Alliance.RED, vexu_bundle) is False

    relaxed = _bundle_with_awp_requirements(vexu_bundle, requires_robot_in_midfield=False)
    assert autonomous_win_point(state, Alliance.RED, relaxed) is True

"""M2 tests: official starting Field configurations for V5RC and VEX U. See
docs/design/06-starting-field-states.md and CLAUDE.md's Gate-less M2 milestone
description (M2 verifies structure, not a scoring gate)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from vexu_sim.field_setup import build_v5rc_starting_state, build_vexu_starting_state
from vexu_sim.model import Alliance, Color, GoalType
from vexu_sim.rules import load_rule_bundle
from vexu_sim.scoring import half_owner, is_pin_placed
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


def _pin_color_combo_counts(pins) -> Counter:
    """Counter of frozenset({half_a.color, half_b.color}) isn't enough to distinguish
    same-color pairs from mixed, so key on a sorted tuple instead."""
    return Counter(tuple(sorted((p.half_a.color.value, p.half_b.color.value))) for p in pins)


# --- Goal / Quadrant / Toggle structure (shared by both programs) ----------------


def test_v5rc_goal_count_and_types(v5rc_bundle):
    state = build_v5rc_starting_state(v5rc_bundle).match_state
    assert len(state.goals) == 9
    types = Counter(g.goal_type for g in state.goals)
    assert types[GoalType.ALLIANCE_RED] == 2
    assert types[GoalType.ALLIANCE_BLUE] == 2
    assert types[GoalType.NEUTRAL_SHORT] == 4
    assert types[GoalType.NEUTRAL_TALL] == 1


def test_vexu_goal_count_and_types(vexu_bundle):
    state = build_vexu_starting_state(vexu_bundle).match_state
    assert len(state.goals) == 9
    types = Counter(g.goal_type for g in state.goals)
    assert types[GoalType.ALLIANCE_RED] == 2
    assert types[GoalType.ALLIANCE_BLUE] == 2
    assert types[GoalType.NEUTRAL_SHORT] == 4
    assert types[GoalType.NEUTRAL_TALL] == 1


def test_v5rc_quadrants_and_toggles(v5rc_bundle):
    state = build_v5rc_starting_state(v5rc_bundle).match_state
    assert len(state.quadrants) == 4
    assert sum(1 for q in state.quadrants if q.alliance_side == Alliance.RED) == 2
    assert sum(1 for q in state.quadrants if q.alliance_side == Alliance.BLUE) == 2

    assert len(state.toggles) == 4
    for toggle in state.toggles:
        # Appendix A "Toggle Assembly - Starting Orientation": yellow face up/into
        # the Field on all four Toggles at kickoff.
        assert toggle.effective_color == Color.YELLOW
        assert toggle.seated is True
        assert toggle.contacted_by_robot is False

    # Every Quadrant has exactly one Toggle and exactly one Alliance-colored Goal
    # matching its own side, plus one neutral-short Goal.
    for quadrant in state.quadrants:
        toggles_here = [t for t in state.toggles if t.quadrant is quadrant]
        assert len(toggles_here) == 1
        goals_here = [g for g in state.goals if g.quadrant is quadrant]
        assert len(goals_here) == 2
        alliance_goals = [g for g in goals_here if g.goal_type in (GoalType.ALLIANCE_RED, GoalType.ALLIANCE_BLUE)]
        assert len(alliance_goals) == 1
        expected_type = GoalType.ALLIANCE_RED if quadrant.alliance_side == Alliance.RED else GoalType.ALLIANCE_BLUE
        assert alliance_goals[0].goal_type == expected_type


def test_vexu_quadrants_and_toggles_match_v5rc_structure(vexu_bundle):
    # Section 6 does not modify Quadrant/Goal/Toggle structure or Toggle starting
    # orientation -- only what starts Placed on the Goals, and Match Load
    # availability.
    state = build_vexu_starting_state(vexu_bundle).match_state
    assert len(state.quadrants) == 4
    assert len(state.toggles) == 4
    for toggle in state.toggles:
        assert toggle.effective_color == Color.YELLOW


# --- V5RC starting Pin/Cup placement and inventory --------------------------------


def test_v5rc_only_neutral_and_midfield_goals_start_with_a_pin(v5rc_bundle):
    state = build_v5rc_starting_state(v5rc_bundle).match_state
    for goal in state.goals:
        occupied = goal.occupant is not None
        if goal.goal_type in (GoalType.NEUTRAL_SHORT, GoalType.NEUTRAL_TALL):
            assert occupied, f"{goal.id} should start with a Pin Placed"
        else:
            assert not occupied, f"{goal.id} (Alliance Goal) should start empty"


def test_v5rc_placed_starting_pins_are_yellow_yellow_and_unowned(v5rc_bundle):
    state = build_v5rc_starting_state(v5rc_bundle).match_state
    placed = [p for p in state.pins if is_pin_placed(p)]
    assert len(placed) == 5  # 4 neutral-short Goals + Midfield Goal
    for pin in placed:
        assert pin.half_a.color == Color.YELLOW
        assert pin.half_b.color == Color.YELLOW
        # Every Toggle starts neutral, so no Alliance owns these yet.
        assert half_owner(pin, "a", state) is None
        assert half_owner(pin, "b", state) is None


def test_v5rc_on_field_pin_inventory_by_color_combination(v5rc_bundle):
    state = build_v5rc_starting_state(v5rc_bundle).match_state
    counts = _pin_color_combo_counts(state.pins)
    assert counts[("blue", "red")] == 4  # red/blue predetermined, loose
    assert counts[("red", "yellow")] == 10  # 8 predetermined (loose) + 2 preloads
    assert counts[("blue", "yellow")] == 10  # 8 predetermined (loose) + 2 preloads
    assert counts[("yellow", "yellow")] == 17  # 12 loose + 5 Placed
    assert len(state.pins) == 41
    assert sum(counts.values()) == 41


def test_v5rc_unplaced_pins_are_not_placed_and_have_no_goal(v5rc_bundle):
    state = build_v5rc_starting_state(v5rc_bundle).match_state
    unplaced = [p for p in state.pins if not is_pin_placed(p)]
    assert len(unplaced) == 41 - 5
    for pin in unplaced:
        assert pin.goal is None


def test_v5rc_cup_inventory(v5rc_bundle):
    state = build_v5rc_starting_state(v5rc_bundle).match_state
    assert len(state.cups) == 36
    for cup in state.cups:
        assert cup.opaque.occupant is None
        assert cup.transparent.occupant is None


def test_v5rc_match_load_inventory(v5rc_bundle):
    bundle = build_v5rc_starting_state(v5rc_bundle)
    pins_by_alliance_combo = {
        (e.alliance, e.color_a.value, e.color_b.value): e.count for e in bundle.match_load_pins
    }
    assert pins_by_alliance_combo[(Alliance.RED, "red", "yellow")] == 10
    assert pins_by_alliance_combo[(Alliance.RED, "yellow", "yellow")] == 1
    assert pins_by_alliance_combo[(Alliance.BLUE, "blue", "yellow")] == 10
    assert pins_by_alliance_combo[(Alliance.BLUE, "yellow", "yellow")] == 1
    assert sum(e.count for e in bundle.match_load_pins) == 22  # Glossary: "22 Pins, 11 per Alliance"

    cups_by_alliance = {e.alliance: e.count for e in bundle.match_load_cups}
    assert cups_by_alliance[Alliance.RED] == 10
    assert cups_by_alliance[Alliance.BLUE] == 10
    assert sum(e.count for e in bundle.match_load_cups) == 20  # Glossary: "20 Cups, 10 per Alliance"


def test_v5rc_total_inventory_matches_field_overview(v5rc_bundle):
    # On-Field (incl. Preloads) + Match Loads must reproduce the manual's own totals:
    # 63 Pins, 56 Cups (Field Overview p.8).
    bundle = build_v5rc_starting_state(v5rc_bundle)
    total_pins = len(bundle.match_state.pins) + sum(e.count for e in bundle.match_load_pins)
    total_cups = len(bundle.match_state.cups) + sum(e.count for e in bundle.match_load_cups)
    assert total_pins == 63
    assert total_cups == 56


# --- VEX U starting Pin/Cup placement and inventory -------------------------------


def test_vexu_only_midfield_goal_starts_with_a_pin(vexu_bundle):
    state = build_vexu_starting_state(vexu_bundle).match_state
    for goal in state.goals:
        occupied = goal.occupant is not None
        if goal.goal_type == GoalType.NEUTRAL_TALL:
            assert occupied, "Midfield Goal should start with a Pin Placed"
        else:
            assert not occupied, f"{goal.id} should start empty (VEX U <field_setup>)"


def test_vexu_midfield_pin_is_yellow_yellow_and_unowned(vexu_bundle):
    state = build_vexu_starting_state(vexu_bundle).match_state
    placed = [p for p in state.pins if is_pin_placed(p)]
    assert len(placed) == 1
    pin = placed[0]
    assert pin.half_a.color == Color.YELLOW
    assert pin.half_b.color == Color.YELLOW
    assert half_owner(pin, "a", state) is None


def test_vexu_no_on_field_cups(vexu_bundle):
    state = build_vexu_starting_state(vexu_bundle).match_state
    assert state.cups == []


def test_vexu_on_field_pin_inventory_is_only_midfield_and_preloads(vexu_bundle):
    state = build_vexu_starting_state(vexu_bundle).match_state
    counts = _pin_color_combo_counts(state.pins)
    assert counts[("yellow", "yellow")] == 1  # Midfield only
    assert counts[("red", "yellow")] == 2  # 2 Preloads (one per red-side Robot)
    assert counts[("blue", "yellow")] == 2  # 2 Preloads (one per blue-side Robot)
    assert counts.get(("blue", "red"), 0) == 0
    assert len(state.pins) == 5


def test_vexu_match_load_inventory(vexu_bundle):
    bundle = build_vexu_starting_state(vexu_bundle)
    pins_by_alliance_combo = {
        (e.alliance, e.color_a.value, e.color_b.value): e.count for e in bundle.match_load_pins
    }
    assert pins_by_alliance_combo[(Alliance.RED, "red", "yellow")] == 10
    assert pins_by_alliance_combo[(Alliance.RED, "yellow", "yellow")] == 3
    assert pins_by_alliance_combo[(Alliance.BLUE, "blue", "yellow")] == 10
    assert pins_by_alliance_combo[(Alliance.BLUE, "yellow", "yellow")] == 3
    assert sum(e.count for e in bundle.match_load_pins) == 26

    cups_by_alliance = {e.alliance: e.count for e in bundle.match_load_cups}
    assert cups_by_alliance[Alliance.RED] == 10
    assert cups_by_alliance[Alliance.BLUE] == 10


# --- Robots / Preloads -------------------------------------------------------------


def test_v5rc_robots_and_preloads(v5rc_bundle):
    state = build_v5rc_starting_state(v5rc_bundle).match_state
    assert len(state.robots) == 4
    assert sum(1 for r in state.robots if r.alliance == Alliance.RED) == 2
    assert sum(1 for r in state.robots if r.alliance == Alliance.BLUE) == 2
    for robot in state.robots:
        assert robot.program == "v5rc"
        assert robot.in_midfield is False
        assert robot.contacting_perimeter is False

    preloads = [p for p in state.pins if p.id.startswith("preload_")]
    assert len(preloads) == 4
    assert not any(is_pin_placed(p) for p in preloads)
    for pin in preloads:
        assert pin.goal is None


def test_vexu_robots_and_preloads(vexu_bundle):
    state = build_vexu_starting_state(vexu_bundle).match_state
    assert len(state.robots) == 4
    ids = {r.id for r in state.robots}
    assert ids == {"red_24", "red_15", "blue_24", "blue_15"}
    for robot in state.robots:
        assert robot.program == "vexu"
        assert robot.in_midfield is False
        assert robot.contacting_perimeter is False


# --- Program separation and object independence -----------------------------------


def test_v5rc_and_vexu_are_explicit_program_specific_builders(v5rc_bundle, vexu_bundle):
    with pytest.raises(ValueError):
        build_v5rc_starting_state(vexu_bundle)
    with pytest.raises(ValueError):
        build_vexu_starting_state(v5rc_bundle)


def test_v5rc_and_vexu_starting_layouts_differ(v5rc_bundle, vexu_bundle):
    v5rc_state = build_v5rc_starting_state(v5rc_bundle).match_state
    vexu_state = build_vexu_starting_state(vexu_bundle).match_state
    assert len(v5rc_state.pins) != len(vexu_state.pins)
    assert len(v5rc_state.cups) != len(vexu_state.cups)
    occupied_goal_types_v5rc = {g.goal_type for g in v5rc_state.goals if g.occupant is not None}
    occupied_goal_types_vexu = {g.goal_type for g in vexu_state.goals if g.occupant is not None}
    assert occupied_goal_types_v5rc == {GoalType.NEUTRAL_SHORT, GoalType.NEUTRAL_TALL}
    assert occupied_goal_types_vexu == {GoalType.NEUTRAL_TALL}


def test_building_starting_state_twice_produces_independent_objects(v5rc_bundle):
    first = build_v5rc_starting_state(v5rc_bundle).match_state
    second = build_v5rc_starting_state(v5rc_bundle).match_state

    assert first.goals[0] is not second.goals[0]
    assert first.pins[0] is not second.pins[0]

    # Mutating one build must not affect the other.
    first_midfield = next(g for g in first.goals if g.goal_type == GoalType.NEUTRAL_TALL)
    second_midfield = next(g for g in second.goals if g.goal_type == GoalType.NEUTRAL_TALL)
    first_midfield.occupant = None
    assert second_midfield.occupant is not None


def test_building_vexu_starting_state_twice_produces_independent_objects(vexu_bundle):
    first = build_vexu_starting_state(vexu_bundle).match_state
    second = build_vexu_starting_state(vexu_bundle).match_state
    assert first.robots[0] is not second.robots[0]
    first.robots[0].in_midfield = True
    assert second.robots[0].in_midfield is False

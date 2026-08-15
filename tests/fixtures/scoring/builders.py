"""Small construction helpers for hand-built MatchState fixtures used by
tests/test_scoring_golden.py. These build a *given* final state directly (no physics,
no stacking simulation) -- see docs/design/03-state-and-scoring.md.
"""

from __future__ import annotations

from vexu_sim.model import (
    Alliance,
    Color,
    Cup,
    CupHalf,
    Goal,
    GoalType,
    Occupant,
    Pin,
    PinHalf,
    Quadrant,
    Robot,
    Toggle,
)


def make_quadrant(id: str, alliance_side: Alliance) -> Quadrant:
    return Quadrant(id=id, alliance_side=alliance_side)


def make_toggle(
    id: str,
    quadrant: Quadrant,
    orientation: Color = Color.YELLOW,
    seated: bool = True,
    contacted_by_robot: bool = False,
) -> Toggle:
    return Toggle(
        id=id,
        quadrant=quadrant,
        orientation=orientation,
        seated=seated,
        contacted_by_robot=contacted_by_robot,
    )


def make_goal(id: str, goal_type: GoalType, quadrant: Quadrant | None) -> Goal:
    return Goal(id=id, goal_type=goal_type, quadrant=quadrant)


def make_cup(id: str) -> Cup:
    return Cup(id=id, opaque=CupHalf(kind="opaque"), transparent=CupHalf(kind="transparent"))


def make_robot(id: str, alliance: Alliance, program: str, in_midfield: bool = False, contacting_perimeter: bool = False) -> Robot:
    return Robot(
        id=id,
        alliance=alliance,
        program=program,
        in_midfield=in_midfield,
        contacting_perimeter=contacting_perimeter,
    )


def make_pin(id: str, color_a: Color, color_b: Color, goal: Goal) -> Pin:
    """A Pin not yet nested anywhere; `goal` records which Goal's stack it belongs to
    (see Pin.goal in docs/design/03-state-and-scoring.md)."""
    return Pin(id=id, half_a=PinHalf(color_a), half_b=PinHalf(color_b), goal=goal)


def nest_half_on_goal(pin: Pin, half: str, goal: Goal) -> None:
    """Record `pin`'s `half` ("a"/"b") as the adjudicated occupant of `goal`'s slot."""
    pin_half = pin.half_a if half == "a" else pin.half_b
    pin_half.rests_on = goal
    goal.occupant = Occupant(pin, half)


def nest_half_on_cup_half(pin: Pin, half: str, cup_half: CupHalf) -> None:
    """Record `pin`'s `half` as the adjudicated occupant of `cup_half`'s slot."""
    pin_half = pin.half_a if half == "a" else pin.half_b
    pin_half.rests_on = cup_half
    cup_half.occupant = Occupant(pin, half)


def rest_half_on_cup_half_without_occupying(pin: Pin, half: str, cup_half: CupHalf) -> None:
    """Record `pin`'s `half` as merely *claiming* (touching) `cup_half`'s slot,
    without becoming its adjudicated occupant -- the Figure SC2-2 capacity-conflict
    scenario: a Pin resting on an already-occupied Cup half is not Placed."""
    pin_half = pin.half_a if half == "a" else pin.half_b
    pin_half.rests_on = cup_half

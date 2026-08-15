"""The minimum typed state model needed for static Override scoring.

A MatchState is a single fully-formed snapshot of the Field at one instant (the end of
the Autonomous Period, or the end of the Match) -- not a live/mutable simulation state.
See docs/design/03-state-and-scoring.md for the reasoning behind this model, especially
the Occupant/rests_on split that represents the <SC2> stacking/capacity rules without
any spatial or physics modeling.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Literal, Optional, Union


class Alliance(str, Enum):
    RED = "red"
    BLUE = "blue"


class Color(str, Enum):
    """The three colors a Pin half or a Toggle's orientation can be."""

    RED = "red"
    BLUE = "blue"
    YELLOW = "yellow"


class GoalType(str, Enum):
    ALLIANCE_RED = "alliance_red"
    ALLIANCE_BLUE = "alliance_blue"
    NEUTRAL_SHORT = "neutral_short"
    NEUTRAL_TALL = "neutral_tall"  # the single Midfield Goal


class ScoringContext(str, Enum):
    """Which instant a MatchState snapshot represents."""

    START = "start"
    """Before either period begins -- the official pre-Match configuration (M2). No
    scoring function reads this value; it is descriptive metadata only."""
    AUTONOMOUS_END = "autonomous_end"
    MATCH_END = "match_end"


@dataclass
class Quadrant:
    id: str
    alliance_side: Alliance
    """Which Alliance's side of the Autonomous Line this Quadrant is on -- matches the
    Alliance-colored Goal it contains (Field Overview, p.8). See
    docs/design/03-state-and-scoring.md for why this doubles as the <SC8>/<VUG6>
    "opposing side of the Autonomous Line" predicate."""


@dataclass
class Toggle:
    id: str
    quadrant: Quadrant
    orientation: Color
    seated: bool
    """<SC4>a: fully seated, in contact and parallel with its Field Perimeter mounts."""
    contacted_by_robot: bool
    """<SC4>b: in contact with a Robot from either Alliance."""

    @property
    def effective_color(self) -> Color:
        """<SC4>: set to `orientation` only if seated and uncontacted; otherwise
        defaults to neutral yellow."""
        if self.seated and not self.contacted_by_robot:
            return self.orientation
        return Color.YELLOW


@dataclass(frozen=True)
class Occupant:
    """The single Pin half adjudicated to hold one slot's one-Pin-half capacity."""

    pin: "Pin"
    half: Literal["a", "b"]


@dataclass
class Goal:
    id: str
    goal_type: GoalType
    quadrant: Optional[Quadrant]
    """None only for the single neutral tall Midfield Goal, which is not in any Quadrant."""
    occupant: Optional[Occupant] = None
    """<SC2>a.ii: a Goal holds a maximum of one Pin half."""


@dataclass
class CupHalf:
    kind: Literal["opaque", "transparent"]
    cup: Optional["Cup"] = field(default=None, repr=False, compare=False)
    occupant: Optional[Occupant] = None
    """<SC2>a.ii: each half of a Cup holds a maximum of one Pin half."""


@dataclass
class Cup:
    id: str
    opaque: CupHalf
    transparent: CupHalf

    def __post_init__(self) -> None:
        self.opaque.cup = self
        self.transparent.cup = self


@dataclass
class PinHalf:
    color: Color
    rests_on: Optional[Union[Goal, CupHalf]] = None
    """The slot this half is physically claiming to nest into. Whether that claim is
    the adjudicated `occupant` of the slot (and therefore actually Placed/visible) is
    resolved by scoring, not stored here -- see Occupant."""


@dataclass
class Pin:
    id: str
    half_a: PinHalf
    half_b: PinHalf
    goal: Optional[Goal] = None
    """The Goal this Pin's stack is built on -- see docs/design/03-state-and-scoring.md
    for why this is recorded directly rather than derived by walking the nesting
    chain. None for a Pin that exists on the Field but is not (yet) Placed on any
    Goal's stack -- e.g. a predetermined Pin resting loose on the Field at the start
    of a Match (M2), or a Preload held by a Robot. A Pin with goal=None can never be
    Placed (is_pin_placed reads rests_on/occupant, not goal, so this is enforced by
    construction discipline in field_setup/, not by scoring.py itself)."""


@dataclass
class Robot:
    id: str
    alliance: Alliance
    program: str
    """"v5rc" | "vexu" -- expected to match the owning MatchState.program."""
    in_midfield: bool
    contacting_perimeter: bool


@dataclass
class MatchState:
    program: str
    scoring_context: ScoringContext
    goals: list[Goal]
    pins: list[Pin]
    cups: list[Cup]
    quadrants: list[Quadrant]
    toggles: list[Toggle]
    robots: list[Robot]
    autonomous_violations: frozenset[Alliance] = frozenset()

    def toggle_for_quadrant(self, quadrant: Quadrant) -> Toggle:
        for toggle in self.toggles:
            if toggle.quadrant is quadrant:
                return toggle
        raise ValueError(f"no Toggle recorded for quadrant {quadrant.id!r}")

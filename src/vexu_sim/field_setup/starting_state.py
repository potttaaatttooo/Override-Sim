"""Official starting Field configurations for V5RC and VEX U Override (M2).

Builds a `MatchState` at `ScoringContext.START` -- the official pre-Match Field
configuration -- for each program, plus the off-field Match Load inventory that is
not physically on the Field until a Drive Team Member introduces it (<SG11>/<VUG4>).
See docs/design/06-starting-field-states.md for the full source-by-source derivation,
including how the Appendix A "Scoring Object Locations" and "Toggle Assembly -
Starting Orientation" drawings were read.

No simulation, no coordinates, no robot strategy: every fact here is either quoted
directly from data/rules/override/v1.1/ (field.yaml, vexu.yaml) or derived from
official Appendix A drawings and the Section 6 field-setup rule text.

Deliberately NOT encoded: the floor position of the 32 V5RC on-Field predetermined
Pins that are not one of the 5 Placed at kickoff (4 neutral-short Goals + Midfield),
nor of the 36 on-Field Cups. Official spatial/start-layout information for these DOES
exist -- Figure FO-2 illustrates them and Appendix A's "Scoring Object Locations"
drawing (A12) dimensions them precisely, the same way it dimensions Goal/Toggle mount
points. They are represented as on the Field but unplaced (`goal=None`) here only
because `MatchState` (M1) is deliberately non-spatial and no current scoring
predicate needs a coordinate -- see `docs/design/03-state-and-scoring.md`, "What is
deliberately not represented." Encoding their positions is deferred to the future
spatial-model milestone (M6, `docs/roadmap.md`), which is the first point a
coordinate/region has a consumer; see `docs/design/06-starting-field-states.md` for
the full derivation. This is a deferral, not a gap in the source data.
"""

from __future__ import annotations

from dataclasses import dataclass

from vexu_sim.model import (
    Alliance,
    Color,
    Cup,
    CupHalf,
    Goal,
    GoalType,
    MatchState,
    Occupant,
    Pin,
    PinHalf,
    Quadrant,
    Robot,
    ScoringContext,
    Toggle,
)
from vexu_sim.rules import RuleBundle


@dataclass(frozen=True)
class MatchLoadPinEntry:
    """An off-field Match Load Pin count: not on the Field, not Placed, held for
    introduction into a Loader per <SG11> (V5RC) / <VUG4> (VEX U). "Match Load - One
    of the 20 Cups, 10 per Alliance, or 22 Pins, 11 per Alliance..." (Glossary,
    p.B6)."""

    alliance: Alliance
    color_a: Color
    color_b: Color
    count: int


@dataclass(frozen=True)
class MatchLoadCupEntry:
    alliance: Alliance
    count: int


@dataclass(frozen=True)
class StartingFieldState:
    """The official starting configuration for one program at kickoff.

    `match_state` holds everything physically on the Field: Goals, Quadrants,
    Toggles, Robots, and every Pin/Cup that is on the Field surface, held by a Robot
    as a Preload (`goal=None`, unplaced -- <SG5>), or actually Placed on a Goal.
    `match_load_pins`/`match_load_cups` are held off-field in the Loader until a
    Drive Team Member introduces them -- see <SG11>/<VUG4>. This split is what
    CLAUDE.md's M2 task calls "objects physically on the Field" vs "Match Load
    inventory."
    """

    match_state: MatchState
    match_load_pins: tuple[MatchLoadPinEntry, ...]
    match_load_cups: tuple[MatchLoadCupEntry, ...]


def _build_quadrants_goals_toggles() -> tuple[list[Quadrant], list[Goal], list[Toggle], Goal]:
    """The Field structure shared, unmodified, by both programs: 4 Quadrants (2
    red-side, 2 blue-side), each with 1 Alliance Goal + 1 neutral-short Goal + 1
    Toggle, plus the single neutral-tall Midfield Goal. Section 6 does not modify
    this structure (only what starts Placed on it, and Match Load availability).

    Sources: Field Overview (p.8: "9 Goals ... 4 Toggles"), Appendix B Figure Q-1
    (Quadrant labels "Red 1"/"Red 2"/"Blue 1"/"Blue 2"), Appendix A "Field Element
    Locations" (A10) and "Scoring Object Locations" (A12), Appendix A "Toggle
    Assembly - Starting Orientation" (A15): every Toggle starts with its yellow face
    up and into the Field, its Alliance-colored face out -- i.e. `effective_color ==
    YELLOW` (neutral) for all four Toggles at kickoff.

    Returns (quadrants, all_goals, toggles, midfield_goal).
    """
    quadrants = [
        Quadrant(id="red_1", alliance_side=Alliance.RED),
        Quadrant(id="red_2", alliance_side=Alliance.RED),
        Quadrant(id="blue_1", alliance_side=Alliance.BLUE),
        Quadrant(id="blue_2", alliance_side=Alliance.BLUE),
    ]

    goals: list[Goal] = []
    toggles: list[Toggle] = []
    for quadrant in quadrants:
        alliance_type = (
            GoalType.ALLIANCE_RED if quadrant.alliance_side == Alliance.RED else GoalType.ALLIANCE_BLUE
        )
        goals.append(Goal(id=f"g_alliance_{quadrant.id}", goal_type=alliance_type, quadrant=quadrant))
        goals.append(
            Goal(id=f"g_neutral_short_{quadrant.id}", goal_type=GoalType.NEUTRAL_SHORT, quadrant=quadrant)
        )
        toggles.append(
            Toggle(
                id=f"t_{quadrant.id}",
                quadrant=quadrant,
                orientation=Color.YELLOW,
                seated=True,
                contacted_by_robot=False,
            )
        )

    midfield_goal = Goal(id="g_midfield", goal_type=GoalType.NEUTRAL_TALL, quadrant=None)
    goals.append(midfield_goal)

    return quadrants, goals, toggles, midfield_goal


def _placed_yellow_pin(pin_id: str, goal: Goal) -> Pin:
    """A yellow/yellow Pin Placed directly on `goal` (no Cup involved) -- both halves
    visible and Scored-eligible from kickoff (unowned, since every Toggle starts
    neutral). Used for the 5 Goals (4 neutral-short + Midfield) that official sources
    show holding a Pin at start: Appendix A "Scoring Object Locations" (A12) for the
    4 neutral-short Goals, and Section 6 "Rule Modifications: Field Setup" (p.72,
    "Only the Midfield Goal should begin the Match with a yellow/yellow Pin Placed in
    it") plus Figure VEXU-1/VEXU-2 for the Midfield Goal in both programs -- A12
    shows the same yellow/yellow Pin already Placed on the V5RC Midfield Goal too.
    """
    pin = Pin(id=pin_id, half_a=PinHalf(Color.YELLOW), half_b=PinHalf(Color.YELLOW), goal=goal)
    pin.half_a.rests_on = goal
    goal.occupant = Occupant(pin, "a")
    return pin


def _loose_pins(prefix: str, color_a: Color, color_b: Color, count: int) -> list[Pin]:
    """`count` Pins on the Field but not Placed on any Goal (`goal=None`, neither
    half rests on anything) -- see module docstring for why exact floor placement is
    not reconstructed."""
    return [Pin(id=f"{prefix}{i}", half_a=PinHalf(color_a), half_b=PinHalf(color_b)) for i in range(count)]


def _loose_cups(prefix: str, count: int) -> list[Cup]:
    return [
        Cup(id=f"{prefix}{i}", opaque=CupHalf(kind="opaque"), transparent=CupHalf(kind="transparent"))
        for i in range(count)
    ]


def _robots_and_preloads(program: str, red_ids: list[str], blue_ids: list[str]) -> tuple[list[Robot], list[Pin]]:
    """Robots plus their Preload Pins, one Preload per Robot (<SG5>, unmodified for
    VEX U -- not in vexu.yaml's overrides_base_rule_ids -- combined with <VUR1>'s 2
    Robots per Team). A Robot at kickoff has done nothing yet, so `in_midfield` is
    trivially False -- not an assumed strategy, just the "hasn't moved" starting
    fact. `contacting_perimeter` is True: <SG1>f requires each Robot to start
    "Contacting the Field tiles and Field Perimeter on their Alliance's side of the
    Autonomous Line"; VEX U's <VUG1>/<VUG3> modify only <SG1>'s size clause (a), not
    clause f, so this holds unmodified for both programs. Preload Pins are on the
    Field (held by a Robot) but not Placed: `goal=None`, `rests_on=None`."""
    robots = [
        Robot(id=rid, alliance=Alliance.RED, program=program, in_midfield=False, contacting_perimeter=True)
        for rid in red_ids
    ] + [
        Robot(id=rid, alliance=Alliance.BLUE, program=program, in_midfield=False, contacting_perimeter=True)
        for rid in blue_ids
    ]
    preloads = [
        Pin(id=f"preload_{rid}", half_a=PinHalf(Color.RED), half_b=PinHalf(Color.YELLOW)) for rid in red_ids
    ] + [
        Pin(id=f"preload_{rid}", half_a=PinHalf(Color.BLUE), half_b=PinHalf(Color.YELLOW)) for rid in blue_ids
    ]
    return robots, preloads


def build_v5rc_starting_state(rule_bundle: RuleBundle) -> StartingFieldState:
    """The official V5RC Override starting Field configuration.

    Sources: data/rules/override/v1.1/field.yaml (`inventory`: the aggregate Pin/Cup
    counts by color combination and category), Appendix A "Scoring Object Locations"
    (A12, which Goals start with a Pin Placed) and "Toggle Assembly - Starting
    Orientation" (A15, Toggle orientation). See
    docs/design/06-starting-field-states.md.
    """
    if rule_bundle.program != "v5rc":
        raise ValueError(f"build_v5rc_starting_state requires a v5rc RuleBundle, got {rule_bundle.program!r}")

    quadrants, goals, toggles, midfield_goal = _build_quadrants_goals_toggles()
    neutral_short_goals = [g for g in goals if g.goal_type == GoalType.NEUTRAL_SHORT]

    placed_pins = [_placed_yellow_pin(f"placed_yy_{g.id}", g) for g in neutral_short_goals]
    placed_pins.append(_placed_yellow_pin("placed_yy_midfield", midfield_goal))

    inventory = rule_bundle.data["field"]["inventory"]
    pins_breakdown = inventory["pins"]["breakdown"]
    cups_breakdown = inventory["cups"]["breakdown"]

    # 5 of the 17 predetermined yellow/yellow Pins are the placed_pins built above
    # (one per neutral-short Goal + Midfield); the remainder of the on-Field
    # predetermined inventory is loose (goal=None) -- see module docstring.
    loose_yellow_yellow_count = pins_breakdown["yellow_yellow_predetermined"] - len(placed_pins)
    loose_pins = (
        _loose_pins("loose_rb_", Color.RED, Color.BLUE, pins_breakdown["red_blue_predetermined"])
        + _loose_pins("loose_ry_", Color.RED, Color.YELLOW, pins_breakdown["red_yellow_predetermined"])
        + _loose_pins("loose_by_", Color.BLUE, Color.YELLOW, pins_breakdown["blue_yellow_predetermined"])
        + _loose_pins("loose_yy_", Color.YELLOW, Color.YELLOW, loose_yellow_yellow_count)
    )
    loose_cups = _loose_cups("loose_cup_gray_", cups_breakdown["start_gray_side_up"]) + _loose_cups(
        "loose_cup_clear_", cups_breakdown["start_clear_side_up"]
    )

    robots, preload_pins = _robots_and_preloads("v5rc", ["red_1", "red_2"], ["blue_1", "blue_2"])

    match_state = MatchState(
        program="v5rc",
        scoring_context=ScoringContext.START,
        goals=goals,
        pins=placed_pins + loose_pins + preload_pins,
        cups=loose_cups,
        quadrants=quadrants,
        toggles=toggles,
        robots=robots,
    )

    match_load_pins, match_load_cups = _match_load_entries(rule_bundle)

    return StartingFieldState(
        match_state=match_state, match_load_pins=match_load_pins, match_load_cups=match_load_cups
    )


def _match_load_entries(
    rule_bundle: RuleBundle,
) -> tuple[tuple[MatchLoadPinEntry, ...], tuple[MatchLoadCupEntry, ...]]:
    """Off-field Match Load entries for either program, read through
    `RuleBundle.match_load_inventory` -- the effective/composed accessor (Session B's
    established pattern: `awp_requirements`, `period_seconds`) so field_setup never
    needs to know whether the underlying counts live in the base field.yaml
    inventory or the vexu.yaml overlay's field_setup.match_loads block."""
    inventory = rule_bundle.match_load_inventory
    match_load_pins = (
        MatchLoadPinEntry(Alliance.RED, Color.RED, Color.YELLOW, inventory.red_own_color_yellow_pins),
        MatchLoadPinEntry(Alliance.RED, Color.YELLOW, Color.YELLOW, inventory.red_yellow_yellow_pins),
        MatchLoadPinEntry(Alliance.BLUE, Color.BLUE, Color.YELLOW, inventory.blue_own_color_yellow_pins),
        MatchLoadPinEntry(Alliance.BLUE, Color.YELLOW, Color.YELLOW, inventory.blue_yellow_yellow_pins),
    )
    match_load_cups = (
        MatchLoadCupEntry(Alliance.RED, inventory.red_cups),
        MatchLoadCupEntry(Alliance.BLUE, inventory.blue_cups),
    )
    return match_load_pins, match_load_cups


def build_vexu_starting_state(rule_bundle: RuleBundle) -> StartingFieldState:
    """The official VEX U Override starting Field configuration.

    Source: Section 6 "Rule Modifications: Field Setup" (p.72, "Modified Field
    layout. Only the Midfield Goal should begin the Match with a yellow/yellow Pin
    Placed in it") and Figures VEXU-1/VEXU-2, data/rules/override/v1.1/vexu.yaml
    (`field_setup.match_loads`). Every Goal except the Midfield Goal begins empty,
    and no Cups start on the Field at all -- confirmed visually by Figure VEXU-1,
    which shows no Cup icon anywhere on the Field. See
    docs/design/06-starting-field-states.md.
    """
    if rule_bundle.program != "vexu":
        raise ValueError(f"build_vexu_starting_state requires a vexu RuleBundle, got {rule_bundle.program!r}")

    quadrants, goals, toggles, midfield_goal = _build_quadrants_goals_toggles()
    placed_pins = [_placed_yellow_pin("placed_yy_midfield", midfield_goal)]

    robots, preload_pins = _robots_and_preloads("vexu", ["red_24", "red_15"], ["blue_24", "blue_15"])

    match_state = MatchState(
        program="vexu",
        scoring_context=ScoringContext.START,
        goals=goals,
        pins=placed_pins + preload_pins,
        cups=[],
        quadrants=quadrants,
        toggles=toggles,
        robots=robots,
    )

    match_load_pins, match_load_cups = _match_load_entries(rule_bundle)

    return StartingFieldState(
        match_state=match_state, match_load_pins=match_load_pins, match_load_cups=match_load_cups
    )


def build_starting_state(rule_bundle: RuleBundle) -> StartingFieldState:
    """Dispatch to build_v5rc_starting_state/build_vexu_starting_state by
    `rule_bundle.program`."""
    if rule_bundle.program == "v5rc":
        return build_v5rc_starting_state(rule_bundle)
    if rule_bundle.program == "vexu":
        return build_vexu_starting_state(rule_bundle)
    raise ValueError(f"unknown program {rule_bundle.program!r}")

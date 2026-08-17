"""Small construction helpers for hand-built observation fixtures used by
tests/test_observations.py. Build raw dicts (the same shape a hand-authored YAML
file would parse to), not dataclasses directly, so tests exercise the real
parse_match/parse_snapshot/parse_event path -- consistent with
tests/fixtures/scoring/builders.py's "build a given state directly" style, adapted
for a data-layer schema instead of a physics-adjacent one.
"""

from __future__ import annotations

from vexu_sim.observations import refs


def minimal_match(
    *,
    program: str = "v5rc",
    robots: list[dict] | None = None,
    cycle_labeled_alliance: str = "red",
) -> dict:
    if robots is None:
        robots = [
            dict(
                robot_ref="r_red_a", alliance="red", team="0001A",
                size_class="unknown_v5rc", visual_key="test robot", cycle_labeled=True,
            ),
            dict(
                robot_ref="r_blue_a", alliance="blue", team="0002B",
                size_class="unknown_v5rc", visual_key="test robot", cycle_labeled=False,
            ),
        ]
    return dict(
        schema_version="m3.0",
        match_key=f"{program}/unit-test/q0",
        program=program,
        event_name="Unit Test Event",
        event_code="UT-0001",
        match_id="Q0",
        match_type="qualification",
        date="2026-08-16",
        manual_version="1.1",
        video=dict(
            url="https://example.invalid/unit-test",
            retrieved="2026-08-16",
            quality="good",
            camera="fixed_full_field",
            period_offsets={"autonomous": 0.0, "driver": 20.0},
            sync_check={"video_t": 25.0, "observed_field_clock": "1:45"},
            timing_precision_s=0.3,
        ),
        roster=robots,
        official_result=dict(
            red_total=0, blue_total=0, autonomous_bonus_to="unknown",
            awp={"red": False, "blue": False}, violations_autonomous=[],
            source_url="https://example.invalid/result", retrieved="2026-08-16",
        ),
        coverage=dict(cycle_labeled_alliance=cycle_labeled_alliance, fully_labeled=True, unlabeled_windows=[]),
        labeling=dict(
            labeler="unit-test", label_date="2026-08-16", pass_id=1,
            selection_stratum="baseline_clean", minutes_spent=0, source_csv_sha256=None,
        ),
    )


def starting_goal_stack(goal_id: str, depth: int) -> list[dict]:
    return [{"object": "pin", "colors": ["yellow", "yellow"]} for _ in range(depth)]


def minimal_snapshots(rule_bundle, *, robot_refs: list[str], goal_depths: dict[str, int] | None = None) -> list[dict]:
    """Two snapshots (autonomous_end, match_end) with every canonical Goal/Toggle
    and every given robot present. `goal_depths` defaults to the program's official
    kickoff depths (via field_setup), so a "no events happened" reconciliation test
    trivially matches."""
    from vexu_sim.observations.reconcile import _starting_goal_depths

    if goal_depths is None:
        goal_depths = _starting_goal_depths(rule_bundle)

    goal_ids = refs.canonical_goal_ids(rule_bundle)
    toggle_ids = refs.canonical_toggle_ids(rule_bundle)

    def build(context: str, video_t: float) -> dict:
        return dict(
            snapshot_id=f"s_{context}",
            context=context,
            video_t=video_t,
            quality="good",
            goals={gid: {"stack": starting_goal_stack(gid, goal_depths.get(gid, 0)), "confidence": "certain"} for gid in goal_ids},
            toggles={
                tid: {"orientation": "yellow", "seated": True, "contacted_by_robot": False, "confidence": "certain"}
                for tid in toggle_ids
            },
            robots={
                rref: {"in_midfield": False, "contacting_perimeter": False, "confidence": "certain"}
                for rref in robot_refs
            },
        )

    return [build("autonomous_end", 5.0), build("match_end", 40.0)]


def action(**overrides) -> dict:
    base = dict(
        record_type="action",
        id="a_test",
        action_type="acquire",
        robot_ref="r_red_a",
        period="driver",
        video_t_start=21.0,
        video_t_end=22.0,
        region="quadrant_red_1",
        outcome="success",
        contested="none",
        retry_of=None,
        confidence="certain",
        source="floor",
        object="pin",
        possession_id="r_red_a#1",
    )
    base.update(overrides)
    return base

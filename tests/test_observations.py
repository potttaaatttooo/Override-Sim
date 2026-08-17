"""M3A tests: observation schema + tooling. No real match video is reviewed or
labeled anywhere in this file -- see docs/plans/m3-observation-plan.md's M3A/M3B
split and CLAUDE.md's "Manual video review ... begin in M3B" constraint. All
fixtures are synthetic (tests/fixtures/observations/)."""

from __future__ import annotations

from pathlib import Path

import pytest

from vexu_sim.observations import refs
from vexu_sim.observations.from_csv import (
    ObservationValidationError as FromCsvValidationError,
    compute_csv_sha256,
    import_events_csv,
    read_events_csv,
    verify_csv_sha256,
    write_events_yaml,
)
from vexu_sim.observations.loader import (
    ObservationValidationError,
    load_match_observation,
    parse_event,
    parse_match,
    parse_snapshot,
    validate_observation_set,
)
from vexu_sim.observations.models import (
    ACTION_TYPES,
    GAP_CLASSES,
    UNKNOWN,
    Action,
    LoaderVisit,
)
from vexu_sim.observations.reconcile import reconcile
from vexu_sim.rules import load_rule_bundle
from vexu_sim.sources import load_sources

from tests.fixtures.observations.builders import action, minimal_match, minimal_snapshots

DATA_ROOT = Path(__file__).parent.parent / "data"
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "observations" / "synth_match"


@pytest.fixture(scope="module")
def sources():
    return load_sources(DATA_ROOT)


@pytest.fixture(scope="module")
def v5rc_bundle(sources):
    return load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)


@pytest.fixture(scope="module")
def vexu_bundle(sources):
    return load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)


def _minimal(v5rc_bundle, **match_overrides):
    match_raw = minimal_match(**match_overrides)
    robot_refs = [r["robot_ref"] for r in match_raw["roster"]]
    snapshots_raw = minimal_snapshots(v5rc_bundle, robot_refs=robot_refs)
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in snapshots_raw)
    return match, snapshots


# --- model / enums -----------------------------------------------------------------


def test_loader_visit_is_not_an_action_type():
    assert "loader_visit" not in ACTION_TYPES
    assert ACTION_TYPES == {"acquire", "place", "descore", "toggle"}


def test_gap_class_includes_no_next_action():
    assert GAP_CLASSES == {"transit", "mixed", "contested", "not_observed", "none", "no_next_action"}


def test_unknown_sentinel_is_literal_string():
    assert UNKNOWN == "unknown"


# --- synthetic fixture loading -------------------------------------------------------


def test_synthetic_fixture_loads_and_validates(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    assert loaded.match.match_key == "v5rc/synthetic_fixture/q000"
    assert len(loaded.snapshots) == 2
    assert len(loaded.events) == 19
    # the one deliberate duplicate-acquisition warning, and nothing else
    assert len(loaded.warnings) == 1
    assert "a_005" in loaded.warnings[0]
    assert "duplicate" in loaded.warnings[0] or "already held" in loaded.warnings[0]


def test_synthetic_fixture_has_no_real_match_data():
    # the fixture must be clearly synthetic, not sourced from a real event.
    text = (FIXTURE_ROOT / "match.yaml").read_text(encoding="utf-8")
    assert "synthetic" in text.lower()


# --- gap_after / no_next_action -----------------------------------------------------


def test_gap_after_no_next_action_on_terminal_actions(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    actions_by_id = {e.id: e for e in loaded.events if isinstance(e, Action)}
    assert actions_by_id["a_001"].gap_after == "no_next_action"  # only auton action
    assert actions_by_id["a_014"].gap_after == "no_next_action"  # last driver action
    assert actions_by_id["a_002"].gap_after == "transit"  # not terminal


def test_no_next_action_disagreement_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        action(id="a_1", video_t_start=21.0, video_t_end=22.0, gap_after="no_next_action", possession_id="r_red_a#1"),
        action(id="a_2", video_t_start=23.0, video_t_end=24.0, gap_after="no_next_action",
               action_type="place", object="pin", target_goal_ref="g_alliance_red_1",
               stack_height_before=0, stack_height_after=1, destabilized_stack=False,
               possession_id="r_red_a#1", source=None),
    )
    events = tuple(parse_event(e) for e in events)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    # a_1 is NOT terminal (a_2 follows) but claims no_next_action -- must be rejected.
    assert any("a_1" in e and "no_next_action" in e for e in errors)


def test_gap_after_absent_for_non_cycle_labeled_robot(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(robot_ref="r_blue_a", gap_after="transit")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("must be absent" in e for e in errors)


def test_gap_after_required_for_cycle_labeled_robot(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(robot_ref="r_red_a", gap_after=None)),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("gap_after is REQ-IF" in e for e in errors)


# --- Action end-time semantics -------------------------------------------------------


def test_action_video_t_end_null_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(video_t_end=None, gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("never be null" in e for e in errors)


def test_action_video_t_end_unknown_is_accepted(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(video_t_end=UNKNOWN, gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert errors == []


def test_action_end_must_be_strictly_after_start(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(video_t_start=21.0, video_t_end=21.0, gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("strictly greater" in e for e in errors)


def test_loader_visit_video_t_exit_may_be_null_open_ended(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    lv = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=21.0, video_t_exit=None, loader_ref="loader_red_1",
        objects_acquired=0, failed_grabs=0, departs_possession_id=None,
        contested="none", confidence="certain",
    )
    events = (parse_event(lv),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert errors == []


# --- reference / enum validation -----------------------------------------------------


def test_invalid_region_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(region="somewhere_off_field", gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("region" in e for e in errors)


def test_invalid_goal_ref_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(
        action_type="place", object="pin", target_goal_ref="g_not_a_real_goal",
        stack_height_before=0, stack_height_after=1, destabilized_stack=False,
        source=None, gap_after="no_next_action",
    )),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("not a canonical Goal id" in e for e in errors)


def test_loader_ref_uses_m3_local_vocabulary(v5rc_bundle):
    assert refs.loader_refs() == {"loader_red_1", "loader_red_2", "loader_blue_1", "loader_blue_2"}


def test_invalid_loader_ref_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    lv = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=21.0, video_t_exit=22.0, loader_ref="loader_green_1",
        objects_acquired=0, failed_grabs=0, departs_possession_id=None,
        contested="none", confidence="certain",
    )
    events = (parse_event(lv),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("Loader vocabulary" in e for e in errors)


def test_program_never_both(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle, program="both")
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("must be one of" in e for e in errors)


def test_v5rc_robot_must_be_unknown_v5rc_size_class(v5rc_bundle):
    robots = [
        dict(robot_ref="r_red_a", alliance="red", team="0001A", size_class="vexu_24",
             visual_key="x", cycle_labeled=True),
    ]
    match, snapshots = _minimal(v5rc_bundle, robots=robots)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("unknown_v5rc" in e for e in errors)


def test_vexu_robot_may_not_be_unknown_v5rc(vexu_bundle):
    robots = [
        dict(robot_ref="r_red_24", alliance="red", team="0001A", size_class="unknown_v5rc",
             visual_key="x", cycle_labeled=True),
    ]
    match, snapshots = _minimal(vexu_bundle, program="vexu", robots=robots)
    errors, _ = validate_observation_set(match, snapshots, (), vexu_bundle)
    assert any("vexu_24" in e and "vexu_15" in e for e in errors)


# --- both snapshots / snapshot completeness ------------------------------------------


def test_missing_a_snapshot_context_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    errors, _ = validate_observation_set(match, (snapshots[0],), (), v5rc_bundle)
    assert any("exactly one snapshot" in e for e in errors)


def test_snapshot_missing_a_goal_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    del raw[1]["goals"]["g_midfield"]
    broken_snapshots = tuple(parse_snapshot(s) for s in raw)
    errors, _ = validate_observation_set(match, broken_snapshots, (), v5rc_bundle)
    assert any("missing Goals" in e for e in errors)


# --- possession episodes --------------------------------------------------------------


def test_possession_episode_pin_and_cup_two_placements(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    actions_by_id = {e.id: e for e in loaded.events if isinstance(e, Action)}
    # a_003 (acquire cup) opens r_red_a#2; a_004 extends it with a pin; a_006/a_007
    # place the cup then the pin from that same episode.
    assert actions_by_id["a_003"].possession_id == "r_red_a#2"
    assert actions_by_id["a_004"].possession_id == "r_red_a#2"
    assert actions_by_id["a_006"].possession_id == "r_red_a#2"
    assert actions_by_id["a_007"].possession_id == "r_red_a#2"
    assert actions_by_id["a_006"].object == "cup"
    assert actions_by_id["a_007"].object == "pin"


def test_duplicate_object_type_acquisition_is_a_warning_not_error(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    assert any("a_005" in w for w in loaded.warnings)


def test_interleaved_possession_id_is_an_error(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        action(id="a_1", video_t_start=21.0, video_t_end=22.0, possession_id="r_red_a#1", gap_after="mixed"),
        # a robot holding one episode's Pin cannot acquire under a *different* fresh id
        action(id="a_2", video_t_start=23.0, video_t_end=24.0, possession_id="r_red_a#7",
               object="cup", gap_after="no_next_action"),
    )
    events = tuple(parse_event(e) for e in events)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("non-interleaved" in e for e in errors)


def test_state_change_transport_drop_closes_episode(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        action(id="a_1", video_t_start=21.0, video_t_end=22.0, possession_id="r_red_a#1", gap_after="mixed"),
        dict(
            record_type="state_change", id="sc_1", period="driver", video_t=23.0,
            change="object_dropped_in_transit", attributed_to="r_red_a", confidence="certain",
            possession_id="r_red_a#1", object="pin",
        ),
        # after the drop, a fresh episode id is legal.
        action(id="a_2", video_t_start=24.0, video_t_end=25.0, possession_id="r_red_a#2", gap_after="no_next_action"),
    )
    events = tuple(parse_event(e) for e in events)
    errors, warnings = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert errors == []


def test_open_episode_at_match_end_is_a_warning(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(id="a_1", gap_after="no_next_action")),)
    errors, warnings = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert errors == []
    assert any("still open" in w for w in warnings)


# --- LoaderVisit semantics -------------------------------------------------------------


def test_loader_visit_has_no_action_only_fields():
    lv = LoaderVisit(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=1.0, video_t_exit=2.0, loader_ref="loader_red_1",
        objects_acquired=1, failed_grabs=0, departs_possession_id="r_red_a#1",
        contested="none", confidence="certain",
    )
    assert not hasattr(lv, "outcome")
    assert not hasattr(lv, "failure_mode")
    assert not hasattr(lv, "gap_after")
    assert not hasattr(lv, "retry_of")


def test_acquire_loader_visit_id_resolves_to_loader_visit_not_action(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        action(id="a_1", loader_visit_id="a_1", gap_after="no_next_action"),  # points at an Action id
    )
    events = tuple(parse_event(e) for e in events)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("does not resolve to a LoaderVisit" in e for e in errors)


def test_zero_object_loader_visit_is_legal(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    lv = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=21.0, video_t_exit=22.0, loader_ref="loader_red_1",
        objects_acquired=0, failed_grabs=0, departs_possession_id=None,
        contested="none", confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(lv),), v5rc_bundle)
    assert errors == []


# --- retry chains ----------------------------------------------------------------------


def test_retry_of_must_resolve(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(id="a_1", retry_of="a_does_not_exist", gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("retry_of" in e and "does not resolve" in e for e in errors)


def test_retry_chain_cycle_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        action(id="a_1", retry_of="a_2", possession_id="r_red_a#1", gap_after="mixed"),
        action(id="a_2", retry_of="a_1", possession_id="r_red_a#1", gap_after="no_next_action"),
    )
    events = tuple(parse_event(e) for e in events)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("cyclic" in e for e in errors)


# --- reconciliation ----------------------------------------------------------------------


def test_reconcile_descore_obscure_contributes_plus_one(v5rc_bundle):
    match, snapshots_raw = (
        minimal_match(),
        minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]),
    )
    # g_alliance_red_1 starts empty (depth 0); a descore{obscure} adds a Cup: +1.
    snapshots_raw[1]["goals"]["g_alliance_red_1"]["stack"] = [{"object": "cup", "down_face": "opaque"}]
    match_parsed = parse_match(match)
    snapshots = tuple(parse_snapshot(s) for s in snapshots_raw)
    events = (
        parse_event(dict(
            record_type="action", id="a_1", action_type="descore", robot_ref="r_red_a",
            period="driver", video_t_start=21.0, video_t_end=22.0, region="quadrant_red_1",
            outcome="success", contested="none", retry_of=None, confidence="certain",
            gap_after="no_next_action", method="obscure", cup_down_face="opaque",
            target_goal_ref="g_alliance_red_1", stack_height_before=0, stack_height_after=1,
        )),
    )
    report = reconcile(match_parsed, snapshots, events, v5rc_bundle)
    assert report.goal_depth["g_alliance_red_1"].status == "match"
    assert "predicted=1" in report.goal_depth["g_alliance_red_1"].detail


def test_reconcile_indeterminate_on_unknown_stack_height(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    report = reconcile(loaded.match, loaded.snapshots, loaded.events, v5rc_bundle)
    result = report.goal_depth["g_alliance_red_1"]
    assert result.status == "indeterminate"
    assert "unknown" in result.detail


def test_reconcile_goal_depth_uses_net_effect_not_assumed_sign(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    report = reconcile(loaded.match, loaded.snapshots, loaded.events, v5rc_bundle)
    # g_neutral_short_blue_1: starts at 1, +1 (place) +0 (failed descore) -1 (extract)
    # +1 (obscure) = net +1 -> predicted 2, matching the snapshot.
    assert report.goal_depth["g_neutral_short_blue_1"].status == "match"


def test_reconcile_toggle_orientation_reflects_last_labeled_state(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    report = reconcile(loaded.match, loaded.snapshots, loaded.events, v5rc_bundle)
    assert report.toggle_orientation["t_red_1"].status == "match"
    assert "red" in report.toggle_orientation["t_red_1"].detail
    # untouched Toggles fall back to the starting orientation (yellow) as predicted.
    assert report.toggle_orientation["t_blue_1"].status == "match"


def test_reconcile_midfield_occupancy_open_episode_covers_match_end(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    report = reconcile(loaded.match, loaded.snapshots, loaded.events, v5rc_bundle)
    assert report.midfield_occupancy["r_red_a@match_end"].status == "match"
    assert report.midfield_occupancy["r_red_a@autonomous_end"].status == "match"


def test_reconcile_never_touches_matchstate_or_scoring(v5rc_bundle):
    import importlib

    reconcile_module = importlib.import_module("vexu_sim.observations.reconcile")
    source = Path(reconcile_module.__file__).read_text(encoding="utf-8")
    assert "vexu_sim.scoring" not in source
    assert "MatchState(" not in source


# --- CSV importer -----------------------------------------------------------------------


def test_csv_import_matches_fixture_events(v5rc_bundle):
    match = parse_match(__import__("yaml").safe_load((FIXTURE_ROOT / "match.yaml").read_text(encoding="utf-8")))
    snapshots = tuple(
        parse_snapshot(s)
        for s in __import__("yaml").safe_load((FIXTURE_ROOT / "snapshots.yaml").read_text(encoding="utf-8"))
    )
    events, warnings, sha256 = import_events_csv(
        FIXTURE_ROOT / "events.source.csv", match=match, snapshots=snapshots, rule_bundle=v5rc_bundle
    )
    assert len(events) == 19
    assert len(warnings) == 1
    assert len(sha256) == 64  # hex sha256


def test_csv_import_is_deterministic(tmp_path, v5rc_bundle):
    match = parse_match(__import__("yaml").safe_load((FIXTURE_ROOT / "match.yaml").read_text(encoding="utf-8")))
    snapshots = tuple(
        parse_snapshot(s)
        for s in __import__("yaml").safe_load((FIXTURE_ROOT / "snapshots.yaml").read_text(encoding="utf-8"))
    )
    events, _, _ = import_events_csv(
        FIXTURE_ROOT / "events.source.csv", match=match, snapshots=snapshots, rule_bundle=v5rc_bundle
    )
    out1 = tmp_path / "events1.yaml"
    out2 = tmp_path / "events2.yaml"
    write_events_yaml(events, out1)
    write_events_yaml(events, out2)
    assert out1.read_bytes() == out2.read_bytes()
    # and matches the committed canonical output exactly.
    assert out1.read_bytes() == (FIXTURE_ROOT / "events.yaml").read_bytes()


def test_csv_import_refuses_on_invalid_enum(tmp_path, v5rc_bundle):
    match = parse_match(__import__("yaml").safe_load((FIXTURE_ROOT / "match.yaml").read_text(encoding="utf-8")))
    snapshots = tuple(
        parse_snapshot(s)
        for s in __import__("yaml").safe_load((FIXTURE_ROOT / "snapshots.yaml").read_text(encoding="utf-8"))
    )
    csv_text = (FIXTURE_ROOT / "events.source.csv").read_text(encoding="utf-8")
    broken = csv_text.replace(",acquire,", ",levitate,", 1)
    assert broken != csv_text
    bad_csv = tmp_path / "events.source.csv"
    bad_csv.write_text(broken, encoding="utf-8")
    with pytest.raises(FromCsvValidationError):
        import_events_csv(bad_csv, match=match, snapshots=snapshots, rule_bundle=v5rc_bundle)


def test_csv_import_refuses_on_invalid_number(tmp_path):
    from vexu_sim.observations.from_csv import CSV_COLUMNS
    import csv as csv_module

    bad_csv = tmp_path / "events.source.csv"
    with bad_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv_module.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        row = {c: "" for c in CSV_COLUMNS}
        row.update(
            record_type="action", id="a_1", robot_ref="r_red_a", period="driver",
            action_type="acquire", video_t_start="not-a-number", video_t_end="unknown",
            region="quadrant_red_1", outcome="success", contested="none",
            confidence="certain", source="floor", object="pin",
        )
        writer.writerow(row)
    with pytest.raises(FromCsvValidationError, match="not a valid number"):
        read_events_csv(bad_csv)


def test_csv_import_refuses_to_emit_when_validation_fails(v5rc_bundle):
    # A roster missing r_blue_a means the fixture CSV's contested_robot_ref/
    # actor_robot_ref references cannot resolve -- the importer must refuse to
    # write anything rather than emit a partially-valid events.yaml.
    robots = [
        dict(robot_ref="r_red_a", alliance="red", team="0001A", size_class="unknown_v5rc",
             visual_key="x", cycle_labeled=True),
    ]
    match_raw = minimal_match(robots=robots)
    snapshots_raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a"])
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in snapshots_raw)
    with pytest.raises(FromCsvValidationError):
        import_events_csv(FIXTURE_ROOT / "events.source.csv", match=match, snapshots=snapshots, rule_bundle=v5rc_bundle)


def test_csv_sha256_verify_detects_mismatch(v5rc_bundle):
    computed = compute_csv_sha256(FIXTURE_ROOT / "events.source.csv")
    assert len(computed) == 64
    with pytest.raises(FromCsvValidationError, match="mismatch"):
        verify_csv_sha256(FIXTURE_ROOT / "events.source.csv", "0" * 64)
    verify_csv_sha256(FIXTURE_ROOT / "events.source.csv", computed)  # no raise


def test_csv_rejects_unrecognized_column(tmp_path):
    bad_csv = tmp_path / "events.source.csv"
    bad_csv.write_text("record_type,id,not_a_real_column\naction,a_1,x\n", encoding="utf-8")
    with pytest.raises(FromCsvValidationError, match="unrecognized column"):
        read_events_csv(bad_csv)

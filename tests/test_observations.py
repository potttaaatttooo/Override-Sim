"""M3A tests: observation schema + tooling. No real match video is reviewed or
labeled anywhere in this file -- see docs/plans/m3-observation-plan.md's M3A/M3B
split and CLAUDE.md's "Manual video review ... begin in M3B" constraint. All
fixtures are synthetic (tests/fixtures/observations/)."""

from __future__ import annotations

from pathlib import Path

import pytest

import shutil

import yaml

from vexu_sim.observations import refs
from vexu_sim.observations.from_csv import (
    ObservationValidationError as FromCsvValidationError,
    compute_csv_sha256,
    import_events_csv,
    import_match_from_csv,
    read_events_csv,
    verify_csv_sha256,
    write_events_yaml,
)
from vexu_sim.observations.loader import (
    ObservationValidationError,
    canonicalize_no_next_action,
    load_match_observation,
    parse_event,
    parse_match,
    parse_snapshot,
    validate_csv_provenance,
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


# =====================================================================================
# M3A corrective pass (commit fef600d review)
# =====================================================================================


def _write_events_csv(csv_path, rows):
    from vexu_sim.observations.from_csv import CSV_COLUMNS
    import csv as csv_module

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv_module.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            full = {c: "" for c in CSV_COLUMNS}
            full.update(row)
            writer.writerow(full)


def _write_match_and_snapshots(match_dir, v5rc_bundle, *, robots=None, sha256=None):
    match_raw = minimal_match(robots=robots)
    match_raw["labeling"]["source_csv_sha256"] = sha256
    robot_refs = [r["robot_ref"] for r in match_raw["roster"]]
    snapshots_raw = minimal_snapshots(v5rc_bundle, robot_refs=robot_refs)
    (match_dir / "match.yaml").write_text(yaml.safe_dump(match_raw, sort_keys=False), encoding="utf-8")
    (match_dir / "snapshots.yaml").write_text(yaml.safe_dump(snapshots_raw, sort_keys=False), encoding="utf-8")
    return match_raw


# --- 1. no_next_action import behavior -----------------------------------------------


def test_canonicalize_marks_terminal_action_no_next_action(v5rc_bundle):
    match, _ = _minimal(v5rc_bundle)
    events = (
        parse_event(action(id="a_1", video_t_start=21.0, video_t_end=22.0,
                            possession_id="r_red_a#1", gap_after="mixed")),
        parse_event(action(id="a_2", video_t_start=23.0, video_t_end=24.0,
                            possession_id="r_red_a#1", gap_after="mixed")),
    )
    canonical = canonicalize_no_next_action(events, match)
    by_id = {e.id: e for e in canonical}
    assert by_id["a_1"].gap_after == "mixed"  # non-terminal: untouched
    assert by_id["a_2"].gap_after == "no_next_action"  # terminal: canonicalized


def test_canonicalize_does_not_touch_non_cycle_labeled_robot(v5rc_bundle):
    match, _ = _minimal(v5rc_bundle)
    events = (parse_event(action(id="a_1", robot_ref="r_blue_a", gap_after=None)),)
    canonical = canonicalize_no_next_action(events, match)
    assert canonical[0].gap_after is None


def test_csv_import_canonicalizes_terminal_action_without_manual_no_next_action(tmp_path, v5rc_bundle):
    match_raw = _write_match_and_snapshots(tmp_path, v5rc_bundle)
    match = parse_match(match_raw)
    snapshots_raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    snapshots = tuple(parse_snapshot(s) for s in snapshots_raw)
    csv_path = tmp_path / "events.source.csv"
    _write_events_csv(csv_path, [
        dict(record_type="action", id="a_1", robot_ref="r_red_a", period="driver",
             action_type="acquire", video_t_start="21.0", video_t_end="22.0",
             region="quadrant_red_1", outcome="success", contested="none",
             confidence="certain", gap_after="mixed", source="floor", object="pin",
             possession_id="r_red_a#1"),
        # terminal Action: the labeler wrote "mixed", not knowing it would be last.
        dict(record_type="action", id="a_2", robot_ref="r_red_a", period="driver",
             action_type="place", video_t_start="23.0", video_t_end="24.0",
             region="quadrant_red_1", outcome="success", contested="none",
             confidence="certain", gap_after="mixed", object="pin",
             target_goal_ref="g_alliance_red_1", stack_height_before="0",
             stack_height_after="1", destabilized_stack="false",
             possession_id="r_red_a#1"),
    ])
    events, warnings, _ = import_events_csv(csv_path, match=match, snapshots=snapshots, rule_bundle=v5rc_bundle)
    by_id = {e.id: e for e in events}
    assert by_id["a_1"].gap_after == "mixed"
    assert by_id["a_2"].gap_after == "no_next_action"


def test_csv_import_rejects_non_terminal_action_manually_labeled_no_next_action(tmp_path, v5rc_bundle):
    match_raw = _write_match_and_snapshots(tmp_path, v5rc_bundle)
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    csv_path = tmp_path / "events.source.csv"
    _write_events_csv(csv_path, [
        # NOT terminal (a_2 follows) but mislabeled no_next_action -- must be rejected.
        dict(record_type="action", id="a_1", robot_ref="r_red_a", period="driver",
             action_type="acquire", video_t_start="21.0", video_t_end="22.0",
             region="quadrant_red_1", outcome="success", contested="none",
             confidence="certain", gap_after="no_next_action", source="floor", object="pin",
             possession_id="r_red_a#1"),
        dict(record_type="action", id="a_2", robot_ref="r_red_a", period="driver",
             action_type="place", video_t_start="23.0", video_t_end="24.0",
             region="quadrant_red_1", outcome="success", contested="none",
             confidence="certain", gap_after="mixed", object="pin",
             target_goal_ref="g_alliance_red_1", stack_height_before="0",
             stack_height_after="1", destabilized_stack="false",
             possession_id="r_red_a#1"),
    ])
    with pytest.raises(FromCsvValidationError, match="no_next_action"):
        import_events_csv(csv_path, match=match, snapshots=snapshots, rule_bundle=v5rc_bundle)


def test_canonicalize_no_next_action_is_deterministic(v5rc_bundle):
    match, _ = _minimal(v5rc_bundle)
    events = (
        parse_event(action(id="a_1", video_t_start=21.0, video_t_end=22.0,
                            possession_id="r_red_a#1", gap_after="mixed")),
        parse_event(action(id="a_2", video_t_start=23.0, video_t_end=24.0,
                            possession_id="r_red_a#1", gap_after="transit")),
    )
    once = canonicalize_no_next_action(events, match)
    twice = canonicalize_no_next_action(once, match)
    assert once == twice


def test_canonicalize_no_next_action_groups_per_robot_and_period(v5rc_bundle):
    robots = [
        dict(robot_ref="r_red_a", alliance="red", team="0001A", size_class="unknown_v5rc",
             visual_key="x", cycle_labeled=True),
        dict(robot_ref="r_red_b", alliance="red", team="0003C", size_class="unknown_v5rc",
             visual_key="x", cycle_labeled=True),
    ]
    match, _ = _minimal(v5rc_bundle, robots=robots)
    events = (
        # r_red_a, autonomous: sole action -> terminal
        parse_event(action(id="a_auto_a", robot_ref="r_red_a", period="autonomous",
                            video_t_start=1.0, video_t_end=2.0, possession_id="r_red_a#1", gap_after="mixed")),
        # r_red_a, driver: two actions -> only the second is terminal
        parse_event(action(id="a_drv_a1", robot_ref="r_red_a", period="driver",
                            video_t_start=21.0, video_t_end=22.0, possession_id="r_red_a#2", gap_after="mixed")),
        parse_event(action(id="a_drv_a2", robot_ref="r_red_a", period="driver",
                            video_t_start=23.0, video_t_end=24.0, possession_id="r_red_a#2", gap_after="mixed")),
        # r_red_b, driver: sole action -> terminal, independent of r_red_a's grouping
        parse_event(action(id="a_drv_b1", robot_ref="r_red_b", period="driver",
                            video_t_start=21.5, video_t_end=22.5, possession_id="r_red_b#1", gap_after="mixed")),
    )
    canonical = {e.id: e for e in canonicalize_no_next_action(events, match)}
    assert canonical["a_auto_a"].gap_after == "no_next_action"
    assert canonical["a_drv_a1"].gap_after == "mixed"
    assert canonical["a_drv_a2"].gap_after == "no_next_action"
    assert canonical["a_drv_b1"].gap_after == "no_next_action"


# --- 2. CSV provenance workflow --------------------------------------------------------


def test_import_match_from_csv_stamps_unset_hash(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    shutil.copy(FIXTURE_ROOT / "events.source.csv", match_dir / "events.source.csv")
    match_raw = yaml.safe_load((FIXTURE_ROOT / "match.yaml").read_text(encoding="utf-8"))
    match_raw["labeling"]["source_csv_sha256"] = None
    (match_dir / "match.yaml").write_text(yaml.safe_dump(match_raw, sort_keys=False), encoding="utf-8")
    shutil.copy(FIXTURE_ROOT / "snapshots.yaml", match_dir / "snapshots.yaml")

    loaded = import_match_from_csv(match_dir, rule_bundle=v5rc_bundle)
    expected_sha = compute_csv_sha256(match_dir / "events.source.csv")
    assert loaded.match.labeling.source_csv_sha256 == expected_sha
    assert (match_dir / "events.yaml").is_file()

    # the hash actually landed on disk, and a normal load now succeeds cleanly.
    on_disk = yaml.safe_load((match_dir / "match.yaml").read_text(encoding="utf-8"))
    assert on_disk["labeling"]["source_csv_sha256"] == expected_sha
    reloaded = load_match_observation(match_dir, rule_bundle=v5rc_bundle)
    assert len(reloaded.events) == len(loaded.events)


def test_import_match_from_csv_leaves_matching_hash_untouched(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    for name in ("match.yaml", "snapshots.yaml", "events.source.csv"):
        shutil.copy(FIXTURE_ROOT / name, match_dir / name)
    before = (match_dir / "match.yaml").read_bytes()
    import_match_from_csv(match_dir, rule_bundle=v5rc_bundle)
    after = (match_dir / "match.yaml").read_bytes()
    assert before == after


def test_import_match_from_csv_rejects_mismatched_hash(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    for name in ("match.yaml", "snapshots.yaml", "events.source.csv"):
        shutil.copy(FIXTURE_ROOT / name, match_dir / name)
    match_raw = yaml.safe_load((match_dir / "match.yaml").read_text(encoding="utf-8"))
    match_raw["labeling"]["source_csv_sha256"] = "0" * 64
    (match_dir / "match.yaml").write_text(yaml.safe_dump(match_raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(FromCsvValidationError, match="mismatch"):
        import_match_from_csv(match_dir, rule_bundle=v5rc_bundle)
    assert not (match_dir / "events.yaml").exists()


def test_load_detects_committed_csv_no_longer_matching_stamped_hash(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    for name in ("match.yaml", "snapshots.yaml", "events.yaml", "events.source.csv"):
        shutil.copy(FIXTURE_ROOT / name, match_dir / name)
    # mutate the committed CSV after the hash was stamped.
    with (match_dir / "events.source.csv").open("a", encoding="utf-8") as f:
        f.write("\n")
    errors = []
    match = parse_match(yaml.safe_load((match_dir / "match.yaml").read_text(encoding="utf-8")))
    validate_csv_provenance(match_dir, match, errors)
    assert any("mismatch" in e for e in errors)


def test_load_detects_missing_hash_when_csv_present(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    for name in ("match.yaml", "snapshots.yaml", "events.yaml", "events.source.csv"):
        shutil.copy(FIXTURE_ROOT / name, match_dir / name)
    match_raw = yaml.safe_load((match_dir / "match.yaml").read_text(encoding="utf-8"))
    match_raw["labeling"]["source_csv_sha256"] = None
    (match_dir / "match.yaml").write_text(yaml.safe_dump(match_raw, sort_keys=False), encoding="utf-8")
    with pytest.raises(ObservationValidationError, match="missing but events.source.csv is present"):
        load_match_observation(match_dir, rule_bundle=v5rc_bundle)


def test_load_detects_stored_hash_with_no_source_csv(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    for name in ("match.yaml", "snapshots.yaml", "events.yaml"):
        shutil.copy(FIXTURE_ROOT / name, match_dir / name)
    # events.source.csv deliberately NOT copied.
    with pytest.raises(ObservationValidationError, match="no events.source.csv is present"):
        load_match_observation(match_dir, rule_bundle=v5rc_bundle)


# --- 3. Midfield reconciliation across periods -----------------------------------------


def test_midfield_reconciliation_autonomous_null_exit_does_not_leak_into_match_end(v5rc_bundle):
    robots = [
        dict(robot_ref="r_red_a", alliance="red", team="0001A", size_class="unknown_v5rc",
             visual_key="x", cycle_labeled=True),
    ]
    match_raw = minimal_match(robots=robots)
    snapshots_raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a"])
    # autonomous_end: robot IS in midfield (occupancy open, null exit).
    snapshots_raw[0]["robots"]["r_red_a"]["in_midfield"] = True
    # match_end: robot is NOT in midfield -- no driver-period occupancy exists.
    snapshots_raw[1]["robots"]["r_red_a"]["in_midfield"] = False
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in snapshots_raw)
    events = (
        parse_event(dict(
            record_type="midfield_occupancy", id="m_1", robot_ref="r_red_a", period="autonomous",
            video_t_enter=2.0, video_t_exit=None, contested_during=False, confidence="certain",
        )),
    )
    report = reconcile(match, snapshots, events, v5rc_bundle)
    assert report.midfield_occupancy["r_red_a@autonomous_end"].status == "match"
    assert report.midfield_occupancy["r_red_a@match_end"].status == "match"


def test_midfield_reconciliation_driver_null_exit_covers_match_end_only(v5rc_bundle):
    robots = [
        dict(robot_ref="r_red_a", alliance="red", team="0001A", size_class="unknown_v5rc",
             visual_key="x", cycle_labeled=True),
    ]
    match_raw = minimal_match(robots=robots)
    snapshots_raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a"])
    snapshots_raw[0]["robots"]["r_red_a"]["in_midfield"] = False  # autonomous: not yet entered
    snapshots_raw[1]["robots"]["r_red_a"]["in_midfield"] = True  # match_end: still inside
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in snapshots_raw)
    events = (
        parse_event(dict(
            record_type="midfield_occupancy", id="m_1", robot_ref="r_red_a", period="driver",
            video_t_enter=35.0, video_t_exit=None, contested_during=False, confidence="certain",
        )),
    )
    report = reconcile(match, snapshots, events, v5rc_bundle)
    assert report.midfield_occupancy["r_red_a@autonomous_end"].status == "match"
    assert report.midfield_occupancy["r_red_a@match_end"].status == "match"


# --- 4. Required-key presence (missing vs explicit null) ------------------------------


def test_loader_visit_video_t_exit_missing_key_is_rejected():
    raw = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=21.0, loader_ref="loader_red_1",
        objects_acquired=0, failed_grabs=0, departs_possession_id=None,
        contested="none", confidence="certain",
    )
    with pytest.raises(ObservationValidationError, match="missing required key 'video_t_exit'"):
        parse_event(raw)


def test_loader_visit_departs_possession_id_missing_key_is_rejected():
    raw = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=21.0, video_t_exit=22.0, loader_ref="loader_red_1",
        objects_acquired=0, failed_grabs=0,
        contested="none", confidence="certain",
    )
    with pytest.raises(ObservationValidationError, match="missing required key 'departs_possession_id'"):
        parse_event(raw)


def test_midfield_occupancy_video_t_exit_missing_key_is_rejected():
    raw = dict(
        record_type="midfield_occupancy", id="m_1", robot_ref="r_red_a", period="driver",
        video_t_enter=21.0, contested_during=False, confidence="certain",
    )
    with pytest.raises(ObservationValidationError, match="missing required key 'video_t_exit'"):
        parse_event(raw)


def test_incident_video_t_end_missing_key_is_rejected():
    raw = dict(
        record_type="incident", id="i_1", robot_ref="r_red_a", period="driver",
        video_t_start=21.0, incident_type="mechanism_stopped", resolution="unresolved",
        confidence="certain",
    )
    with pytest.raises(ObservationValidationError, match="missing required key 'video_t_end'"):
        parse_event(raw)


def test_action_retry_of_missing_key_is_rejected():
    raw = action()
    del raw["retry_of"]
    with pytest.raises(ObservationValidationError, match="missing required key 'retry_of'"):
        parse_event(raw)


def test_state_change_attributed_to_missing_key_is_rejected():
    raw = dict(
        record_type="state_change", id="sc_1", period="driver", video_t=21.0,
        change="stack_toppled", target_goal_ref="g_alliance_red_1",
        stack_height_before=1, stack_height_after=0, confidence="certain",
    )
    with pytest.raises(ObservationValidationError, match="missing required key 'attributed_to'"):
        parse_event(raw)


def test_coverage_unlabeled_windows_missing_key_is_rejected():
    raw = minimal_match()
    del raw["coverage"]["unlabeled_windows"]
    with pytest.raises(ObservationValidationError, match="missing required key 'unlabeled_windows'"):
        parse_match(raw)


def test_goal_snapshot_stack_missing_key_is_rejected(v5rc_bundle):
    raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    del raw[0]["goals"]["g_midfield"]["stack"]
    with pytest.raises(ObservationValidationError, match="missing required key 'stack'"):
        parse_snapshot(raw[0])


def test_explicit_null_still_accepted_for_these_fields(v5rc_bundle):
    # Every field above must still accept an EXPLICIT null -- only an absent key is
    # newly rejected; the unknown-vs-null convention itself is unchanged.
    match, snapshots = _minimal(v5rc_bundle)
    lv = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=21.0, video_t_exit=None, loader_ref="loader_red_1",
        objects_acquired=0, failed_grabs=0, departs_possession_id=None,
        contested="none", confidence="certain",
    )
    mo = dict(
        record_type="midfield_occupancy", id="m_1", robot_ref="r_red_a", period="driver",
        video_t_enter=21.0, video_t_exit=None, contested_during=False, confidence="certain",
    )
    inc = dict(
        record_type="incident", id="i_1", robot_ref="r_red_a", period="driver",
        video_t_start=21.0, video_t_end=None, incident_type="mechanism_stopped",
        resolution="unresolved", confidence="certain",
    )
    sc = dict(
        record_type="state_change", id="sc_1", period="driver", video_t=21.0,
        change="stack_toppled", target_goal_ref="g_alliance_red_1",
        stack_height_before=1, stack_height_after=0, attributed_to=None, confidence="certain",
    )
    events = tuple(parse_event(e) for e in (lv, mo, inc, sc))
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert errors == []


# --- 5. Possession episode id integrity ------------------------------------------------


def test_possession_id_malformed_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(id="a_1", possession_id="not-a-valid-id", gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("not of the form" in e for e in errors)


def test_possession_id_wrong_robot_is_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(id="a_1", robot_ref="r_red_a", possession_id="r_blue_a#1",
                                  gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("belongs to" in e and "not the acting robot" in e for e in errors)


def test_possession_id_closed_episode_cannot_be_reused(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        # opens and closes r_red_a#1
        action(id="a_1", video_t_start=21.0, video_t_end=22.0, possession_id="r_red_a#1", gap_after="mixed"),
        dict(record_type="state_change", id="sc_1", period="driver", video_t=22.5,
             change="object_dropped_in_transit", attributed_to="r_red_a", confidence="certain",
             possession_id="r_red_a#1", object="pin"),
        # tries to reopen the SAME id after it closed.
        action(id="a_2", video_t_start=23.0, video_t_end=24.0, possession_id="r_red_a#1", gap_after="no_next_action"),
    )
    events = tuple(parse_event(e) for e in events)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("reuses or is not greater than" in e for e in errors)


def test_possession_id_must_move_monotonically_forward(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        action(id="a_1", video_t_start=21.0, video_t_end=22.0, possession_id="r_red_a#5", gap_after="mixed"),
        dict(record_type="state_change", id="sc_1", period="driver", video_t=22.5,
             change="object_dropped_in_transit", attributed_to="r_red_a", confidence="certain",
             possession_id="r_red_a#5", object="pin"),
        # #3 < #5 -- not monotonically forward.
        action(id="a_2", video_t_start=23.0, video_t_end=24.0, possession_id="r_red_a#3", gap_after="no_next_action"),
    )
    events = tuple(parse_event(e) for e in events)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("reuses or is not greater than" in e for e in errors)


def test_possession_id_suffix_must_be_positive(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(id="a_1", possession_id="r_red_a#0", gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("positive integer" in e for e in errors)


def test_extending_open_episode_keeps_same_id_no_error(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    # a_003 opens r_red_a#2, a_004 extends it -- already exercised end-to-end by the
    # fixture; re-assert here that no possession-id-integrity error was raised.
    assert loaded is not None


# --- 6. Unique record ids + reference integrity ----------------------------------------


def test_duplicate_action_ids_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        action(id="a_1", video_t_start=21.0, video_t_end=22.0, possession_id="r_red_a#1", gap_after="mixed"),
        action(id="a_1", video_t_start=23.0, video_t_end=24.0, possession_id="r_red_a#1", gap_after="no_next_action"),
    )
    events = tuple(parse_event(e) for e in events)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("duplicate event record id 'a_1'" in e for e in errors)


def test_duplicate_ids_across_record_types_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        parse_event(action(id="dup_1", gap_after="no_next_action")),
        parse_event(dict(
            record_type="loader_visit", id="dup_1", robot_ref="r_red_a", period="driver",
            video_t_enter=21.0, video_t_exit=22.0, loader_ref="loader_red_1",
            objects_acquired=0, failed_grabs=0, departs_possession_id=None,
            contested="none", confidence="certain",
        )),
    )
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("duplicate event record id 'dup_1'" in e for e in errors)


def test_departs_possession_id_must_belong_to_referenced_robot(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        parse_event(dict(
            record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
            video_t_enter=21.0, video_t_exit=22.0, loader_ref="loader_red_1",
            objects_acquired=1, failed_grabs=0, departs_possession_id="r_blue_a#1",
            contested="none", confidence="certain",
        )),
    )
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("belongs to" in e for e in errors)


def test_departs_possession_id_must_name_a_real_episode(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        parse_event(dict(
            record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
            video_t_enter=21.0, video_t_exit=22.0, loader_ref="loader_red_1",
            objects_acquired=1, failed_grabs=0, departs_possession_id="r_red_a#9",
            contested="none", confidence="certain",
        )),
    )
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("does not name a possession episode ever opened" in e for e in errors)


def test_departs_possession_id_unknown_is_allowed(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        parse_event(dict(
            record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
            video_t_enter=21.0, video_t_exit=22.0, loader_ref="loader_red_1",
            objects_acquired=1, failed_grabs=0, departs_possession_id=UNKNOWN,
            contested="none", confidence="certain",
        )),
    )
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert errors == []


def test_loader_linked_acquire_robot_mismatch_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        parse_event(dict(
            record_type="loader_visit", id="lv_1", robot_ref="r_blue_a", period="driver",
            video_t_enter=21.0, video_t_exit=22.0, loader_ref="loader_blue_1",
            objects_acquired=1, failed_grabs=0, departs_possession_id=None,
            contested="none", confidence="certain",
        )),
        parse_event(action(id="a_1", robot_ref="r_red_a", source="loader", loader_visit_id="lv_1",
                            gap_after="no_next_action")),
    )
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("does not match loader_visit" in e and "robot_ref" in e for e in errors)


def test_loader_linked_acquire_period_mismatch_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        parse_event(dict(
            record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="autonomous",
            video_t_enter=1.0, video_t_exit=2.0, loader_ref="loader_red_1",
            objects_acquired=1, failed_grabs=0, departs_possession_id=None,
            contested="none", confidence="certain",
        )),
        parse_event(action(id="a_1", robot_ref="r_red_a", period="driver", source="loader",
                            loader_visit_id="lv_1", gap_after="no_next_action")),
    )
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("does not match loader_visit" in e and "period" in e for e in errors)


def test_loader_linked_acquire_matching_robot_and_period_is_clean(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        parse_event(dict(
            record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
            video_t_enter=20.0, video_t_exit=20.5, loader_ref="loader_red_1",
            objects_acquired=1, failed_grabs=0, departs_possession_id="r_red_a#1",
            contested="none", confidence="certain",
        )),
        parse_event(action(id="a_1", robot_ref="r_red_a", period="driver", source="loader",
                            loader_visit_id="lv_1", possession_id="r_red_a#1", gap_after="no_next_action")),
    )
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert errors == []


# --- 7. Validation audit spot-checks ----------------------------------------------------


def test_synthetic_fixture_still_loads_cleanly_after_corrective_pass(v5rc_bundle):
    loaded = load_match_observation(FIXTURE_ROOT, rule_bundle=v5rc_bundle)
    assert len(loaded.events) == 19
    assert len(loaded.warnings) == 1


# =====================================================================================
# Final M3A validation-hardening pass
# =====================================================================================


# --- 1. Closed-vocabulary / type audit: Snapshot / StackItem / ToggleSnapshot ---------


def test_pin_colors_illegal_color_rejected(v5rc_bundle):
    raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    raw[1]["goals"]["g_midfield"]["stack"] = [{"object": "pin", "colors": ["green", "yellow"]}]
    match, _ = _minimal(v5rc_bundle)
    snapshots = tuple(parse_snapshot(s) for s in raw)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("colors" in e and "invalid" in e for e in errors)


def test_pin_colors_wrong_length_rejected(v5rc_bundle):
    raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    raw[1]["goals"]["g_midfield"]["stack"] = [{"object": "pin", "colors": ["yellow"]}]
    match, _ = _minimal(v5rc_bundle)
    snapshots = tuple(parse_snapshot(s) for s in raw)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("colors" in e and "invalid" in e for e in errors)


def test_colors_on_a_cup_rejected(v5rc_bundle):
    raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    raw[1]["goals"]["g_midfield"]["stack"] = [
        {"object": "cup", "down_face": "opaque", "colors": ["yellow", "yellow"]}
    ]
    match, _ = _minimal(v5rc_bundle)
    snapshots = tuple(parse_snapshot(s) for s in raw)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("colors must be absent when object == 'cup'" in e for e in errors)


def test_down_face_on_a_pin_rejected(v5rc_bundle):
    raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    raw[1]["goals"]["g_midfield"]["stack"] = [
        {"object": "pin", "colors": ["yellow", "yellow"], "down_face": "opaque"}
    ]
    match, _ = _minimal(v5rc_bundle)
    snapshots = tuple(parse_snapshot(s) for s in raw)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("down_face must be absent when object == 'pin'" in e for e in errors)


def test_invalid_toggle_snapshot_confidence_rejected(v5rc_bundle):
    raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    raw[1]["toggles"]["t_red_1"]["confidence"] = "very_sure"
    match, _ = _minimal(v5rc_bundle)
    snapshots = tuple(parse_snapshot(s) for s in raw)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("toggles['t_red_1']" in e.replace('"', "'") and "confidence" in e for e in errors)


def test_snapshot_video_t_nonnumeric_rejected(v5rc_bundle):
    raw = minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"])
    raw[1]["video_t"] = "unknown"
    match, _ = _minimal(v5rc_bundle)
    snapshots = tuple(parse_snapshot(s) for s in raw)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("video_t" in e and "numeric" in e for e in errors)


# --- 2. Action validation ---------------------------------------------------------------


def test_action_video_t_start_nonnumeric_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (parse_event(action(video_t_start="unknown", gap_after="no_next_action")),)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("video_t_start" in e and "numeric" in e for e in errors)


def test_place_invalid_cup_down_face_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = action(
        action_type="place", object="cup", target_goal_ref="g_alliance_red_1",
        stack_height_before=0, stack_height_after=1, destabilized_stack=False,
        cup_down_face="translucent", gap_after="no_next_action", source=None,
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("invalid cup_down_face" in e for e in errors)


def test_descore_invalid_cup_down_face_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="action", id="a_test", action_type="descore", robot_ref="r_red_a",
        period="driver", video_t_start=21.0, video_t_end=22.0, region="quadrant_red_1",
        outcome="success", contested="none", retry_of=None, confidence="certain",
        gap_after="no_next_action", method="obscure", cup_down_face="sideways",
        target_goal_ref="g_alliance_red_1", stack_height_before=0, stack_height_after=1,
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("invalid cup_down_face" in e for e in errors)


def test_irrelevant_field_for_action_type_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    # toggle_ref belongs only to action_type='toggle', not 'acquire'.
    raw = action(toggle_ref="t_red_1", gap_after="no_next_action")
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("toggle_ref must be absent for action_type='acquire'" in e for e in errors)


def test_toggle_action_with_place_field_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="action", id="a_test", action_type="toggle", robot_ref="r_red_a",
        period="driver", video_t_start=21.0, video_t_end=22.0, region="quadrant_red_1",
        outcome="success", contested="none", retry_of=None, confidence="certain",
        gap_after="no_next_action", toggle_ref="t_red_1", state_before="yellow",
        state_after="red", seated_after=True, method="stopped_contact",
        target_goal_ref="g_alliance_red_1",  # belongs to place/descore, not toggle
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("target_goal_ref must be absent for action_type='toggle'" in e for e in errors)


def test_place_fractional_stack_height_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = action(
        action_type="place", object="pin", target_goal_ref="g_alliance_red_1",
        stack_height_before=0, stack_height_after=1.5, destabilized_stack=False,
        gap_after="no_next_action", source=None,
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("must be a (non-fractional) int" in e for e in errors)


def test_place_negative_stack_height_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = action(
        action_type="place", object="pin", target_goal_ref="g_alliance_red_1",
        stack_height_before=-1, stack_height_after=0, destabilized_stack=False,
        gap_after="no_next_action", source=None,
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("must be >= 0" in e for e in errors)


def test_descore_negative_objects_removed_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="action", id="a_test", action_type="descore", robot_ref="r_red_a",
        period="driver", video_t_start=21.0, video_t_end=22.0, region="quadrant_red_1",
        outcome="success", contested="none", retry_of=None, confidence="certain",
        gap_after="no_next_action", method="extract", objects_removed=-2,
        target_goal_ref="g_alliance_red_1", stack_height_before=1, stack_height_after=0,
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("objects_removed" in e and "must be >= 0" in e for e in errors)


# --- 3. Other event types ----------------------------------------------------------------


def test_loader_visit_video_t_enter_nonnumeric_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=UNKNOWN, video_t_exit=22.0, loader_ref="loader_red_1",
        objects_acquired=0, failed_grabs=0, departs_possession_id=None,
        contested="none", confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("video_t_enter" in e and "numeric" in e for e in errors)


def test_loader_visit_exit_before_enter_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=25.0, video_t_exit=20.0, loader_ref="loader_red_1",
        objects_acquired=0, failed_grabs=0, departs_possession_id=None,
        contested="none", confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("must be after video_t_enter" in e for e in errors)


def test_loader_visit_fractional_objects_acquired_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=20.0, video_t_exit=22.0, loader_ref="loader_red_1",
        objects_acquired=1.5, failed_grabs=0, departs_possession_id=None,
        contested="none", confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("objects_acquired" in e and "must be a (non-fractional) int" in e for e in errors)


def test_loader_visit_invalid_objects_types_entry_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="loader_visit", id="lv_1", robot_ref="r_red_a", period="driver",
        video_t_enter=20.0, video_t_exit=22.0, loader_ref="loader_red_1",
        objects_acquired=1, failed_grabs=0, departs_possession_id=None,
        objects_types=["pin", "robot"], contested="none", confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("objects_types entry 'robot'" in e for e in errors)


def test_midfield_occupancy_exit_before_enter_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="midfield_occupancy", id="m_1", robot_ref="r_red_a", period="driver",
        video_t_enter=30.0, video_t_exit=25.0, contested_during=False, confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("must be after video_t_enter" in e for e in errors)


def test_incident_end_before_start_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="incident", id="i_1", robot_ref="r_red_a", period="driver",
        video_t_start=30.0, video_t_end=25.0, incident_type="mechanism_stopped",
        resolution="unresolved", confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("must be after video_t_start" in e for e in errors)


def test_interaction_invalid_subject_region_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="interaction", id="ia_1", actor_robot_ref="r_blue_a",
        subject_robot_ref="r_red_a", video_t_start=21.0, video_t_end=22.0, period="driver",
        interaction_type="sustained_contact", confidence="certain", subject_region="off_field",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("subject_region" in e and "region vocabulary" in e for e in errors)


def test_interaction_end_before_start_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="interaction", id="ia_1", actor_robot_ref="r_blue_a",
        subject_robot_ref="r_red_a", video_t_start=25.0, video_t_end=20.0, period="driver",
        interaction_type="sustained_contact", confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("must be after video_t_start" in e for e in errors)


def test_state_change_invalid_toggle_state_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="state_change", id="sc_1", period="driver", video_t=21.0,
        change="toggle_changed", toggle_ref="t_red_1", state_after="green",
        seated_after=True, attributed_to=None, confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("invalid state_after 'green'" in e for e in errors)


def test_state_change_invalid_seated_after_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="state_change", id="sc_1", period="driver", video_t=21.0,
        change="toggle_changed", toggle_ref="t_red_1", state_after="red",
        seated_after="mostly", attributed_to=None, confidence="certain",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("seated_after" in e for e in errors)


def test_state_change_invalid_possession_object_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        action(id="a_1", video_t_start=21.0, video_t_end=22.0, possession_id="r_red_a#1", gap_after="no_next_action"),
        dict(record_type="state_change", id="sc_1", period="driver", video_t=22.5,
             change="object_dropped_in_transit", attributed_to="r_red_a", confidence="certain",
             possession_id="r_red_a#1", object="robot_arm"),
    )
    events = tuple(parse_event(e) for e in events)
    errors, _ = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("invalid object 'robot_arm'" in e for e in errors)


def test_state_change_video_t_nonnumeric_rejected(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    raw = dict(
        record_type="state_change", id="sc_1", period="driver", video_t="unknown",
        change="object_dropped_in_transit", attributed_to="r_red_a", confidence="certain",
        possession_id="r_red_a#1", object="pin",
    )
    errors, _ = validate_observation_set(match, snapshots, (parse_event(raw),), v5rc_bundle)
    assert any("video_t" in e and "numeric" in e for e in errors)


def test_possession_state_change_wrong_episode_does_not_silently_close(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    events = (
        # opens r_red_a#1, holding a pin
        action(id="a_1", video_t_start=21.0, video_t_end=22.0, possession_id="r_red_a#1", gap_after="mixed"),
        # references a DIFFERENT (never-opened) episode id but the same object type
        dict(record_type="state_change", id="sc_1", period="driver", video_t=22.5,
             change="object_dropped_in_transit", attributed_to="r_red_a", confidence="certain",
             possession_id="r_red_a#9", object="pin"),
        # a later acquire under the ORIGINAL episode must still see it as open --
        # a duplicate-type warning proves r_red_a#1 was never actually closed.
        action(id="a_2", video_t_start=23.0, video_t_end=24.0, possession_id="r_red_a#1", gap_after="no_next_action"),
    )
    events = tuple(parse_event(e) for e in events)
    errors, warnings = validate_observation_set(match, snapshots, events, v5rc_bundle)
    assert any("does not match" in e and "sc_1" in e for e in errors)
    assert any("acquiring object type already held" in w for w in warnings)


# --- 4. Hand-authored match metadata -----------------------------------------------------


def test_roster_cycle_labeled_non_bool_rejected(v5rc_bundle):
    robots = [
        dict(robot_ref="r_red_a", alliance="red", team="0001A", size_class="unknown_v5rc",
             visual_key="x", cycle_labeled="yes"),
    ]
    match, snapshots = _minimal(v5rc_bundle, robots=robots)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("cycle_labeled" in e and "real bool" in e for e in errors)


def test_roster_invalid_alliance_rejected(v5rc_bundle):
    robots = [
        dict(robot_ref="r_red_a", alliance="green", team="0001A", size_class="unknown_v5rc",
             visual_key="x", cycle_labeled=True),
    ]
    match, snapshots = _minimal(v5rc_bundle, robots=robots)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("alliance='green'" in e.replace('"', "'") for e in errors)


def test_period_offsets_missing_key_rejected(v5rc_bundle):
    match_raw = minimal_match()
    del match_raw["video"]["period_offsets"]["driver"]
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("period_offsets keys must be exactly" in e for e in errors)


def test_period_offsets_nonnumeric_value_rejected(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["video"]["period_offsets"]["driver"] = "later"
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("period_offsets['driver']" in e.replace('"', "'") and "numeric" in e for e in errors)


def test_timing_precision_s_must_be_positive(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["video"]["timing_precision_s"] = 0
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("timing_precision_s" in e and "positive" in e for e in errors)


def test_coverage_fully_labeled_non_bool_rejected(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["coverage"]["fully_labeled"] = "yes"
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("fully_labeled" in e and "real bool" in e for e in errors)


def test_unlabeled_window_invalid_period_rejected(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["coverage"]["unlabeled_windows"] = [
        {"period": "warmup", "t_start": 0.0, "t_end": 5.0, "reason": "camera off"}
    ]
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("unlabeled_windows: invalid period 'warmup'" in e for e in errors)


def test_unlabeled_window_end_before_start_rejected(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["coverage"]["unlabeled_windows"] = [
        {"period": "driver", "t_start": 10.0, "t_end": 5.0, "reason": "camera off"}
    ]
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("t_end (5.0) must be after t_start (10.0)" in e for e in errors)


def test_labeling_pass_id_must_be_positive(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["labeling"]["pass_id"] = 0
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("pass_id" in e and "positive int" in e for e in errors)


def test_labeling_minutes_spent_nonnegative(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["labeling"]["minutes_spent"] = -5
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("minutes_spent" in e and "nonnegative int" in e for e in errors)


def test_labeling_selection_stratum_must_be_approved_vocabulary(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["labeling"]["selection_stratum"] = "made_up_stratum"
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("selection_stratum" in e for e in errors)


def test_official_result_negative_total_rejected(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["official_result"]["red_total"] = -1
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("red_total" in e and "nonnegative int" in e for e in errors)


def test_official_result_awp_non_bool_rejected(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["official_result"]["awp"]["red"] = "yes"
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("awp['red']" in e.replace('"', "'") and "real bool" in e for e in errors)


def test_official_result_autonomous_bonus_to_invalid_rejected(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["official_result"]["autonomous_bonus_to"] = "purple"
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("autonomous_bonus_to" in e for e in errors)


def test_official_result_violations_autonomous_invalid_entry_rejected(v5rc_bundle):
    match_raw = minimal_match()
    match_raw["official_result"]["violations_autonomous"] = ["purple"]
    match = parse_match(match_raw)
    snapshots = tuple(parse_snapshot(s) for s in minimal_snapshots(v5rc_bundle, robot_refs=["r_red_a", "r_blue_a"]))
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert any("violations_autonomous" in e for e in errors)


def test_valid_metadata_produces_no_metadata_errors(v5rc_bundle):
    match, snapshots = _minimal(v5rc_bundle)
    errors, _ = validate_observation_set(match, snapshots, (), v5rc_bundle)
    assert errors == []


# --- 5. Import write safety --------------------------------------------------------------


def test_import_match_from_csv_missing_hash_key_writes_nothing(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    for name in ("snapshots.yaml", "events.source.csv"):
        shutil.copy(FIXTURE_ROOT / name, match_dir / name)
    match_text = (FIXTURE_ROOT / "match.yaml").read_text(encoding="utf-8")
    # Remove the entire "source_csv_sha256: ..." line -- the key is not merely
    # null, it is completely absent from the file.
    lines = [ln for ln in match_text.splitlines(keepends=True) if "source_csv_sha256" not in ln]
    stripped_text = "".join(lines)
    assert "source_csv_sha256" not in stripped_text
    (match_dir / "match.yaml").write_text(stripped_text, encoding="utf-8")

    with pytest.raises(FromCsvValidationError, match="source_csv_sha256"):
        import_match_from_csv(match_dir, rule_bundle=v5rc_bundle)

    assert not (match_dir / "events.yaml").exists()
    assert (match_dir / "match.yaml").read_text(encoding="utf-8") == stripped_text


def test_import_match_from_csv_still_stamps_valid_null_hash(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    shutil.copy(FIXTURE_ROOT / "events.source.csv", match_dir / "events.source.csv")
    shutil.copy(FIXTURE_ROOT / "snapshots.yaml", match_dir / "snapshots.yaml")
    match_raw = yaml.safe_load((FIXTURE_ROOT / "match.yaml").read_text(encoding="utf-8"))
    match_raw["labeling"]["source_csv_sha256"] = None
    (match_dir / "match.yaml").write_text(yaml.safe_dump(match_raw, sort_keys=False), encoding="utf-8")

    loaded = import_match_from_csv(match_dir, rule_bundle=v5rc_bundle)
    assert loaded.match.labeling.source_csv_sha256 == compute_csv_sha256(match_dir / "events.source.csv")
    assert (match_dir / "events.yaml").is_file()


def test_import_match_from_csv_still_leaves_matching_hash_untouched(tmp_path, v5rc_bundle):
    match_dir = tmp_path / "synth"
    match_dir.mkdir()
    for name in ("match.yaml", "snapshots.yaml", "events.source.csv"):
        shutil.copy(FIXTURE_ROOT / name, match_dir / name)
    before = (match_dir / "match.yaml").read_bytes()
    import_match_from_csv(match_dir, rule_bundle=v5rc_bundle)
    assert (match_dir / "match.yaml").read_bytes() == before

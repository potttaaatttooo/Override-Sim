from pathlib import Path

import pytest

from vexu_sim.rules import RuleValidationError, load_rule_bundle
from vexu_sim.sources import load_sources

DATA_ROOT = Path(__file__).parent.parent / "data"


@pytest.fixture(scope="module")
def sources():
    return load_sources(DATA_ROOT)


def test_v5rc_bundle_loads(sources):
    bundle = load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)
    assert bundle.manual_version == "v1.1"
    assert bundle.program == "v5rc"
    assert "vexu_overlay" not in bundle.data
    assert bundle.data["scoring"]["point_values"]["scored_pin_half_yellow"]["points"] == 10


def test_vexu_bundle_loads_and_composes_overlay(sources):
    bundle = load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)
    assert bundle.program == "vexu"
    assert "vexu_overlay" in bundle.data
    # base sections are still present and untouched -- composition does not deep-merge
    assert bundle.data["scoring"]["point_values"]["scored_pin_half_yellow"]["points"] == 10
    # overlay-only data is reachable
    assert bundle.data["vexu_overlay"]["robot_sizes"]["robot_a_max_inches"] == [24, 24, 24]
    assert bundle.data["vexu_overlay"]["robot_sizes"]["robot_b_max_inches"] == [15, 15, 15]


def test_vexu_overlay_reports_overridden_rule_ids_matching_manifest(sources):
    bundle = load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)
    expected = bundle.data["vexu_overlay"]["overrides_base_rule_ids"]
    assert bundle.overridden_rule_ids == expected
    # a human-reviewable spot check against Section 6: these rule IDs are genuinely
    # ones VEX U changes the effective meaning of.
    assert "SC7" in bundle.overridden_rule_ids  # VUG5 changes autonomous bonus evaluation
    assert "SC8" in bundle.overridden_rule_ids  # VUG6 replaces the AWP criteria entirely
    assert "SG2a" in bundle.overridden_rule_ids  # flagged applicability question, tracked either way


def test_v5rc_bundle_has_no_overridden_rule_ids(sources):
    bundle = load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)
    assert bundle.overridden_rule_ids == []


def test_rejects_unknown_program(sources):
    with pytest.raises(RuleValidationError, match="program must be one of"):
        load_rule_bundle(DATA_ROOT, "v1.1", "vurc-typo", sources)


def test_rejects_unknown_version(sources):
    with pytest.raises(RuleValidationError, match="no rule bundle directory"):
        load_rule_bundle(DATA_ROOT, "v9.9", "v5rc", sources)


def test_every_rule_datum_has_a_resolving_source(sources):
    # load_rule_bundle raises on any unresolved citation; loading both bundles cleanly
    # is itself the proof that every datum resolves. This test also spot-checks that
    # citations are actually present (not silently absent) in a few known-nontrivial spots.
    v5rc = load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)
    vexu = load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)

    assert v5rc.data["scoring"]["autonomous_bonus_evaluation"]["sources"]
    assert vexu.data["vexu_overlay"]["autonomous_bonus_scoring"]["sources"]
    # the qna:3188-sourced datum must actually cite it, not just cite the manual
    refs = [c["ref"] for c in vexu.data["vexu_overlay"]["autonomous_bonus_scoring"]["sources"]]
    assert "qna:3188" in refs


def test_field_inventory_matches_manual_field_overview(sources):
    bundle = load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)
    inventory = bundle.data["field"]["inventory"]

    cups = inventory["cups"]
    assert cups["total"] == 56
    assert sum(cups["breakdown"].values()) == cups["total"]

    pins = inventory["pins"]
    assert pins["total"] == 63
    assert sum(pins["breakdown"].values()) == pins["total"]

    goals = inventory["goals"]
    assert goals["total"] == 9
    assert sum(goals["breakdown"].values()) == goals["total"]

    assert inventory["toggles"]["total"] == 4
    assert inventory["loaders"]["total"] == 4


def test_bad_bundle_with_empty_sources_list_is_rejected(tmp_path, sources):
    # Construct a minimal malformed bundle: a datum with an empty sources list must be
    # rejected rather than silently accepted as "no citation needed".
    bad_root = tmp_path / "data"
    version_dir = bad_root / "rules" / "override" / "v1.1"
    version_dir.mkdir(parents=True)
    (bad_root / "sources").mkdir(parents=True)
    (bad_root / "sources" / "manuals.yaml").write_text("[]", encoding="utf-8")

    for name in ["meta", "field", "robot_limits"]:
        (version_dir / f"{name}.yaml").write_text("{}", encoding="utf-8")
    (version_dir / "periods.yaml").write_text("{}", encoding="utf-8")
    (version_dir / "scoring.yaml").write_text(
        "some_datum:\n  points: 5\n  sources: []\n", encoding="utf-8"
    )

    empty_sources = load_sources(bad_root)
    with pytest.raises(RuleValidationError, match="empty sources"):
        load_rule_bundle(bad_root, "v1.1", "v5rc", empty_sources)


def test_point_values_identical_across_programs(sources):
    v5rc = load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)
    vexu = load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)
    assert v5rc.point_values == vexu.point_values
    assert v5rc.point_values["scored_pin_half_alliance_colored"]["points"] == 5
    assert v5rc.point_values["autonomous_bonus"]["tie_points_each"] == 6


def test_autonomous_bonus_includes_midfield_is_program_specific(sources):
    v5rc = load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)
    vexu = load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)
    assert v5rc.autonomous_bonus_includes_midfield is False
    assert vexu.autonomous_bonus_includes_midfield is True


def test_awp_requirements_differ_between_programs(sources):
    v5rc = load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)
    vexu = load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)

    v5rc_req = v5rc.awp_requirements
    vexu_req = vexu.awp_requirements
    assert v5rc_req != vexu_req

    assert v5rc_req.min_pins_scored == 7
    assert v5rc_req.min_qualifying_goals == 3
    assert v5rc_req.min_pins_per_qualifying_goal == 2
    assert v5rc_req.excludes_opposing_side_of_autonomous_line is True
    assert v5rc_req.perimeter_contact_forbidden is True
    assert v5rc_req.requires_robot_in_midfield is False

    assert vexu_req.min_pins_scored == 12
    assert vexu_req.min_qualifying_goals == 4
    assert vexu_req.min_pins_per_qualifying_goal == 2
    assert vexu_req.excludes_opposing_side_of_autonomous_line is True
    assert vexu_req.perimeter_contact_forbidden is True
    assert vexu_req.requires_robot_in_midfield is True


def test_period_seconds_effective_view_hides_overlay_storage(sources):
    v5rc = load_rule_bundle(DATA_ROOT, "v1.1", "v5rc", sources)
    vexu = load_rule_bundle(DATA_ROOT, "v1.1", "vexu", sources)
    assert v5rc.period_seconds("autonomous") == 15
    assert v5rc.period_seconds("driver_controlled") == 105
    assert vexu.period_seconds("autonomous") == 30
    assert vexu.period_seconds("driver_controlled") == 90


def test_bad_bundle_citing_superseded_source_is_rejected(tmp_path):
    from vexu_sim.sources import Source, SourceRegistry

    bad_root = tmp_path / "data"
    version_dir = bad_root / "rules" / "override" / "v1.1"
    version_dir.mkdir(parents=True)

    for name in ["meta", "field", "robot_limits", "periods"]:
        (version_dir / f"{name}.yaml").write_text("{}", encoding="utf-8")
    (version_dir / "scoring.yaml").write_text(
        "some_datum:\n  points: 5\n  sources: [{ref: 'qna:fake-superseded'}]\n",
        encoding="utf-8",
    )

    fake_registry = SourceRegistry(
        {
            "qna:fake-superseded": Source(
                id="qna:fake-superseded",
                source_type="q_and_a",
                program="v5rc",
                status="superseded",
                applies_to_manual_versions=["1.1"],
                raw={},
            )
        }
    )
    with pytest.raises(RuleValidationError):
        load_rule_bundle(bad_root, "v1.1", "v5rc", fake_registry)

from datetime import date
from pathlib import Path

import pytest
import yaml

from vexu_sim.sources import Source, SourceValidationError, load_sources, validate_empirical_program

DATA_ROOT = Path(__file__).parent.parent / "data"


def test_manuals_loaded():
    sources = load_sources(DATA_ROOT)
    manual = sources.get("manual:v1.1")
    assert manual.source_type == "manual"
    assert manual.program == "both"
    assert manual.applies_to_manual_versions == ["1.1"]
    assert manual.status == "active"


def test_qna_3188_loaded_verbatim_with_expected_fields():
    sources = load_sources(DATA_ROOT)
    q = sources.get("qna:3188")
    assert q.source_type == "q_and_a"
    assert q.program == "both"
    assert q.status == "active"
    assert "1.1" in q.applies_to_manual_versions
    assert set(q.raw["rule_ids"]) >= {"SC7", "VUG5"}
    # spot-check the verbatim holding contains the actual controlling sentence, not a paraphrase
    assert "Robots do not receive credit for being in the Midfield" in q.raw["holding"]
    assert "VUG5" in q.raw["holding"]


def test_qna_3134_loaded():
    sources = load_sources(DATA_ROOT)
    q = sources.get("qna:3134")
    assert q.program == "vexu"
    assert "VUG4" in q.raw["rule_ids"]


def test_released_and_effective_dates_are_independent():
    with (DATA_ROOT / "sources" / "manuals.yaml").open(encoding="utf-8") as f:
        records = yaml.safe_load(f)
    v11 = next(r for r in records if r["id"] == "manual:v1.1")
    assert v11["released"] == date(2026, 8, 6)
    assert v11["effective"] == date(2026, 8, 13)
    assert v11["released"] != v11["effective"]


def test_manual_sha256_matches_committed_pdf():
    import hashlib

    pdf_path = Path(__file__).parent.parent / "docs" / "manuals" / "override-v1.1.pdf"
    assert pdf_path.is_file(), "committed manual PDF is missing"
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    sources = load_sources(DATA_ROOT)
    manual = sources.get("manual:v1.1")
    assert manual.raw["sha256"] == digest


def test_resolve_rejects_unknown_ref():
    sources = load_sources(DATA_ROOT)
    with pytest.raises(SourceValidationError):
        sources.resolve({"ref": "manual:v9.9"})


def test_resolve_rejects_superseded_source():
    sources = load_sources(DATA_ROOT)
    # Synthesize a superseded source to test the resolver's status check without
    # depending on any real ruling actually being superseded yet.
    sources._sources["qna:9999-fake-superseded"] = Source(
        id="qna:9999-fake-superseded",
        source_type="q_and_a",
        program="vexu",
        status="superseded",
        applies_to_manual_versions=["1.1"],
        raw={},
    )
    with pytest.raises(SourceValidationError, match="not active"):
        sources.resolve({"ref": "qna:9999-fake-superseded"})


def test_resolve_rejects_inapplicable_manual_version():
    sources = load_sources(DATA_ROOT)
    with pytest.raises(SourceValidationError, match="does not declare applicability"):
        sources.resolve({"ref": "qna:3188"}, manual_version="9.9")


def test_resolve_accepts_applicable_manual_version():
    sources = load_sources(DATA_ROOT)
    source = sources.resolve({"ref": "qna:3188"}, manual_version="1.1")
    assert source.id == "qna:3188"


@pytest.mark.parametrize("program", ["v5rc", "vexu", "both"])
def test_program_both_accepted_on_source_records(program):
    # Sources may legitimately claim v5rc, vexu, or both (see CLAUDE.md "Program tagging").
    sources = load_sources(DATA_ROOT)
    assert sources.get("manual:v1.1").program in {"v5rc", "vexu", "both"}
    if program == "both":
        assert sources.get("manual:v1.1").program == "both"


@pytest.mark.parametrize("program", ["v5rc", "vexu"])
def test_validate_empirical_program_accepts_v5rc_and_vexu(program):
    validate_empirical_program(program)  # must not raise


def test_validate_empirical_program_rejects_both():
    with pytest.raises(SourceValidationError, match="never 'both'"):
        validate_empirical_program("both")

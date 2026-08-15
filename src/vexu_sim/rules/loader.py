"""Load, compose, and validate versioned rule bundles.

No game logic lives here (see CLAUDE.md) -- this module only loads YAML, composes base +
VEX U overlay, and validates that every rule datum resolves to an official source.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

import yaml

from vexu_sim.sources import SourceRegistry, SourceValidationError

from .models import RuleBundle

BASE_RULE_FILES = ["meta", "periods", "scoring", "field", "robot_limits"]
VALID_PROGRAMS = frozenset({"v5rc", "vexu"})


class RuleValidationError(Exception):
    """Raised when rule data is malformed or a citation fails to resolve.

    Wraps SourceValidationError (via `raise ... from`) so callers of this module only
    need to catch one exception type for any rule-loading failure, including failures
    that originate in citation resolution.
    """


def _iter_citation_lists(node: Any, path: str = "") -> Iterator[tuple[str, list[dict]]]:
    """Walk a loaded YAML tree, yielding (path, citation_list) for every dict node that
    carries a "sources" (list) or "source" (single dict, normalized to a list) key.

    This is the only place that knows the rule-data citation convention described in
    CLAUDE.md ("Provenance convention"): a datum is citable if it has a sources/source key.
    """
    if isinstance(node, dict):
        if "sources" in node and isinstance(node["sources"], list):
            yield path, node["sources"]
        elif "source" in node and isinstance(node["source"], dict):
            yield path, [node["source"]]
        for key, value in node.items():
            yield from _iter_citation_lists(value, f"{path}.{key}" if path else key)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _iter_citation_lists(item, f"{path}[{index}]")


def _manual_version_for_sources(bundle_version: str) -> str:
    """Rule bundle directories are named 'v1.1'; source records' manual_version is '1.1'."""
    return bundle_version[1:] if bundle_version.startswith("v") else bundle_version


def load_rule_bundle(
    data_root: Path,
    version: str,
    program: str,
    sources: SourceRegistry,
) -> RuleBundle:
    """Load the rule bundle for `version` (e.g. "v1.1") and `program` ("v5rc" or "vexu"),
    composing the VEX U overlay on top of the base bundle when program == "vexu", and
    validating that every rule datum resolves to an active, applicable official source.
    """
    if program not in VALID_PROGRAMS:
        raise RuleValidationError(
            f"program must be one of {sorted(VALID_PROGRAMS)}, got {program!r}"
        )

    version_dir = data_root / "rules" / "override" / version
    if not version_dir.is_dir():
        raise RuleValidationError(f"no rule bundle directory for version {version!r}: {version_dir}")

    base_data: dict[str, Any] = {}
    for name in BASE_RULE_FILES:
        file_path = version_dir / f"{name}.yaml"
        if not file_path.is_file():
            raise RuleValidationError(f"missing base rule file: {file_path}")
        with file_path.open(encoding="utf-8") as f:
            base_data[name] = yaml.safe_load(f)

    overridden_rule_ids: list[str] = []
    composed: dict[str, Any] = base_data
    if program == "vexu":
        overlay_path = version_dir / "vexu.yaml"
        if not overlay_path.is_file():
            raise RuleValidationError(f"missing VEX U overlay file: {overlay_path}")
        with overlay_path.open(encoding="utf-8") as f:
            overlay_data = yaml.safe_load(f)
        overridden_rule_ids = list(overlay_data.get("overrides_base_rule_ids", []))
        composed = {**base_data, "vexu_overlay": overlay_data}

    manual_version = _manual_version_for_sources(version)
    for section_name, section_data in composed.items():
        for datum_path, citations in _iter_citation_lists(section_data):
            if not citations:
                raise RuleValidationError(
                    f"{section_name}.{datum_path} has an empty sources/source list"
                )
            for ref in citations:
                try:
                    sources.resolve(ref, manual_version=manual_version)
                except SourceValidationError as exc:
                    raise RuleValidationError(
                        f"{section_name}.{datum_path}: {exc}"
                    ) from exc

    return RuleBundle(
        manual_version=version,
        program=program,
        data=composed,
        overridden_rule_ids=overridden_rule_ids,
    )

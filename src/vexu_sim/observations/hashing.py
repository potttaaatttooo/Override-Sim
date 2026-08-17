"""A tiny shared SHA-256 helper for `events.source.csv` provenance.

Factored out of `from_csv.py` so `loader.py` can verify a committed CSV's hash
against `match.labeling.source_csv_sha256` without an import cycle: `from_csv.py`
already imports from `loader.py` (it reuses `parse_event`/`validate_observation_set`),
so `loader.py` cannot import back from `from_csv.py`. Both modules import this one.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


class HashMismatchError(Exception):
    """Raised when a committed CSV's bytes do not match an expected SHA-256."""


def compute_csv_sha256(csv_path: Path) -> str:
    return hashlib.sha256(csv_path.read_bytes()).hexdigest()


def verify_csv_sha256(csv_path: Path, expected: Optional[str]) -> None:
    """Re-hash the committed CSV and compare against `expected`. No-op if `expected`
    is None (nothing to verify against). Raises HashMismatchError on a mismatch --
    a mismatch is always a validation error, never a warning (§R.2)."""
    if expected is None:
        return
    actual = compute_csv_sha256(csv_path)
    if actual != expected:
        raise HashMismatchError(
            f"{csv_path}: source_csv_sha256 mismatch -- expected {expected}, computed {actual}"
        )

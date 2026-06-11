"""The two schema directories must not drift.

ARCHITECTURE.md: schemas live in ``src/aether_forge/schemas/`` (packaged)
and ``schemas/`` (top level — "kept in sync"). That sync was previously
manual and had drifted: four v0.22/v0.23 runtime schemas existed only in
the packaged copy and ``migration-contract.schema.json`` differed between
the two. This test makes the claim machine-checked in both directions —
the same pattern the TS SDK uses for its generated-types drift gate.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGED = REPO_ROOT / "src" / "aether_forge" / "schemas"
TOP_LEVEL = REPO_ROOT / "schemas"


def _schema_files(root: Path) -> dict[str, Path]:
    return {
        str(path.relative_to(root)): path
        for path in sorted(root.rglob("*.schema.json"))
    }


def test_every_packaged_schema_exists_at_top_level() -> None:
    packaged = _schema_files(PACKAGED)
    top_level = _schema_files(TOP_LEVEL)
    missing = sorted(set(packaged) - set(top_level))
    assert not missing, f"schemas missing from top-level schemas/: {missing}"


def test_every_top_level_schema_exists_in_package() -> None:
    packaged = _schema_files(PACKAGED)
    top_level = _schema_files(TOP_LEVEL)
    missing = sorted(set(top_level) - set(packaged))
    assert not missing, f"schemas missing from src/aether_forge/schemas/: {missing}"


def test_schema_contents_are_identical() -> None:
    packaged = _schema_files(PACKAGED)
    top_level = _schema_files(TOP_LEVEL)
    drifted = [
        rel
        for rel in sorted(set(packaged) & set(top_level))
        if json.loads(packaged[rel].read_text(encoding="utf8"))
        != json.loads(top_level[rel].read_text(encoding="utf8"))
    ]
    assert not drifted, f"schema content drift between the two directories: {drifted}"

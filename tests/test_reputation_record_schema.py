"""Schema conformance for reputation-record.json (docs/specs/agent-reputation.md).

Parametrizes over the shared fixtures in ``tests/fixtures/reputation-records/``
— the same files the TypeScript suite (``sdk-ts/test/reputation-record.test.ts``)
validates, keeping the two validators in cross-language agreement, mirroring the
planner-output conformance pattern.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = (
    REPO_ROOT / "src" / "aether_forge" / "schemas" / "artifacts" / "reputation-record.schema.json"
)
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "reputation-records"

VALID_FIXTURES = ["v0-runtime-record.json", "v1-extended-record.json"]
INVALID_FIXTURES = ["invalid-score-out-of-range.json"]


def _load(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf8"))


@pytest.fixture(scope="module")
def validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


@pytest.mark.parametrize("fixture_name", VALID_FIXTURES)
def test_valid_records_pass(validator: Draft202012Validator, fixture_name: str) -> None:
    validator.validate(_load(fixture_name))


@pytest.mark.parametrize("fixture_name", INVALID_FIXTURES)
def test_invalid_records_fail(validator: Draft202012Validator, fixture_name: str) -> None:
    with pytest.raises(ValidationError):
        validator.validate(_load(fixture_name))


def test_packaged_and_top_level_schema_copies_match() -> None:
    """The repo keeps schemas/ and src/aether_forge/schemas/ in sync."""
    top_level = REPO_ROOT / "schemas" / "artifacts" / "reputation-record.schema.json"
    assert json.loads(top_level.read_text(encoding="utf8")) == json.loads(
        SCHEMA_PATH.read_text(encoding="utf8")
    )


def test_v0_record_from_default_scorer_shape_is_forward_compatible(
    validator: Draft202012Validator,
) -> None:
    """A minimal v0 record (no extension blocks) must stay valid so the
    runtime scorer's output never needs the RFC extensions to validate."""
    record = _load("v0-runtime-record.json")
    for extension_block in ("confidence", "window", "identity", "claims", "publication"):
        record.pop(extension_block, None)
    validator.validate(record)

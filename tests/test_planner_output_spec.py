"""Cross-language conformance for the planner-output spec (Sprint 3.1 / FP-1).

Runs every fixture under ``tests/fixtures/planner-outputs/`` through the
Python reference parser (``aether_forge.planner._extract_json``) and asserts
the result matches the fixture's ``expected`` block. The TypeScript SDK's
``sdk-ts/test/conformance.test.ts`` runs the same fixtures against
``parsePlannerOutput`` and asserts identical results — both implementations
MUST agree on every case or the spec at ``docs/specs/planner-output.md`` has
drifted.

Adding a fixture is a single-step change: drop a JSON file in
``tests/fixtures/planner-outputs/``. This test discovers them automatically
via Glob; the TypeScript test does the same. CI runs both jobs as a gate on
any schema or parser change.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.planner import PlannerParseError, _extract_json

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "planner-outputs"


def _discover_fixtures() -> list[tuple[str, dict]]:
    """Load every fixture as ``(name, data)`` pairs. Skips README.md."""
    fixtures: list[tuple[str, dict]] = []
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf8"))
        fixtures.append((path.stem, data))
    return fixtures


FIXTURES = _discover_fixtures()
assert FIXTURES, f"no fixtures found at {FIXTURE_DIR} — did the discovery glob change?"


@pytest.mark.parametrize("name,fixture", FIXTURES, ids=[name for name, _ in FIXTURES])
def test_python_reference_parser_matches_fixture(name: str, fixture: dict) -> None:
    """Drive ``_extract_json`` with the fixture input; compare to ``expected``.

    ``expected.outcome`` is either ``"parsed"`` (assert equality with the
    ``value`` field) or ``"parse-failure"`` (assert ``PlannerParseError`` is
    raised). Any mismatch is a contract violation.
    """
    raw_input = fixture["input"]
    expected = fixture["expected"]
    if expected["outcome"] == "parsed":
        assert _extract_json(raw_input) == expected["value"], (
            f"fixture {name!r}: parsed value does not match expected"
        )
    elif expected["outcome"] == "parse-failure":
        with pytest.raises(PlannerParseError):
            _extract_json(raw_input)
    else:
        raise AssertionError(
            f"fixture {name!r}: unknown outcome {expected['outcome']!r}; "
            "spec only defines 'parsed' and 'parse-failure'"
        )


def test_fixture_discovery_finds_all_documented_cases() -> None:
    """Tripwire: if the fixture suite is empty or shrinks unexpectedly,
    the conformance gate is meaningless. Pin the minimum count so a
    careless deletion is caught immediately."""
    assert len(FIXTURES) >= 13, (
        f"expected at least 13 fixtures (the v0.23.0 baseline), found {len(FIXTURES)}. "
        "If you removed a fixture intentionally, lower the threshold and document why."
    )


def test_every_fixture_has_required_shape() -> None:
    """Pin the fixture format so authors don't drift the contract over time."""
    for name, fixture in FIXTURES:
        assert "description" in fixture, f"{name}: missing 'description'"
        assert "input" in fixture, f"{name}: missing 'input'"
        assert "expected" in fixture, f"{name}: missing 'expected'"
        outcome = fixture["expected"].get("outcome")
        assert outcome in {"parsed", "parse-failure"}, (
            f"{name}: outcome must be 'parsed' or 'parse-failure', got {outcome!r}"
        )
        if outcome == "parsed":
            assert "value" in fixture["expected"], (
                f"{name}: outcome=parsed requires 'value' in expected block"
            )

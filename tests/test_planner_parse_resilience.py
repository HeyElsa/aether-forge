"""Verify PromptDrivenPlanner survives messy real-world LLM output.

Sprint 1.1 (FP-1): the in-tree parser previously only stripped a single
``` fence. Reasoning preambles, trailing prose, mid-JSON truncation, and
double-fenced responses all silently triggered the heuristic fallback
with no audit trail. These tests pin the new behavior:

- preambles, trailing prose, and code fences all parse cleanly,
- unparseable responses STILL fall back, but now record a structured
  ``last_planner_parse_failure`` event on the session state,
- empty / model-error / parse-exception cases each emit a distinct ``kind``
  so an operator can grep for silent regressions in replays.
"""

from __future__ import annotations

from pathlib import Path

from aether_forge.crypto import MockCryptoExecutionRouter
from aether_forge.models import StaticPlanningModel
from aether_forge.planner import (
    PlannerParseError,
    PromptDrivenPlanner,
    _extract_json,
)
from aether_forge.runtime import RuntimeSession, StepKind, load_artifact_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def _planner_with_response(response: str) -> PromptDrivenPlanner:
    return PromptDrivenPlanner(model=StaticPlanningModel(response))


def _fresh_session() -> RuntimeSession:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    return RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=_planner_with_response("{}"),  # unused; planner is provided per-test
        execution_router=MockCryptoExecutionRouter(),
        scenario_inputs={"basisBps": 25},
    )


# ---------------------------------------------------------------------------
# _extract_json — the new helper
# ---------------------------------------------------------------------------


def test_extract_json_strips_unfenced_payload() -> None:
    assert _extract_json('{"steps": []}') == {"steps": []}


def test_extract_json_strips_json_fence() -> None:
    payload = "```json\n{\"steps\": [1, 2]}\n```"
    assert _extract_json(payload) == {"steps": [1, 2]}


def test_extract_json_strips_bare_fence() -> None:
    payload = "```\n{\"steps\": []}\n```"
    assert _extract_json(payload) == {"steps": []}


def test_extract_json_recovers_from_reasoning_preamble() -> None:
    payload = (
        "Let me think through this carefully. The session needs a basis read.\n"
        'Here is my plan: {"steps": [{"kind": "reason", "description": "go"}]}'
    )
    parsed = _extract_json(payload)
    assert isinstance(parsed, dict)
    assert parsed["steps"][0]["description"] == "go"


def test_extract_json_recovers_from_trailing_prose() -> None:
    payload = '{"steps": [{"kind": "reason", "description": "go"}]}\n\nLet me know if you need anything else.'
    parsed = _extract_json(payload)
    assert parsed["steps"][0]["kind"] == "reason"


def test_extract_json_recovers_from_double_fenced_response() -> None:
    payload = (
        "Some commentary first.\n"
        "```json\n"
        '{"steps": [{"kind": "reason", "description": "first"}]}\n'
        "```\n"
        "More commentary."
    )
    parsed = _extract_json(payload)
    assert parsed["steps"][0]["description"] == "first"


def test_extract_json_handles_braces_inside_strings() -> None:
    payload = 'Note: {{handlebars}} are fine.\n{"steps": [{"description": "use {{var}}"}]}'
    parsed = _extract_json(payload)
    assert parsed["steps"][0]["description"] == "use {{var}}"


def test_extract_json_raises_on_plain_text() -> None:
    try:
        _extract_json("I cannot help with that request.")
    except PlannerParseError as error:
        assert "could not recover" in str(error).lower()
    else:
        raise AssertionError("expected PlannerParseError")


def test_extract_json_raises_on_truncated_object() -> None:
    """Mid-JSON truncation (the most common provider failure mode) must raise
    so the planner records ``parse-failure`` rather than silently falling back."""
    try:
        _extract_json('{"steps": [{"kind": "reason", "description": "tru')
    except PlannerParseError:
        pass
    else:
        raise AssertionError("expected PlannerParseError on truncated JSON")


def test_extract_json_raises_on_empty_string() -> None:
    try:
        _extract_json("   \n  ")
    except PlannerParseError:
        pass
    else:
        raise AssertionError("expected PlannerParseError on whitespace-only response")


def test_extract_json_accepts_bare_scalars() -> None:
    """RFC 8259 permits a top-level scalar — accept what's actually valid JSON
    even though such a response cannot be turned into proposals downstream."""
    assert _extract_json("null") is None
    assert _extract_json("true") is True
    assert _extract_json("42") == 42
    assert _extract_json('"just a string"') == "just a string"


def test_extract_json_accepts_top_level_array() -> None:
    """A planner that returns a bare ``[...]`` of steps (no wrapping object)
    must still parse — _parse_response handles both shapes."""
    parsed = _extract_json('[{"kind": "reason", "description": "go"}]')
    assert isinstance(parsed, list)
    assert parsed[0]["description"] == "go"


# ---------------------------------------------------------------------------
# PromptDrivenPlanner integration — failure observability
# ---------------------------------------------------------------------------


def test_planner_records_parse_failure_on_plain_text() -> None:
    planner = _planner_with_response("I cannot help with that request.")
    session = _fresh_session()

    proposals = planner.propose_plan(session)

    # Falls back to heuristic — proposals still come from somewhere
    assert isinstance(proposals, list)
    # And the parse failure is recorded for the audit ledger
    failure = session.session_state.get("last_planner_parse_failure")
    assert failure is not None
    assert failure["kind"] == "parse-failure"
    assert "could not recover" in failure["detail"].lower()
    assert "I cannot help" in failure["responsePreview"]
    assert "recordedAt" in failure


def test_planner_records_empty_plan_distinct_from_parse_failure() -> None:
    """A model returning ``{"steps": []}`` parsed cleanly but produced nothing
    actionable. That is operationally different from "model returned garbage" —
    the recorded ``kind`` must distinguish them."""
    planner = _planner_with_response('{"steps": []}')
    session = _fresh_session()

    planner.propose_plan(session)

    failure = session.session_state.get("last_planner_parse_failure")
    assert failure is not None
    assert failure["kind"] == "empty-plan"


def test_planner_records_model_error_when_complete_raises() -> None:
    class _BoomModel:
        def complete(self, _prompt: str) -> str:
            raise RuntimeError("provider hard-down")

    planner = PromptDrivenPlanner(model=_BoomModel())
    session = _fresh_session()
    planner.propose_plan(session)

    failure = session.session_state.get("last_planner_parse_failure")
    assert failure is not None
    assert failure["kind"] == "model-error"
    assert "provider hard-down" in failure["detail"]
    assert failure["responsePreview"] is None


def test_planner_does_not_record_failure_on_happy_path() -> None:
    planner = _planner_with_response(
        '{"steps": [{"kind": "reason", "description": "go", "payload": {"mark_complete": true}}]}'
    )
    session = _fresh_session()

    proposals = planner.propose_plan(session)
    assert proposals[0].kind == StepKind.REASON
    assert "last_planner_parse_failure" not in session.session_state


def test_planner_recovers_when_response_has_preamble_and_fence() -> None:
    """End-to-end: messy real-world response → clean proposals + no recorded failure."""
    response = (
        "I'll need to read the basis first. Here's the plan:\n"
        "```json\n"
        '{"steps": [{"kind": "use-capability", "description": "Read basis.",'
        ' "capabilityId": "cap-market-basis", "payload": {"basis_bps": 20}}]}\n'
        "```\n"
        "Let me know if you want me to adjust."
    )
    planner = _planner_with_response(response)
    session = _fresh_session()

    proposals = planner.propose_plan(session)
    assert proposals[0].kind == StepKind.USE_CAPABILITY
    assert proposals[0].capability_id == "cap-market-basis"
    assert "last_planner_parse_failure" not in session.session_state


def test_planner_response_preview_is_truncated() -> None:
    """Recorded preview must not bloat the replay JSON beyond ~500 chars."""
    long_garbage = "x" * 2000
    planner = _planner_with_response(long_garbage)
    session = _fresh_session()
    planner.propose_plan(session)

    failure = session.session_state["last_planner_parse_failure"]
    assert len(failure["responsePreview"]) <= 501  # 500 chars + ellipsis
    assert failure["responsePreview"].endswith("…")

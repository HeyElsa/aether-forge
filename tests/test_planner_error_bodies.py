"""Provider error bodies must reach the operator, not vanish.

Before this fix, a planner provider failing with HTTP 400/429 recorded only
``repr(HTTPError)`` — the body carrying the actionable message ("credit
balance is too low", "insufficient_quota") was discarded, and the
``last_planner_parse_failure`` event shipped ``responsePreview: null``.
These tests pin the new behavior: the body is captured into the failure
event and surfaced in the fallback log line.
"""

from __future__ import annotations

import io
import urllib.error
from email.message import Message

from aether_forge.models import error_body_preview
from aether_forge.planner import PromptDrivenPlanner
from aether_forge.runtime import RuntimeSession


def _http_error_with_body(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.invalid/v1",
        code=code,
        msg="Bad Request",
        hdrs=Message(),
        fp=io.BytesIO(body),
    )


class _RaisingModel:
    """PlanningModel whose complete() raises like a real provider call."""

    def __init__(self, error: Exception) -> None:
        self._error = error

    def complete(self, prompt: str) -> str:
        raise self._error


def test_error_body_preview_reads_http_error_body() -> None:
    error = _http_error_with_body(
        400, b'{"error": {"message": "Your credit balance is too low"}}'
    )
    preview = error_body_preview(error)
    assert preview is not None
    assert "credit balance is too low" in preview


def test_error_body_preview_truncates_long_bodies() -> None:
    error = _http_error_with_body(429, b"x" * 2000)
    preview = error_body_preview(error)
    assert preview is not None
    assert len(preview) == 501  # 500 chars + ellipsis
    assert preview.endswith("…")


def test_error_body_preview_handles_non_http_and_empty() -> None:
    assert error_body_preview(ValueError("boom")) is None
    assert error_body_preview(_http_error_with_body(500, b"")) is None
    assert error_body_preview(_http_error_with_body(500, b"   ")) is None


def test_model_error_event_carries_provider_body(runtime_session: RuntimeSession) -> None:
    error = _http_error_with_body(
        429, b'{"error": {"message": "insufficient_quota: add a payment method"}}'
    )
    planner = PromptDrivenPlanner(model=_RaisingModel(error))

    proposals = planner.propose_plan(runtime_session)

    assert proposals, "heuristic fallback should still produce a plan"
    failure = runtime_session.session_state.get("last_planner_parse_failure")
    assert failure is not None
    assert failure["kind"] == "model-error"
    assert failure["responsePreview"] is not None
    assert "insufficient_quota" in failure["responsePreview"]


def test_model_error_event_preview_stays_null_without_body(
    runtime_session: RuntimeSession,
) -> None:
    planner = PromptDrivenPlanner(model=_RaisingModel(TimeoutError("timed out")))

    planner.propose_plan(runtime_session)

    failure = runtime_session.session_state.get("last_planner_parse_failure")
    assert failure is not None
    assert failure["kind"] == "model-error"
    assert failure["responsePreview"] is None

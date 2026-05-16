"""Verify PlanningModel providers retry transient errors with backoff.

Sprint 1.1 (FP-1): the in-tree models previously called ``urlopen`` once and
raised straight through on URLError / 429 / 503 / 504. These tests pin the
new ``_with_retry`` envelope:

- transient errors retry up to ``retry_attempts`` (default 3),
- HTTP 429 honors the ``Retry-After`` header,
- non-transient HTTP codes (e.g. 400) raise on the first attempt,
- ``retry_attempts=1`` opts out of all retries,
- the wrapped sleep is injectable for deterministic, fast tests.
"""

from __future__ import annotations

import io
import urllib.error

from aether_forge.models import (
    AnthropicPlanningModel,
    OpenAICompatiblePlanningModel,
    _retry_after_seconds,
    _with_retry,
)


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    """Build a realistic HTTPError, optionally with a Retry-After header.

    Mirrors the shape ``urllib.request.urlopen`` actually produces; tests use
    this to exercise the retry envelope without spinning up an HTTP server.
    """
    from email.message import Message

    headers = Message()
    if retry_after is not None:
        headers["Retry-After"] = retry_after
    return urllib.error.HTTPError(
        url="https://example.invalid/v1",
        code=code,
        msg=f"HTTP {code}",
        hdrs=headers,  # type: ignore[arg-type]
        fp=io.BytesIO(b""),
    )


# ---------------------------------------------------------------------------
# _with_retry — the bare helper
# ---------------------------------------------------------------------------


def test_with_retry_returns_first_success() -> None:
    calls: list[int] = []

    def _ok() -> str:
        calls.append(1)
        return "ok"

    result = _with_retry(_ok, attempts=3, sleep=lambda _s: None)
    assert result == "ok"
    assert len(calls) == 1


def test_with_retry_retries_url_error_then_succeeds() -> None:
    calls: list[int] = []

    def _flaky() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.URLError("network blip")
        return "recovered"

    sleeps: list[float] = []
    result = _with_retry(_flaky, attempts=3, sleep=sleeps.append)

    assert result == "recovered"
    assert len(calls) == 3
    assert len(sleeps) == 2  # two backoffs between three attempts


def test_with_retry_honors_retry_after_on_429() -> None:
    calls: list[int] = []

    def _rate_limited() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise _http_error(429, retry_after="2")
        return "ok"

    sleeps: list[float] = []
    _with_retry(_rate_limited, attempts=3, sleep=sleeps.append)

    assert sleeps == [2.0]  # honored exactly, no jittered backoff


def test_with_retry_raises_non_transient_immediately() -> None:
    calls: list[int] = []

    def _bad_request() -> str:
        calls.append(1)
        raise _http_error(400)

    try:
        _with_retry(_bad_request, attempts=3, sleep=lambda _s: None)
    except urllib.error.HTTPError as error:
        assert error.code == 400
    else:
        raise AssertionError("expected HTTPError on 400")
    assert len(calls) == 1  # no retry


def test_with_retry_exhausts_and_raises_last_error() -> None:
    def _always_503() -> str:
        raise _http_error(503)

    try:
        _with_retry(_always_503, attempts=3, sleep=lambda _s: None)
    except urllib.error.HTTPError as error:
        assert error.code == 503
    else:
        raise AssertionError("expected HTTPError after exhaustion")


def test_with_retry_attempts_one_disables_retries() -> None:
    calls: list[int] = []

    def _flaky() -> str:
        calls.append(1)
        raise urllib.error.URLError("blip")

    try:
        _with_retry(_flaky, attempts=1, sleep=lambda _s: None)
    except urllib.error.URLError:
        pass
    else:
        raise AssertionError("expected URLError after opt-out")
    assert len(calls) == 1


def test_retry_after_seconds_parses_int_seconds() -> None:
    assert _retry_after_seconds(_http_error(429, retry_after="7")) == 7.0


def test_retry_after_seconds_returns_none_when_header_absent() -> None:
    assert _retry_after_seconds(_http_error(429)) is None


# ---------------------------------------------------------------------------
# Provider integration — OpenAI-compatible + Anthropic
# ---------------------------------------------------------------------------


def test_openai_compatible_retries_url_error_via_request_fn() -> None:
    calls: list[int] = []

    def _flaky_request(url: str, headers: dict[str, str], body: bytes) -> dict:
        calls.append(1)
        if len(calls) < 2:
            raise urllib.error.URLError("transient")
        return {"choices": [{"message": {"content": '{"steps": []}'}}]}

    model = OpenAICompatiblePlanningModel(
        model="gpt-4o",
        api_key="test",
        base_url="https://example.invalid/v1",
        request_fn=_flaky_request,
    )
    assert model.complete("plan") == '{"steps": []}'
    assert len(calls) == 2


def test_openai_compatible_opts_out_of_retry() -> None:
    calls: list[int] = []

    def _flaky_request(url: str, headers: dict[str, str], body: bytes) -> dict:
        calls.append(1)
        raise urllib.error.URLError("transient")

    model = OpenAICompatiblePlanningModel(
        model="gpt-4o",
        api_key="test",
        base_url="https://example.invalid/v1",
        request_fn=_flaky_request,
        retry_attempts=1,
    )
    try:
        model.complete("plan")
    except urllib.error.URLError:
        pass
    else:
        raise AssertionError("expected URLError with retry_attempts=1")
    assert len(calls) == 1


def test_anthropic_retries_on_429() -> None:
    calls: list[int] = []

    def _rate_limited(url: str, headers: dict[str, str], body: bytes) -> dict:
        calls.append(1)
        if len(calls) < 2:
            raise _http_error(429, retry_after="0")
        return {"content": [{"text": '{"steps": []}'}]}

    model = AnthropicPlanningModel(
        model="claude-sonnet-4",
        api_key="test",
        base_url="https://example.invalid",
        request_fn=_rate_limited,
    )
    assert model.complete("plan") == '{"steps": []}'
    assert len(calls) == 2

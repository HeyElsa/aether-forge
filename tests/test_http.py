"""Tests for the HTTP retry utility."""

from __future__ import annotations

import json

import pytest

from aether_forge.http import HttpError, RetryPolicy, http_get_json, http_post_json


def test_http_get_json_with_mock(monkeypatch) -> None:
    """Test successful GET request with mocked urlopen."""
    import urllib.request

    class FakeResponse:
        def __init__(self, data: bytes):
            self._data = data
        def read(self):
            return self._data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    def fake_urlopen(req, timeout=None):
        assert req.get_method() == "GET"
        return FakeResponse(json.dumps({"status": "ok"}).encode("utf8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = http_get_json("https://example.com/api", retry_policy=RetryPolicy(max_retries=0))
    assert result["status"] == "ok"


def test_http_post_json_with_mock(monkeypatch) -> None:
    import urllib.request

    class FakeResponse:
        def __init__(self, data: bytes):
            self._data = data
        def read(self):
            return self._data
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["method"] = req.get_method()
        captured["data"] = req.data
        captured["headers"] = dict(req.headers)
        return FakeResponse(json.dumps({"created": True}).encode("utf8"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = http_post_json(
        "https://example.com/api",
        body={"name": "test"},
        headers={"Authorization": "Bearer token"},
        retry_policy=RetryPolicy(max_retries=0),
    )
    assert result["created"] is True
    assert captured["method"] == "POST"
    payload = json.loads(captured["data"].decode("utf8"))
    assert payload["name"] == "test"


def test_retry_policy_defaults() -> None:
    policy = RetryPolicy()
    assert policy.max_retries == 3
    assert policy.base_delay_seconds == 1.0
    assert 429 in policy.retryable_status_codes
    assert 503 in policy.retryable_status_codes


def test_http_error_carries_context() -> None:
    err = HttpError("test error", status_code=503, url="https://example.com")
    assert err.status_code == 503
    assert err.url == "https://example.com"
    assert "test error" in str(err)

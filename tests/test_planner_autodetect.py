"""Verify cli._autodetect_planner picks cloud over Ollama (Sprint 1.2 / FP-2).

Pre-Sprint-1 behavior: Ollama was always probed first. A production host
running Ollama for an unrelated reason silently got picked up — the dev's
exact complaint. This test pins the new order:

- cloud key present → cloud wins (Ollama is not even probed),
- no cloud key + Ollama reachable → Ollama is the fallback,
- no cloud key + no Ollama → heuristic with a labeled ``source``,
- ``AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT=1`` overrides cloud (escape hatch),
- ``source`` is always populated so generated configs are audit-grade.

Also pins the doctor advisory at ``_check_planner_source``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.cli import _autodetect_planner
from aether_forge.doctor import _check_planner_source


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------


_CLOUD_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
)
_FLAG_VARS = (
    "AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT",
    "OLLAMA_BASE_URL",
)


@pytest.fixture(autouse=True)
def _clean_planner_env(monkeypatch):
    """Wipe every env var the autodetect path consults so each test starts clean."""
    for var in (*_CLOUD_VARS, *_FLAG_VARS):
        monkeypatch.delenv(var, raising=False)
    yield


def _stub_ollama(monkeypatch, *, reachable: bool, models: list[dict] | None = None):
    """Replace urllib_request.urlopen inside cli._autodetect_planner with a fake.

    ``reachable=True`` returns ``{"models": models or [{"name": "gemma:7b"}]}``;
    ``reachable=False`` raises URLError so the autodetect branch falls through.
    """
    import io
    import json as _json
    from urllib import error as _urllib_error

    from aether_forge import cli as cli_mod

    fake_models = models if models is not None else [{"name": "gemma:7b"}]

    class _FakeResponse:
        def __init__(self, payload: bytes) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return self._payload

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def _fake_urlopen(req, *args, **kwargs):
        if not reachable:
            raise _urllib_error.URLError("ollama unreachable in test")
        return _FakeResponse(_json.dumps({"models": fake_models}).encode("utf8"))

    # cli._autodetect_planner does ``from urllib import request as _urllib_request``
    # inside the function body, so we patch the module the import resolves to.
    monkeypatch.setattr(
        "urllib.request.urlopen",
        _fake_urlopen,
    )


# ---------------------------------------------------------------------------
# Autodetect order — the FP-2 fix
# ---------------------------------------------------------------------------


def test_cloud_key_wins_over_running_ollama(monkeypatch) -> None:
    """The exact regression the dev hit: a production host with both a cloud
    key and a running Ollama daemon must NOT silently pick Ollama."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    _stub_ollama(monkeypatch, reachable=True)

    result = _autodetect_planner()

    assert result["mode"] == "anthropic"
    assert result["source"] == "cloud"
    assert result["api_key_env"] == "ANTHROPIC_API_KEY"


def test_first_cloud_key_in_chain_wins(monkeypatch) -> None:
    """Anthropic → OpenAI → Gemini → OpenRouter order is preserved when
    multiple cloud keys are set."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or")
    _stub_ollama(monkeypatch, reachable=False)

    result = _autodetect_planner()

    assert result["mode"] == "openai"
    assert result["api_key_env"] == "OPENAI_API_KEY"


def test_ollama_picked_when_no_cloud_key_present(monkeypatch) -> None:
    """Local-dev convenience case: no cloud keys, Ollama running → Ollama wins
    (without needing the override flag)."""
    _stub_ollama(monkeypatch, reachable=True, models=[{"name": "llama3:8b"}])

    result = _autodetect_planner()

    assert result["mode"] == "ollama"
    assert result["source"] == "ollama"
    assert result["model"] == "llama3:8b"


def test_ollama_prefers_gemma_when_available(monkeypatch) -> None:
    _stub_ollama(
        monkeypatch,
        reachable=True,
        models=[{"name": "llama3:8b"}, {"name": "gemma2:9b"}],
    )

    result = _autodetect_planner()

    assert result["mode"] == "ollama"
    assert result["model"] == "gemma2:9b"


def test_heuristic_fallback_when_nothing_available(monkeypatch) -> None:
    _stub_ollama(monkeypatch, reachable=False)

    result = _autodetect_planner()

    assert result["mode"] == "heuristic"
    assert result["source"] == "heuristic"
    assert result["model"] is None
    assert result["api_key_env"] is None


def test_allow_ollama_autodetect_override_beats_cloud_key(monkeypatch) -> None:
    """Escape hatch: local devs who run Ollama and have a cloud key in their
    shell from another project can still force Ollama via the override flag."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT", "1")
    _stub_ollama(monkeypatch, reachable=True)

    result = _autodetect_planner()

    assert result["mode"] == "ollama"
    assert result["source"] == "ollama"


def test_allow_ollama_override_falls_through_when_ollama_unreachable(monkeypatch) -> None:
    """Override doesn't break the cloud-key path when Ollama is actually down."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT", "1")
    _stub_ollama(monkeypatch, reachable=False)

    result = _autodetect_planner()

    assert result["mode"] == "anthropic"
    assert result["source"] == "cloud"


def test_no_ollama_probe_when_cloud_key_present(monkeypatch) -> None:
    """Pin the no-probe contract: if a cloud key is set and the override flag
    is not, we never even open a connection to localhost:11434. This is the
    behavior production deploys depend on for predictable startup time."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")

    probe_calls: list[str] = []

    def _explode(_req, *args, **kwargs):
        probe_calls.append("called")
        raise AssertionError("autodetect must not probe Ollama when cloud key is set")

    monkeypatch.setattr("urllib.request.urlopen", _explode)

    result = _autodetect_planner()
    assert result["mode"] == "openai"
    assert probe_calls == []


# ---------------------------------------------------------------------------
# Doctor advisory — planner.source stamp surfaces in `forge doctor`
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, planner_block: dict) -> Path:
    config = {"planner": planner_block, "runtime": {"cryptoRouter": "mock"}}
    path = tmp_path / "aether-forge.json"
    path.write_text(json.dumps(config), encoding="utf8")
    return path


def test_doctor_planner_source_marks_explicit_as_production_safe(tmp_path: Path) -> None:
    path = _write_config(tmp_path, {"mode": "anthropic", "source": "explicit"})

    result = _check_planner_source(path)

    assert result.passed
    assert "explicit" in result.message
    assert "production-safe" in result.message


def test_doctor_planner_source_warns_on_autodetected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        {"mode": "ollama", "source": "autodetected", "detectedAt": "2026-05-16T10:00:00+00:00"},
    )

    result = _check_planner_source(path)

    assert result.passed  # not a hard fail in Sprint 1.2 — advisory only
    assert "autodetected" in result.message
    assert "AETHER_FORGE_PLANNER_MODE" in result.message


def test_doctor_planner_source_handles_legacy_unstamped_config(tmp_path: Path) -> None:
    """An aether-forge.json from before Sprint 1.2 has no ``source`` field —
    treat as informational, not an error."""
    path = _write_config(tmp_path, {"mode": "anthropic"})

    result = _check_planner_source(path)

    assert result.passed
    assert "unstamped" in result.message

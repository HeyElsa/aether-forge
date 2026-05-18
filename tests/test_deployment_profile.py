"""Verify deploymentProfile enforcement (Sprint 2.2 / FP-2 deepening).

Pins:
- resolve_deployment_profile order: explicit arg > env var > config > default 'local'
- invalid profile raises a clear ValueError
- generate-fast bakes the profile into aether-forge.json
- generate-fast with profile=production rejects autodetected planners
- generate-fast with profile=production rejects --planner-mode heuristic
- generate-fast with profile=staging rejects heuristic fallback when autodetect runs
- forge doctor fails when production + autodetected
- forge doctor fails when production + heuristic
- forge doctor fails when staging + autodetected
- forge doctor passes when production + explicit
- legacy configs without deploymentProfile default to 'local' (advisory only)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.config import (
    DEFAULT_DEPLOYMENT_PROFILE,
    DEPLOYMENT_PROFILES,
    resolve_deployment_profile,
)
from aether_forge.doctor import (
    _check_deployment_profile,
    _check_planner_source,
)

# ---------------------------------------------------------------------------
# Env helpers — keep tests deterministic regardless of host shell state
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clean_profile_env(monkeypatch):
    for var in (
        "AETHER_FORGE_DEPLOYMENT_PROFILE",
        "AETHER_FORGE_PLANNER_MODE",
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "OPENROUTER_API_KEY",
        "AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT",
        "OLLAMA_BASE_URL",
    ):
        monkeypatch.delenv(var, raising=False)
    yield


# ---------------------------------------------------------------------------
# resolve_deployment_profile — the resolution chain
# ---------------------------------------------------------------------------


def test_resolve_default_is_local() -> None:
    assert resolve_deployment_profile() == "local"
    assert DEFAULT_DEPLOYMENT_PROFILE == "local"


def test_resolve_config_value() -> None:
    assert resolve_deployment_profile(config={"deploymentProfile": "staging"}) == "staging"


def test_resolve_env_var_beats_config(monkeypatch) -> None:
    monkeypatch.setenv("AETHER_FORGE_DEPLOYMENT_PROFILE", "production")
    assert (
        resolve_deployment_profile(config={"deploymentProfile": "staging"}) == "production"
    )


def test_resolve_explicit_beats_env(monkeypatch) -> None:
    monkeypatch.setenv("AETHER_FORGE_DEPLOYMENT_PROFILE", "production")
    assert resolve_deployment_profile(profile="staging") == "staging"


def test_resolve_rejects_invalid_value() -> None:
    with pytest.raises(ValueError) as exc:
        resolve_deployment_profile(profile="prod")
    assert "Must be one of" in str(exc.value)


def test_deployment_profiles_tuple_is_exact() -> None:
    """Pin the set so a future addition shows up as a deliberate test change
    rather than silently widening the contract."""
    assert DEPLOYMENT_PROFILES == ("local", "staging", "production")


# ---------------------------------------------------------------------------
# Generator integration — the profile is stamped into aether-forge.json
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, *, profile: str | None = None, planner: dict | None = None) -> Path:
    config: dict = {}
    if profile is not None:
        config["deploymentProfile"] = profile
    if planner is not None:
        config["planner"] = planner
    config.setdefault("planner", {"mode": "heuristic"})
    config.setdefault("runtime", {"cryptoRouter": "mock"})
    path = tmp_path / "aether-forge.json"
    path.write_text(json.dumps(config), encoding="utf8")
    return path


def test_generated_aether_forge_json_includes_deployment_profile(tmp_path: Path) -> None:
    """Round-trip: generate-fast with explicit profile → JSON contains it."""
    from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set

    out = tmp_path / "agent"
    request = FastGenerateRequest(
        name="ProfileAgent",
        idea="test profile baked into config",
        output_directory=out,
        deployment_profile="staging",
        planner_mode="anthropic",
        planner_model="claude-sonnet-4-5",
        planner_api_key_env="ANTHROPIC_API_KEY",
        planner_source="explicit",
    )
    generate_fast_artifact_set(request)

    config = json.loads((out / "aether-forge.json").read_text())
    assert config["deploymentProfile"] == "staging"


def test_generated_aether_forge_json_defaults_to_local(tmp_path: Path) -> None:
    """When the request doesn't pass deployment_profile, the field defaults to 'local'."""
    from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set

    out = tmp_path / "agent"
    request = FastGenerateRequest(
        name="DefaultProfileAgent",
        idea="test default profile",
        output_directory=out,
    )
    generate_fast_artifact_set(request)

    config = json.loads((out / "aether-forge.json").read_text())
    assert config["deploymentProfile"] == "local"


# ---------------------------------------------------------------------------
# CLI gate — generate-fast refuses unsafe profile combinations
# ---------------------------------------------------------------------------


def test_generate_fast_refuses_production_with_autodetected_planner(tmp_path, capsys) -> None:
    """The exact regression to prevent: a developer running `forge generate-fast
    --deployment-profile production` without `--planner-mode` must get a clear
    failure, not a silently autodetected provider."""
    from aether_forge.cli import main

    out = tmp_path / "agent"
    rc = main(
        [
            "generate-fast",
            "--name", "ProdAgent",
            "--idea", "prod test",
            "--output", str(out),
            "--deployment-profile", "production",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2, f"expected exit 2, got {rc} (stderr: {captured.err})"
    assert "production deployment profile forbids autodetected" in captured.err
    assert not out.exists(), "agent dir must not be created on profile rejection"


def test_generate_fast_refuses_production_with_explicit_heuristic(tmp_path, capsys) -> None:
    from aether_forge.cli import main

    out = tmp_path / "agent"
    rc = main(
        [
            "generate-fast",
            "--name", "ProdAgent",
            "--idea", "prod test",
            "--output", str(out),
            "--deployment-profile", "production",
            "--planner-mode", "heuristic",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2, f"expected exit 2, got {rc} (stderr: {captured.err})"
    assert "heuristic planner is not allowed in production" in captured.err
    assert not out.exists()


def test_generate_fast_accepts_production_with_explicit_anthropic(tmp_path, monkeypatch) -> None:
    """Happy path for production: explicit --planner-mode is the contract."""
    from aether_forge.cli import main

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-fixture")
    out = tmp_path / "agent"
    rc = main(
        [
            "generate-fast",
            "--name", "ProdAgent",
            "--idea", "prod test",
            "--output", str(out),
            "--deployment-profile", "production",
            "--planner-mode", "anthropic",
            "--planner-model", "claude-sonnet-4-5",
            "--planner-api-key-env", "ANTHROPIC_API_KEY",
            "--no-registry",
        ]
    )
    assert rc == 0
    config = json.loads((out / "aether-forge.json").read_text())
    assert config["deploymentProfile"] == "production"
    assert config["planner"]["mode"] == "anthropic"
    assert config["planner"]["source"] == "explicit"


def test_generate_fast_refuses_staging_with_heuristic_fallback(tmp_path, capsys) -> None:
    """Staging + autodetect-falls-to-heuristic (no cloud key, no Ollama) is rejected."""
    from aether_forge.cli import main

    out = tmp_path / "agent"
    # No env vars set (clean fixture). Ollama is not stubbed reachable.
    rc = main(
        [
            "generate-fast",
            "--name", "StagingAgent",
            "--idea", "staging test",
            "--output", str(out),
            "--deployment-profile", "staging",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 2, f"expected exit 2, got {rc} (stderr: {captured.err})"
    assert "heuristic fallback not allowed in staging" in captured.err


# ---------------------------------------------------------------------------
# Doctor — escalates verdict in non-local profiles
# ---------------------------------------------------------------------------


def test_doctor_deployment_profile_passes_for_known_value(tmp_path: Path) -> None:
    path = _write_config(tmp_path, profile="staging", planner={"mode": "anthropic", "source": "explicit"})
    result = _check_deployment_profile(path)
    assert result.passed
    assert "staging" in result.message


def test_doctor_deployment_profile_fails_for_unknown(tmp_path: Path) -> None:
    path = _write_config(tmp_path, profile="prod", planner={"mode": "anthropic", "source": "explicit"})
    result = _check_deployment_profile(path)
    assert not result.passed
    assert "Invalid deploymentProfile" in result.message


def test_doctor_deployment_profile_implicit_local(tmp_path: Path) -> None:
    path = _write_config(tmp_path, planner={"mode": "anthropic", "source": "explicit"})
    result = _check_deployment_profile(path)
    assert result.passed
    assert "local" in result.message
    assert "implicit default" in result.message


def test_doctor_planner_source_fails_on_production_autodetected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path,
        profile="production",
        planner={"mode": "anthropic", "source": "autodetected", "detectedAt": "2026-05-16T18:00:00+00:00"},
    )
    result = _check_planner_source(path)
    assert not result.passed
    assert "production profile forbids autodetected" in result.message


def test_doctor_planner_source_fails_on_production_heuristic(tmp_path: Path) -> None:
    path = _write_config(tmp_path, profile="production", planner={"mode": "heuristic", "source": "explicit"})
    result = _check_planner_source(path)
    assert not result.passed
    assert "heuristic planner is not allowed in production" in result.message


def test_doctor_planner_source_fails_on_staging_autodetected(tmp_path: Path) -> None:
    path = _write_config(
        tmp_path, profile="staging",
        planner={"mode": "openai", "source": "autodetected"},
    )
    result = _check_planner_source(path)
    assert not result.passed
    assert "staging profile forbids autodetected" in result.message


def test_doctor_planner_source_passes_on_production_explicit(tmp_path: Path) -> None:
    path = _write_config(tmp_path, profile="production", planner={"mode": "anthropic", "source": "explicit"})
    result = _check_planner_source(path)
    assert result.passed
    assert "production-safe" in result.message


def test_doctor_planner_source_advisory_on_local_autodetected(tmp_path: Path) -> None:
    """Local-profile autodetected stays advisory (don't break dev machines)."""
    path = _write_config(tmp_path, profile="local", planner={"mode": "ollama", "source": "autodetected"})
    result = _check_planner_source(path)
    assert result.passed
    assert result.optional
    assert "autodetected" in result.message

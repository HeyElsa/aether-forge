from __future__ import annotations

import json
from pathlib import Path

from aether_forge.config import (
    PlannerSettings,
    build_planner_factory,
    discover_default_config_path,
    load_config_file,
    resolve_planner_settings,
    resolve_runtime_settings,
)
from aether_forge.models import AnthropicPlanningModel, GeminiPlanningModel, StaticPlanningModel
from aether_forge.planner import HeuristicPlanner, PromptDrivenPlanner


def test_resolve_planner_settings_uses_env_api_key_reference(monkeypatch) -> None:
    monkeypatch.setenv("AETHER_FORGE_PLANNER_MODE", "openai-compatible")
    monkeypatch.setenv("AETHER_FORGE_PLANNER_MODEL", "hermes-3")
    monkeypatch.setenv("AETHER_FORGE_PLANNER_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("AETHER_FORGE_PLANNER_API_KEY_ENV", "MY_TEST_PLANNER_KEY")
    monkeypatch.setenv("MY_TEST_PLANNER_KEY", "resolved-key")

    settings = resolve_planner_settings()

    assert settings.mode == "openai-compatible"
    assert settings.model == "hermes-3"
    assert settings.base_url == "https://example.invalid/v1"
    assert settings.api_key == "resolved-key"
    assert settings.api_key_env == "MY_TEST_PLANNER_KEY"


def test_build_planner_factory_returns_heuristic_planner() -> None:
    factory = build_planner_factory(PlannerSettings(mode="heuristic"))

    planner = factory()

    assert isinstance(planner, HeuristicPlanner)


def test_build_planner_factory_returns_prompt_planner_for_static_mode(tmp_path: Path) -> None:
    response_file = tmp_path / "planner-response.json"
    response_file.write_text('{"steps": [{"kind": "reason", "description": "done", "payload": {"mark_complete": true}}]}\n', encoding="utf8")

    factory = build_planner_factory(
        PlannerSettings(
            mode="static",
            static_response_file=str(response_file),
        )
    )

    planner = factory()

    assert isinstance(planner, PromptDrivenPlanner)
    assert isinstance(planner.model, StaticPlanningModel)


def test_load_config_file_reads_json_object(tmp_path: Path) -> None:
    config_path = tmp_path / "aether-forge.json"
    config_path.write_text(json.dumps({"planner": {"mode": "static"}}), encoding="utf8")

    config = load_config_file(config_path)

    assert config == {"planner": {"mode": "static"}}


def test_resolve_settings_can_use_config_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "aether-forge.json"
    config_path.write_text(
        json.dumps(
            {
                "planner": {
                    "mode": "static",
                    "staticResponseFile": "/tmp/response.json",
                },
                "runtime": {
                    "cryptoRouter": "public-market-data",
                },
            }
        ),
        encoding="utf8",
    )
    config = load_config_file(config_path)

    planner_settings = resolve_planner_settings(config=config)
    runtime_settings = resolve_runtime_settings(config=config)

    assert planner_settings.mode == "static"
    assert planner_settings.static_response_file == "/tmp/response.json"
    assert runtime_settings.crypto_router == "public-market-data"


def test_discover_default_config_path_prefers_artifact_directory(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "artifact-set"
    artifact_dir.mkdir()
    config_path = artifact_dir / "aether-forge.json"
    config_path.write_text("{}", encoding="utf8")

    discovered = discover_default_config_path(artifact_dir)

    assert discovered == config_path


def test_build_planner_factory_returns_anthropic_planner() -> None:
    settings = PlannerSettings(mode="anthropic", model="claude-sonnet-4-20250514", api_key="test-key")

    factory = build_planner_factory(settings)
    planner = factory()

    assert isinstance(planner, PromptDrivenPlanner)
    assert isinstance(planner.model, AnthropicPlanningModel)
    assert planner.model.model == "claude-sonnet-4-20250514"


def test_build_planner_factory_returns_gemini_planner() -> None:
    settings = PlannerSettings(mode="gemini", model="gemini-2.5-pro", api_key="test-key")

    factory = build_planner_factory(settings)
    planner = factory()

    assert isinstance(planner, PromptDrivenPlanner)
    assert isinstance(planner.model, GeminiPlanningModel)


def test_resolve_planner_settings_resolves_named_provider_openai() -> None:
    settings = resolve_planner_settings(mode="openai", model="gpt-4o", api_key="test-key")

    assert settings.mode == "openai-compatible"
    assert settings.base_url == "https://api.openai.com/v1"


def test_resolve_planner_settings_resolves_named_provider_openrouter() -> None:
    settings = resolve_planner_settings(mode="openrouter", model="anthropic/claude-sonnet-4", api_key="test-key")

    assert settings.mode == "openai-compatible"
    assert settings.base_url == "https://openrouter.ai/api/v1"


def test_resolve_planner_settings_resolves_named_provider_ollama() -> None:
    settings = resolve_planner_settings(mode="ollama", model="llama3")

    assert settings.mode == "openai-compatible"
    assert settings.base_url == "http://localhost:11434/v1"


def test_resolve_planner_settings_preserves_custom_base_url() -> None:
    settings = resolve_planner_settings(mode="openai", model="gpt-4o", api_key="k", base_url="https://custom.example.com/v1")

    assert settings.mode == "openai-compatible"
    assert settings.base_url == "https://custom.example.com/v1"

"""Tests for the secrets provider module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.secrets import (
    ChainSecretsProvider,
    EnvSecretsProvider,
    FileSecretsProvider,
    SecretNotFoundError,
    build_secrets_provider,
)


def test_env_provider_reads_from_env(monkeypatch) -> None:
    monkeypatch.setenv("BINANCE_API_KEY", "sk-test-123")
    provider = EnvSecretsProvider()
    assert provider.get("binance-api-key") == "sk-test-123"


def test_env_provider_with_prefix(monkeypatch) -> None:
    monkeypatch.setenv("FORGE_MY_SECRET", "secret-value")
    provider = EnvSecretsProvider(prefix="FORGE_")
    assert provider.get("my-secret") == "secret-value"


def test_env_provider_with_explicit_mapping(monkeypatch) -> None:
    monkeypatch.setenv("CUSTOM_VAR", "mapped-value")
    provider = EnvSecretsProvider(mapping={"my-key": "CUSTOM_VAR"})
    assert provider.get("my-key") == "mapped-value"


def test_env_provider_raises_on_missing() -> None:
    provider = EnvSecretsProvider()
    with pytest.raises(SecretNotFoundError, match="not set"):
        provider.get("nonexistent-secret-xyz-999")


def test_env_provider_has(monkeypatch) -> None:
    monkeypatch.setenv("TEST_KEY", "value")
    provider = EnvSecretsProvider()
    assert provider.has("test-key")
    assert not provider.has("missing-key-xyz-999")


def test_file_provider_reads_from_vault(tmp_path: Path) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text(json.dumps({"my-api-key": "file-secret-123"}), encoding="utf8")
    provider = FileSecretsProvider(vault)
    assert provider.get("my-api-key") == "file-secret-123"


def test_file_provider_raises_on_missing_key(tmp_path: Path) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text("{}", encoding="utf8")
    provider = FileSecretsProvider(vault)
    with pytest.raises(SecretNotFoundError, match="not found in vault"):
        provider.get("missing-key")


def test_file_provider_raises_on_missing_file() -> None:
    provider = FileSecretsProvider("/nonexistent/path/secrets.json")
    with pytest.raises(SecretNotFoundError, match="does not exist"):
        provider.get("any-key")


def test_file_provider_has(tmp_path: Path) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text(json.dumps({"existing": "value"}), encoding="utf8")
    provider = FileSecretsProvider(vault)
    assert provider.has("existing")
    assert not provider.has("missing")


def test_file_provider_caches_vault(tmp_path: Path) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text(json.dumps({"key": "v1"}), encoding="utf8")
    provider = FileSecretsProvider(vault)
    assert provider.get("key") == "v1"

    vault.write_text(json.dumps({"key": "v2"}), encoding="utf8")
    assert provider.get("key") == "v1"  # cached

    provider.reload()
    assert provider.get("key") == "v2"  # reloaded


def test_chain_provider_tries_in_order(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text(json.dumps({"file-only": "from-file"}), encoding="utf8")
    monkeypatch.setenv("ENV_ONLY", "from-env")

    provider = ChainSecretsProvider([
        FileSecretsProvider(vault),
        EnvSecretsProvider(mapping={"env-only": "ENV_ONLY"}),
    ])

    assert provider.get("file-only") == "from-file"
    assert provider.get("env-only") == "from-env"


def test_chain_provider_file_takes_precedence(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text(json.dumps({"shared-key": "from-file"}), encoding="utf8")
    monkeypatch.setenv("SHARED_KEY", "from-env")

    provider = ChainSecretsProvider([
        FileSecretsProvider(vault),
        EnvSecretsProvider(),
    ])
    assert provider.get("shared-key") == "from-file"


def test_chain_provider_raises_when_all_fail() -> None:
    provider = ChainSecretsProvider([EnvSecretsProvider()])
    with pytest.raises(SecretNotFoundError, match="not found in any provider"):
        provider.get("nonexistent-xyz-999")


def test_chain_provider_has(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text(json.dumps({"file-key": "v"}), encoding="utf8")
    monkeypatch.setenv("ENV_KEY_XYZ", "v")

    provider = ChainSecretsProvider([
        FileSecretsProvider(vault),
        EnvSecretsProvider(mapping={"env-key": "ENV_KEY_XYZ"}),
    ])
    assert provider.has("file-key")
    assert provider.has("env-key")
    assert not provider.has("missing-xyz")


def test_build_secrets_provider_env_only(monkeypatch) -> None:
    monkeypatch.setenv("MY_SECRET", "env-value")
    provider = build_secrets_provider()
    assert provider.get("my-secret") == "env-value"


def test_build_secrets_provider_with_vault(tmp_path: Path, monkeypatch) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text(json.dumps({"vault-key": "vault-value"}), encoding="utf8")
    monkeypatch.setenv("FALLBACK_KEY", "env-value")

    provider = build_secrets_provider(vault_path=vault, env_mapping={"fallback-key": "FALLBACK_KEY"})
    assert provider.get("vault-key") == "vault-value"
    assert provider.get("fallback-key") == "env-value"


def test_file_provider_rejects_non_object_vault(tmp_path: Path) -> None:
    vault = tmp_path / "secrets.json"
    vault.write_text('["not", "an", "object"]', encoding="utf8")
    provider = FileSecretsProvider(vault)
    with pytest.raises(ValueError, match="JSON object"):
        provider.get("any-key")

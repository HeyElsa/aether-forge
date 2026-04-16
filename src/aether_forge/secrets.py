"""Secrets provider interface and backends for Aether Forge.

Provides a pluggable abstraction for resolving secrets (API keys, credentials)
without embedding them in specs, prompts, or persisted state. Backends include
environment variables and file-based vaults.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol


class SecretNotFoundError(KeyError):
    """Raised when a requested secret cannot be resolved."""


class SecretsProvider(Protocol):
    """Protocol for resolving secrets by handle ID."""

    def get(self, handle_id: str) -> str:
        """Return the secret value for the given handle ID.

        Raises ``SecretNotFoundError`` if the handle cannot be resolved.
        """
        ...

    def has(self, handle_id: str) -> bool:
        """Return whether the handle ID can be resolved."""
        ...


class EnvSecretsProvider:
    """Resolves secrets from environment variables.

    Maps handle IDs to env var names. By default, the handle ID is uppercased
    and hyphens are replaced with underscores (e.g., ``binance-api-key`` ->
    ``BINANCE_API_KEY``). An explicit mapping can override this.

    Usage::

        provider = EnvSecretsProvider()
        api_key = provider.get("binance-api-key")  # reads BINANCE_API_KEY

        provider = EnvSecretsProvider(mapping={"my-key": "CUSTOM_VAR"})
        api_key = provider.get("my-key")  # reads CUSTOM_VAR
    """

    def __init__(
        self,
        *,
        mapping: dict[str, str] | None = None,
        prefix: str = "",
    ) -> None:
        self._mapping = mapping or {}
        self._prefix = prefix

    def get(self, handle_id: str) -> str:
        env_var = self._resolve_env_var(handle_id)
        value = os.getenv(env_var)
        if value is None:
            raise SecretNotFoundError(
                f"Secret '{handle_id}' not found: environment variable '{env_var}' is not set"
            )
        return value

    def has(self, handle_id: str) -> bool:
        env_var = self._resolve_env_var(handle_id)
        return os.getenv(env_var) is not None

    def _resolve_env_var(self, handle_id: str) -> str:
        if handle_id in self._mapping:
            return self._mapping[handle_id]
        normalized = handle_id.upper().replace("-", "_").replace(".", "_")
        return f"{self._prefix}{normalized}" if self._prefix else normalized


class FileSecretsProvider:
    """Resolves secrets from a JSON file vault.

    The vault file should be a flat JSON object mapping handle IDs to secret values::

        {
            "binance-api-key": "sk-...",
            "binance-api-secret": "..."
        }

    Usage::

        provider = FileSecretsProvider("/path/to/secrets.json")
        api_key = provider.get("binance-api-key")
    """

    def __init__(self, vault_path: str | Path) -> None:
        self._vault_path = Path(vault_path)
        self._cache: dict[str, str] | None = None

    def get(self, handle_id: str) -> str:
        vault = self._load_vault()
        if handle_id not in vault:
            raise SecretNotFoundError(
                f"Secret '{handle_id}' not found in vault file '{self._vault_path}'"
            )
        return str(vault[handle_id])

    def has(self, handle_id: str) -> bool:
        vault = self._load_vault()
        return handle_id in vault

    def _load_vault(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        if not self._vault_path.exists():
            raise SecretNotFoundError(f"Vault file does not exist: {self._vault_path}")
        data = json.loads(self._vault_path.read_text(encoding="utf8"))
        if not isinstance(data, dict):
            raise ValueError(f"Vault file must contain a JSON object: {self._vault_path}")
        self._cache = data
        return self._cache

    def reload(self) -> None:
        """Clear the cached vault and reload from disk on next access."""
        self._cache = None


class ChainSecretsProvider:
    """Chains multiple providers, trying each in order until one succeeds.

    Usage::

        provider = ChainSecretsProvider([
            FileSecretsProvider("./secrets.json"),
            EnvSecretsProvider(),
        ])
        api_key = provider.get("binance-api-key")
    """

    def __init__(self, providers: list[SecretsProvider]) -> None:
        if not providers:
            raise ValueError("ChainSecretsProvider requires at least one provider")
        self._providers = providers

    def get(self, handle_id: str) -> str:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return provider.get(handle_id)
            except (SecretNotFoundError, KeyError) as error:
                errors.append(str(error))
        raise SecretNotFoundError(
            f"Secret '{handle_id}' not found in any provider. Tried {len(self._providers)} providers."
        )

    def has(self, handle_id: str) -> bool:
        return any(provider.has(handle_id) for provider in self._providers)


def build_secrets_provider(
    *,
    vault_path: str | Path | None = None,
    env_prefix: str = "",
    env_mapping: dict[str, str] | None = None,
) -> SecretsProvider:
    """Build a secrets provider from configuration.

    If a vault path is provided, creates a chain that checks the file first,
    then falls back to environment variables. Otherwise, uses env vars only.
    """
    env_provider = EnvSecretsProvider(prefix=env_prefix, mapping=env_mapping)
    if vault_path is not None:
        return ChainSecretsProvider([
            FileSecretsProvider(vault_path),
            env_provider,
        ])
    return env_provider

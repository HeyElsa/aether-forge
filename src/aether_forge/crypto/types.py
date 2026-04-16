"""Crypto type definitions and constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


CRYPTO_KINDS = {"wallet-action", "exchange-action", "onchain-action", "data-source"}


@dataclass(slots=True)
class CryptoCapabilityDescriptor:
    capability_id: str
    kind: str
    provider: str
    risk_level: str
    allowed_environments: list[str]
    credential_handle_id: str | None
    provider_constraints: dict[str, Any]
    effect_semantics: dict[str, Any] | None = None


RequestFn = Callable[[str], dict[str, Any]]


@dataclass(slots=True)
class CredentialLease:
    handle_id: str
    environment: str
    maximum_access_scope: dict[str, Any]
    metadata: dict[str, Any]


@dataclass(slots=True)
class PaperPosition:
    symbol: str
    notional_usd: float
    side: str


@dataclass(slots=True)
class SimWalletAccount:
    address: str
    chain: str
    native_balance: float

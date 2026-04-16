"""Utility functions for crypto capabilities."""

from __future__ import annotations

import json
from importlib import import_module
from typing import Any, TYPE_CHECKING
from urllib import request as urllib_request

from .types import CRYPTO_KINDS, CryptoCapabilityDescriptor

if TYPE_CHECKING:
    from .wallets import OWSBindings


def load_crypto_capabilities(capability_manifest: dict[str, Any]) -> dict[str, CryptoCapabilityDescriptor]:
    descriptors: dict[str, CryptoCapabilityDescriptor] = {}
    for capability in capability_manifest.get("capabilities", []):
        kind = capability.get("kind")
        capability_id = capability.get("capabilityId")
        if kind not in CRYPTO_KINDS or not isinstance(capability_id, str):
            continue

        descriptors[capability_id] = CryptoCapabilityDescriptor(
            capability_id=capability_id,
            kind=str(kind),
            provider=str(capability.get("provider", "unknown-provider")),
            risk_level=str(capability.get("riskLevel", "unknown")),
            allowed_environments=list(capability.get("allowedEnvironments", [])),
            credential_handle_id=capability.get("credentialHandleId"),
            provider_constraints=dict(capability.get("providerConstraints", {})),
            effect_semantics=dict(capability.get("effectSemantics", {})) if isinstance(capability.get("effectSemantics"), dict) else None,
        )

    return descriptors


def _default_json_request(url: str) -> dict[str, Any]:
    req = urllib_request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib_request.urlopen(req) as response:  # noqa: S310 - provider URL is explicit and public by design.
        return json.loads(response.read().decode("utf8"))


def _normalize_spot_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace("-", "")


def _normalize_perp_symbol(symbol: str) -> str:
    normalized = symbol.replace("/", "").replace("-", "")
    return normalized.replace("PERP", "USDT") if normalized.endswith("PERP") else normalized


def _load_ows_bindings() -> OWSBindings:
    try:
        module = import_module("ows")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "The Open Wallet Standard Python SDK is not installed or importable as `ows`. "
            "Install with `pip install open-wallet-standard` or `pip install .[wallet]`."
        ) from error
    return module  # type: ignore[return-value]


def _ows_chain_matches(chain_id: str, chain_alias: str) -> bool:
    normalized_alias = chain_alias.lower()
    normalized_chain_id = chain_id.lower()
    alias_map = {
        "evm": {"eip155", "ethereum", "evm"},
        "ethereum": {"eip155", "ethereum", "evm"},
        "solana": {"solana"},
        "bitcoin": {"bip122", "bitcoin"},
        "sui": {"sui"},
        "ton": {"ton"},
    }
    accepted = alias_map.get(normalized_alias, {normalized_alias})
    return any(candidate in normalized_chain_id for candidate in accepted)

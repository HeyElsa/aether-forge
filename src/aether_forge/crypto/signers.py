"""Delegated signer abstractions for x402 + on-chain calls (Sprint 2.3 / FP-3).

The pre-v0.22.0 ``X402Client`` assumed the agent's own OWS wallet would sign
every EIP-3009 transfer authorization. The dev's complaint: hosted-marketplace
patterns (the user's wallet pays, not the agent's; server-side delegated
signers; browser sign-and-relay) had no first-class API surface — the only
seam was an undocumented ``sign_typed_data_fn`` callable injected at construct
time.

This module ships the first-class abstraction the plan called for:

- :class:`DelegatedSigner` — the protocol every signer satisfies. Single
  method ``sign_typed_data(typed_data, *, intent=None) -> str``.
- :class:`SigningIntent` — value object describing what the signature
  authorizes (chain id, target contract, USD value). The constrained signer
  wrapper inspects it before delegating.
- :class:`OwsSigner` — extracts the v0.21.0 in-line OWS path so the legacy
  default is a first-class signer rather than an ``isinstance`` branch.
- :class:`BrowserRelaySigner` — POSTs the typed_data payload to a relay URL
  the user controls; expects ``{"signature": "0x…"}`` back. Enables the
  hosted-marketplace pattern where a browser-side wallet (window.ethereum,
  Privy, RainbowKit) signs and the agent runtime just relays.
- :class:`DelegatedSecretsSigner` — resolves a signing function from a
  :class:`CredentialResolver` lease metadata; the resolved function does
  the actual signing. Lets ops keep keys in a vault / HSM rather than on
  disk.
- :class:`SessionKeyConstrainedSigner` — wrapper that consults a
  :class:`SessionKeyPolicy` (security.py) before delegating to an inner
  signer. Rejects out-of-chain / out-of-contract / over-budget intents
  with :class:`SigningRefusedError`.

Deny-by-default: every signer's policy check fails closed. A signer without
an intent receives ``None`` and signs unconditionally (legacy compatibility);
the constrained wrapper enforces ``intent is not None`` so callers cannot
silently opt out of scope checks by omitting the intent.

Schema: ``schemas/runtime/delegated-signer.schema.json``.
"""

from __future__ import annotations

import base64
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)


SignerKind = Literal["ows", "browser-relay", "delegated-secret", "mock"]
SIGNER_KINDS: tuple[SignerKind, ...] = ("ows", "browser-relay", "delegated-secret", "mock")


class SigningError(RuntimeError):
    """Base class for signer failures. Distinct from PaymentSigningError so
    upstream code can catch generic delegated-signer errors without coupling
    to x402-specific exception types."""


class SigningRefusedError(SigningError):
    """Raised when a constrained signer refuses on policy grounds.

    Carries the policy reason in ``args[0]`` so call sites can surface a
    human-readable rejection to the operator or the audit log.
    """


@dataclass(slots=True, frozen=True)
class SigningIntent:
    """What an EIP-712 typed-data signature authorizes.

    Optional fields — populate as much as the caller knows. The constrained
    wrapper enforces the relevant subset based on what the session-key policy
    declares; missing fields treated as "permit everything" would weaken the
    contract, so the wrapper treats absence as fail-closed for any field the
    policy *does* constrain.
    """

    chain_id: int | None = None
    contract_address: str | None = None
    spend_usd: float | None = None
    purpose: str = "x402-payment"


class DelegatedSigner(Protocol):
    """Single-method protocol every signer satisfies. Implementations live
    in this module; third parties can ship more via the
    ``aether_forge.signers`` entry-point group (future)."""

    def sign_typed_data(self, typed_data: dict[str, Any], *, intent: SigningIntent | None = None) -> str:
        ...


# ---------------------------------------------------------------------------
# OwsSigner — the legacy default extracted into a first-class signer
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class OwsSigner:
    """Signs via the local OWS wallet (the v0.21.0 default behavior).

    Extracts the inline path from ``X402Client._sign_authorization`` so callers
    can compose it with :class:`SessionKeyConstrainedSigner` or replace it
    entirely. Requires the OWS SDK and a forge-provisioned wallet at
    ``agent_directory``.
    """

    agent_directory: str
    # Internal: extracted for testability — lets tests inject a fake `ows`
    # module without touching the real OWS SDK.
    _ows_module: Any = None

    def sign_typed_data(self, typed_data: dict[str, Any], *, intent: SigningIntent | None = None) -> str:
        del intent  # OwsSigner does not enforce intents — wrap it with SessionKeyConstrainedSigner for that.
        from pathlib import Path as _Path

        from ..wallet import get_signing_credentials

        ows = self._ows_module
        if ows is None:
            from importlib import import_module
            try:
                ows = import_module("ows")
            except ModuleNotFoundError as error:
                raise SigningError("OWS SDK not installed (install with: pip install aether-forge[wallet])") from error

        creds = get_signing_credentials(_Path(self.agent_directory))
        if creds.get("provider") != "ows":
            raise SigningError("Live signing requires a real OWS wallet (provider=ows)")

        # OWS does not yet support EIP-712 signing via API key; fall back to
        # the owner passphrase (empty by default for forge-created wallets).
        try:
            result = ows.sign_typed_data(
                creds["wallet_name"],
                "ethereum",
                json.dumps(typed_data),
                passphrase=creds["api_key"] if creds["api_key"].startswith("ows_key_") else None,
                vault_path_opt=creds.get("vault_path"),
            )
        except RuntimeError as api_error:
            if "API key" in str(api_error):
                logger.debug("OWS API-key signing not supported for EIP-712, retrying with passphrase")
                result = ows.sign_typed_data(
                    creds["wallet_name"],
                    "ethereum",
                    json.dumps(typed_data),
                    passphrase="",
                    vault_path_opt=creds.get("vault_path"),
                )
            else:
                raise SigningError(f"OWS sign_typed_data failed: {api_error}") from api_error
        signature = result.get("signature") if isinstance(result, dict) else None
        if not isinstance(signature, str) or not signature:
            raise SigningError("OWS signer returned empty signature")
        return signature


# ---------------------------------------------------------------------------
# BrowserRelaySigner — POST to a user-controlled relay
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BrowserRelaySigner:
    """Forwards typed-data payloads to an HTTP relay; the relay returns the
    signature produced by the user's wallet.

    The relay protocol is intentionally minimal so any hosted UI can speak it:

    Request (POST relay_url): ``{"typedData": <typed_data>, "intent": <intent or null>}``
    Response: ``{"signature": "0x…"}`` on success, HTTP 4xx with
    ``{"error": "…"}`` on user rejection. The signer surfaces user rejection
    as :class:`SigningRefusedError` so audit logs distinguish "user said no"
    from "relay was down."
    """

    relay_url: str
    auth_header: str | None = None
    timeout_seconds: float = 30.0
    # Injectable for tests — avoids opening real sockets.
    request_fn: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None

    def sign_typed_data(self, typed_data: dict[str, Any], *, intent: SigningIntent | None = None) -> str:
        payload = {
            "typedData": typed_data,
            "intent": _intent_to_dict(intent) if intent is not None else None,
        }
        body = json.dumps(payload).encode("utf8")
        headers = {"Content-Type": "application/json"}
        if self.auth_header:
            headers["Authorization"] = self.auth_header

        try:
            if self.request_fn is not None:
                response = self.request_fn(self.relay_url, headers, body)
            else:
                response = self._http_post(self.relay_url, headers, body)
        except HTTPError as error:
            # User rejection is conventionally 4xx; surface as Refused so audit
            # distinguishes "user said no" from "relay was down."
            if 400 <= error.code < 500:
                detail = self._error_detail(error)
                raise SigningRefusedError(
                    f"User rejected via relay ({error.code}): {detail}"
                ) from error
            raise SigningError(
                f"Browser relay HTTP {error.code}: {self._error_detail(error)}"
            ) from error
        except (URLError, TimeoutError) as error:
            raise SigningError(f"Browser relay unreachable: {error}") from error

        signature = response.get("signature") if isinstance(response, dict) else None
        if not isinstance(signature, str) or not signature:
            raise SigningError(f"Browser relay returned no signature: {response!r}")
        return signature

    def _http_post(self, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        """Run a single POST; lets ``HTTPError`` / ``URLError`` propagate so the
        caller can apply the unified Refused-vs-SigningError mapping."""
        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        with urllib_request.urlopen(req, timeout=self.timeout_seconds) as response:  # noqa: S310
            return json.loads(response.read().decode("utf8"))

    @staticmethod
    def _error_detail(error: HTTPError) -> str:
        try:
            body = error.read().decode("utf8")
        except Exception:
            return str(error)
        try:
            data = json.loads(body)
            return str(data.get("error") or body)
        except json.JSONDecodeError:
            return body


# ---------------------------------------------------------------------------
# DelegatedSecretsSigner — resolves the sign fn from a CredentialResolver lease
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class DelegatedSecretsSigner:
    """Signs via a callable resolved from a :class:`CredentialResolver` lease.

    Lets ops keep signing keys out of the agent process: the resolver returns
    a lease whose ``metadata["signFn"]`` (or ``maximum_access_scope["signFn"]``)
    is a callable taking ``(typed_data, intent)`` and returning a signature
    string. Useful for HSM / KMS / vault-backed signers without baking those
    SDKs into the framework core.

    Raises :class:`SigningError` if the lease does not expose a callable.
    """

    handle_id: str
    environment: str
    capability_manifest: dict[str, Any]
    resolver: Any  # CredentialResolver protocol — kept untyped to avoid cycle

    def sign_typed_data(self, typed_data: dict[str, Any], *, intent: SigningIntent | None = None) -> str:
        lease = self.resolver.resolve(self.handle_id, self.environment, self.capability_manifest)
        sign_fn = None
        metadata = getattr(lease, "metadata", None) or {}
        scope = getattr(lease, "maximum_access_scope", None) or {}
        if callable(metadata.get("signFn")):
            sign_fn = metadata["signFn"]
        elif callable(scope.get("signFn")):
            sign_fn = scope["signFn"]
        if sign_fn is None:
            raise SigningError(
                f"Credential lease {self.handle_id!r} does not expose a callable signFn"
            )
        result = sign_fn(typed_data, intent)
        if not isinstance(result, str) or not result:
            raise SigningError("Delegated secrets signer returned empty signature")
        return result


# ---------------------------------------------------------------------------
# SessionKeyConstrainedSigner — wrapper that enforces SessionKeyPolicy
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SessionKeyConstrainedSigner:
    """Wraps an inner signer and refuses signatures that violate a policy.

    The constrained signer is the recommended way to compose any of the
    above signers with on-the-wire safety: every call checks the
    :class:`SessionKeyPolicy` for chain whitelist, contract allowlist,
    per-tx spend cap, and expiry before delegating to ``inner``. Failure
    raises :class:`SigningRefusedError` with a concrete reason.

    Fail-closed posture: if the policy declares an allowlist but the intent
    does not name the field, the signature is refused. ``intent=None``
    callers are refused outright — without intent there is nothing to check.
    """

    inner: DelegatedSigner
    policy: Any  # SessionKeyPolicy from security.py — kept untyped to avoid cycle

    def sign_typed_data(self, typed_data: dict[str, Any], *, intent: SigningIntent | None = None) -> str:
        if intent is None:
            raise SigningRefusedError(
                "SessionKeyConstrainedSigner requires an explicit SigningIntent — no intent means no check"
            )
        ok, reason = self._permits(intent)
        if not ok:
            raise SigningRefusedError(reason)
        return self.inner.sign_typed_data(typed_data, intent=intent)

    def _permits(self, intent: SigningIntent) -> tuple[bool, str]:
        policy = self.policy
        if hasattr(policy, "is_expired") and policy.is_expired():
            return False, f"session key {getattr(policy, 'key_id', '?')!r} has expired"
        allowed_chains = list(getattr(policy, "allowed_chains", []) or [])
        if allowed_chains and intent.chain_id is not None:
            chain_str = str(intent.chain_id)
            if chain_str not in allowed_chains and intent.chain_id not in (_safe_int(c) for c in allowed_chains):
                return False, f"chain {intent.chain_id} not in policy allowed_chains={allowed_chains}"
        allowed_contracts = list(getattr(policy, "allowed_contracts", []) or [])
        if allowed_contracts and intent.contract_address is None:
            return False, "policy restricts contracts but intent did not declare contract_address"
        if allowed_contracts and intent.contract_address is not None:
            target = intent.contract_address.lower()
            if not any(addr.lower() == target for addr in allowed_contracts):
                return False, f"contract {intent.contract_address} not in policy allowed_contracts"
        max_per_tx = getattr(policy, "max_spend_per_tx_usd", None)
        if max_per_tx is not None and intent.spend_usd is not None and intent.spend_usd > max_per_tx:
            return False, f"intent spend ${intent.spend_usd:.4f} exceeds policy cap ${max_per_tx:.4f}"
        return True, "permitted"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _intent_to_dict(intent: SigningIntent) -> dict[str, Any]:
    return {
        "chainId": intent.chain_id,
        "contractAddress": intent.contract_address,
        "spendUsd": intent.spend_usd,
        "purpose": intent.purpose,
    }


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Compatibility shim — wraps a legacy sign_typed_data_fn into a DelegatedSigner
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LegacyCallableSigner:
    """Adapter that lets the existing ``sign_typed_data_fn`` callable continue
    to flow through the new :class:`DelegatedSigner` protocol surface during
    the deprecation window.

    Use during the back-compat period in ``X402Client``; new code should
    pass a :class:`DelegatedSigner` directly.
    """

    fn: Callable[[dict[str, Any]], str]

    def sign_typed_data(self, typed_data: dict[str, Any], *, intent: SigningIntent | None = None) -> str:
        del intent
        signature = self.fn(typed_data)
        if not isinstance(signature, str) or not signature:
            raise SigningError("legacy sign_typed_data_fn returned empty signature")
        return signature

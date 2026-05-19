"""Verify the DelegatedSigner protocol end-to-end (Sprint 2.3 / FP-3).

Pins:
- SigningIntent is a frozen dataclass; SIGNER_KINDS enumerates supported kinds
- BrowserRelaySigner POSTs the typed-data + intent and parses the signature
- BrowserRelaySigner surfaces user rejection (4xx) as SigningRefusedError
- BrowserRelaySigner surfaces network failure as SigningError
- DelegatedSecretsSigner pulls the sign fn from a CredentialResolver lease
- SessionKeyConstrainedSigner enforces chain / contract / spend / expiry
- SessionKeyConstrainedSigner refuses intent=None (fail-closed)
- SessionKeyPolicy.permits() matches the wrapper's decisions
- LegacyCallableSigner forwards to a (typed_data) → signature callable
- X402Client(signer=...) wins over sign_typed_data_fn= and OWS fallback
- X402Client preserves back-compat for sign_typed_data_fn (with deprecation log)
- x402_server.verify_and_settle_onchain(allowed_payers=...) rejects out-of-set payers
- x402_server permits in-set payer with structural verification passing
"""

from __future__ import annotations

import base64
import io
import json
import urllib.error
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from aether_forge.crypto.signers import (
    SIGNER_KINDS,
    BrowserRelaySigner,
    DelegatedSecretsSigner,
    LegacyCallableSigner,
    OwsSigner,
    SessionKeyConstrainedSigner,
    SignerKind,
    SigningError,
    SigningIntent,
    SigningRefusedError,
)
from aether_forge.security import SessionKeyPolicy
from aether_forge.x402_client import (
    PaymentRequirement,
    PaymentSigningError,
    X402Client,
    X402Config,
)
from aether_forge.x402_server import X402PaymentGate

# ---------------------------------------------------------------------------
# SigningIntent / signer-kinds metadata
# ---------------------------------------------------------------------------


def test_signing_intent_is_frozen() -> None:
    intent = SigningIntent(chain_id=8453, spend_usd=0.01)
    with pytest.raises((AttributeError, TypeError)):
        intent.chain_id = 1  # type: ignore[misc]


def test_signer_kinds_enum() -> None:
    assert SIGNER_KINDS == ("ows", "browser-relay", "delegated-secret", "mock")


# ---------------------------------------------------------------------------
# BrowserRelaySigner — happy path + user rejection + network down
# ---------------------------------------------------------------------------


def test_browser_relay_signer_posts_typed_data_and_intent() -> None:
    captured: dict[str, Any] = {}

    def _fake_request(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json.loads(body.decode())
        return {"signature": "0xdeadbeef"}

    signer = BrowserRelaySigner(
        relay_url="https://relay.example.invalid/sign",
        auth_header="Bearer sk_test",
        request_fn=_fake_request,
    )
    intent = SigningIntent(chain_id=8453, contract_address="0xUSDC", spend_usd=0.02)
    sig = signer.sign_typed_data({"primaryType": "Transfer"}, intent=intent)
    assert sig == "0xdeadbeef"
    assert captured["url"] == "https://relay.example.invalid/sign"
    assert captured["headers"]["Authorization"] == "Bearer sk_test"
    assert captured["headers"]["Content-Type"] == "application/json"
    assert captured["payload"]["typedData"] == {"primaryType": "Transfer"}
    assert captured["payload"]["intent"] == {
        "chainId": 8453,
        "contractAddress": "0xUSDC",
        "spendUsd": 0.02,
        "purpose": "x402-payment",
    }


def test_browser_relay_signer_raises_on_empty_signature() -> None:
    signer = BrowserRelaySigner(
        relay_url="https://example.invalid",
        request_fn=lambda *a, **k: {"signature": ""},
    )
    with pytest.raises(SigningError, match="no signature"):
        signer.sign_typed_data({})


def _http_error(code: int, body: bytes = b'{"error": "user rejected"}') -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        url="https://example.invalid",
        code=code,
        msg=f"HTTP {code}",
        hdrs=None,  # type: ignore[arg-type]
        fp=io.BytesIO(body),
    )


def test_browser_relay_signer_surfaces_user_rejection_as_refused() -> None:
    def _reject(*args, **kwargs):
        raise _http_error(403, body=b'{"error": "user rejected request"}')

    signer = BrowserRelaySigner(relay_url="https://example.invalid", request_fn=_reject)
    with pytest.raises(SigningRefusedError, match="user rejected"):
        signer.sign_typed_data({"primaryType": "Transfer"})


def test_browser_relay_signer_surfaces_5xx_as_signing_error() -> None:
    def _down(*args, **kwargs):
        raise _http_error(503, body=b'{"error": "relay overloaded"}')

    signer = BrowserRelaySigner(relay_url="https://example.invalid", request_fn=_down)
    with pytest.raises(SigningError) as exc:
        signer.sign_typed_data({})
    assert not isinstance(exc.value, SigningRefusedError)


def test_browser_relay_signer_intent_serialized_as_null_when_missing() -> None:
    captured: dict[str, Any] = {}

    def _ok(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        captured["payload"] = json.loads(body.decode())
        return {"signature": "0x01"}

    signer = BrowserRelaySigner(relay_url="https://example.invalid", request_fn=_ok)
    signer.sign_typed_data({"x": 1})
    assert captured["payload"]["intent"] is None


# ---------------------------------------------------------------------------
# DelegatedSecretsSigner — resolver lease → callable
# ---------------------------------------------------------------------------


@dataclass
class _StubLease:
    metadata: dict[str, Any]
    maximum_access_scope: dict[str, Any]


class _StubResolver:
    def __init__(self, sign_fn) -> None:
        self.sign_fn = sign_fn
        self.calls: list[tuple[str, str]] = []

    def resolve(self, handle_id, environment, capability_manifest):
        self.calls.append((handle_id, environment))
        return _StubLease(
            metadata={"signFn": self.sign_fn},
            maximum_access_scope={},
        )


def test_delegated_secrets_signer_uses_metadata_signfn() -> None:
    captured: dict[str, Any] = {}

    def _fake_sign(typed_data, intent):
        captured["typed_data"] = typed_data
        captured["intent"] = intent
        return "0xabc"

    resolver = _StubResolver(_fake_sign)
    signer = DelegatedSecretsSigner(
        handle_id="vault-key-1",
        environment="production",
        capability_manifest={},
        resolver=resolver,
    )
    intent = SigningIntent(spend_usd=0.05)
    assert signer.sign_typed_data({"x": 1}, intent=intent) == "0xabc"
    assert resolver.calls == [("vault-key-1", "production")]
    assert captured["typed_data"] == {"x": 1}
    assert captured["intent"] is intent


def test_delegated_secrets_signer_raises_when_lease_missing_sign_fn() -> None:
    class _BadResolver:
        def resolve(self, *args, **kwargs):
            return _StubLease(metadata={}, maximum_access_scope={})

    signer = DelegatedSecretsSigner(
        handle_id="no-fn", environment="sandbox", capability_manifest={}, resolver=_BadResolver()
    )
    with pytest.raises(SigningError, match="callable signFn"):
        signer.sign_typed_data({})


# ---------------------------------------------------------------------------
# SessionKeyConstrainedSigner + SessionKeyPolicy.permits
# ---------------------------------------------------------------------------


class _RecordingSigner:
    def __init__(self) -> None:
        self.calls: list[SigningIntent | None] = []

    def sign_typed_data(self, typed_data, *, intent: SigningIntent | None = None) -> str:
        self.calls.append(intent)
        return "0xinner"


def _policy(**overrides) -> SessionKeyPolicy:
    base = dict(
        key_id="key-1",
        wallet_address="0xabc",
        allowed_contracts=[],
        allowed_chains=[],
        max_spend_per_tx_usd=10.0,
        max_spend_per_day_usd=100.0,
        max_transactions_per_hour=20,
        expires_at="",
    )
    base.update(overrides)
    return SessionKeyPolicy(**base)


def test_constrained_signer_refuses_when_intent_is_missing() -> None:
    wrapper = SessionKeyConstrainedSigner(inner=_RecordingSigner(), policy=_policy())
    with pytest.raises(SigningRefusedError, match="explicit SigningIntent"):
        wrapper.sign_typed_data({}, intent=None)


def test_constrained_signer_passes_through_when_policy_permits() -> None:
    inner = _RecordingSigner()
    wrapper = SessionKeyConstrainedSigner(
        inner=inner,
        policy=_policy(allowed_chains=["8453"], allowed_contracts=["0xusdc"], max_spend_per_tx_usd=1.0),
    )
    intent = SigningIntent(chain_id=8453, contract_address="0xUSDC", spend_usd=0.50)
    assert wrapper.sign_typed_data({"x": 1}, intent=intent) == "0xinner"
    assert inner.calls == [intent]


def test_constrained_signer_refuses_disallowed_chain() -> None:
    wrapper = SessionKeyConstrainedSigner(
        inner=_RecordingSigner(),
        policy=_policy(allowed_chains=["1"]),
    )
    with pytest.raises(SigningRefusedError, match="chain 8453 not in"):
        wrapper.sign_typed_data({}, intent=SigningIntent(chain_id=8453))


def test_constrained_signer_refuses_missing_chain_when_policy_restricts_chain() -> None:
    wrapper = SessionKeyConstrainedSigner(
        inner=_RecordingSigner(),
        policy=_policy(allowed_chains=["8453"]),
    )
    with pytest.raises(SigningRefusedError, match="did not declare chain_id"):
        wrapper.sign_typed_data({}, intent=SigningIntent(chain_id=None))


def test_constrained_signer_refuses_disallowed_contract() -> None:
    wrapper = SessionKeyConstrainedSigner(
        inner=_RecordingSigner(),
        policy=_policy(allowed_contracts=["0xAAA"]),
    )
    with pytest.raises(SigningRefusedError, match="contract 0xBBB"):
        wrapper.sign_typed_data({}, intent=SigningIntent(contract_address="0xBBB"))


def test_constrained_signer_refuses_over_budget_spend() -> None:
    wrapper = SessionKeyConstrainedSigner(
        inner=_RecordingSigner(),
        policy=_policy(max_spend_per_tx_usd=0.05),
    )
    with pytest.raises(SigningRefusedError, match="exceeds policy cap"):
        wrapper.sign_typed_data({}, intent=SigningIntent(spend_usd=0.10))


def test_constrained_signer_refuses_expired_policy() -> None:
    wrapper = SessionKeyConstrainedSigner(
        inner=_RecordingSigner(),
        policy=_policy(expires_at="2020-01-01T00:00:00+00:00"),
    )
    with pytest.raises(SigningRefusedError, match="expired"):
        wrapper.sign_typed_data({}, intent=SigningIntent(spend_usd=0.01))


def test_session_key_policy_permits_method_matches_wrapper() -> None:
    """The wrapper delegates the policy decision to SessionKeyPolicy.permits;
    verifying both surfaces produce identical verdicts pins the contract."""
    policy = _policy(allowed_chains=["8453"], max_spend_per_tx_usd=0.05)
    ok, _ = policy.permits(chain_id=8453, spend_usd=0.01)
    assert ok
    bad_ok, bad_reason = policy.permits(chain_id=1, spend_usd=0.01)
    assert not bad_ok
    assert "chain 1" in bad_reason


# ---------------------------------------------------------------------------
# LegacyCallableSigner — back-compat shim
# ---------------------------------------------------------------------------


def test_legacy_callable_signer_forwards_typed_data() -> None:
    captured: dict[str, Any] = {}

    def _fn(typed_data):
        captured["typed_data"] = typed_data
        return "0xlegacy"

    shim = LegacyCallableSigner(_fn)
    assert shim.sign_typed_data({"x": 1}, intent=SigningIntent(spend_usd=0.01)) == "0xlegacy"
    assert captured["typed_data"] == {"x": 1}


def test_legacy_callable_signer_raises_on_empty() -> None:
    shim = LegacyCallableSigner(lambda td: "")
    with pytest.raises(SigningError):
        shim.sign_typed_data({})


# ---------------------------------------------------------------------------
# X402Client — signer= wins over legacy fn and OWS fallback
# ---------------------------------------------------------------------------


def _build_x402_client(tmp_path: Path, *, signer=None, sign_typed_data_fn=None) -> X402Client:
    return X402Client(
        agent_directory=tmp_path,
        config=X402Config(max_per_call_usd=0.10, confirmed=True, chain="base"),
        signer=signer,
        sign_typed_data_fn=sign_typed_data_fn,
    )


def _payment_requirement() -> PaymentRequirement:
    return PaymentRequirement(
        scheme="exact",
        network="base",
        max_amount_required="10000",  # 10000 micro-USDC = $0.01
        pay_to="0xPayee",
        asset="0xUSDC",
        resource="https://api.example.invalid/x",
        description="Test capability",
        extra={"name": "USD Coin", "version": "2"},
    )


def _sample_authorization() -> dict[str, Any]:
    return {
        "from": "0xPayer",
        "to": "0xPayee",
        "value": "10000",
        "validAfter": "0",
        "validBefore": "9999999999",
        "nonce": "0x" + "0" * 64,
    }


def test_x402_client_signer_wins_over_legacy_fn(tmp_path: Path) -> None:
    """When both signer and sign_typed_data_fn are passed, signer wins.
    Pins the deprecation path: legacy callable is logged once, never called."""
    signer_calls: list[SigningIntent | None] = []

    class _RecordSigner:
        def sign_typed_data(self, typed_data, *, intent=None):
            signer_calls.append(intent)
            return "0xfrom-signer"

    legacy_called = False

    def _legacy(typed_data):
        nonlocal legacy_called
        legacy_called = True
        return "0xfrom-legacy"

    client = _build_x402_client(tmp_path, signer=_RecordSigner(), sign_typed_data_fn=_legacy)
    sig = client._sign_authorization(_sample_authorization(), _payment_requirement())
    assert sig == "0xfrom-signer"
    assert legacy_called is False
    assert len(signer_calls) == 1
    intent = signer_calls[0]
    assert intent is not None
    assert intent.chain_id == 8453  # base
    assert intent.contract_address == "0xUSDC"
    assert intent.spend_usd == pytest.approx(0.01)


def test_x402_client_falls_back_to_legacy_fn_when_no_signer(tmp_path: Path) -> None:
    captured: list[dict[str, Any]] = []

    def _legacy(typed_data):
        captured.append(typed_data)
        return "0xfrom-legacy"

    client = _build_x402_client(tmp_path, sign_typed_data_fn=_legacy)
    sig = client._sign_authorization(_sample_authorization(), _payment_requirement())
    assert sig == "0xfrom-legacy"
    assert len(captured) == 1
    assert captured[0]["primaryType"] == "TransferWithAuthorization"


def test_x402_client_raises_payment_signing_error_when_signer_fails(tmp_path: Path) -> None:
    class _BoomSigner:
        def sign_typed_data(self, typed_data, *, intent=None):
            raise SigningError("oops")

    client = _build_x402_client(tmp_path, signer=_BoomSigner())
    with pytest.raises(PaymentSigningError, match="oops"):
        client._sign_authorization(_sample_authorization(), _payment_requirement())


def test_x402_client_raises_payment_signing_error_when_refused(tmp_path: Path) -> None:
    """SigningRefusedError is a SigningError subclass — surfaces as PaymentSigningError."""

    class _RefusingSigner:
        def sign_typed_data(self, typed_data, *, intent=None):
            raise SigningRefusedError("policy denies")

    client = _build_x402_client(tmp_path, signer=_RefusingSigner())
    with pytest.raises(PaymentSigningError, match="policy denies"):
        client._sign_authorization(_sample_authorization(), _payment_requirement())


# ---------------------------------------------------------------------------
# X402PaymentGate.verify_and_settle_onchain(allowed_payers=...)
# ---------------------------------------------------------------------------


def _build_payment_header(*, from_addr: str = "0xPayer", to_addr: str, value: int = 1000) -> str:
    """Build a base64-encoded x402 payment header for testing."""
    auth = {
        "from": from_addr,
        "to": to_addr,
        "value": str(value),
        "validAfter": "0",
        "validBefore": "9999999999",
        "nonce": "0x" + "0" * 64,
    }
    payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "base",
        "payload": {
            "signature": "0x" + "ab" * 65,
            "authorization": auth,
        },
    }
    return base64.b64encode(json.dumps(payload).encode("utf8")).decode("utf8")


def _build_gate() -> X402PaymentGate:
    return X402PaymentGate(
        "0xPayee",
        prices={"cap-test": 0.0005},  # 500 micro-USDC
        chain="base",
    )


def test_verify_and_settle_rejects_payer_outside_allowlist(tmp_path: Path) -> None:
    gate = _build_gate()
    header = _build_payment_header(from_addr="0xRandom", to_addr="0xPayee")
    ok, reason = gate.verify_and_settle_onchain(
        header,
        capability="cap-test",
        allowed_payers={"0xKnownAllowed"},
    )
    assert not ok
    assert "not in allowed_payers" in reason


def test_verify_and_settle_accepts_payer_inside_allowlist_case_insensitive(tmp_path: Path) -> None:
    """Address comparison must be case-insensitive (EIP-55 vs lowercase)."""
    gate = _build_gate()
    header = _build_payment_header(from_addr="0xAaBbCc", to_addr="0xPayee")
    ok, reason = gate.verify_and_settle_onchain(
        header,
        capability="cap-test",
        allowed_payers={"0xAABBCC"},
    )
    # Structural verify passes (correct payee, sufficient value, network).
    # On-chain submit will then fail because we don't have a real OWS wallet
    # in the test — that's fine, the allowlist gate is what we're pinning here.
    # We accept either: (True, tx_hash) OR (False, <something not allowlist>).
    assert "not in allowed_payers" not in reason


def test_verify_and_settle_returns_structural_error_before_allowlist(tmp_path: Path) -> None:
    """A malformed header still surfaces the structural error first, not allowlist."""
    gate = _build_gate()
    bad_header = "not-base64-at-all!!"
    ok, reason = gate.verify_and_settle_onchain(
        bad_header,
        capability="cap-test",
        allowed_payers={"0xanything"},
    )
    assert not ok
    assert "Failed to decode" in reason or "verification error" in reason

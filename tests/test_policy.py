from __future__ import annotations

from pathlib import Path

from aether_forge.crypto import MockCryptoExecutionRouter
from aether_forge.policy import NativePolicyGate
from aether_forge.runtime import RuntimeSession, SessionStatus, StepKind, StepProposal, load_artifact_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def test_policy_gate_uses_policy_bundle_version_and_limit() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    gate = NativePolicyGate.from_policy_bundle(artifacts.policy_bundle)
    capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-exchange-order"
    )

    decision = gate.evaluate_action(
        capability=capability,
        credential_handles=artifacts.capability_manifest["credentialHandles"],
        environment="sandbox",
        action_payload={"requested_notional_usd": 150000},
    )

    assert decision.policy_bundle_version == "0.1.0"
    assert decision.final_disposition == "hold"
    assert "exposure-limit" in decision.reason_ids


def test_runtime_holds_when_policy_bundle_requires_approval_for_environment() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    artifacts.policy_bundle["rules"]["requireApprovalEnvironments"] = ["sandbox"]

    class ApprovalPolicyPlanner:
        def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Attempt an order without pre-approval.",
                    capability_id="cap-exchange-order",
                    payload={"requested_notional_usd": 5000},
                )
            ]

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=ApprovalPolicyPlanner(),
        execution_router=MockCryptoExecutionRouter(),
    )

    status = session.run()

    assert status == SessionStatus.HOLD
    assert "approval-required-by-policy-bundle" in session.step_ledger[-1].message


def test_policy_gate_denies_wallet_chain_outside_allowed_set() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    artifacts.policy_bundle["rules"]["walletAllowedChains"] = ["evm"]
    gate = NativePolicyGate.from_policy_bundle(artifacts.policy_bundle)
    capability = {
        "capabilityId": "cap-wallet-manage",
        "kind": "wallet-action",
        "provider": "ows-wallet",
        "allowedEnvironments": ["sandbox"],
        "providerConstraints": {"chain": "solana"},
        "effectSemantics": {
            "idempotencyClass": "conditionally-idempotent",
            "duplicateSubmitBehavior": "none",
            "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
            "compensationClass": "compensatable",
        },
    }

    decision = gate.evaluate_action(
        capability=capability,
        credential_handles=[],
        environment="sandbox",
        action_payload={"wallet_action": "get-account", "chain": "solana"},
    )

    assert decision.final_disposition == "deny"
    assert "wallet-chain-not-allowed" in decision.reason_ids


def test_policy_gate_denies_wallet_action_missing_constrained_chain() -> None:
    gate = NativePolicyGate(wallet_allowed_chains=["evm"])
    capability = {
        "capabilityId": "cap-wallet-manage",
        "kind": "wallet-action",
        "provider": "ows-wallet",
        "allowedEnvironments": ["sandbox"],
        "providerConstraints": {},
        "effectSemantics": {
            "idempotencyClass": "conditionally-idempotent",
            "duplicateSubmitBehavior": "none",
            "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
            "compensationClass": "compensatable",
        },
    }

    decision = gate.evaluate_action(
        capability=capability,
        credential_handles=[],
        environment="sandbox",
        action_payload={"wallet_action": "send-transaction", "amount": 1},
    )

    assert decision.final_disposition == "deny"
    assert "wallet-chain-missing" in decision.reason_ids


def test_policy_gate_holds_wallet_transfer_above_limit() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    artifacts.policy_bundle["rules"]["maxWalletTransferAmount"] = 2
    gate = NativePolicyGate.from_policy_bundle(artifacts.policy_bundle)
    capability = {
        "capabilityId": "cap-wallet-manage",
        "kind": "wallet-action",
        "provider": "ows-wallet",
        "allowedEnvironments": ["sandbox"],
        "providerConstraints": {"chain": "evm"},
        "effectSemantics": {
            "idempotencyClass": "conditionally-idempotent",
            "duplicateSubmitBehavior": "none",
            "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
            "compensationClass": "compensatable",
        },
    }

    decision = gate.evaluate_action(
        capability=capability,
        credential_handles=[],
        environment="sandbox",
        action_payload={"wallet_action": "send-transaction", "chain": "evm", "amount": 3},
    )

    assert decision.final_disposition == "hold"
    assert "wallet-transfer-limit" in decision.reason_ids


def test_policy_gate_denies_invalid_wallet_transfer_amounts() -> None:
    gate = NativePolicyGate(wallet_allowed_chains=["evm"], max_wallet_transfer_amount=2)
    capability = {
        "capabilityId": "cap-wallet-manage",
        "kind": "wallet-action",
        "provider": "ows-wallet",
        "allowedEnvironments": ["sandbox"],
        "providerConstraints": {"chain": "evm"},
        "effectSemantics": {
            "idempotencyClass": "conditionally-idempotent",
            "duplicateSubmitBehavior": "none",
            "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
            "compensationClass": "compensatable",
        },
    }

    for amount in ("1", -1, 0):
        decision = gate.evaluate_action(
            capability=capability,
            credential_handles=[],
            environment="sandbox",
            action_payload={"wallet_action": "send-transaction", "chain": "evm", "amount": amount},
        )
        assert decision.final_disposition == "deny"
        assert "wallet-amount-invalid" in decision.reason_ids


def test_policy_gate_requires_wallet_approval_in_configured_environment() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    artifacts.policy_bundle["rules"]["requireWalletApprovalEnvironments"] = ["sandbox"]
    gate = NativePolicyGate.from_policy_bundle(artifacts.policy_bundle)
    capability = {
        "capabilityId": "cap-wallet-manage",
        "kind": "wallet-action",
        "provider": "ows-wallet",
        "allowedEnvironments": ["sandbox"],
        "providerConstraints": {"chain": "evm"},
        "effectSemantics": {
            "idempotencyClass": "conditionally-idempotent",
            "duplicateSubmitBehavior": "none",
            "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
            "compensationClass": "compensatable",
        },
    }

    decision = gate.evaluate_action(
        capability=capability,
        credential_handles=[],
        environment="sandbox",
        action_payload={"wallet_action": "sign-transaction", "chain": "evm", "tx_hex": "0xabc"},
    )

    assert decision.final_disposition == "hold"
    assert "approval-required-by-wallet-policy" in decision.reason_ids

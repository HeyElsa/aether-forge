"""Native policy gate for Aether Forge runtime."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


SIDE_EFFECTING_KINDS = {"wallet-action", "exchange-action", "onchain-action"}

# Default memory sensitivity rules per environment tier.
# Keys are environment names; values are sets of denied sensitivity levels.
_DEFAULT_MEMORY_SENSITIVITY_DENIED: dict[str, set[str]] = {
    "sandbox": set(),
    "paper": {"restricted"},
    "canary-live": {"restricted"},
    "production": {"confidential", "restricted"},
}


@dataclass(slots=True)
class PolicyDecision:
    decision_id: str
    policy_bundle_version: str
    input_scope: dict[str, Any]
    rule_matches: list[str]
    severity: str
    approval_path: list[str]
    final_disposition: str
    reason_ids: list[str] = field(default_factory=list)


class NativePolicyGate:
    def __init__(
        self,
        policy_bundle_version: str = "native-policy-0.1.0",
        max_notional_usd: int = 100_000,
        require_approval_environments: list[str] | None = None,
        wallet_allowed_chains: list[str] | None = None,
        max_wallet_transfer_amount: float | None = None,
        require_wallet_approval_environments: list[str] | None = None,
        enforce_staleness_checks: bool = True,
        memory_rules: dict[str, Any] | None = None,
    ) -> None:
        self.policy_bundle_version = policy_bundle_version
        self.max_notional_usd = max_notional_usd
        self.require_approval_environments = set(require_approval_environments or [])
        self.wallet_allowed_chains = set(wallet_allowed_chains or [])
        self.max_wallet_transfer_amount = max_wallet_transfer_amount
        self.require_wallet_approval_environments = set(require_wallet_approval_environments or [])
        self.enforce_staleness_checks = enforce_staleness_checks
        self.memory_rules: dict[str, Any] = memory_rules or {}

    @classmethod
    def from_policy_bundle(cls, policy_bundle: dict[str, Any]) -> "NativePolicyGate":
        rules = policy_bundle.get("rules", {}) if isinstance(policy_bundle.get("rules"), dict) else {}
        return cls(
            policy_bundle_version=str(policy_bundle.get("artifactVersion", "native-policy-0.1.0")),
            max_notional_usd=int(rules.get("maxNotionalUsd", 100_000)),
            require_approval_environments=list(rules.get("requireApprovalEnvironments", [])),
            wallet_allowed_chains=list(rules.get("walletAllowedChains", [])),
            max_wallet_transfer_amount=rules.get("maxWalletTransferAmount"),
            require_wallet_approval_environments=list(rules.get("requireWalletApprovalEnvironments", [])),
            enforce_staleness_checks=bool(rules.get("enforceStalenessChecks", True)),
            memory_rules=rules.get("memoryRules") if isinstance(rules.get("memoryRules"), dict) else None,
        )

    def evaluate_action(
        self,
        capability: dict[str, Any],
        credential_handles: list[dict[str, Any]],
        environment: str,
        action_payload: dict[str, Any],
    ) -> PolicyDecision:
        capability_id = str(capability.get("capabilityId", "unknown-capability"))
        handle_id = capability.get("credentialHandleId")
        kind = capability.get("kind")
        allowed_environments = set(capability.get("allowedEnvironments", []))

        reasons: list[str] = []
        rule_matches: list[str] = []
        disposition = "allow"
        severity = "info"

        if environment not in allowed_environments:
            reasons.append("environment-not-allowed")
            rule_matches.append("capability.environment")
            disposition = "deny"
            severity = "error"

        handle = None
        if handle_id is not None:
            for candidate in credential_handles:
              if candidate.get("handleId") == handle_id:
                  handle = candidate
                  break
            if handle is None:
                reasons.append("credential-handle-missing")
                rule_matches.append("credential.handle.existence")
                disposition = "deny"
                severity = "error"
            elif environment not in set(handle.get("allowedEnvironments", [])):
                reasons.append("credential-handle-scope")
                rule_matches.append("credential.handle.environment")
                disposition = "deny"
                severity = "error"

        provider_constraints = capability.get("providerConstraints", {})
        max_notional = provider_constraints.get("maxNotionalUsd", self.max_notional_usd)
        requested_notional = action_payload.get("requested_notional_usd")
        if isinstance(requested_notional, (int, float)) and requested_notional > max_notional:
            reasons.append("exposure-limit")
            rule_matches.append("risk.max-notional")
            disposition = "hold"
            severity = "error"

        max_staleness_ms = provider_constraints.get("stalenessBudgetMs")
        market_data_age_ms = action_payload.get("market_data_age_ms")
        if (
            self.enforce_staleness_checks
            and isinstance(max_staleness_ms, (int, float))
            and isinstance(market_data_age_ms, (int, float))
            and market_data_age_ms > max_staleness_ms
        ):
            reasons.append("stale-market-data")
            rule_matches.append("data.staleness-budget")
            disposition = "hold"
            severity = "error"

        if capability.get("requiredApproval") and not action_payload.get("approval_token"):
            reasons.append("approval-required")
            rule_matches.append("approval.required")
            disposition = "hold"
            severity = "warning"

        if kind in SIDE_EFFECTING_KINDS and environment in self.require_approval_environments and not action_payload.get("approval_token"):
            reasons.append("approval-required-by-policy-bundle")
            rule_matches.append("approval.environment-policy")
            disposition = "hold"
            severity = "warning"

        wallet_action = action_payload.get("wallet_action")
        wallet_chain = action_payload.get("chain") or provider_constraints.get("chain")
        if kind == "wallet-action" and self.wallet_allowed_chains and isinstance(wallet_chain, str):
            if wallet_chain not in self.wallet_allowed_chains:
                reasons.append("wallet-chain-not-allowed")
                rule_matches.append("wallet.allowed-chains")
                disposition = "deny"
                severity = "error"

        wallet_amount = action_payload.get("amount")
        if (
            kind == "wallet-action"
            and isinstance(wallet_amount, (int, float))
            and self.max_wallet_transfer_amount is not None
            and wallet_amount > self.max_wallet_transfer_amount
        ):
            reasons.append("wallet-transfer-limit")
            rule_matches.append("wallet.max-transfer-amount")
            disposition = "hold"
            severity = "error"

        if (
            kind == "wallet-action"
            and environment in self.require_wallet_approval_environments
            and wallet_action in {"send-transaction", "sign-transaction"}
            and not action_payload.get("approval_token")
        ):
            reasons.append("approval-required-by-wallet-policy")
            rule_matches.append("wallet.approval.environment-policy")
            disposition = "hold"
            severity = "warning"

        if kind in SIDE_EFFECTING_KINDS and not capability.get("effectSemantics"):
            reasons.append("effect-semantics-missing")
            rule_matches.append("capability.effect-semantics")
            disposition = "deny"
            severity = "error"

        # --- Memory capability policy enforcement ---
        if capability_id.startswith("memory."):
            # Resolve sensitivity deny-list: bundle overrides take precedence
            bundle_denied = self.memory_rules.get("sensitivityDenied", {})
            if isinstance(bundle_denied, dict) and bundle_denied:
                env_denied: set[str] = set(bundle_denied.get(environment, []))
            else:
                env_denied = _DEFAULT_MEMORY_SENSITIVITY_DENIED.get(environment, set())

            if capability_id == "memory.write":
                sensitivity = str(action_payload.get("sensitivity", "")).lower()
                if sensitivity and sensitivity in env_denied:
                    reasons.append("memory-sensitivity-exceeds-environment")
                    rule_matches.append("memory.write.sensitivity")
                    disposition = "deny"
                    severity = "error"

            elif capability_id == "memory.promote":
                # PRD non-negotiable: promotions always require manual approval.
                reasons.append("memory-promotion-requires-approval")
                rule_matches.append("memory.promote.approval")
                disposition = "hold"
                severity = "warning"

            # memory.read — allowed by default; no additional restrictions.

        for rule_id in rule_matches:
            logger.debug("Policy rule matched: %s severity=%s", rule_id, severity)

        if disposition == "deny":
            logger.warning("Policy denied: %s reasons=%s", capability_id, reasons)

        if any(r.startswith("approval-required") or r == "memory-promotion-requires-approval" for r in reasons):
            logger.info("Approval required: %s", capability_id)

        return PolicyDecision(
            decision_id=f"policy_{uuid4().hex}",
            policy_bundle_version=self.policy_bundle_version,
            input_scope={
                "capabilityId": capability_id,
                "environment": environment,
                "payload": action_payload,
            },
            rule_matches=rule_matches,
            severity=severity,
            approval_path=["manual"] if disposition == "hold" and any(
                reason.startswith("approval-required") or reason == "memory-promotion-requires-approval"
                for reason in reasons
            ) else [],
            final_disposition=disposition,
            reason_ids=reasons,
        )

"""ERC-8126 agent trust evaluation and risk scoring protocol."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class VerificationResult:
    """Result of a single verification check."""

    verification_type: str  # "ETV", "SCV", "WAV", "WV"
    score: int  # 0-100 (0=low risk, 100=critical)
    details: dict[str, Any] = field(default_factory=dict)
    proof_id: str = ""
    proof_url: str = ""


@dataclass(slots=True)
class TrustAssessment:
    """Complete trust assessment for an agent."""

    agent_id: str
    overall_score: int  # 0-100
    risk_tier: str  # "low", "moderate", "elevated", "high", "critical"
    verifications: list[VerificationResult] = field(default_factory=list)
    assessed_at: str = ""  # ISO datetime

    @staticmethod
    def risk_tier_from_score(score: int) -> str:
        """Map a numeric risk score to a human-readable tier label."""
        if score <= 20:
            return "low"
        if score <= 40:
            return "moderate"
        if score <= 60:
            return "elevated"
        if score <= 80:
            return "high"
        return "critical"


class ERC8126Client:
    """Client for ERC-8126 agent verification.

    Builds data structures and transaction payloads for trust
    registration and assessment.  Actual on-chain submission requires
    a web3 provider and is left to the caller.
    """

    def __init__(
        self,
        rpc_url: str | None = None,
        registry_address: str | None = None,
    ) -> None:
        self.rpc_url = rpc_url
        self.registry_address = registry_address

    def build_registration_payload(
        self,
        name: str,
        description: str,
        wallet_address: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build registration transaction payload."""
        return {
            "method": "registerVerifier",
            "params": {
                "name": name,
                "description": description,
                "wallet_address": wallet_address,
                "url": url,
                "registry_address": self.registry_address or "",
                **kwargs,
            },
        }

    def assess_trust_from_policy(
        self,
        agent_spec: dict[str, Any],
        policy_bundle: dict[str, Any],
    ) -> TrustAssessment:
        """Perform a local trust assessment based on forge artifacts.

        Checks:
        - Policy completeness
        - Approval requirements
        - Environment restrictions
        - Credential handle usage
        - Effect semantics declarations
        """
        verifications: list[VerificationResult] = []
        agent_id = str(agent_spec.get("agent_id", agent_spec.get("name", "unknown")))

        # --- Policy completeness (SCV) ---
        policy_keys = {"rules", "environments", "approval_paths"}
        present = policy_keys & set(policy_bundle.keys())
        completeness_ratio = len(present) / len(policy_keys) if policy_keys else 1.0
        completeness_score = int((1.0 - completeness_ratio) * 100)
        verifications.append(
            VerificationResult(
                verification_type="SCV",
                score=completeness_score,
                details={
                    "present_keys": sorted(present),
                    "expected_keys": sorted(policy_keys),
                },
            )
        )

        # --- Approval requirements (WAV) ---
        approval_paths = policy_bundle.get("approval_paths", [])
        if not approval_paths:
            approval_score = 60  # No approval path defined is risky.
        else:
            approval_score = 10
        verifications.append(
            VerificationResult(
                verification_type="WAV",
                score=approval_score,
                details={"approval_paths_count": len(approval_paths)},
            )
        )

        # --- Environment restrictions (ETV) ---
        environments = policy_bundle.get("environments", [])
        has_prod_guard = any(
            env.get("name") in ("production", "canary-live")
            for env in environments
            if isinstance(env, dict)
        )
        env_score = 15 if has_prod_guard else 50
        verifications.append(
            VerificationResult(
                verification_type="ETV",
                score=env_score,
                details={
                    "environment_count": len(environments),
                    "has_production_guard": has_prod_guard,
                },
            )
        )

        # --- Credential / effect semantics (WV) ---
        effects = agent_spec.get("effects", [])
        credentials = agent_spec.get("credentials", [])
        wv_score = 0
        if not effects:
            wv_score += 25  # No declared effects is suspicious.
        if not credentials:
            wv_score += 15  # No credential handles declared.
        verifications.append(
            VerificationResult(
                verification_type="WV",
                score=min(wv_score, 100),
                details={
                    "declared_effects": len(effects),
                    "credential_handles": len(credentials),
                },
            )
        )

        # Overall score is the average across all verification checks.
        overall = (
            sum(v.score for v in verifications) // len(verifications)
            if verifications
            else 0
        )
        risk_tier = TrustAssessment.risk_tier_from_score(overall)

        return TrustAssessment(
            agent_id=agent_id,
            overall_score=overall,
            risk_tier=risk_tier,
            verifications=verifications,
            assessed_at=datetime.now(timezone.utc).isoformat(),
        )


def assess_agent_trust(artifacts: dict[str, Any]) -> TrustAssessment:
    """Assess trust score from forge artifact bundle without on-chain interaction."""
    agent_spec = artifacts.get("agent-spec", {})
    policy_bundle = artifacts.get("policy-bundle", {})
    client = ERC8126Client()
    return client.assess_trust_from_policy(agent_spec, policy_bundle)

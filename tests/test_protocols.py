"""Tests for ERC-8004, ERC-8126, ERC-8183, and x402 protocol modules."""

from __future__ import annotations

from aether_forge.protocols.erc8004 import (
    AgentCard,
    generate_agent_card_from_artifacts,
)
from aether_forge.protocols.erc8126 import (
    TrustAssessment,
    assess_agent_trust,
)
from aether_forge.protocols.erc8183 import JobSpec, JobStatus
from aether_forge.protocols.x402 import (
    PaymentRequirement,
    parse_402_response,
    search_402_directory,
)

# ── ERC-8004 ──────────────────────────────────────────────────────────────


def test_agent_card_to_json_round_trip() -> None:
    card = AgentCard(
        name="test-agent",
        description="A test agent",
        services=[
            {
                "endpoint": "https://example.com/api",
                "version": "1.0",
                "skills": ["summarize"],
                "domains": ["text"],
                "type": "llm",
            }
        ],
        x402_support=True,
        active=True,
        supported_trust_types=["erc8126", "erc8183"],
    )
    data = card.to_json()
    restored = AgentCard.from_json(data)

    assert restored.name == card.name
    assert restored.description == card.description
    assert restored.services == card.services
    assert restored.x402_support == card.x402_support
    assert restored.active == card.active
    assert restored.supported_trust_types == card.supported_trust_types


def test_generate_agent_card_from_artifacts() -> None:
    artifacts = {
        "agent-spec": {
            "name": "forge-bot",
            "description": "Automated forge agent",
        },
        "capabilities": [
            {
                "endpoint": "https://forge.example/v1",
                "version": "2.0",
                "skills": ["deploy", "monitor"],
                "domains": ["infra"],
                "type": "devops",
            }
        ],
        "x402_support": True,
    }
    card = generate_agent_card_from_artifacts(artifacts)

    assert card.name == "forge-bot"
    assert card.description == "Automated forge agent"
    assert len(card.services) == 1
    assert card.services[0]["version"] == "2.0"
    assert card.services[0]["skills"] == ["deploy", "monitor"]
    assert card.x402_support is True


# ── ERC-8126 ──────────────────────────────────────────────────────────────


def test_trust_assessment_risk_tiers() -> None:
    assert TrustAssessment.risk_tier_from_score(10) == "low"
    assert TrustAssessment.risk_tier_from_score(30) == "moderate"
    assert TrustAssessment.risk_tier_from_score(50) == "elevated"
    assert TrustAssessment.risk_tier_from_score(70) == "high"
    assert TrustAssessment.risk_tier_from_score(90) == "critical"


def test_assess_agent_trust_from_artifacts() -> None:
    artifacts = {
        "agent-spec": {
            "name": "my-agent",
            "effects": ["write-file"],
            "credentials": ["api-key-handle"],
        },
        "policy-bundle": {
            "rules": [{"action": "allow"}],
            "environments": [{"name": "production"}],
            "approval_paths": [{"approver": "human"}],
        },
    }
    assessment = assess_agent_trust(artifacts)

    assert isinstance(assessment.overall_score, int)
    assert 0 <= assessment.overall_score <= 100
    assert assessment.risk_tier in ("low", "moderate", "elevated", "high", "critical")
    assert len(assessment.verifications) > 0
    vtypes = {v.verification_type for v in assessment.verifications}
    assert "SCV" in vtypes
    assert "WAV" in vtypes


# ── ERC-8183 ──────────────────────────────────────────────────────────────


def test_job_spec_serialization() -> None:
    spec = JobSpec(
        description="Build a dashboard",
        client_address="0xAAA",
        provider_address="0xBBB",
        evaluator_address="0xCCC",
        budget_amount=5000,
        budget_token="0xUSDC",
        expires_at="2026-12-31T23:59:59Z",
        hook_address="0xHOOK",
        deliverables=["dashboard.html", "report.pdf"],
    )
    data = spec.to_json()
    restored = JobSpec.from_json(data)

    assert restored.description == spec.description
    assert restored.client_address == spec.client_address
    assert restored.provider_address == spec.provider_address
    assert restored.budget_amount == spec.budget_amount
    assert restored.deliverables == spec.deliverables
    assert restored.hook_address == spec.hook_address


def test_job_status_lifecycle() -> None:
    expected = {"open", "funded", "submitted", "completed", "rejected", "expired"}
    actual = {s.value for s in JobStatus}
    assert actual == expected


# ── x402 ──────────────────────────────────────────────────────────────────


def test_payment_requirement_header_round_trip() -> None:
    req = PaymentRequirement(
        scheme="exact",
        network="base-sepolia",
        max_amount_required=1000,
        resource="https://api.example.com/data",
        description="API call",
        mime_type="application/json",
        pay_to="0xPAYABLE",
        required_deadline_seconds=300,
    )
    header = req.to_header()
    restored = PaymentRequirement.from_header(header)

    assert restored.scheme == req.scheme
    assert restored.network == req.network
    assert restored.max_amount_required == req.max_amount_required
    assert restored.resource == req.resource
    assert restored.description == req.description
    assert restored.pay_to == req.pay_to
    assert restored.required_deadline_seconds == req.required_deadline_seconds


def test_parse_402_response_non_402() -> None:
    result = parse_402_response(200, {"X-Payment": "{}"})
    assert result is None


def test_search_402_directory_returns_list() -> None:
    result = search_402_directory()
    assert isinstance(result, list)

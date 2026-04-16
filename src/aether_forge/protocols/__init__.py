"""On-chain agent economy protocol modules for Aether Forge."""

from aether_forge.protocols.erc8004 import (
    AgentCard,
    AgentIdentity,
    ERC8004Client,
    generate_agent_card_from_artifacts,
)
from aether_forge.protocols.erc8126 import (
    ERC8126Client,
    TrustAssessment,
    VerificationResult,
    assess_agent_trust,
)
from aether_forge.protocols.erc8183 import (
    ERC8183Client,
    JobRecord,
    JobSpec,
    JobStatus,
    create_job_from_scenario,
)
from aether_forge.protocols.x402 import (
    PaymentPayload,
    PaymentReceipt,
    PaymentRequirement,
    X402Client,
    X402PaymentFlow,
    parse_402_response,
    search_402_directory,
)

__all__ = [
    "AgentCard",
    "AgentIdentity",
    "ERC8004Client",
    "ERC8126Client",
    "ERC8183Client",
    "JobRecord",
    "JobSpec",
    "JobStatus",
    "PaymentPayload",
    "PaymentReceipt",
    "PaymentRequirement",
    "TrustAssessment",
    "VerificationResult",
    "X402Client",
    "X402PaymentFlow",
    "assess_agent_trust",
    "create_job_from_scenario",
    "generate_agent_card_from_artifacts",
    "parse_402_response",
    "search_402_directory",
]

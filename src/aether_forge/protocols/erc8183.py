"""ERC-8183 agent-to-agent commerce protocol (escrow, evaluation, settlement)."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class JobStatus(Enum):
    """Lifecycle status of an ERC-8183 job."""

    OPEN = "open"
    FUNDED = "funded"
    SUBMITTED = "submitted"
    COMPLETED = "completed"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(slots=True)
class JobSpec:
    """A job specification following ERC-8183."""

    description: str
    client_address: str
    provider_address: str = ""
    evaluator_address: str = ""
    budget_amount: int = 0  # in token smallest unit
    budget_token: str = ""  # ERC-20 token address
    expires_at: str = ""  # ISO datetime
    hook_address: str = ""  # optional IACPHook contract
    deliverables: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        """Serialize the job spec to a JSON-compatible dictionary."""
        return {
            "description": self.description,
            "client_address": self.client_address,
            "provider_address": self.provider_address,
            "evaluator_address": self.evaluator_address,
            "budget_amount": self.budget_amount,
            "budget_token": self.budget_token,
            "expires_at": self.expires_at,
            "hook_address": self.hook_address,
            "deliverables": list(self.deliverables),
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> JobSpec:
        """Deserialize a job spec from a JSON-compatible dictionary."""
        return cls(
            description=data["description"],
            client_address=data["client_address"],
            provider_address=data.get("provider_address", ""),
            evaluator_address=data.get("evaluator_address", ""),
            budget_amount=int(data.get("budget_amount", 0)),
            budget_token=data.get("budget_token", ""),
            expires_at=data.get("expires_at", ""),
            hook_address=data.get("hook_address", ""),
            deliverables=list(data.get("deliverables", [])),
        )


@dataclass(slots=True)
class JobRecord:
    """Record of a job's lifecycle."""

    job_id: str
    spec: JobSpec
    status: JobStatus
    created_at: str
    funded_at: str = ""
    submitted_at: str = ""
    completed_at: str = ""
    deliverable_hash: str = ""  # bytes32 hash of deliverable
    completion_reason: str = ""
    rejection_reason: str = ""
    tx_hash: str = ""


class ERC8183Client:
    """Client for ERC-8183 agentic commerce.

    This class builds data structures and transaction payloads.  Actual
    on-chain submission requires a web3 provider and is intentionally
    left to the caller.
    """

    def __init__(
        self,
        rpc_url: str | None = None,
        contract_address: str | None = None,
    ) -> None:
        self.rpc_url = rpc_url
        self.contract_address = contract_address

    def build_create_job_payload(self, spec: JobSpec) -> dict[str, Any]:
        """Build transaction payload for creating a job."""
        job_id = uuid.uuid4().hex
        spec_json = json.dumps(spec.to_json(), separators=(",", ":"))
        return {
            "method": "createJob",
            "params": {
                "job_id": job_id,
                "spec_json": spec_json,
                "client_address": spec.client_address,
                "provider_address": spec.provider_address,
                "evaluator_address": spec.evaluator_address,
                "budget_amount": spec.budget_amount,
                "budget_token": spec.budget_token,
                "expires_at": spec.expires_at,
                "hook_address": spec.hook_address,
                "contract_address": self.contract_address or "",
            },
        }

    def build_fund_payload(
        self, job_id: str, amount: int
    ) -> dict[str, Any]:
        """Build payload to fund a job's escrow."""
        return {
            "method": "fundJob",
            "params": {
                "job_id": job_id,
                "amount": amount,
                "contract_address": self.contract_address or "",
            },
        }

    def build_submit_payload(
        self, job_id: str, deliverable_hash: str
    ) -> dict[str, Any]:
        """Build payload to submit work."""
        return {
            "method": "submitDeliverable",
            "params": {
                "job_id": job_id,
                "deliverable_hash": deliverable_hash,
                "contract_address": self.contract_address or "",
            },
        }

    def build_complete_payload(
        self, job_id: str, reason_hash: str
    ) -> dict[str, Any]:
        """Build payload to mark job completed (evaluator only)."""
        return {
            "method": "completeJob",
            "params": {
                "job_id": job_id,
                "reason_hash": reason_hash,
                "contract_address": self.contract_address or "",
            },
        }

    def build_reject_payload(
        self, job_id: str, reason_hash: str
    ) -> dict[str, Any]:
        """Build payload to reject work."""
        return {
            "method": "rejectDeliverable",
            "params": {
                "job_id": job_id,
                "reason_hash": reason_hash,
                "contract_address": self.contract_address or "",
            },
        }


def create_job_from_scenario(
    scenario: dict[str, Any], agent_spec: dict[str, Any]
) -> JobSpec:
    """Create a JobSpec from a forge scenario and agent spec.

    Extracts job parameters from the scenario configuration and maps
    the agent spec wallet and evaluator details into the job.
    """
    description = scenario.get("description", "")
    client_address = agent_spec.get("wallet_address", "")
    provider_address = scenario.get("provider_address", "")
    evaluator_address = scenario.get("evaluator_address", "")

    budget = scenario.get("budget", {})
    budget_amount = int(budget.get("amount", 0))
    budget_token = budget.get("token", "")

    expires_at = scenario.get("expires_at", "")
    hook_address = scenario.get("hook_address", "")
    deliverables = list(scenario.get("deliverables", []))

    return JobSpec(
        description=description,
        client_address=client_address,
        provider_address=provider_address,
        evaluator_address=evaluator_address,
        budget_amount=budget_amount,
        budget_token=budget_token,
        expires_at=expires_at,
        hook_address=hook_address,
        deliverables=deliverables,
    )

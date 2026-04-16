"""ERC-8004 agent identity, reputation, and on-chain registry protocol."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AgentCard:
    """Agent Card metadata following ERC-8004 Agent Card JSON schema."""

    name: str
    description: str
    services: list[dict[str, Any]]  # [{endpoint, version, skills, domains, type}]
    x402_support: bool = False
    active: bool = True
    supported_trust_types: list[str] = field(
        default_factory=lambda: ["erc8126"]
    )

    def to_json(self) -> dict[str, Any]:
        """Serialize the agent card to a JSON-compatible dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "services": self.services,
            "x402_support": self.x402_support,
            "active": self.active,
            "supported_trust_types": self.supported_trust_types,
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> AgentCard:
        """Deserialize an agent card from a JSON-compatible dictionary."""
        return cls(
            name=data["name"],
            description=data["description"],
            services=data.get("services", []),
            x402_support=data.get("x402_support", False),
            active=data.get("active", True),
            supported_trust_types=data.get(
                "supported_trust_types", ["erc8126"]
            ),
        )


@dataclass(slots=True)
class AgentIdentity:
    """On-chain agent identity reference."""

    agent_id: int
    chain_id: int
    registry_address: str
    wallet_address: str
    agent_uri: str  # URL to Agent Card JSON
    global_id: str  # eip155:{chainId}:{registry}:{agentId}


class ERC8004Client:
    """Client for interacting with ERC-8004 registries.

    This class builds data structures and transaction payloads.  Actual
    on-chain submission requires a web3 provider and is intentionally
    left to the caller.
    """

    def __init__(
        self,
        rpc_url: str | None = None,
        registry_address: str | None = None,
    ) -> None:
        self.rpc_url = rpc_url
        self.registry_address = registry_address

    def build_agent_card(
        self,
        name: str,
        description: str,
        capabilities: list[dict[str, Any]],
        x402_support: bool = False,
    ) -> AgentCard:
        """Build an Agent Card from forge capability-manifest."""
        services: list[dict[str, Any]] = []
        for cap in capabilities:
            service: dict[str, Any] = {
                "endpoint": cap.get("endpoint", ""),
                "version": cap.get("version", "1.0"),
                "skills": cap.get("skills", []),
                "domains": cap.get("domains", []),
                "type": cap.get("type", "generic"),
            }
            services.append(service)
        return AgentCard(
            name=name,
            description=description,
            services=services,
            x402_support=x402_support,
        )

    def build_registration_payload(
        self,
        agent_card: AgentCard,
        wallet_address: str,
    ) -> dict[str, Any]:
        """Build the transaction payload for registering an agent on-chain."""
        card_json = json.dumps(agent_card.to_json(), separators=(",", ":"))
        return {
            "method": "registerAgent",
            "params": {
                "wallet_address": wallet_address,
                "agent_card_json": card_json,
                "registry_address": self.registry_address or "",
            },
        }

    def build_feedback_payload(
        self,
        agent_id: int,
        value: int,
        tag1: str = "",
        tag2: str = "",
    ) -> dict[str, Any]:
        """Build payload to submit reputation feedback."""
        return {
            "method": "submitFeedback",
            "params": {
                "agent_id": agent_id,
                "value": value,
                "tag1": tag1,
                "tag2": tag2,
                "registry_address": self.registry_address or "",
            },
        }

    def build_register_tx(self, agent_card: AgentCard, *, registry_address: str, chain_id: int = 8453) -> dict[str, Any]:
        """Build an unsigned registration transaction for on-chain Agent Card submission.

        Returns a transaction envelope dict suitable for signing via OWS wallet.
        The registry is assumed to implement a register(string name, string metadata) interface.
        """
        import json as _json
        metadata_json = _json.dumps(agent_card.to_json())
        # ABI-encode a simple register(string,string) call
        call_data = _encode_register_call(agent_card.name, metadata_json)
        return {
            "to": registry_address,
            "chainId": chain_id,
            "data": call_data,
            "value": "0x0",
            "type": "erc8004.register",
            "agentName": agent_card.name,
        }

    def build_update_tx(self, agent_id: str, agent_card: AgentCard, *, registry_address: str, chain_id: int = 8453) -> dict[str, Any]:
        """Build an unsigned update transaction for an existing Agent Card."""
        import json as _json
        metadata_json = _json.dumps(agent_card.to_json())
        call_data = _encode_update_call(agent_id, metadata_json)
        return {
            "to": registry_address,
            "chainId": chain_id,
            "data": call_data,
            "value": "0x0",
            "type": "erc8004.update",
            "agentId": agent_id,
            "agentName": agent_card.name,
        }


def _encode_register_call(name: str, metadata: str) -> str:
    """Simplified ABI encoding for register(string,string).

    This produces a hex string suitable for transaction data field.
    Real deployments should use proper ABI encoding; this provides
    the correct structure for testing and simulation.
    """
    name_hex = name.encode("utf8").hex()
    metadata_hex = metadata.encode("utf8").hex()
    # Simplified: function selector + offset + offset + length + data + length + data
    selector = "d4e12f28"  # placeholder selector for register(string,string)
    return f"0x{selector}{name_hex[:64].ljust(64, '0')}{metadata_hex[:128]}"


def _encode_update_call(agent_id: str, metadata: str) -> str:
    """Simplified ABI encoding for update(string,string)."""
    id_hex = agent_id.encode("utf8").hex()
    metadata_hex = metadata.encode("utf8").hex()
    selector = "a7e5764b"  # placeholder selector for update(string,string)
    return f"0x{selector}{id_hex[:64].ljust(64, '0')}{metadata_hex[:128]}"


def generate_agent_card_from_artifacts(
    artifacts: dict[str, Any],
) -> AgentCard:
    """Generate an ERC-8004 Agent Card from forge artifact bundle.

    Extracts name and description from the ``agent-spec`` key, maps
    capabilities to services, and checks for x402 payment support.
    """
    agent_spec = artifacts.get("agent-spec", {})
    name = agent_spec.get("name", "unnamed-agent")
    description = agent_spec.get("description", "")

    # Map capabilities to services.
    capabilities = artifacts.get("capabilities", [])
    services: list[dict[str, Any]] = []
    for cap in capabilities:
        services.append(
            {
                "endpoint": cap.get("endpoint", ""),
                "version": cap.get("version", "1.0"),
                "skills": cap.get("skills", []),
                "domains": cap.get("domains", []),
                "type": cap.get("type", "generic"),
            }
        )

    # Detect x402 support from artifact metadata.
    x402_support = bool(artifacts.get("x402_support", False))

    return AgentCard(
        name=name,
        description=description,
        services=services,
        x402_support=x402_support,
    )

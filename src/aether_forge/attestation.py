"""Agent attestation for Aether Forge.

Provides two layers of identity verification for agents registered on the
ERC-8004 on-chain registry:

**Layer 1 — Self-attestation (automatic):**
  The agent's own OWS wallet signs an EIP-712 ``AetherForgeAttestation``
  at generation time. Proves the wallet owner authorized this agent's
  creation with these specific capabilities. Saved as ``attestation.json``
  in the agent directory and published on-chain.

**Layer 2 — Framework attestation (opt-in):**
  The Aether Forge project's attestor wallet signs the agent after
  verifying its artifacts. Proves the agent was genuinely created by
  an authentic Aether Forge installation. Only the project team can
  produce this signature.

Trust tiers:
  - **Verified**: framework attestor signed it
  - **Self-attested**: agent's own wallet signed it
  - **Unverified**: just metadata tags, no signatures
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# EIP-712 type definitions for AetherForgeAttestation
# ---------------------------------------------------------------------------

ATTESTATION_DOMAIN = {
    "name": "AetherForge",
    "version": "1",
    "chainId": 8453,  # Base mainnet
}

ATTESTATION_TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"},
        {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"},
    ],
    "AetherForgeAttestation": [
        {"name": "artifactSetId", "type": "string"},
        {"name": "capabilitiesHash", "type": "bytes32"},
        {"name": "agentAddress", "type": "address"},
        {"name": "framework", "type": "string"},
        {"name": "frameworkVersion", "type": "string"},
        {"name": "timestamp", "type": "uint256"},
    ],
}

# The framework attestor address — published in ATTESTOR.md and on-chain.
# Only this address can produce Layer 2 "verified" attestations.
# Set to empty string until the project team generates and publishes it.
FRAMEWORK_ATTESTOR_ADDRESS = ""


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class Attestation:
    """A signed attestation linking an agent to its capabilities."""

    artifact_set_id: str
    capabilities_hash: str  # hex-encoded sha256 of capability-manifest.json
    agent_address: str  # EVM address that signed this
    framework: str = "aether-forge"
    framework_version: str = "0.1.0"
    timestamp: int = 0
    signature: str = ""  # hex-encoded EIP-712 signature
    tier: str = "self-attested"  # self-attested | verified | unverified

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifactSetId": self.artifact_set_id,
            "capabilitiesHash": self.capabilities_hash,
            "agentAddress": self.agent_address,
            "framework": self.framework,
            "frameworkVersion": self.framework_version,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "tier": self.tier,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Attestation:
        return cls(
            artifact_set_id=data.get("artifactSetId", ""),
            capabilities_hash=data.get("capabilitiesHash", ""),
            agent_address=data.get("agentAddress", ""),
            framework=data.get("framework", "aether-forge"),
            framework_version=data.get("frameworkVersion", "0.1.0"),
            timestamp=data.get("timestamp", 0),
            signature=data.get("signature", ""),
            tier=data.get("tier", "unverified"),
        )

    def save(self, agent_directory: Path) -> None:
        """Save the attestation to ``attestation.json`` in the agent directory."""
        path = agent_directory / "attestation.json"
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf8")
        # Lock down permissions — attestation contains a signature
        try:
            path.chmod(0o600)
        except Exception:
            pass
        logger.info("Saved attestation to %s (tier=%s)", path, self.tier)

    @classmethod
    def load(cls, agent_directory: Path) -> Attestation | None:
        """Load an attestation from an agent directory. Returns None if absent."""
        path = agent_directory / "attestation.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf8"))
            return cls.from_dict(data)
        except Exception as error:
            logger.warning("Failed to load attestation from %s: %s", path, error)
            return None


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def hash_capability_manifest(agent_directory: Path) -> str:
    """Compute sha256 of the agent's capability-manifest.json.

    Returns the hex-encoded hash, or empty string if the file doesn't exist.
    """
    manifest_path = agent_directory / "capability-manifest.json"
    if not manifest_path.exists():
        return ""
    content = manifest_path.read_bytes()
    return hashlib.sha256(content).hexdigest()


# ---------------------------------------------------------------------------
# EIP-712 typed data construction
# ---------------------------------------------------------------------------


def build_attestation_typed_data(
    attestation: Attestation,
    *,
    chain_id: int = 8453,
) -> dict[str, Any]:
    """Build the EIP-712 typed data object for signing.

    This is the payload that gets passed to OWS ``sign_typed_data()``.
    The ``chain_id`` parameter defaults to Base mainnet (8453) but should
    be set to 84532 for Base Sepolia testnet (flagged by protocol audit).
    """
    # Ensure capabilities_hash is 32 bytes hex (pad or truncate)
    cap_hash = attestation.capabilities_hash.replace("0x", "")
    if len(cap_hash) < 64:
        cap_hash = cap_hash.ljust(64, "0")
    cap_hash = "0x" + cap_hash[:64]

    domain = {**ATTESTATION_DOMAIN, "chainId": chain_id}

    return {
        "types": ATTESTATION_TYPES,
        "primaryType": "AetherForgeAttestation",
        "domain": domain,
        "message": {
            "artifactSetId": attestation.artifact_set_id,
            "capabilitiesHash": cap_hash,
            "agentAddress": attestation.agent_address,
            "framework": attestation.framework,
            "frameworkVersion": attestation.framework_version,
            "timestamp": attestation.timestamp,
        },
    }


# ---------------------------------------------------------------------------
# Signing (Layer 1 — self-attestation)
# ---------------------------------------------------------------------------


def create_self_attestation(
    agent_directory: Path,
    artifact_set_id: str,
    agent_address: str,
) -> Attestation:
    """Create a self-attestation for an agent.

    Signs the attestation using the agent's OWS wallet (EIP-712 typed data).
    If the wallet is unavailable (simulated provider), creates an unsigned
    attestation with tier="unverified".

    The attestation is saved to ``attestation.json`` in the agent directory.
    """
    cap_hash = hash_capability_manifest(agent_directory)
    now = int(time.time())

    attestation = Attestation(
        artifact_set_id=artifact_set_id,
        capabilities_hash=cap_hash,
        agent_address=agent_address,
        timestamp=now,
        tier="unverified",  # upgraded to self-attested if signing succeeds
    )

    # Try to sign with OWS wallet
    try:
        from .wallet import sign_message

        typed_data = build_attestation_typed_data(attestation)
        typed_data_json = json.dumps(typed_data)

        # Use sign_message with the typed data as the message content.
        # For a proper EIP-712 flow, the wallet should support sign_typed_data,
        # but sign_message with the JSON payload is a workable fallback.
        result = sign_message(agent_directory, "evm", typed_data_json)
        if result and result.get("signature"):
            attestation.signature = result["signature"]
            attestation.tier = "self-attested"
            logger.info("Self-attestation signed for %s", artifact_set_id)
        else:
            logger.warning("OWS sign_message returned no signature for %s", artifact_set_id)
    except Exception as error:
        # Wallet unavailable (simulated provider, missing OWS SDK, etc.)
        logger.debug("Could not sign self-attestation for %s: %s", artifact_set_id, error)

    attestation.save(agent_directory)
    return attestation


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify_self_attestation(attestation: Attestation) -> bool:
    """Verify that a self-attestation has a non-empty signature.

    .. warning::

       This performs **structural validation only**, not cryptographic
       verification. It checks that the signature field is present and
       the required fields are populated, but it does NOT recover the
       signer address via ecrecover. A forged attestation with a random
       signature value will pass this check.

       For production trust decisions, callers MUST either:
       (a) Perform on-chain ecrecover (via a Solidity verifier), or
       (b) Use a Python ECDSA library (``eth-account``) to recover the
           signer and compare against the claimed ``agentAddress``.

       This function is safe for initial filtering (reject obviously
       malformed attestations) but NOT for access control decisions.
    """
    if not attestation.signature or len(attestation.signature) < 10:
        return False
    if attestation.tier not in ("self-attested", "verified"):
        return False
    if not attestation.artifact_set_id or not attestation.agent_address:
        return False
    return True


def verify_framework_attestation(attestation: Attestation) -> bool:
    """Verify that an attestation was signed by the framework attestor.

    This checks that ``tier == "verified"`` and the signature is present.
    Full verification (recovering the signer address and comparing to
    ``FRAMEWORK_ATTESTOR_ADDRESS``) requires ecrecover and is left to the
    caller or the on-chain verification path.

    Returns False if the framework attestor address is not yet published.
    Logs a WARNING when the attestor address is empty so operators know
    framework verification is not yet operational (flagged by security audit).
    """
    if not FRAMEWORK_ATTESTOR_ADDRESS:
        logger.warning(
            "FRAMEWORK_ATTESTOR_ADDRESS is not set — framework attestation "
            "verification is not operational. All agents will be 'self-attested' "
            "at best. See ATTESTOR.md for setup instructions."
        )
        return False
    if attestation.tier != "verified":
        return False
    if not attestation.signature or len(attestation.signature) < 10:
        return False
    return True


def determine_trust_tier(attestation: Attestation | None) -> str:
    """Determine the trust tier for an agent based on its attestation.

    Returns one of: "verified", "self-attested", "unverified".
    """
    if attestation is None:
        return "unverified"
    if verify_framework_attestation(attestation):
        return "verified"
    if verify_self_attestation(attestation):
        return "self-attested"
    return "unverified"

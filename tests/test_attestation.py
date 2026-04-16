"""Tests for the agent attestation module."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.attestation import (
    Attestation,
    build_attestation_typed_data,
    create_self_attestation,
    determine_trust_tier,
    hash_capability_manifest,
    verify_framework_attestation,
    verify_self_attestation,
)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------

def test_hash_capability_manifest(tmp_path: Path) -> None:
    manifest = {"capabilities": [{"capabilityId": "cap-test"}]}
    (tmp_path / "capability-manifest.json").write_text(json.dumps(manifest))
    h = hash_capability_manifest(tmp_path)
    assert len(h) == 64  # sha256 hex digest
    assert h.isalnum()


def test_hash_missing_manifest(tmp_path: Path) -> None:
    assert hash_capability_manifest(tmp_path) == ""


# ---------------------------------------------------------------------------
# Attestation data type
# ---------------------------------------------------------------------------

def test_attestation_roundtrip() -> None:
    att = Attestation(
        artifact_set_id="aset_test_123",
        capabilities_hash="abcd" * 16,
        agent_address="0x" + "a" * 40,
        timestamp=1234567890,
        signature="0xsig",
        tier="self-attested",
    )
    d = att.to_dict()
    loaded = Attestation.from_dict(d)
    assert loaded.artifact_set_id == att.artifact_set_id
    assert loaded.capabilities_hash == att.capabilities_hash
    assert loaded.agent_address == att.agent_address
    assert loaded.timestamp == att.timestamp
    assert loaded.signature == att.signature
    assert loaded.tier == att.tier


def test_attestation_save_and_load(tmp_path: Path) -> None:
    att = Attestation(
        artifact_set_id="aset_save_test",
        capabilities_hash="beef" * 16,
        agent_address="0x" + "b" * 40,
        timestamp=9999,
        signature="0xdeadbeef",
        tier="self-attested",
    )
    att.save(tmp_path)
    loaded = Attestation.load(tmp_path)
    assert loaded is not None
    assert loaded.artifact_set_id == "aset_save_test"
    assert loaded.signature == "0xdeadbeef"


def test_attestation_load_missing(tmp_path: Path) -> None:
    assert Attestation.load(tmp_path) is None


# ---------------------------------------------------------------------------
# EIP-712 typed data
# ---------------------------------------------------------------------------

def test_build_typed_data_structure() -> None:
    att = Attestation(
        artifact_set_id="aset_typed_test",
        capabilities_hash="1234" * 16,
        agent_address="0x" + "c" * 40,
        timestamp=1000,
    )
    td = build_attestation_typed_data(att)
    assert td["primaryType"] == "AetherForgeAttestation"
    assert td["domain"]["name"] == "AetherForge"
    assert td["domain"]["chainId"] == 8453
    assert td["message"]["artifactSetId"] == "aset_typed_test"
    assert td["message"]["agentAddress"] == "0x" + "c" * 40
    assert td["message"]["framework"] == "aether-forge"
    # capabilities hash should be 0x-prefixed and 66 chars total
    assert td["message"]["capabilitiesHash"].startswith("0x")
    assert len(td["message"]["capabilitiesHash"]) == 66


def test_build_typed_data_pads_short_hash() -> None:
    att = Attestation(
        artifact_set_id="x",
        capabilities_hash="abc",  # too short
        agent_address="0x" + "0" * 40,
    )
    td = build_attestation_typed_data(att)
    # Should be padded to 32 bytes
    assert len(td["message"]["capabilitiesHash"]) == 66


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def test_verify_self_attestation_valid() -> None:
    att = Attestation(
        artifact_set_id="aset_v",
        capabilities_hash="x" * 64,
        agent_address="0x" + "a" * 40,
        signature="0x" + "ab" * 65,
        tier="self-attested",
    )
    assert verify_self_attestation(att) is True


def test_verify_self_attestation_missing_signature() -> None:
    att = Attestation(
        artifact_set_id="aset_v",
        capabilities_hash="x" * 64,
        agent_address="0x" + "a" * 40,
        signature="",
        tier="self-attested",
    )
    assert verify_self_attestation(att) is False


def test_verify_self_attestation_wrong_tier() -> None:
    att = Attestation(
        artifact_set_id="aset_v",
        capabilities_hash="x" * 64,
        agent_address="0x" + "a" * 40,
        signature="0x" + "ab" * 65,
        tier="unverified",
    )
    assert verify_self_attestation(att) is False


def test_verify_framework_attestation_no_attestor() -> None:
    """Framework attestation always returns False when attestor address is empty."""
    att = Attestation(
        artifact_set_id="x",
        capabilities_hash="x" * 64,
        agent_address="0x" + "a" * 40,
        signature="0x" + "ab" * 65,
        tier="verified",
    )
    # FRAMEWORK_ATTESTOR_ADDRESS is empty string → always False
    assert verify_framework_attestation(att) is False


# ---------------------------------------------------------------------------
# Trust tiers
# ---------------------------------------------------------------------------

def test_determine_trust_tier_none() -> None:
    assert determine_trust_tier(None) == "unverified"


def test_determine_trust_tier_self_attested() -> None:
    att = Attestation(
        artifact_set_id="x",
        capabilities_hash="x" * 64,
        agent_address="0x" + "a" * 40,
        signature="0x" + "ab" * 65,
        tier="self-attested",
    )
    assert determine_trust_tier(att) == "self-attested"


def test_determine_trust_tier_unverified_no_sig() -> None:
    att = Attestation(artifact_set_id="x", capabilities_hash="x" * 64, agent_address="0x" + "a" * 40, tier="self-attested")
    assert determine_trust_tier(att) == "unverified"


# ---------------------------------------------------------------------------
# Self-attestation creation (integration)
# ---------------------------------------------------------------------------

def test_create_self_attestation_saves_file(tmp_path: Path) -> None:
    """create_self_attestation should produce an attestation.json even
    without a real OWS wallet (falls back to unsigned/unverified)."""
    # Write a fake capability manifest so hashing works
    (tmp_path / "capability-manifest.json").write_text('{"capabilities":[]}')

    att = create_self_attestation(
        agent_directory=tmp_path,
        artifact_set_id="aset_create_test",
        agent_address="0x" + "d" * 40,
    )
    assert att.artifact_set_id == "aset_create_test"
    assert att.capabilities_hash  # non-empty
    assert att.timestamp > 0

    # File should exist
    assert (tmp_path / "attestation.json").exists()
    loaded = Attestation.load(tmp_path)
    assert loaded is not None
    assert loaded.artifact_set_id == "aset_create_test"

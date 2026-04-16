"""Tests for the on-chain ERC-8004 registry client.

Uses mocked RPC responses so tests don't depend on live Base mainnet.
The ABI encoding was validated against the live contract (returned
'AgentIdentity' from contract_name() during development).
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from aether_forge.onchain_registry import (
    OnchainRegistry,
    _decode_address,
    _decode_string,
    _decode_uint256,
    _encode_address,
    _encode_register_with_uri,
    _encode_string,
    _encode_uint256,
)


# ---------------------------------------------------------------------------
# ABI encoding tests
# ---------------------------------------------------------------------------


def test_encode_uint256() -> None:
    assert _encode_uint256(0) == "0" * 64
    assert _encode_uint256(1) == "0" * 63 + "1"
    assert _encode_uint256(42) == "0" * 62 + "2a"
    assert _encode_uint256(256) == "0" * 61 + "100"


def test_encode_address() -> None:
    addr = "0x0000000000000000000000000000000000000001"
    encoded = _encode_address(addr)
    assert len(encoded) == 64
    assert encoded.endswith("0000000000000000000000000000000000000001")


def test_encode_string() -> None:
    encoded = _encode_string("hello")
    # length = 5 → 0x05 padded to 32 bytes
    assert encoded.startswith("0" * 63 + "5")  # length = 5
    # data = "hello" = 68656c6c6f
    assert "68656c6c6f" in encoded


def test_encode_register_with_uri() -> None:
    calldata = _encode_register_with_uri("ipfs://QmTest123")
    assert calldata.startswith("0x")
    assert len(calldata) > 10  # has the selector + encoded string


# ---------------------------------------------------------------------------
# ABI decoding tests
# ---------------------------------------------------------------------------


def test_decode_uint256() -> None:
    assert _decode_uint256("0x" + "0" * 63 + "1") == 1
    assert _decode_uint256("0x" + "0" * 62 + "2a") == 42
    assert _decode_uint256("0x") == 0
    assert _decode_uint256("") == 0


def test_decode_address() -> None:
    hex_result = "0x" + "0" * 24 + "0000000000000000000000000000000000000001"
    assert _decode_address(hex_result).lower() == "0x0000000000000000000000000000000000000001"


def test_decode_string_simple() -> None:
    # Encode "AgentIdentity" and verify round-trip
    text = "AgentIdentity"
    # ABI dynamic string: offset (32) + length (13) + data padded to 32 bytes
    offset = "0" * 62 + "20"  # offset = 32 (0x20), 62+2=64 hex chars
    length = "0" * 63 + "d"  # length = 13 (0x0d)
    data = text.encode("utf8").hex().ljust(64, "0")
    hex_result = "0x" + offset + length + data
    assert _decode_string(hex_result) == "AgentIdentity"


# ---------------------------------------------------------------------------
# Mocked RPC tests
# ---------------------------------------------------------------------------


def _mock_rpc(responses: dict[str, str]):
    """Return a monkeypatch-able _eth_call that returns canned responses keyed by selector."""
    def fake_eth_call(rpc_url: str, to: str, data: str) -> str:
        selector = data[2:10] if data.startswith("0x") else data[:8]
        if selector in responses:
            return responses[selector]
        return "0x"
    return fake_eth_call


def test_balance_of(monkeypatch) -> None:
    # balanceOf returns 3
    monkeypatch.setattr(
        "aether_forge.onchain_registry._eth_call",
        _mock_rpc({"70a08231": "0x" + "0" * 63 + "3"}),
    )
    reg = OnchainRegistry()
    assert reg.balance_of("0xabc") == 3


def test_owner_of(monkeypatch) -> None:
    addr = "0000000000000000000000000000000000000001"
    monkeypatch.setattr(
        "aether_forge.onchain_registry._eth_call",
        _mock_rpc({"6352211e": "0x" + "0" * 24 + addr}),
    )
    reg = OnchainRegistry()
    assert reg.owner_of(1).lower() == "0x" + addr


def test_contract_name(monkeypatch) -> None:
    # Encode "AgentIdentity" as ABI string
    text = "AgentIdentity"
    offset = _encode_uint256(32)  # 0x20
    length = _encode_uint256(13)  # 0x0d
    data = text.encode("utf8").hex().ljust(64, "0")
    monkeypatch.setattr(
        "aether_forge.onchain_registry._eth_call",
        _mock_rpc({"06fdde03": "0x" + offset + length + data}),
    )
    reg = OnchainRegistry()
    assert reg.contract_name() == "AgentIdentity"


def test_is_reachable(monkeypatch) -> None:
    text = "AgentIdentity"
    offset = _encode_uint256(32)  # 0x20
    length = _encode_uint256(13)  # 0x0d
    data = text.encode("utf8").hex().ljust(64, "0")
    monkeypatch.setattr(
        "aether_forge.onchain_registry._eth_call",
        _mock_rpc({"06fdde03": "0x" + offset + length + data}),
    )
    reg = OnchainRegistry()
    assert reg.is_reachable() is True


def test_is_reachable_fails(monkeypatch) -> None:
    def fail(*args, **kwargs):
        raise RuntimeError("RPC down")
    monkeypatch.setattr("aether_forge.onchain_registry._eth_call", fail)
    reg = OnchainRegistry()
    assert reg.is_reachable() is False


def test_build_register_tx() -> None:
    reg = OnchainRegistry()
    tx = reg.build_register_tx(agent_uri="ipfs://QmTest123")
    assert tx["to"] == "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
    assert tx["value"] == "0x0"
    assert tx["chainId"] == hex(8453)
    assert tx["data"].startswith("0x")
    assert len(tx["data"]) > 20


def test_build_register_tx_empty_uri() -> None:
    reg = OnchainRegistry()
    tx = reg.build_register_tx()
    assert tx["data"].startswith("0x1aa3a008")  # register() selector


def test_build_set_uri_tx() -> None:
    reg = OnchainRegistry()
    tx = reg.build_set_uri_tx(agent_id=42, new_uri="ipfs://QmNew")
    assert tx["to"] == "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
    assert tx["data"].startswith("0x")


def test_agent_info(monkeypatch) -> None:
    owner_addr = "0000000000000000000000000000000000000001"
    wallet_addr = "1234567890abcdef1234567890abcdef12345678"

    uri_text = "ipfs://QmTest"
    offset = "0" * 62 + "20"  # 62+2=64
    length = _encode_uint256(len(uri_text))
    data = uri_text.encode("utf8").hex().ljust(64, "0")

    responses = {
        "6352211e": "0x" + "0" * 24 + owner_addr,
        "a66760e2": "0x" + "0" * 24 + wallet_addr,
        "c87b56dd": "0x" + offset + length + data,
    }
    monkeypatch.setattr("aether_forge.onchain_registry._eth_call", _mock_rpc(responses))

    reg = OnchainRegistry()
    info = reg.agent_info(1)
    assert info["agent_id"] == 1
    assert info["owner"].lower() == "0x" + owner_addr
    assert info["wallet"].lower() == "0x" + wallet_addr
    assert info["token_uri"] == "ipfs://QmTest"

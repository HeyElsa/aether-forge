"""On-chain ERC-8004 agent registry client for Base mainnet.

Reads and writes to the deployed IdentityRegistry contract at
``0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`` on Base mainnet (chain ID
8453). The contract is an ERC-721 where each agent is an NFT with a
metadata URI pointing to the agent's capability manifest on IPFS.

All write operations produce unsigned transaction envelopes suitable for
signing via OWS ``wallet-sign-tx`` / ``wallet-send-tx``. Read operations
use ``eth_call`` via the Base RPC and do not require gas.

Usage::

    from aether_forge.onchain_registry import OnchainRegistry

    reg = OnchainRegistry()

    # Read: how many agents does this address own?
    count = reg.balance_of("0x0000000000000000000000000000000000000001")

    # Read: get agent metadata URI
    uri = reg.token_uri(42)

    # Write: build a registration transaction
    tx = reg.build_register_tx(agent_uri="ipfs://Qm...")
    # Then sign and send via OWS: forge wallet-send-tx --chain evm --tx-hex ...
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Contract addresses (deployed by erc-8004/erc-8004-contracts)
# ---------------------------------------------------------------------------

IDENTITY_REGISTRY_BASE = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
REPUTATION_REGISTRY_BASE = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"
IDENTITY_REGISTRY_BASE_SEPOLIA = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
REPUTATION_REGISTRY_BASE_SEPOLIA = "0x8004B663056A597Dffe9eCcC1965A193B7388713"

BASE_CHAIN_ID = 8453
BASE_SEPOLIA_CHAIN_ID = 84532

# Base public RPCs — tried in order. Free endpoints rate-limit aggressively,
# so we fall through to the next one on 403/429.
BASE_RPCS = [
    "https://1rpc.io/base",
    "https://base.llamarpc.com",
    "https://mainnet.base.org",
]
DEFAULT_RPC = BASE_RPCS[0]
DEFAULT_RPC_SEPOLIA = "https://sepolia.base.org"

# ---------------------------------------------------------------------------
# ABI function selectors (4-byte Keccak256 prefixes)
# Computed from the verified IdentityRegistryUpgradeable source.
# ---------------------------------------------------------------------------

# register() → uint256
SEL_REGISTER_EMPTY = "1aa3a008"
# register(string) → uint256
SEL_REGISTER_URI = "f2c298be"  # keccak256("register(string)")[:4]
# setAgentURI(uint256,string)
SEL_SET_AGENT_URI = "7e5cd5c1"  # keccak256("setAgentURI(uint256,string)")[:4]
# getAgentWallet(uint256) → address
SEL_GET_AGENT_WALLET = "a66760e2"  # keccak256("getAgentWallet(uint256)")[:4]
# tokenURI(uint256) → string
SEL_TOKEN_URI = "c87b56dd"  # keccak256("tokenURI(uint256)")[:4]
# ownerOf(uint256) → address
SEL_OWNER_OF = "6352211e"  # keccak256("ownerOf(uint256)")[:4]
# balanceOf(address) → uint256
SEL_BALANCE_OF = "70a08231"  # keccak256("balanceOf(address)")[:4]
# name() → string
SEL_NAME = "06fdde03"
# symbol() → string
SEL_SYMBOL = "95d89b41"


# ---------------------------------------------------------------------------
# Minimal RLP encoder for EIP-1559 transactions (pure stdlib)
# ---------------------------------------------------------------------------


def _rlp_encode_item(data: bytes) -> bytes:
    """RLP-encode a single byte string."""
    if len(data) == 1 and data[0] < 0x80:
        return data
    if len(data) <= 55:
        return bytes([0x80 + len(data)]) + data
    length_bytes = _to_bytes(len(data))
    return bytes([0xB7 + len(length_bytes)]) + length_bytes + data


def _rlp_encode_list(items: list[bytes]) -> bytes:
    """RLP-encode a list of already-encoded items."""
    payload = b"".join(items)
    if len(payload) <= 55:
        return bytes([0xC0 + len(payload)]) + payload
    length_bytes = _to_bytes(len(payload))
    return bytes([0xF7 + len(length_bytes)]) + length_bytes + payload


def _to_bytes(n: int) -> bytes:
    """Convert an integer to its minimal big-endian byte representation."""
    if n == 0:
        return b""
    return n.to_bytes((n.bit_length() + 7) // 8, "big")


def _hex_to_bytes(hex_str: str) -> bytes:
    """Convert a 0x-prefixed hex string to bytes."""
    raw = hex_str.replace("0x", "")
    if len(raw) % 2 == 1:
        raw = "0" + raw
    return bytes.fromhex(raw)


def _addr_to_bytes(addr: str) -> bytes:
    """Convert an address to 20 bytes."""
    return _hex_to_bytes(addr)


def encode_eip1559_unsigned(tx: dict[str, Any]) -> str:
    """Encode an unsigned EIP-1559 transaction as hex for signing.

    Returns ``0x02 || rlp(...)`` hex string suitable for OWS ``sign_and_send()``.
    The tx dict must have: chainId, nonce, maxPriorityFeePerGas, maxFeePerGas,
    gas, to, value, data. accessList is always empty.
    """
    fields = [
        _to_bytes(int(tx.get("chainId", "0x2105"), 16)),       # chainId
        _to_bytes(int(tx.get("nonce", "0x0"), 16)),             # nonce
        _to_bytes(int(tx.get("maxPriorityFeePerGas", "0x0"), 16)),  # maxPriorityFeePerGas
        _to_bytes(int(tx.get("maxFeePerGas", "0x0"), 16)),     # maxFeePerGas
        _to_bytes(int(tx.get("gas", "0x0"), 16)),               # gasLimit
        _addr_to_bytes(tx["to"]),                                # to
        _to_bytes(int(tx.get("value", "0x0"), 16)),             # value
        _hex_to_bytes(tx["data"]),                               # data (calldata)
        b"",                                                     # accessList (empty)
    ]

    encoded_fields = [_rlp_encode_item(f) for f in fields]
    # accessList is an empty list, encode as such
    encoded_fields[-1] = _rlp_encode_list([])  # empty list = 0xc0

    rlp_payload = _rlp_encode_list(encoded_fields)

    # EIP-1559: type prefix 0x02 || rlp(...)
    return "0x02" + rlp_payload.hex()


def _pad32(hex_str: str) -> str:
    """Left-pad a hex string to 32 bytes (64 hex chars)."""
    return hex_str.replace("0x", "").rjust(64, "0")


def _encode_uint256(value: int) -> str:
    """ABI-encode a uint256."""
    return hex(value)[2:].rjust(64, "0")


def _encode_address(addr: str) -> str:
    """ABI-encode an address (left-padded to 32 bytes)."""
    return addr.lower().replace("0x", "").rjust(64, "0")


MAX_ABI_STRING_BYTES = 8192  # 8 KB — generous limit for metadata URIs


def _encode_string(s: str) -> str:
    """ABI-encode a dynamic string (offset + length + data, padded to 32-byte words).

    Raises ValueError if the string exceeds ``MAX_ABI_STRING_BYTES`` to prevent
    transactions that would revert on-chain (flagged by protocol audit).
    """
    raw = s.encode("utf8")
    if len(raw) > MAX_ABI_STRING_BYTES:
        raise ValueError(
            f"String is {len(raw)} bytes, exceeds ABI encoding limit of "
            f"{MAX_ABI_STRING_BYTES} bytes. Shorten the agent URI or metadata."
        )
    encoded = raw.hex()
    length = len(raw)
    # Pad data to 32-byte boundary
    padded_data = encoded.ljust(((len(encoded) + 63) // 64) * 64, "0")
    length_hex = _encode_uint256(length)
    return length_hex + padded_data


def _encode_register_with_uri(agent_uri: str) -> str:
    """Encode calldata for register(string agentURI)."""
    # function selector + offset to string param + string encoding
    offset = _encode_uint256(32)  # offset to the string data (one word)
    string_data = _encode_string(agent_uri)
    return "0x" + SEL_REGISTER_URI + offset + string_data


def _encode_set_agent_uri(agent_id: int, new_uri: str) -> str:
    """Encode calldata for setAgentURI(uint256 agentId, string newURI)."""
    agent_id_hex = _encode_uint256(agent_id)
    offset = _encode_uint256(64)  # offset past the two fixed-size params
    string_data = _encode_string(new_uri)
    return "0x" + SEL_SET_AGENT_URI + agent_id_hex + offset + string_data


# ---------------------------------------------------------------------------
# RPC helpers
# ---------------------------------------------------------------------------


def _eth_call(rpc_url: str, to: str, data: str) -> str:
    """Make a read-only eth_call and return the hex result.

    If the primary RPC returns 403/429 (rate-limited), falls through to
    alternative RPCs in ``BASE_RPCS``.
    """
    # If a paid/private RPC was provided (not in the free public list),
    # use ONLY that RPC — don't fall back to rate-limited public endpoints.
    if rpc_url not in BASE_RPCS:
        rpcs = [rpc_url]
    else:
        rpcs = [rpc_url] + [r for r in BASE_RPCS if r != rpc_url]
    last_error: Exception | None = None

    for rpc in rpcs:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": to, "data": data}, "latest"],
        }
        body = json.dumps(payload).encode("utf8")
        req = urllib_request.Request(
            rpc,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read().decode("utf8"))
                if "error" in result:
                    last_error = RuntimeError(f"RPC error from {rpc}: {result['error']}")
                    continue
                return result.get("result", "0x")
        except (urllib_error.URLError, urllib_error.HTTPError) as error:
            last_error = RuntimeError(f"RPC call to {rpc} failed: {error}")
            continue

    raise last_error or RuntimeError("All RPCs failed")


def _decode_uint256(hex_result: str) -> int:
    """Decode a uint256 from an eth_call hex result."""
    if not hex_result or hex_result == "0x":
        return 0
    return int(hex_result, 16)


def _decode_address(hex_result: str) -> str:
    """Decode an address from an eth_call hex result (last 20 bytes)."""
    if not hex_result or hex_result == "0x":
        return "0x" + "0" * 40
    raw = hex_result.replace("0x", "")
    return "0x" + raw[-40:]


def _decode_string(hex_result: str) -> str:
    """Decode a dynamic string from an eth_call hex result."""
    if not hex_result or hex_result == "0x" or len(hex_result) < 130:
        return ""
    raw = hex_result.replace("0x", "")
    # First 32 bytes = offset, next 32 bytes = length, then data
    try:
        offset = int(raw[:64], 16) * 2  # offset in hex chars
        length = int(raw[offset:offset + 64], 16)
        data_start = offset + 64
        data_hex = raw[data_start:data_start + length * 2]
        return bytes.fromhex(data_hex).decode("utf8")
    except (ValueError, UnicodeDecodeError):
        return ""


# ---------------------------------------------------------------------------
# OnchainRegistry class
# ---------------------------------------------------------------------------


class OnchainRegistry:
    """Client for the deployed ERC-8004 IdentityRegistry on Base.

    Read operations use eth_call (no gas). Write operations return unsigned
    transaction envelopes for signing via OWS wallet.
    """

    def __init__(
        self,
        *,
        registry_address: str = IDENTITY_REGISTRY_BASE,
        rpc_url: str = DEFAULT_RPC,
        chain_id: int = BASE_CHAIN_ID,
    ) -> None:
        self.registry_address = registry_address
        self.rpc_url = rpc_url
        self.chain_id = chain_id

    # ------------------------------------------------------------------
    # Read operations (free, no gas)
    # ------------------------------------------------------------------

    def balance_of(self, address: str) -> int:
        """How many agent NFTs does this address own?"""
        data = "0x" + SEL_BALANCE_OF + _encode_address(address)
        result = _eth_call(self.rpc_url, self.registry_address, data)
        return _decode_uint256(result)

    def owner_of(self, agent_id: int) -> str:
        """Who owns agent NFT #agent_id?"""
        data = "0x" + SEL_OWNER_OF + _encode_uint256(agent_id)
        result = _eth_call(self.rpc_url, self.registry_address, data)
        return _decode_address(result)

    def token_uri(self, agent_id: int) -> str:
        """Get the metadata URI for agent #agent_id."""
        data = "0x" + SEL_TOKEN_URI + _encode_uint256(agent_id)
        result = _eth_call(self.rpc_url, self.registry_address, data)
        return _decode_string(result)

    def get_agent_wallet(self, agent_id: int) -> str:
        """Get the wallet address associated with agent #agent_id."""
        data = "0x" + SEL_GET_AGENT_WALLET + _encode_uint256(agent_id)
        result = _eth_call(self.rpc_url, self.registry_address, data)
        return _decode_address(result)

    def contract_name(self) -> str:
        """Read the contract's ERC-721 name (should be 'AgentIdentity')."""
        data = "0x" + SEL_NAME
        result = _eth_call(self.rpc_url, self.registry_address, data)
        return _decode_string(result)

    # ------------------------------------------------------------------
    # Write operations (return unsigned tx envelopes)
    # ------------------------------------------------------------------

    def build_register_tx(self, agent_uri: str = "", *, from_address: str = "") -> dict[str, Any]:
        """Build an unsigned tx to register a new agent on-chain.

        The transaction mints an agent NFT to ``msg.sender`` and sets the
        metadata URI to ``agent_uri`` (typically an IPFS URL pointing to
        the agent's capability manifest + Agent Card JSON).

        If ``from_address`` is provided and the RPC is available, fetches
        the nonce and gas estimate to build a complete EIP-1559 envelope
        ready for signing. Otherwise returns a partial envelope.
        """
        if agent_uri:
            calldata = _encode_register_with_uri(agent_uri)
        else:
            calldata = "0x" + SEL_REGISTER_EMPTY

        tx: dict[str, Any] = {
            "to": self.registry_address,
            "data": calldata,
            "value": "0x0",
            "chainId": hex(self.chain_id),
            "type": "0x2",  # EIP-1559
        }

        # Fetch nonce + gas estimate if we have a from address
        if from_address:
            try:
                tx.update(self._estimate_tx_params(from_address, calldata))
            except Exception as error:
                logger.warning("Failed to estimate tx params: %s", error)

        return tx

    def _estimate_tx_params(self, from_address: str, calldata: str) -> dict[str, Any]:
        """Fetch nonce, gas estimate, and fee data from the RPC."""
        import json as _json
        from urllib import request as _ur

        def _rpc(method: str, params: list) -> Any:
            body = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
            req = _ur.Request(self.rpc_url, data=body, headers={"Content-Type": "application/json"})
            with _ur.urlopen(req, timeout=15) as resp:
                result = _json.loads(resp.read())
                if "error" in result:
                    raise RuntimeError(result["error"])
                return result["result"]

        nonce = int(_rpc("eth_getTransactionCount", [from_address, "latest"]), 16)
        gas_price = int(_rpc("eth_gasPrice", []), 16)

        # Estimate gas
        try:
            gas_estimate = int(_rpc("eth_estimateGas", [{
                "from": from_address,
                "to": self.registry_address,
                "data": calldata,
            }]), 16)
        except Exception:
            gas_estimate = 300_000  # safe default for register()

        # Add 20% buffer to gas estimate
        gas_limit = int(gas_estimate * 1.2)

        return {
            "from": from_address,
            "nonce": hex(nonce),
            "gas": hex(gas_limit),
            "maxFeePerGas": hex(gas_price * 2),
            "maxPriorityFeePerGas": hex(gas_price),
        }

    def build_set_uri_tx(self, agent_id: int, new_uri: str) -> dict[str, Any]:
        """Build an unsigned tx to update an agent's metadata URI."""
        calldata = _encode_set_agent_uri(agent_id, new_uri)
        return {
            "to": self.registry_address,
            "data": calldata,
            "value": "0x0",
            "chainId": hex(self.chain_id),
            "type": "0x2",
        }

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def is_reachable(self) -> bool:
        """Check if the Base RPC and registry contract are reachable."""
        try:
            name = self.contract_name()
            return bool(name)
        except Exception:
            return False

    def agent_info(self, agent_id: int) -> dict[str, Any]:
        """Fetch all available on-chain info for an agent.

        Handles reverts gracefully — some agents may not have a wallet set
        or a token URI, in which case those fields return empty strings.
        """
        info: dict[str, Any] = {"agent_id": agent_id}
        try:
            info["owner"] = self.owner_of(agent_id)
        except Exception:
            info["owner"] = ""
        try:
            info["wallet"] = self.get_agent_wallet(agent_id)
        except Exception:
            info["wallet"] = ""
        try:
            info["token_uri"] = self.token_uri(agent_id)
        except Exception:
            info["token_uri"] = ""
        return info

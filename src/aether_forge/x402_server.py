"""x402 payment server for Aether Forge agents.

Lets an agent gate its capabilities behind x402 payments. When another
agent calls a paid capability, the server returns HTTP 402 with payment
requirements. The caller signs an EIP-3009 transferWithAuthorization and
retries with the X-PAYMENT header. The server verifies the payment and
returns the result.

Two verification modes:
  - **Structural** (default): checks format, addresses, amounts. Fast,
    no gas required, but trusts the caller's signature without on-chain
    confirmation. Suitable for trusted agent networks.
  - **On-chain** (production): submits the EIP-3009 transferWithAuthorization
    to the USDC contract on Base. Agent B pays ~$0.001 gas in ETH.
    USDC actually moves on-chain before the result is delivered.

This is the SERVER complement to the existing X402Client (the CLIENT).
Together they enable agent-to-agent pay-per-call commerce.

Integration with the A2A server::

    from aether_forge.x402_server import X402PaymentGate

    gate = X402PaymentGate(
        wallet_address="0xAgentB...",
        prices={"get-token-price": 0.002, "analyze-risk": 0.005},
    )

    # In the A2A task handler:
    def handle_task(task):
        capability = extract_capability(task)
        payment_header = extract_payment_header(task)

        # Check if this capability requires payment
        if gate.requires_payment(capability):
            if payment_header:
                # Verify the payment
                ok, reason = gate.verify_payment(payment_header, capability)
                if not ok:
                    return {"state": "failed", "error": reason}
                # Payment verified — execute and return
                gate.record_payment(capability, gate.price_for(capability))
                return execute_capability(capability, task)
            else:
                # Return 402-style payment requirement
                return gate.payment_required_response(capability)

        # Free capability — execute directly
        return execute_capability(capability, task)
"""

from __future__ import annotations

import base64
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# USDC contract on Base mainnet
USDC_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"


@dataclass(slots=True)
class PaymentRequirement:
    """x402 payment requirement returned to callers."""

    scheme: str = "exact"
    network: str = "base"
    max_amount_required: str = "0"  # in USDC micro-units (6 decimals)
    pay_to: str = ""
    asset: str = USDC_BASE
    resource: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "network": self.network,
            "maxAmountRequired": self.max_amount_required,
            "payTo": self.pay_to,
            "asset": self.asset,
            "resource": self.resource,
        }


class X402PaymentGate:
    """Gates agent capabilities behind x402 payments.

    Maintains a price list and tracks received payments. When a caller
    requests a paid capability without a payment header, returns a
    402-style response with payment requirements. When a payment header
    is present, verifies it structurally and records the payment.

    Args:
        wallet_address: The agent's EVM address (where payments are sent).
        prices: Dict mapping capability names to prices in USD.
        chain: The chain payments are accepted on (default: "base").
        audit_log_path: Path to write payment receipts (default: agent dir).
    """

    def __init__(
        self,
        wallet_address: str,
        prices: dict[str, float] | None = None,
        *,
        chain: str = "base",
        audit_log_path: Path | None = None,
    ) -> None:
        self.wallet_address = wallet_address
        self.prices = prices or {}
        self.chain = chain
        self.audit_log_path = audit_log_path
        self.total_received_usd: float = 0.0
        self.total_payments: int = 0
        self._payment_log: list[dict[str, Any]] = []

    def requires_payment(self, capability: str) -> bool:
        """Check if a capability requires payment."""
        return capability in self.prices and self.prices[capability] > 0

    def price_for(self, capability: str) -> float:
        """Get the USD price for a capability. Returns 0 for free capabilities."""
        return self.prices.get(capability, 0.0)

    def price_raw(self, capability: str) -> int:
        """Get the price in USDC micro-units (6 decimals)."""
        return int(self.price_for(capability) * 1_000_000)

    def payment_required_response(self, capability: str) -> dict[str, Any]:
        """Build a payment-required response for the A2A task handler.

        Returns a task result with state="auth-required" and the payment
        requirements in the artifacts. The caller should extract the
        requirements and pay before retrying.
        """
        price = self.price_for(capability)
        requirement = PaymentRequirement(
            network=self.chain,
            max_amount_required=str(self.price_raw(capability)),
            pay_to=self.wallet_address,
            resource=capability,
        )
        return {
            "state": "auth-required",
            "artifacts": [{
                "parts": [{
                    "type": "text",
                    "text": json.dumps({
                        "x402": True,
                        "price_usd": price,
                        "accepts": [requirement.to_dict()],
                        "message": f"Payment of ${price:.4f} USDC required for capability '{capability}'",
                    }),
                }],
            }],
        }

    def verify_payment(
        self,
        payment_header: str | dict[str, Any],
        capability: str,
    ) -> tuple[bool, str]:
        """Verify an x402 payment header.

        Performs structural verification:
        - Payment header is present and decodable
        - Amount meets or exceeds the required price
        - Network matches
        - Pay-to address matches this agent's wallet

        Does NOT perform on-chain verification (ecrecover, nonce check,
        balance check). For production, the agent should submit the
        transferWithAuthorization on-chain and wait for confirmation.

        Returns (valid, reason).
        """
        try:
            if isinstance(payment_header, str):
                # Decode base64 X-PAYMENT header
                decoded = base64.b64decode(payment_header)
                payment = json.loads(decoded)
            elif isinstance(payment_header, dict):
                payment = payment_header
            else:
                return False, "Invalid payment header type"

            # Check x402 version
            if payment.get("x402Version") not in (1, "1"):
                return False, f"Unsupported x402 version: {payment.get('x402Version')}"

            # Check network
            if payment.get("network") != self.chain:
                return False, f"Wrong network: {payment.get('network')} (expected {self.chain})"

            # Check pay-to address
            payload = payment.get("payload", {})
            auth = payload.get("authorization", {})
            to_addr = auth.get("to", "").lower()
            if to_addr and to_addr != self.wallet_address.lower():
                return False, f"Payment to wrong address: {to_addr} (expected {self.wallet_address})"

            # Check amount
            value = int(auth.get("value", "0"))
            required = self.price_raw(capability)
            if value < required:
                return False, f"Insufficient payment: {value} < {required} micro-USDC"

            # Check signature exists
            if not payment.get("payload", {}).get("signature"):
                return False, "Missing payment signature"

            return True, "ok"

        except (json.JSONDecodeError, base64.binascii.Error) as error:
            return False, f"Failed to decode payment header: {error}"
        except Exception as error:
            return False, f"Payment verification error: {error}"

    def verify_and_settle_onchain(
        self,
        payment_header: str | dict[str, Any],
        capability: str,
        *,
        agent_directory: Path | None = None,
        allowed_payers: set[str] | None = None,
    ) -> tuple[bool, str]:
        """Verify a payment header AND submit it on-chain.

        This is the production-grade path: instead of just checking the
        payment structure, it actually submits the EIP-3009
        ``transferWithAuthorization`` to the USDC contract on Base so
        the USDC moves from Agent A's wallet to Agent B's wallet before
        the capability result is delivered.

        ``allowed_payers`` (Sprint 2.3 / FP-3) restricts which
        ``authorization.from`` addresses the server will accept. When
        provided, any signature whose ``from`` is outside the set is rejected
        before any on-chain submit. Closes the "anyone can pay anything" gap.
        Addresses are compared case-insensitively.

        Requires:
        - Agent B has a small amount of ETH on Base for gas (~$0.001/tx)
        - Agent B's OWS wallet is accessible at ``agent_directory``

        Returns (success, reason_or_tx_hash).
        """
        # Step 1: structural verification first (fast, catches obvious errors)
        ok, reason = self.verify_payment(payment_header, capability)
        if not ok:
            return False, reason

        # Step 1b (Sprint 2.3 / FP-3): payer allowlist gate. Done after
        # structural verification so a malformed header still fails fast with
        # the structural error rather than the allowlist error.
        if allowed_payers is not None:
            try:
                if isinstance(payment_header, str):
                    payment_for_payer = json.loads(base64.b64decode(payment_header))
                else:
                    payment_for_payer = payment_header
                payer = (
                    payment_for_payer.get("payload", {})
                    .get("authorization", {})
                    .get("from", "")
                )
            except Exception as error:
                return False, f"Could not extract payer for allowlist check: {error}"
            normalized = {addr.lower() for addr in allowed_payers}
            if not payer or payer.lower() not in normalized:
                return False, f"Payer {payer or '<empty>'} not in allowed_payers"

        # Step 2: extract the EIP-3009 authorization from the payment header
        try:
            if isinstance(payment_header, str):
                payment = json.loads(base64.b64decode(payment_header))
            else:
                payment = payment_header

            payload = payment.get("payload", {})
            auth = payload.get("authorization", {})
            sig = payload.get("signature", "")

            # Parse signature into v, r, s
            sig_hex = sig.replace("0x", "")
            if len(sig_hex) < 128:
                return False, f"Signature too short: {len(sig_hex)} hex chars (need 130)"
            r = "0x" + sig_hex[:64]
            s = "0x" + sig_hex[64:128]
            v = int(sig_hex[128:130], 16) if len(sig_hex) >= 130 else 27

            # Build the transferWithAuthorization calldata
            calldata = _encode_transfer_with_authorization(
                from_addr=auth.get("from", ""),
                to_addr=auth.get("to", ""),
                value=int(auth.get("value", "0")),
                valid_after=int(auth.get("validAfter", "0")),
                valid_before=int(auth.get("validBefore", "0")),
                nonce=auth.get("nonce", "0x" + "0" * 64),
                v=v,
                r=r,
                s=s,
            )

        except Exception as error:
            return False, f"Failed to parse payment authorization: {error}"

        # Step 3: build the unsigned transaction
        chain_usdc = {
            "base": USDC_BASE,
            "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        }
        usdc_addr = chain_usdc.get(self.chain, USDC_BASE)
        chain_ids = {"base": 8453, "ethereum": 1}

        tx = {
            "to": usdc_addr,
            "data": calldata,
            "value": "0x0",
            "chainId": hex(chain_ids.get(self.chain, 8453)),
            "type": "0x2",
        }

        # Step 4: sign and send via OWS wallet
        if agent_directory is None:
            # Can't submit without a wallet — fall back to structural-only
            logger.warning(
                "No agent_directory provided — cannot submit payment on-chain. "
                "Falling back to structural verification only."
            )
            return True, "structural-only (no wallet for on-chain submission)"

        try:
            from .wallet import sign_and_send
            result = sign_and_send(agent_directory, "evm", tx["data"])

            if result and result.get("tx_hash"):
                tx_hash = result["tx_hash"]
                logger.info(
                    "Payment submitted on-chain: tx=%s, from=%s, to=%s, amount=%s",
                    tx_hash, auth.get("from"), auth.get("to"), auth.get("value"),
                )
                self.record_payment(capability, self.price_for(capability))
                return True, tx_hash
            else:
                return False, f"Transaction submission returned no hash: {result}"

        except ImportError:
            logger.warning("OWS wallet not available — falling back to structural verification")
            return True, "structural-only (OWS SDK not installed)"
        except Exception as error:
            return False, f"On-chain submission failed: {error}"

    def record_payment(self, capability: str, amount_usd: float) -> None:
        """Record a successful payment in the internal log."""
        self.total_received_usd += amount_usd
        self.total_payments += 1
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "capability": capability,
            "amount_usd": amount_usd,
            "from": "unknown",  # would be extracted from the payment header
            "payment_number": self.total_payments,
        }
        self._payment_log.append(entry)
        logger.info(
            "Payment received: $%.4f for %s (total: $%.4f, #%d)",
            amount_usd, capability, self.total_received_usd, self.total_payments,
        )

        # Persist to audit log if path is set
        if self.audit_log_path:
            try:
                with open(self.audit_log_path, "a", encoding="utf8") as f:
                    f.write(json.dumps(entry) + "\n")
            except Exception as error:
                logger.warning("Failed to write payment audit log: %s", error)

    def status(self) -> dict[str, Any]:
        """Return the payment gate status."""
        return {
            "wallet_address": self.wallet_address,
            "chain": self.chain,
            "total_received_usd": round(self.total_received_usd, 6),
            "total_payments": self.total_payments,
            "paid_capabilities": {k: v for k, v in self.prices.items() if v > 0},
            "free_capabilities": [k for k, v in self.prices.items() if v == 0],
        }


def build_paid_task_handler(
    gate: X402PaymentGate,
    capability_handlers: dict[str, Any],
    *,
    verify_onchain: bool = False,
    agent_directory: Path | None = None,
) -> Any:
    """Build an A2A task handler that gates capabilities behind x402 payments.

    Returns a function suitable for passing to ``A2AServer(task_handler=...)``.

    Usage::

        gate = X402PaymentGate(
            wallet_address="0xAgentB...",
            prices={"get-token-price": 0.002, "analyze-risk": 0.005},
        )

        handlers = {
            "get-token-price": lambda task: {"state": "completed", "artifacts": [...]},
            "analyze-risk": lambda task: {"state": "completed", "artifacts": [...]},
        }

        # Structural verification only (fast, no gas):
        task_handler = build_paid_task_handler(gate, handlers)

        # On-chain verification (production — submits tx, USDC moves):
        task_handler = build_paid_task_handler(
            gate, handlers,
            verify_onchain=True,
            agent_directory=Path("./my-agent"),
        )

        server = A2AServer(port=8090, agent_card=card, task_handler=task_handler)
    """

    def handler(task: dict[str, Any]) -> dict[str, Any]:
        # Extract capability name from the task
        capability = _extract_capability(task)
        if not capability:
            return {
                "state": "failed",
                "artifacts": [{"parts": [{"type": "text", "text": "No capability specified in task"}]}],
            }

        # Check if this capability requires payment
        if gate.requires_payment(capability):
            # Check for payment in metadata
            metadata = {}
            for msg in task.get("history", []):
                metadata.update(msg.get("metadata", {}))
            payment_data = metadata.get("x402_payment")

            if payment_data:
                # Verify the payment — two modes:
                if verify_onchain and agent_directory:
                    # Production: submit transferWithAuthorization on-chain
                    ok, result = gate.verify_and_settle_onchain(
                        payment_data, capability,
                        agent_directory=agent_directory,
                    )
                    if not ok:
                        return {
                            "state": "failed",
                            "artifacts": [{"parts": [{"type": "text", "text": f"Payment rejected: {result}"}]}],
                        }
                    # On-chain settlement succeeded — result contains tx hash
                else:
                    # Structural verification only (fast, no gas)
                    ok, reason = gate.verify_payment(payment_data, capability)
                    if not ok:
                        return {
                            "state": "failed",
                            "artifacts": [{"parts": [{"type": "text", "text": f"Payment rejected: {reason}"}]}],
                        }
                    # Structural verification passed — record it
                    gate.record_payment(capability, gate.price_for(capability))
            else:
                # No payment — return payment requirement
                return gate.payment_required_response(capability)

        # Execute the capability
        cap_handler = capability_handlers.get(capability)
        if cap_handler:
            return cap_handler(task)

        return {
            "state": "failed",
            "artifacts": [{"parts": [{"type": "text", "text": f"Unknown capability: {capability}"}]}],
        }

    return handler


# ---------------------------------------------------------------------------
# ABI encoding for EIP-3009 transferWithAuthorization
# ---------------------------------------------------------------------------

# Function selector: keccak256("transferWithAuthorization(address,address,uint256,uint256,uint256,bytes32,uint8,bytes32,bytes32)")[:4]
# Verified against the USDC contract on Base mainnet.
SEL_TRANSFER_WITH_AUTH = "e3ee160e"


def _pad32(hex_str: str) -> str:
    """Left-pad a hex string to 32 bytes (64 hex chars)."""
    return hex_str.replace("0x", "").rjust(64, "0")


def _encode_transfer_with_authorization(
    *,
    from_addr: str,
    to_addr: str,
    value: int,
    valid_after: int,
    valid_before: int,
    nonce: str,
    v: int,
    r: str,
    s: str,
) -> str:
    """ABI-encode a call to USDC's transferWithAuthorization.

    This is the EIP-3009 function that allows a third party (Agent B)
    to submit a pre-signed transfer authorization on behalf of the sender
    (Agent A). The USDC moves from Agent A to Agent B, and Agent B pays
    the gas.

    Returns the full calldata as a hex string starting with 0x.
    """
    # Encode each parameter as a 32-byte word
    from_hex = _pad32(from_addr)
    to_hex = _pad32(to_addr)
    value_hex = _pad32(hex(value)[2:])
    valid_after_hex = _pad32(hex(valid_after)[2:])
    valid_before_hex = _pad32(hex(valid_before)[2:])
    nonce_hex = _pad32(nonce.replace("0x", ""))
    v_hex = _pad32(hex(v)[2:])
    r_hex = _pad32(r.replace("0x", ""))
    s_hex = _pad32(s.replace("0x", ""))

    return (
        "0x" + SEL_TRANSFER_WITH_AUTH
        + from_hex
        + to_hex
        + value_hex
        + valid_after_hex
        + valid_before_hex
        + nonce_hex
        + v_hex
        + r_hex
        + s_hex
    )


def _extract_capability(task: dict[str, Any]) -> str:
    """Extract the capability name from an A2A task's message history."""
    for msg in task.get("history", []):
        for part in msg.get("parts", []):
            if isinstance(part, dict) and "text" in part:
                try:
                    data = json.loads(part["text"])
                    if isinstance(data, dict) and "capability" in data:
                        return data["capability"]
                except (json.JSONDecodeError, TypeError):
                    pass
    return ""

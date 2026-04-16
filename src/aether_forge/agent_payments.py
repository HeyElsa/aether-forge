"""Agent-to-agent payment protocol for Aether Forge.

Three payment channels for inter-agent commerce, all on Base mainnet:

1. **x402 pay-per-call** — Agent B exposes a capability as a paid HTTP
   endpoint. Agent A calls it and pays per request via the existing
   :class:`X402Client` (EIP-3009 transferWithAuthorization on USDC).

2. **Direct USDC transfer** — Agent A sends USDC to Agent B's wallet on
   Base. One-shot transfer via OWS ``sign_and_send()``. For tips, bounties,
   or simple flat-fee work.

3. **ERC-8183 escrowed jobs** — Agent A deposits into an on-chain escrow.
   Agent B delivers. An evaluator confirms quality. Escrow releases to
   Agent B. For complex multi-step tasks where trust is low.

Payment information travels in the A2A message metadata::

    {
      "metadata": {
        "payment": {
          "method": "x402",           // x402 | transfer | escrow
          "budget_usd": 0.05,
          "asset": "USDC",
          "chain": "base",
          "pay_to": "0x..."           // recipient wallet address
        }
      }
    }

All three channels reuse existing Aether Forge infrastructure:
- ``X402Client`` for x402 pay-per-call (already battle-tested with Elsa)
- ``OWS wallet-send-tx`` for direct transfers
- ``ERC8183Client`` tx-building for escrow (contract deployment TBD)
"""

from __future__ import annotations

import fcntl
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# File lock for atomic budget check + payment execution.
# Prevents race conditions when two ticks or agents share the same
# x402_state.json (flagged as CRITICAL by security audit).
_budget_lock_path: Path | None = None


# ---------------------------------------------------------------------------
# Payment request / response types
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PaymentRequest:
    """Payment terms attached to an A2A task proposal."""

    method: str  # x402 | transfer | escrow
    budget_usd: float
    asset: str = "USDC"
    chain: str = "base"
    pay_to: str = ""  # recipient EVM address (filled by acceptor)
    x402_endpoint: str = ""  # for x402: the paid HTTP endpoint URL

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "budget_usd": self.budget_usd,
            "asset": self.asset,
            "chain": self.chain,
            "pay_to": self.pay_to,
            "x402_endpoint": self.x402_endpoint,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaymentRequest:
        return cls(
            method=data.get("method", "transfer"),
            budget_usd=float(data.get("budget_usd", 0)),
            asset=data.get("asset", "USDC"),
            chain=data.get("chain", "base"),
            pay_to=data.get("pay_to", ""),
            x402_endpoint=data.get("x402_endpoint", ""),
        )


@dataclass(slots=True)
class PaymentResult:
    """Outcome of a payment attempt."""

    success: bool
    method: str
    amount_usd: float
    tx_hash: str = ""
    error: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "method": self.method,
            "amount_usd": self.amount_usd,
            "tx_hash": self.tx_hash,
            "error": self.error,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------


def check_budget(
    agent_directory: Path,
    amount_usd: float,
    *,
    max_per_call_usd: float = 0.10,
    max_session_usd: float = 1.0,
) -> tuple[bool, str]:
    """Check whether the agent's budget allows this payment.

    Reads the existing ``x402_state.json`` to get cumulative spending.
    The same budget caps that govern Elsa x402 calls also govern
    inter-agent payments — one budget, two channels.

    Returns (allowed, reason).
    """
    if amount_usd > max_per_call_usd:
        return False, f"Amount ${amount_usd:.4f} exceeds per-call cap ${max_per_call_usd:.4f}"

    state_path = agent_directory / "x402_state.json"
    session_spent = 0.0
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf8"))
            session_spent = float(state.get("session_spent_usd", 0))
        except Exception:
            pass

    if session_spent + amount_usd > max_session_usd:
        return False, (
            f"Session total ${session_spent + amount_usd:.4f} would exceed "
            f"session cap ${max_session_usd:.4f} (already spent ${session_spent:.4f})"
        )

    return True, "ok"


# ---------------------------------------------------------------------------
# Payment execution — x402 channel
# ---------------------------------------------------------------------------


def pay_via_x402(
    agent_directory: Path,
    endpoint: str,
    body: dict[str, Any] | None = None,
    *,
    max_per_call_usd: float = 0.10,
    max_session_usd: float = 1.0,
    chain: str = "base",
) -> PaymentResult:
    """Execute an x402 payment to another agent's paid endpoint.

    Reuses the existing :class:`X402Client` infrastructure — the same
    client that handles Elsa x402 calls. The remote agent must respond
    with a 402 + payment requirement, and the client signs an EIP-3009
    transferWithAuthorization to pay.
    """
    try:
        from .x402_client import X402Client, X402Config

        config = X402Config(
            max_per_call_usd=max_per_call_usd,
            max_session_usd=max_session_usd,
            chain=chain,
            confirmed=True,
            check_balance=False,
        )
        client = X402Client(agent_directory=agent_directory, config=config)
        response = client.post(endpoint, body=body or {})

        if response.get("status") in (200, 201, 202):
            status = client.status()
            return PaymentResult(
                success=True,
                method="x402",
                amount_usd=status.get("session_spent_usd", 0),
            )
        else:
            return PaymentResult(
                success=False,
                method="x402",
                amount_usd=0,
                error=f"x402 call returned status {response.get('status')}",
            )
    except Exception as error:
        return PaymentResult(
            success=False,
            method="x402",
            amount_usd=0,
            error=str(error),
        )


# ---------------------------------------------------------------------------
# Payment execution — direct USDC transfer
# ---------------------------------------------------------------------------


def build_transfer_tx(
    recipient: str,
    amount_usd: float,
    *,
    chain: str = "base",
) -> dict[str, Any]:
    """Build an unsigned USDC transfer transaction.

    Returns a transaction envelope for signing via OWS ``wallet-send-tx``.
    Uses the ERC-20 ``transfer(address,uint256)`` function on the USDC
    contract.
    """
    # USDC contract addresses per chain
    usdc_contracts = {
        "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    }
    usdc_address = usdc_contracts.get(chain, usdc_contracts["base"])

    # USDC has 6 decimals
    amount_raw = int(amount_usd * 1_000_000)

    # ABI encode transfer(address,uint256)
    selector = "a9059cbb"  # keccak256("transfer(address,uint256)")[:4]
    to_padded = recipient.lower().replace("0x", "").rjust(64, "0")
    amount_padded = hex(amount_raw)[2:].rjust(64, "0")
    calldata = f"0x{selector}{to_padded}{amount_padded}"

    chain_ids = {"base": 8453, "ethereum": 1}

    return {
        "to": usdc_address,
        "data": calldata,
        "value": "0x0",
        "chainId": hex(chain_ids.get(chain, 8453)),
        "type": "0x2",
        "description": f"Transfer {amount_usd} USDC to {recipient[:10]}...",
    }


# ---------------------------------------------------------------------------
# Payment execution — ERC-8183 escrow (tx builder only)
# ---------------------------------------------------------------------------


def build_escrow_fund_tx(
    job_id: str,
    amount_usd: float,
    provider_address: str,
    *,
    escrow_contract: str = "",
    chain: str = "base",
) -> dict[str, Any]:
    """Build an unsigned escrow funding transaction.

    This creates the ERC-8183 job on-chain and deposits the budget into
    escrow. The provider agent can then deliver work and claim payment.

    Note: the escrow contract is not yet deployed on Base. This function
    builds the transaction structure so it's ready when the contract ships.
    """
    if not escrow_contract:
        return {
            "error": "ERC-8183 escrow contract not yet deployed on Base",
            "job_id": job_id,
            "amount_usd": amount_usd,
            "provider_address": provider_address,
            "status": "pending_deployment",
        }

    # Placeholder ABI encoding — will be replaced with real escrow contract ABI
    return {
        "to": escrow_contract,
        "data": "0x",  # TODO: encode createJob(jobId, provider, amount)
        "value": "0x0",
        "chainId": hex(8453),
        "type": "0x2",
        "description": f"Fund escrow: {amount_usd} USDC for job {job_id} to {provider_address[:10]}...",
    }


# ---------------------------------------------------------------------------
# High-level payment dispatcher
# ---------------------------------------------------------------------------


def execute_payment(
    agent_directory: Path,
    payment: PaymentRequest,
    *,
    task_body: dict[str, Any] | None = None,
) -> PaymentResult:
    """Execute a payment based on the payment request method.

    Dispatches to the right channel (x402, transfer, escrow) and returns
    the result. Budget caps are checked before any payment is attempted.

    **Thread safety:** holds an exclusive file lock on ``x402_state.lock``
    across the budget check + payment execution to prevent race conditions
    where two concurrent payments both pass the budget check and overspend.
    (Flagged as CRITICAL by security audit — budget check was non-atomic.)
    """
    # Acquire file lock BEFORE budget check so the check + execution is atomic.
    lock_path = agent_directory / "x402_state.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_file = open(lock_path, "w")  # noqa: SIM115
    try:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        return _execute_payment_locked(agent_directory, payment, task_body=task_body)
    finally:
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()


def _execute_payment_locked(
    agent_directory: Path,
    payment: PaymentRequest,
    *,
    task_body: dict[str, Any] | None = None,
) -> PaymentResult:
    """Inner payment dispatcher — called with the budget lock held."""
    # Budget check (under lock — atomic with the payment below)
    allowed, reason = check_budget(agent_directory, payment.budget_usd)
    if not allowed:
        return PaymentResult(
            success=False,
            method=payment.method,
            amount_usd=0,
            error=f"Budget check failed: {reason}",
        )

    if payment.method == "x402":
        if not payment.x402_endpoint:
            return PaymentResult(
                success=False,
                method="x402",
                amount_usd=0,
                error="No x402_endpoint provided in payment request",
            )
        return pay_via_x402(
            agent_directory,
            payment.x402_endpoint,
            body=task_body,
            max_per_call_usd=payment.budget_usd * 2,  # allow headroom
            chain=payment.chain,
        )

    if payment.method == "transfer":
        if not payment.pay_to:
            return PaymentResult(
                success=False,
                method="transfer",
                amount_usd=0,
                error="No pay_to address provided",
            )
        tx = build_transfer_tx(
            payment.pay_to,
            payment.budget_usd,
            chain=payment.chain,
        )
        return PaymentResult(
            success=True,
            method="transfer",
            amount_usd=payment.budget_usd,
            tx_hash="",  # populated after actual send
            error=json.dumps(tx),  # carry the unsigned tx for the caller
        )

    if payment.method == "escrow":
        tx = build_escrow_fund_tx(
            job_id=f"job_{int(time.time())}",
            amount_usd=payment.budget_usd,
            provider_address=payment.pay_to,
        )
        if "error" in tx:
            return PaymentResult(
                success=False,
                method="escrow",
                amount_usd=0,
                error=tx["error"],
            )
        return PaymentResult(
            success=True,
            method="escrow",
            amount_usd=payment.budget_usd,
        )

    return PaymentResult(
        success=False,
        method=payment.method,
        amount_usd=0,
        error=f"Unknown payment method: {payment.method}",
    )

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

        # Policy gate — require explicit opt-in for agent-to-agent transfers
        policy_ok, policy_reason = _check_transfer_policy(
            agent_directory, payment.pay_to, payment.budget_usd, payment.chain
        )
        if not policy_ok:
            _audit_payment(agent_directory, "payment_denied", {
                "method": "transfer", "amount_usd": payment.budget_usd,
                "pay_to": payment.pay_to, "reason": policy_reason,
            })
            return PaymentResult(
                success=False,
                method="transfer",
                amount_usd=0,
                error=f"policy denied: {policy_reason}",
            )

        # Build, sign, and broadcast on-chain
        tx = build_transfer_tx(
            payment.pay_to,
            payment.budget_usd,
            chain=payment.chain,
        )
        try:
            tx_hash = _sign_and_send_transfer(agent_directory, tx, payment.chain)
        except Exception as error:
            _audit_payment(agent_directory, "payment_failed", {
                "method": "transfer", "amount_usd": payment.budget_usd,
                "pay_to": payment.pay_to, "error": str(error),
            })
            return PaymentResult(
                success=False,
                method="transfer",
                amount_usd=payment.budget_usd,
                error=f"sign/send failed: {error}",
            )

        # Update budget atomically (we hold the lock from caller)
        _record_spend(agent_directory, payment.budget_usd)
        _audit_payment(agent_directory, "payment_settled", {
            "method": "transfer", "amount_usd": payment.budget_usd,
            "pay_to": payment.pay_to, "tx_hash": tx_hash,
        })

        return PaymentResult(
            success=True,
            method="transfer",
            amount_usd=payment.budget_usd,
            tx_hash=tx_hash,
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


# ---------------------------------------------------------------------------
# Direct USDC transfer — full sign + broadcast wiring
# ---------------------------------------------------------------------------


# RPC defaults per chain (override via AETHER_FORGE_RPC_<CHAIN> env var or
# by passing rpc_url through to the helper).
_RPC_DEFAULTS = {
    "base": "https://mainnet.base.org",
    "ethereum": "https://eth.llamarpc.com",
    "polygon": "https://polygon-rpc.com",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "optimism": "https://mainnet.optimism.io",
}


def _check_transfer_policy(
    agent_directory: Path,
    recipient: str,
    amount_usd: float,
    chain: str,
) -> tuple[bool, str]:
    """Verify the agent's policy permits this direct USDC transfer.

    Reads ``policy-bundle.json`` for an ``agentPayments`` block:

    .. code-block:: json

        {
          "agentPayments": {
            "directTransferEnabled": true,
            "maxPerTransferUsd": 1.0,
            "allowedRecipients": ["0xabc...", "0xdef..."],
            "allowedChains": ["base"]
          }
        }

    If ``agentPayments`` is missing, transfers are DENIED by default
    (defense in depth — explicit opt-in required).

    ``allowedRecipients`` is optional; if absent, all recipients allowed
    up to the per-transfer limit. If present, the recipient MUST be in
    the list (case-insensitive).
    """
    policy_path = agent_directory / "policy-bundle.json"
    if not policy_path.exists():
        return (False, "no policy-bundle.json — transfers default to deny")

    try:
        policy = json.loads(policy_path.read_text())
    except Exception as error:
        return (False, f"policy-bundle.json invalid: {error}")

    cfg = policy.get("agentPayments")
    if not cfg or not cfg.get("directTransferEnabled"):
        return (False, "policy.agentPayments.directTransferEnabled is not true")

    max_per = float(cfg.get("maxPerTransferUsd", 0))
    if max_per <= 0:
        return (False, "policy.agentPayments.maxPerTransferUsd must be > 0")
    if amount_usd > max_per:
        return (False, f"amount ${amount_usd} exceeds policy max ${max_per}")

    allowed_chains = cfg.get("allowedChains")
    if allowed_chains and chain not in allowed_chains:
        return (False, f"chain '{chain}' not in policy.allowedChains")

    allowed_recipients = cfg.get("allowedRecipients")
    if allowed_recipients:
        normalized = {r.lower() for r in allowed_recipients}
        if recipient.lower() not in normalized:
            return (False, f"recipient {recipient} not in policy.allowedRecipients")

    return (True, "ok")


def _sign_and_send_transfer(
    agent_directory: Path,
    tx_partial: dict[str, Any],
    chain: str,
    *,
    rpc_url: str | None = None,
) -> str:
    """Complete the unsigned tx, sign via OWS, broadcast, and return tx_hash.

    Takes the ``build_transfer_tx`` partial (to/data/value/chainId/type) and
    enriches it with nonce + gas estimate via RPC, then RLP-encodes it as an
    EIP-1559 unsigned envelope and hands it to ``wallet.sign_and_send``.
    """
    from .wallet import sign_and_send, load_agent_wallet
    from .onchain_registry import encode_eip1559_unsigned

    rpc = rpc_url or _RPC_DEFAULTS.get(chain) or _RPC_DEFAULTS["base"]

    # Get the agent's EVM address
    wallet_cfg = load_agent_wallet(agent_directory)
    accounts = wallet_cfg.get("accounts", []) or wallet_cfg.get("addresses", {})
    if isinstance(accounts, dict):
        from_address = accounts.get("evm")
    else:
        evm = next((a for a in accounts if a.get("chain") == "evm"), None)
        from_address = evm["address"] if evm else None
    if not from_address:
        raise RuntimeError("could not determine agent EVM address")

    # Fetch nonce + gas via RPC
    nonce = _rpc_call(rpc, "eth_getTransactionCount", [from_address, "latest"])
    gas_price = _rpc_call(rpc, "eth_gasPrice", [])
    try:
        gas_estimate_hex = _rpc_call(rpc, "eth_estimateGas", [{
            "from": from_address,
            "to": tx_partial["to"],
            "data": tx_partial["data"],
            "value": tx_partial.get("value", "0x0"),
        }])
        gas_estimate = int(gas_estimate_hex, 16)
    except Exception:
        gas_estimate = 100_000  # safe default for ERC-20 transfer
    gas_limit = int(gas_estimate * 1.2)

    full_tx = {
        "from": from_address,
        "to": tx_partial["to"],
        "data": tx_partial["data"],
        "value": tx_partial.get("value", "0x0"),
        "chainId": tx_partial["chainId"],
        "type": "0x2",
        "nonce": nonce,
        "gas": hex(gas_limit),
        "maxFeePerGas": hex(int(gas_price, 16) * 2),
        "maxPriorityFeePerGas": hex(int(gas_price, 16) // 10 + 1),
    }

    # RLP-encode as unsigned EIP-1559 envelope
    tx_hex = encode_eip1559_unsigned(full_tx)

    # Sign + broadcast via OWS
    result = sign_and_send(agent_directory, chain, tx_hex, rpc_url=rpc)
    tx_hash = result.get("tx_hash") or result.get("txHash") or ""
    if not tx_hash:
        raise RuntimeError(f"sign_and_send returned no tx_hash: {result}")
    return tx_hash


def _rpc_call(rpc_url: str, method: str, params: list) -> str:
    """Single JSON-RPC call returning the raw hex result string."""
    import json as _json
    from urllib import request as _ur

    body = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = _ur.Request(rpc_url, data=body, headers={"Content-Type": "application/json"})
    with _ur.urlopen(req, timeout=15) as resp:
        out = _json.loads(resp.read())
        if "error" in out:
            raise RuntimeError(out["error"])
        return out["result"]


def _record_spend(agent_directory: Path, amount_usd: float) -> None:
    """Update x402_state.json after a successful payment."""
    state_path = agent_directory / "x402_state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text())
        except Exception:
            state = {}
    state["session_spent_usd"] = state.get("session_spent_usd", 0.0) + amount_usd
    today = datetime.now(UTC).date().isoformat()
    daily = state.get("daily_spent_usd", {}) or {}
    daily[today] = daily.get(today, 0.0) + amount_usd
    state["daily_spent_usd"] = daily
    state["total_payments"] = state.get("total_payments", 0) + 1
    state["saved_at"] = datetime.now(UTC).isoformat()
    state_path.write_text(json.dumps(state, indent=2))


def _audit_payment(agent_directory: Path, event: str, details: dict[str, Any]) -> None:
    """Append a payment event to x402_audit.jsonl."""
    audit_path = agent_directory / "x402_audit.jsonl"
    record = {
        "timestamp": datetime.now(UTC).isoformat(),
        "event": event,
        **details,
    }
    with audit_path.open("a") as f:
        f.write(json.dumps(record) + "\n")

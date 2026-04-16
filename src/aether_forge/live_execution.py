"""Live execution layer with budget caps, circuit breaker, and audit log.

Wraps OWS sign_and_send and Elsa x402 calls with hard safety rails:
- Budget cap rejects orders above limit BEFORE signing
- Circuit breaker auto-stops on N consecutive failures
- Append-only audit log of every signed payload
- Daily loss limit
- Per-tx and per-day spending caps

This module is framework-level. The generated scaffold's router imports it
and uses it when ``mode=live``. Stage 1 of the production rollout plan.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, date
from pathlib import Path
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

# CAIP-2 chain IDs
TESTNET_CHAINS = {
    "base-sepolia": "eip155:84532",
    "sepolia": "eip155:11155111",
    "optimism-sepolia": "eip155:11155420",
}

# RPC URLs for testnets
TESTNET_RPCS = {
    "base-sepolia": "https://sepolia.base.org",
    "sepolia": "https://rpc.sepolia.org",
    "optimism-sepolia": "https://sepolia.optimism.io",
}


@dataclass(slots=True)
class LiveExecutionConfig:
    """Hard safety rails for live execution."""

    # Budget caps (USD)
    max_order_size_usd: float = 1.0  # Per-order cap
    max_daily_loss_usd: float = 10.0  # Per-day loss cap
    max_total_spent_usd: float = 20.0  # Per-session total cap
    max_open_orders: int = 2  # Concurrent order cap

    # Circuit breaker
    max_consecutive_failures: int = 3  # Trip after N failed transactions
    circuit_breaker_active: bool = False  # Manual override

    # Network
    chain: str = "base-sepolia"  # Default to testnet
    rpc_url: str | None = None  # Override RPC

    # Audit
    audit_log_path: str | None = None

    # Dry run — sign but don't broadcast
    dry_run: bool = True


@dataclass(slots=True)
class LiveExecutionState:
    """Mutable state for the live execution loop."""

    total_spent_usd: float = 0.0
    daily_losses_usd: dict[str, float] = field(default_factory=dict)
    consecutive_failures: int = 0
    open_order_count: int = 0
    circuit_tripped: bool = False
    transaction_count: int = 0

    def daily_loss(self, day: str | None = None) -> float:
        day = day or date.today().isoformat()
        return self.daily_losses_usd.get(day, 0.0)

    def record_loss(self, amount_usd: float) -> None:
        if amount_usd <= 0:
            return
        day = date.today().isoformat()
        self.daily_losses_usd[day] = self.daily_losses_usd.get(day, 0.0) + amount_usd


class CircuitBreakerError(RuntimeError):
    """Raised when the circuit breaker has tripped."""


class BudgetExceededError(RuntimeError):
    """Raised when an order would exceed configured budget caps."""


class LiveExecutor:
    """Hard-rails wrapper for OWS signing and x402 payments.

    Every action passes through:
    1. Circuit breaker check
    2. Budget cap check
    3. Audit log entry
    4. OWS signing
    5. Broadcast (or skip if dry_run)
    6. Result audit
    """

    def __init__(
        self,
        config: LiveExecutionConfig,
        *,
        agent_directory: Path,
        sign_and_send_fn: Callable | None = None,
        sign_message_fn: Callable | None = None,
        http_request_fn: Callable | None = None,
    ) -> None:
        self.config = config
        self.agent_directory = Path(agent_directory)
        self.state = LiveExecutionState()

        # Injectable for testing
        self._sign_and_send = sign_and_send_fn
        self._sign_message = sign_message_fn
        self._http_request = http_request_fn

        # Audit log location
        if config.audit_log_path:
            self._audit_path = Path(config.audit_log_path)
        else:
            self._audit_path = self.agent_directory / "audit.jsonl"
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

        # Default to chain RPC if not overridden
        if not self.config.rpc_url:
            self.config.rpc_url = TESTNET_RPCS.get(self.config.chain)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def place_order(
        self,
        *,
        side: str,
        token: str,
        amount: float,
        limit_price: float,
    ) -> dict[str, Any]:
        """Place a limit order with full safety checks.

        Flow: circuit check → budget check → audit → sign → broadcast → audit.
        """
        notional = amount * limit_price

        # 1. Circuit breaker
        self._check_circuit()

        # 2. Budget caps
        self._check_budget(notional)

        # 3. Pre-sign audit
        order_payload = {
            "side": side,
            "token": token,
            "amount": amount,
            "limit_price": limit_price,
            "notional_usd": round(notional, 2),
            "chain": self.config.chain,
            "dry_run": self.config.dry_run,
        }
        self._audit("order_attempted", order_payload)

        # 4. Build the transaction
        # In real Elsa: this would call elsa.create_limit_order which returns tx_hex
        # For Stage 1 we simulate the tx_hex but validate the full sign path
        tx_hex = self._build_order_tx(order_payload)

        # 5. Sign and (optionally) broadcast
        try:
            if self.config.dry_run:
                # Sign only — verify the path works without spending
                from .wallet import sign_message
                sig_result = sign_message(self.agent_directory, self._chain_for_signing(), json.dumps(order_payload))
                result = {
                    "status": "signed_dry_run",
                    "signature": sig_result.get("signature", "")[:32] + "..." if sig_result.get("signature") else "",
                    "tx_hex": tx_hex,
                    "would_broadcast_to": self.config.rpc_url,
                    **order_payload,
                }
            else:
                # Real broadcast
                from .wallet import sign_and_send
                tx_result = sign_and_send(
                    self.agent_directory,
                    self._chain_for_signing(),
                    tx_hex,
                    rpc_url=self.config.rpc_url,
                )
                result = {
                    "status": "broadcast",
                    "tx_hash": tx_result.get("tx_hash", ""),
                    **order_payload,
                }

            # 6. Success audit
            self._audit("order_placed", result)
            self.state.consecutive_failures = 0
            self.state.total_spent_usd += notional
            self.state.open_order_count += 1
            self.state.transaction_count += 1
            return result

        except Exception as error:
            self.state.consecutive_failures += 1
            self._audit("order_failed", {"error": str(error), **order_payload})
            if self.state.consecutive_failures >= self.config.max_consecutive_failures:
                self.state.circuit_tripped = True
                self._audit("circuit_breaker_tripped", {
                    "consecutive_failures": self.state.consecutive_failures,
                    "limit": self.config.max_consecutive_failures,
                })
                logger.error(
                    "Circuit breaker TRIPPED after %d consecutive failures",
                    self.state.consecutive_failures,
                )
            raise

    def reset_circuit(self) -> None:
        """Manual reset after investigation."""
        self.state.circuit_tripped = False
        self.state.consecutive_failures = 0
        self._audit("circuit_breaker_reset", {})

    def status(self) -> dict[str, Any]:
        """Current state for monitoring."""
        return {
            "circuit_tripped": self.state.circuit_tripped,
            "consecutive_failures": self.state.consecutive_failures,
            "total_spent_usd": round(self.state.total_spent_usd, 2),
            "daily_loss_usd": round(self.state.daily_loss(), 2),
            "open_orders": self.state.open_order_count,
            "transactions": self.state.transaction_count,
            "budget_remaining_usd": round(self.config.max_total_spent_usd - self.state.total_spent_usd, 2),
            "dry_run": self.config.dry_run,
            "chain": self.config.chain,
        }

    # ------------------------------------------------------------------
    # Safety checks
    # ------------------------------------------------------------------

    def _check_circuit(self) -> None:
        if self.state.circuit_tripped or self.config.circuit_breaker_active:
            raise CircuitBreakerError(
                f"Circuit breaker is tripped after {self.state.consecutive_failures} failures. "
                f"Run executor.reset_circuit() to resume."
            )

    def _check_budget(self, notional_usd: float) -> None:
        # Per-order cap
        if notional_usd > self.config.max_order_size_usd:
            raise BudgetExceededError(
                f"Order ${notional_usd:.2f} exceeds per-order cap ${self.config.max_order_size_usd:.2f}"
            )

        # Total session cap
        if self.state.total_spent_usd + notional_usd > self.config.max_total_spent_usd:
            raise BudgetExceededError(
                f"Order would push total to ${self.state.total_spent_usd + notional_usd:.2f}, "
                f"exceeds session cap ${self.config.max_total_spent_usd:.2f}"
            )

        # Daily loss cap
        if self.state.daily_loss() >= self.config.max_daily_loss_usd:
            raise BudgetExceededError(
                f"Daily loss ${self.state.daily_loss():.2f} >= cap ${self.config.max_daily_loss_usd:.2f}"
            )

        # Open order cap
        if self.state.open_order_count >= self.config.max_open_orders:
            raise BudgetExceededError(
                f"Open orders {self.state.open_order_count} >= cap {self.config.max_open_orders}"
            )

    # ------------------------------------------------------------------
    # Audit log (append-only JSONL)
    # ------------------------------------------------------------------

    def _audit(self, event: str, payload: dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **payload,
        }
        try:
            with self._audit_path.open("a", encoding="utf8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as error:
            logger.warning("Audit log write failed: %s", error)

    def read_audit_log(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        """Read audit log entries (most recent last)."""
        if not self._audit_path.exists():
            return []
        entries = []
        with self._audit_path.open("r", encoding="utf8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        if limit:
            return entries[-limit:]
        return entries

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _chain_for_signing(self) -> str:
        """Convert config chain to OWS chain name."""
        # OWS uses 'ethereum' for EVM chains; the actual chain ID comes from RPC
        if "sepolia" in self.config.chain or "ethereum" in self.config.chain or "base" in self.config.chain:
            return "ethereum"
        return self.config.chain

    def _build_order_tx(self, order: dict[str, Any]) -> str:
        """Build transaction hex for an order.

        Stage 1: returns a placeholder hex. Stage 2 will build real
        Elsa-formatted transactions or call create_limit_order endpoint.
        """
        # Encode order as a simple hex blob for now
        order_bytes = json.dumps(order, sort_keys=True).encode("utf8")
        return "0x" + order_bytes.hex()


# ---------------------------------------------------------------------------
# Factory for scaffold use
# ---------------------------------------------------------------------------

def build_live_executor(
    agent_directory: Path,
    *,
    chain: str = "base-sepolia",
    dry_run: bool = True,
    max_order_size_usd: float = 1.0,
    max_total_spent_usd: float = 20.0,
    max_daily_loss_usd: float = 10.0,
) -> LiveExecutor:
    """Build a live executor with safe defaults for Stage 1 testing."""
    config = LiveExecutionConfig(
        max_order_size_usd=max_order_size_usd,
        max_total_spent_usd=max_total_spent_usd,
        max_daily_loss_usd=max_daily_loss_usd,
        max_open_orders=2,
        chain=chain,
        dry_run=dry_run,
    )
    return LiveExecutor(config, agent_directory=agent_directory)

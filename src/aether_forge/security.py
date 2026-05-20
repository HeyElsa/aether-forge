"""Agent security hardening for Aether Forge.

Implements defense-in-depth controls:
- Session key management with expiry and scope constraints
- Budget controls with circuit breakers
- Input sanitization against prompt injection
- Audit logging for all sensitive operations
- Rate limiting
"""

from __future__ import annotations

import base64
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)

_UTC = UTC


class SecurityLevel(Enum):
    SANDBOX = "sandbox"
    PAPER = "paper"
    CANARY = "canary"
    PRODUCTION = "production"


# ---------------------------------------------------------------------------
# Session-key management
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SessionKeyPolicy:
    """Scoped session key with constraints. Never give agents master keys."""

    key_id: str
    wallet_address: str
    allowed_contracts: list[str] = field(default_factory=list)
    allowed_chains: list[str] = field(default_factory=list)
    max_spend_per_tx_usd: float = 10.0
    max_spend_per_day_usd: float = 100.0
    max_transactions_per_hour: int = 20
    expires_at: str = ""
    created_at: str = field(
        default_factory=lambda: datetime.now(_UTC).isoformat()
    )

    def is_expired(self) -> bool:
        """Return True if the session key has passed its expiry time."""
        if not self.expires_at:
            return False
        try:
            expiry = datetime.fromisoformat(self.expires_at)
            if expiry.tzinfo is None:
                expiry = expiry.replace(tzinfo=_UTC)
            return datetime.now(_UTC) >= expiry
        except ValueError:
            # Malformed expiry string treated as expired for safety.
            return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "wallet_address": self.wallet_address,
            "allowed_contracts": list(self.allowed_contracts),
            "allowed_chains": list(self.allowed_chains),
            "max_spend_per_tx_usd": self.max_spend_per_tx_usd,
            "max_spend_per_day_usd": self.max_spend_per_day_usd,
            "max_transactions_per_hour": self.max_transactions_per_hour,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionKeyPolicy:
        return cls(
            key_id=data["key_id"],
            wallet_address=data["wallet_address"],
            allowed_contracts=data.get("allowed_contracts", []),
            allowed_chains=data.get("allowed_chains", []),
            max_spend_per_tx_usd=data.get("max_spend_per_tx_usd", 10.0),
            max_spend_per_day_usd=data.get("max_spend_per_day_usd", 100.0),
            max_transactions_per_hour=data.get(
                "max_transactions_per_hour", 20
            ),
            expires_at=data.get("expires_at", ""),
            created_at=data.get(
                "created_at", datetime.now(_UTC).isoformat()
            ),
        )

    def permits(
        self,
        *,
        chain_id: int | str | None = None,
        contract_address: str | None = None,
        spend_usd: float | None = None,
    ) -> tuple[bool, str]:
        """Check whether a signing intent satisfies this session-key policy
        (Sprint 2.3 / FP-3).

        Returns ``(True, "permitted")`` on success or ``(False, reason)`` when
        any constraint is violated. Designed to be called by
        :class:`aether_forge.crypto.signers.SessionKeyConstrainedSigner`
        before delegating to an inner signer.

        Fail-closed semantics:
        - Expired policy refuses everything.
        - A populated ``allowed_chains`` / ``allowed_contracts`` list with a
          ``None`` intent value refuses (intent must declare every constrained
          field). Empty lists permit any value for that field — opt-in scoping.
        - Spend exceeding ``max_spend_per_tx_usd`` refuses. A ``None`` spend
          intent is permitted (callers may legitimately sign non-payment
          typed-data; constrain via policy.spend if required).
        """
        if self.is_expired():
            return False, f"session key {self.key_id!r} has expired"
        if self.allowed_chains and chain_id is None:
            return False, "policy restricts chains but intent did not declare chain_id"
        if self.allowed_chains and chain_id is not None:
            chain_str = str(chain_id)
            target_int = _coerce_chain_id(chain_id)
            matches = chain_str in self.allowed_chains or any(
                target_int is not None and _coerce_chain_id(allowed) == target_int
                for allowed in self.allowed_chains
            )
            if not matches:
                return False, f"chain {chain_id} not in policy allowed_chains={self.allowed_chains}"
        if self.allowed_contracts and contract_address is None:
            return False, "policy restricts contracts but intent did not declare contract_address"
        if self.allowed_contracts and contract_address is not None:
            target = contract_address.lower()
            if not any(addr.lower() == target for addr in self.allowed_contracts):
                return False, f"contract {contract_address} not in policy allowed_contracts"
        if spend_usd is not None and spend_usd > self.max_spend_per_tx_usd:
            return False, f"intent spend ${spend_usd:.4f} exceeds policy cap ${self.max_spend_per_tx_usd:.4f}"
        return True, "permitted"


def _coerce_chain_id(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Budget control
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class BudgetControl:
    """Runtime budget tracking with circuit breaker."""

    budget_limit_usd: float
    spent_usd: float = 0.0
    transaction_count: int = 0
    circuit_breaker_triggered: bool = False
    circuit_breaker_reason: str = ""
    velocity_window_seconds: int = 3600
    velocity_threshold: float = 3.0
    _recent_spends: list[tuple[str, float]] = field(default_factory=list)

    def can_spend(self, amount_usd: float) -> tuple[bool, str]:
        """Check if a spend is allowed. Returns (allowed, reason)."""
        logger.debug("Budget check: spent=%.2f limit=%.2f", self.spent_usd, self.budget_limit_usd)
        if self.circuit_breaker_triggered:
            return (
                False,
                f"Circuit breaker: {self.circuit_breaker_reason}",
            )
        if amount_usd < 0:
            return False, "Negative spend amount"
        if self.spent_usd + amount_usd > self.budget_limit_usd:
            return (
                False,
                (
                    f"Budget exceeded: "
                    f"{self.spent_usd + amount_usd:.2f} > "
                    f"{self.budget_limit_usd:.2f}"
                ),
            )
        return True, ""

    def record_spend(self, amount_usd: float) -> None:
        """Record a spend and check velocity circuit breaker."""
        self.spent_usd += amount_usd
        self.transaction_count += 1
        now = datetime.now(_UTC).isoformat()
        self._recent_spends.append((now, amount_usd))
        self._check_velocity()

    def _check_velocity(self) -> None:
        """Trigger circuit breaker if spending velocity exceeds threshold.

        Compares the average of the last 3 transactions against the
        overall historical average.  This works even when all spends
        arrive in the same instant (common in tests and burst scenarios).
        """
        # Prune spends outside the rolling window
        cutoff = (
            datetime.now(_UTC)
            - timedelta(seconds=self.velocity_window_seconds)
        ).isoformat()
        self._recent_spends = [
            (t, a) for t, a in self._recent_spends if t >= cutoff
        ]
        if len(self._recent_spends) < 3:
            return
        if self.transaction_count <= 5:
            return

        # Compare the tail (last 3 spends) against overall average
        tail = self._recent_spends[-3:]
        tail_avg = sum(a for _, a in tail) / len(tail)
        overall_avg = self.spent_usd / self.transaction_count

        if overall_avg > 0 and tail_avg > overall_avg * self.velocity_threshold:
            logger.warning("Circuit breaker triggered: velocity=%.2f threshold=%.2f", tail_avg, self.velocity_threshold)
            self.circuit_breaker_triggered = True
            self.circuit_breaker_reason = (
                f"Velocity {tail_avg:.2f}/tx exceeds "
                f"{self.velocity_threshold}x avg "
                f"{overall_avg:.2f}/tx"
            )

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker after human review."""
        self.circuit_breaker_triggered = False
        self.circuit_breaker_reason = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget_limit_usd": self.budget_limit_usd,
            "spent_usd": self.spent_usd,
            "transaction_count": self.transaction_count,
            "circuit_breaker_triggered": self.circuit_breaker_triggered,
            "circuit_breaker_reason": self.circuit_breaker_reason,
            "velocity_window_seconds": self.velocity_window_seconds,
            "velocity_threshold": self.velocity_threshold,
            "recent_spends": list(self._recent_spends),
        }


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class AuditEntry:
    """Immutable audit log entry for sensitive operations."""

    timestamp: str
    operation: str
    actor: str
    target: str
    amount_usd: float = 0.0
    status: str = "success"
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class AuditLog:
    """Append-only audit log for agent operations."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(
        self,
        operation: str,
        actor: str,
        target: str,
        **kwargs: Any,
    ) -> AuditEntry:
        """Create and append an audit entry. Returns the entry."""
        entry = AuditEntry(
            timestamp=datetime.now(_UTC).isoformat(),
            operation=operation,
            actor=actor,
            target=target,
            amount_usd=kwargs.get("amount_usd", 0.0),
            status=kwargs.get("status", "success"),
            reason=kwargs.get("reason", ""),
            metadata=kwargs.get("metadata", {}),
        )
        self._entries.append(entry)
        return entry

    def get_entries(
        self,
        operation: str | None = None,
        limit: int = 100,
    ) -> list[AuditEntry]:
        """Return entries, optionally filtered, most recent first."""
        if operation is not None:
            filtered = [
                e for e in self._entries if e.operation == operation
            ]
        else:
            filtered = list(self._entries)
        return filtered[-limit:][::-1]

    def export(self) -> list[dict[str, Any]]:
        """Export all entries as serializable dicts."""
        return [
            {
                "timestamp": e.timestamp,
                "operation": e.operation,
                "actor": e.actor,
                "target": e.target,
                "amount_usd": e.amount_usd,
                "status": e.status,
                "reason": e.reason,
                "metadata": e.metadata,
            }
            for e in self._entries
        ]

    def __len__(self) -> int:
        return len(self._entries)


# ---------------------------------------------------------------------------
# Input sanitiser
# ---------------------------------------------------------------------------


class InputSanitizer:
    """Detect and neutralize prompt injection attempts."""

    INJECTION_PATTERNS: list[str] = [
        # 1. Direct instruction override
        r"(?i)ignore\s+(all\s+)?previous\s+instructions",
        # 2. System role impersonation
        r"(?i)^(system|SYSTEM)\s*:",
        # 3. Prompt leaking / extraction
        r"(?i)(reveal|show|print|output|repeat)\s+.{0,20}"
        r"(prompt|instructions|rules)",
        # 4. Role-play jailbreaks
        r"(?i)(DAN|developer\s+mode|jailbreak|do\s+anything\s+now)",
        # 5. Delimiter injection -- fake message boundaries
        r"(?i)(###\s*(SYSTEM|USER|ASSISTANT)"
        r"|<\|im_start\|>|<\|im_end\|>)",
        # 6. Hidden instruction markers
        r"(?i)\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>",
        # 7. Base64-encoded payload blocks
        r"(?i)(base64|b64)[:\s]+[A-Za-z0-9+/=]{40,}",
        # 8. Invisible unicode / zero-width chars
        r"[\u200b\u200c\u200d\u2060\ufeff]{3,}",
        # 9. HTML/Markdown hiding tricks
        r"(?i)<(div|span|p)\s+style\s*=\s*[\"'].*?"
        r"display\s*:\s*none",
        # 10. "You are now" persona rewrite
        r"(?i)you\s+are\s+now\s+(a|an|the)\s+",
        # 11. Token smuggling via markdown comments
        r"<!--.*?-->",
        # 12. Excessive repetition of override language
        r"(?i)(forget|disregard|override|bypass)"
        r"\s+(everything|all|prior|above)",
    ]

    _compiled: list[re.Pattern[str]] = [
        re.compile(p, re.DOTALL) for p in INJECTION_PATTERNS
    ]

    @staticmethod
    def scan(text: str) -> tuple[bool, list[str]]:
        """Scan text for prompt injection indicators.

        Returns ``(is_suspicious, matched_patterns)``.
        """
        matched: list[str] = []
        for pattern, compiled in zip(
            InputSanitizer.INJECTION_PATTERNS,
            InputSanitizer._compiled,
        ):
            if compiled.search(text):
                matched.append(pattern)
                logger.warning("Prompt injection detected: pattern=%s", pattern)

        # Heuristic: decode base64 blobs and re-scan
        b64_blocks = re.findall(r"[A-Za-z0-9+/=]{60,}", text)
        for block in b64_blocks:
            try:
                decoded = base64.b64decode(
                    block, validate=True
                ).decode("utf-8", errors="ignore")
                for compiled in InputSanitizer._compiled:
                    if compiled.search(decoded):
                        matched.append(
                            f"base64-hidden: {block[:30]}..."
                        )
                        break
            except Exception:  # noqa: BLE001
                pass

        return bool(matched), matched

    @staticmethod
    def sanitize(text: str) -> str:
        """Strip or neutralize detected injection patterns."""
        out = text

        # Remove zero-width / invisible unicode
        out = re.sub(r"[\u200b\u200c\u200d\u2060\ufeff]", "", out)

        # Remove HTML comments
        out = re.sub(r"<!--.*?-->", "", out, flags=re.DOTALL)

        # Remove hidden HTML elements
        out = re.sub(
            r"(?i)<(div|span|p)\s+style\s*=\s*[\"'].*?"
            r"display\s*:\s*none.*?</(div|span|p)>",
            "",
            out,
            flags=re.DOTALL,
        )

        # Neutralize system role impersonation
        out = re.sub(
            r"(?im)^(system|SYSTEM)\s*:",
            "[BLOCKED-ROLE]:",
            out,
        )

        # Neutralize fake delimiters
        out = re.sub(
            r"(?i)(###\s*(SYSTEM|USER|ASSISTANT))",
            "[BLOCKED-DELIMITER]",
            out,
        )
        out = re.sub(
            r"(<\|im_start\|>|<\|im_end\|>)",
            "[BLOCKED-DELIMITER]",
            out,
        )
        out = re.sub(
            r"(?i)(\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>)",
            "[BLOCKED-DELIMITER]",
            out,
        )

        return out


# ---------------------------------------------------------------------------
# Rate limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket rate limiter for agent operations."""

    def __init__(
        self,
        max_requests: int = 60,
        window_seconds: int = 60,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._tokens = float(max_requests)
        self._last_refill = time.monotonic()

    def allow(self) -> bool:
        """Consume a token and return True, or return False."""
        self._refill()
        if self._tokens >= 1.0:
            self._tokens -= 1.0
            logger.debug("Rate limit: %s tokens=%d", "allowed", int(self._tokens))
            return True
        logger.debug("Rate limit: %s tokens=%d", "denied", int(self._tokens))
        return False

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        rate = self.max_requests / self.window_seconds
        self._tokens = min(
            float(self.max_requests),
            self._tokens + elapsed * rate,
        )
        self._last_refill = now

    def reset(self) -> None:
        """Reset the limiter to full capacity."""
        self._tokens = float(self.max_requests)
        self._last_refill = time.monotonic()


# ---------------------------------------------------------------------------
# Default security configuration
# ---------------------------------------------------------------------------


def create_default_security_config(
    level: SecurityLevel,
) -> dict[str, Any]:
    """Create security configuration defaults for a given level.

    sandbox:    permissive limits, no real money
    paper:      moderate limits, simulated execution
    canary:     tight limits, real money, low exposure
    production: strictest limits, full audit, circuit breakers active
    """
    configs: dict[SecurityLevel, dict[str, Any]] = {
        SecurityLevel.SANDBOX: {
            "level": "sandbox",
            "session_key": {
                "max_spend_per_tx_usd": 1000.0,
                "max_spend_per_day_usd": 10000.0,
                "max_transactions_per_hour": 1000,
                "expiry_hours": 168,
            },
            "budget": {
                "budget_limit_usd": 10000.0,
                "velocity_threshold": 10.0,
                "velocity_window_seconds": 3600,
            },
            "rate_limit": {
                "max_requests": 600,
                "window_seconds": 60,
            },
            "audit": {
                "enabled": True,
                "log_denials": True,
                "log_spends": False,
            },
            "input_sanitization": {
                "enabled": False,
                "block_on_detection": False,
            },
        },
        SecurityLevel.PAPER: {
            "level": "paper",
            "session_key": {
                "max_spend_per_tx_usd": 100.0,
                "max_spend_per_day_usd": 1000.0,
                "max_transactions_per_hour": 100,
                "expiry_hours": 24,
            },
            "budget": {
                "budget_limit_usd": 1000.0,
                "velocity_threshold": 5.0,
                "velocity_window_seconds": 3600,
            },
            "rate_limit": {
                "max_requests": 120,
                "window_seconds": 60,
            },
            "audit": {
                "enabled": True,
                "log_denials": True,
                "log_spends": True,
            },
            "input_sanitization": {
                "enabled": True,
                "block_on_detection": False,
            },
        },
        SecurityLevel.CANARY: {
            "level": "canary",
            "session_key": {
                "max_spend_per_tx_usd": 10.0,
                "max_spend_per_day_usd": 100.0,
                "max_transactions_per_hour": 20,
                "expiry_hours": 4,
            },
            "budget": {
                "budget_limit_usd": 100.0,
                "velocity_threshold": 3.0,
                "velocity_window_seconds": 1800,
            },
            "rate_limit": {
                "max_requests": 60,
                "window_seconds": 60,
            },
            "audit": {
                "enabled": True,
                "log_denials": True,
                "log_spends": True,
            },
            "input_sanitization": {
                "enabled": True,
                "block_on_detection": True,
            },
        },
        SecurityLevel.PRODUCTION: {
            "level": "production",
            "session_key": {
                "max_spend_per_tx_usd": 5.0,
                "max_spend_per_day_usd": 50.0,
                "max_transactions_per_hour": 10,
                "expiry_hours": 1,
            },
            "budget": {
                "budget_limit_usd": 50.0,
                "velocity_threshold": 2.0,
                "velocity_window_seconds": 900,
            },
            "rate_limit": {
                "max_requests": 30,
                "window_seconds": 60,
            },
            "audit": {
                "enabled": True,
                "log_denials": True,
                "log_spends": True,
            },
            "input_sanitization": {
                "enabled": True,
                "block_on_detection": True,
            },
        },
    }
    return configs[level]

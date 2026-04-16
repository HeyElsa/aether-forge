"""Domain-specific exception hierarchy for Aether Forge."""

from __future__ import annotations


class ForgeError(Exception):
    """Base exception for all Aether Forge errors."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class ValidationError(ForgeError):
    """Raised when artifact or schema validation fails."""


class ArtifactNotFoundError(ForgeError, FileNotFoundError):
    """Raised when a required artifact file is missing."""


# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

class PolicyError(ForgeError):
    """Raised when a policy enforcement rule is violated."""


class PolicyDeniedError(PolicyError):
    """Raised when a policy check explicitly denies an action."""

    def __init__(self, message: str, *, rule_ids: list[str] | None = None) -> None:
        super().__init__(message)
        self.rule_ids = rule_ids or []


class ApprovalRequiredError(PolicyError):
    """Raised when an action requires manual approval."""

    def __init__(self, message: str, *, approval_kind: str = "manual") -> None:
        super().__init__(message)
        self.approval_kind = approval_kind


# ---------------------------------------------------------------------------
# Runtime
# ---------------------------------------------------------------------------

class RuntimeError_(ForgeError):
    """Raised for runtime session execution errors."""


class SessionHeldError(RuntimeError_):
    """Raised when a session is held pending approval."""


class MaxStepsExceededError(RuntimeError_):
    """Raised when the runtime loop exceeds the step limit."""


# ---------------------------------------------------------------------------
# Provider / Model
# ---------------------------------------------------------------------------

class ProviderError(ForgeError):
    """Raised for LLM provider communication errors."""


class ModelResponseError(ProviderError):
    """Raised when an LLM response cannot be parsed."""


class ProviderConnectionError(ProviderError):
    """Raised when a provider endpoint is unreachable."""


# ---------------------------------------------------------------------------
# Crypto / Exchange
# ---------------------------------------------------------------------------

class CryptoError(ForgeError):
    """Raised for crypto execution layer errors."""


class CredentialError(CryptoError):
    """Raised when credential resolution fails."""


class ExchangeError(CryptoError):
    """Raised for exchange operation failures."""


class WalletError(CryptoError):
    """Raised for wallet operation failures."""


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

class SecurityError(ForgeError):
    """Raised for security-related violations."""


class BudgetExceededError(SecurityError):
    """Raised when a spending operation would exceed budget limits."""


class CircuitBreakerError(SecurityError):
    """Raised when the circuit breaker is triggered."""


class InjectionDetectedError(SecurityError):
    """Raised when prompt injection is detected."""

    def __init__(self, message: str, *, patterns: list[str] | None = None) -> None:
        super().__init__(message)
        self.patterns = patterns or []


class RateLimitError(SecurityError):
    """Raised when a rate limit is exceeded."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

class ConfigError(ForgeError):
    """Raised for configuration errors."""


class SecretNotFoundError(ConfigError, KeyError):
    """Raised when a required secret cannot be resolved."""


# ---------------------------------------------------------------------------
# Market Data
# ---------------------------------------------------------------------------

class MarketDataError(ForgeError):
    """Raised when market data fetching fails."""


class VenueUnavailableError(MarketDataError):
    """Raised when a market data venue is unreachable."""

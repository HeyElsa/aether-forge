"""Tests for the domain exception hierarchy."""

from aether_forge.exceptions import (
    ApprovalRequiredError,
    BudgetExceededError,
    CircuitBreakerError,
    ConfigError,
    CredentialError,
    CryptoError,
    ExchangeError,
    ForgeError,
    InjectionDetectedError,
    MarketDataError,
    ModelResponseError,
    PolicyDeniedError,
    PolicyError,
    ProviderConnectionError,
    ProviderError,
    RateLimitError,
    RuntimeError_,
    SecretNotFoundError,
    SecurityError,
    SessionHeldError,
    ValidationError,
    VenueUnavailableError,
    WalletError,
)


def test_forge_error_is_base() -> None:
    assert issubclass(ForgeError, Exception)


def test_hierarchy_chains() -> None:
    assert issubclass(ValidationError, ForgeError)
    assert issubclass(PolicyError, ForgeError)
    assert issubclass(PolicyDeniedError, PolicyError)
    assert issubclass(ApprovalRequiredError, PolicyError)
    assert issubclass(RuntimeError_, ForgeError)
    assert issubclass(SessionHeldError, RuntimeError_)
    assert issubclass(ProviderError, ForgeError)
    assert issubclass(ModelResponseError, ProviderError)
    assert issubclass(ProviderConnectionError, ProviderError)
    assert issubclass(CryptoError, ForgeError)
    assert issubclass(CredentialError, CryptoError)
    assert issubclass(ExchangeError, CryptoError)
    assert issubclass(WalletError, CryptoError)
    assert issubclass(SecurityError, ForgeError)
    assert issubclass(BudgetExceededError, SecurityError)
    assert issubclass(CircuitBreakerError, SecurityError)
    assert issubclass(InjectionDetectedError, SecurityError)
    assert issubclass(RateLimitError, SecurityError)
    assert issubclass(ConfigError, ForgeError)
    assert issubclass(SecretNotFoundError, ConfigError)
    assert issubclass(SecretNotFoundError, KeyError)
    assert issubclass(MarketDataError, ForgeError)
    assert issubclass(VenueUnavailableError, MarketDataError)


def test_policy_denied_carries_rule_ids() -> None:
    err = PolicyDeniedError("denied", rule_ids=["rule-1", "rule-2"])
    assert err.rule_ids == ["rule-1", "rule-2"]
    assert "denied" in str(err)


def test_injection_detected_carries_patterns() -> None:
    err = InjectionDetectedError("detected", patterns=["pattern-1"])
    assert err.patterns == ["pattern-1"]


def test_approval_required_carries_kind() -> None:
    err = ApprovalRequiredError("needs approval", approval_kind="human")
    assert err.approval_kind == "human"


def test_can_catch_forge_error_broadly() -> None:
    try:
        raise PolicyDeniedError("test")
    except ForgeError:
        pass  # Should be caught


def test_secret_not_found_is_key_error() -> None:
    try:
        raise SecretNotFoundError("missing-key")
    except KeyError:
        pass  # Should be caught as KeyError too

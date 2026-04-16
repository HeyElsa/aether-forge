"""Token usage tracking for LLM provider calls.

Tracks input/output tokens, cost estimation, and per-session aggregates
across all model invocations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TokenUsage:
    """Token counts from a single model call."""

    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def estimated_cost_usd(self, input_price_per_m: float = 0.0, output_price_per_m: float = 0.0) -> float:
        """Estimate cost in USD given per-million-token prices."""
        return (self.input_tokens * input_price_per_m + self.output_tokens * output_price_per_m) / 1_000_000


@dataclass(slots=True)
class UsageTracker:
    """Aggregates token usage across a session."""

    calls: list[TokenUsage] = field(default_factory=list)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)

    @property
    def total_tokens(self) -> int:
        return self.total_input_tokens + self.total_output_tokens

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def record(self, usage: TokenUsage) -> None:
        self.calls.append(usage)
        logger.debug(
            "Token usage: model=%s in=%d out=%d total=%d",
            usage.model, usage.input_tokens, usage.output_tokens, usage.total_tokens,
        )

    def estimated_cost_usd(self, input_price_per_m: float = 0.0, output_price_per_m: float = 0.0) -> float:
        return sum(c.estimated_cost_usd(input_price_per_m, output_price_per_m) for c in self.calls)

    def summary(self) -> dict[str, Any]:
        return {
            "calls": self.call_count,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_tokens": self.total_tokens,
            "by_model": self._by_model(),
        }

    def _by_model(self) -> dict[str, dict[str, int]]:
        models: dict[str, dict[str, int]] = {}
        for c in self.calls:
            key = c.model or "unknown"
            if key not in models:
                models[key] = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
            models[key]["calls"] += 1
            models[key]["input_tokens"] += c.input_tokens
            models[key]["output_tokens"] += c.output_tokens
        return models


# ---------------------------------------------------------------------------
# Provider-specific usage parsing
# ---------------------------------------------------------------------------

def parse_openai_usage(response: dict[str, Any], *, model: str = "") -> TokenUsage:
    """Parse token usage from an OpenAI-compatible response."""
    usage = response.get("usage", {})
    return TokenUsage(
        input_tokens=usage.get("prompt_tokens", 0),
        output_tokens=usage.get("completion_tokens", 0),
        model=response.get("model", model),
        provider="openai-compatible",
    )


def parse_anthropic_usage(response: dict[str, Any], *, model: str = "") -> TokenUsage:
    """Parse token usage from an Anthropic response."""
    usage = response.get("usage", {})
    return TokenUsage(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        model=response.get("model", model),
        provider="anthropic",
    )


def parse_gemini_usage(response: dict[str, Any], *, model: str = "") -> TokenUsage:
    """Parse token usage from a Gemini response."""
    metadata = response.get("usageMetadata", {})
    return TokenUsage(
        input_tokens=metadata.get("promptTokenCount", 0),
        output_tokens=metadata.get("candidatesTokenCount", 0),
        model=model,
        provider="gemini",
    )


# ---------------------------------------------------------------------------
# Pricing reference (per million tokens)
# ---------------------------------------------------------------------------

PRICING: dict[str, tuple[float, float]] = {
    # (input_per_m, output_per_m) in USD
    "claude-sonnet-4-20250514": (3.0, 15.0),
    "claude-opus-4-20250514": (15.0, 75.0),
    "claude-haiku-4-20250514": (0.25, 1.25),
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.15, 0.60),
}


def estimate_session_cost(tracker: UsageTracker) -> float:
    """Estimate total session cost using known model pricing."""
    total = 0.0
    for call in tracker.calls:
        pricing = PRICING.get(call.model)
        if pricing:
            total += call.estimated_cost_usd(pricing[0], pricing[1])
    return total

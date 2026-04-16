"""Tests for token usage tracking."""

from __future__ import annotations

from aether_forge.usage import (
    PRICING,
    TokenUsage,
    UsageTracker,
    estimate_session_cost,
    parse_anthropic_usage,
    parse_gemini_usage,
    parse_openai_usage,
)


def test_token_usage_total() -> None:
    usage = TokenUsage(input_tokens=100, output_tokens=50)
    assert usage.total_tokens == 150


def test_token_usage_cost_estimate() -> None:
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=500_000)
    cost = usage.estimated_cost_usd(input_price_per_m=3.0, output_price_per_m=15.0)
    assert cost == 3.0 + 7.5  # $3 input + $7.50 output


def test_tracker_aggregation() -> None:
    tracker = UsageTracker()
    tracker.record(TokenUsage(input_tokens=100, output_tokens=50, model="gpt-4o"))
    tracker.record(TokenUsage(input_tokens=200, output_tokens=100, model="gpt-4o"))
    tracker.record(TokenUsage(input_tokens=50, output_tokens=25, model="claude-sonnet-4-20250514"))

    assert tracker.call_count == 3
    assert tracker.total_input_tokens == 350
    assert tracker.total_output_tokens == 175
    assert tracker.total_tokens == 525


def test_tracker_summary() -> None:
    tracker = UsageTracker()
    tracker.record(TokenUsage(input_tokens=100, output_tokens=50, model="gpt-4o"))
    tracker.record(TokenUsage(input_tokens=200, output_tokens=100, model="claude-sonnet-4-20250514"))

    summary = tracker.summary()
    assert summary["calls"] == 2
    assert summary["total_tokens"] == 450
    assert "gpt-4o" in summary["by_model"]
    assert "claude-sonnet-4-20250514" in summary["by_model"]
    assert summary["by_model"]["gpt-4o"]["calls"] == 1


def test_parse_openai_usage() -> None:
    response = {
        "model": "gpt-4o",
        "usage": {"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700},
    }
    usage = parse_openai_usage(response)
    assert usage.input_tokens == 500
    assert usage.output_tokens == 200
    assert usage.model == "gpt-4o"
    assert usage.provider == "openai-compatible"


def test_parse_anthropic_usage() -> None:
    response = {
        "model": "claude-sonnet-4-20250514",
        "usage": {"input_tokens": 1000, "output_tokens": 300},
    }
    usage = parse_anthropic_usage(response)
    assert usage.input_tokens == 1000
    assert usage.output_tokens == 300
    assert usage.model == "claude-sonnet-4-20250514"


def test_parse_gemini_usage() -> None:
    response = {
        "usageMetadata": {"promptTokenCount": 800, "candidatesTokenCount": 150},
    }
    usage = parse_gemini_usage(response, model="gemini-2.5-pro")
    assert usage.input_tokens == 800
    assert usage.output_tokens == 150


def test_estimate_session_cost() -> None:
    tracker = UsageTracker()
    tracker.record(TokenUsage(input_tokens=1_000_000, output_tokens=500_000, model="gpt-4o"))
    cost = estimate_session_cost(tracker)
    # gpt-4o: $2.50/M input, $10/M output
    assert cost == 2.5 + 5.0


def test_pricing_has_known_models() -> None:
    assert "gpt-4o" in PRICING
    assert "claude-sonnet-4-20250514" in PRICING
    assert "gemini-2.5-pro" in PRICING


def test_empty_tracker() -> None:
    tracker = UsageTracker()
    assert tracker.call_count == 0
    assert tracker.total_tokens == 0
    assert estimate_session_cost(tracker) == 0.0

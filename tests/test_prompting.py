from __future__ import annotations

from pathlib import Path

from aether_forge.crypto import MockCryptoExecutionRouter
from aether_forge.planner import HeuristicPlanner
from aether_forge.prompting import assemble_planning_prompt_sections, build_planning_prompt_from_session
from aether_forge.runtime import RuntimeSession, load_artifact_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def test_planning_prompt_includes_artifact_state_and_memory_context() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=HeuristicPlanner(),
        execution_router=MockCryptoExecutionRouter(),
        scenario_inputs={"basisBps": 25, "volatilityRegime": "normal"},
    )
    session.session_state["memory_context"] = [
        {"summary": "User prefers explicit unwind rules."},
        "Venue data can drift during spikes.",
    ]

    declared_capability_ids = {"cap-market-btc-price", "cap-market-basis", "cap-exchange-order"}
    prompt = build_planning_prompt_from_session(session, declared_capability_ids)

    assert "## Objective" in prompt
    assert "Delta Neutral BTC Basis Agent" not in prompt  # title is not the primary objective block
    assert "Capture delta-neutral BTC basis opportunities" in prompt
    assert "## Capabilities" in prompt
    assert "cap-market-basis" in prompt
    assert "## Runtime State" in prompt
    assert "basisBps" in prompt
    assert "## Memory Context" in prompt
    assert "User prefers explicit unwind rules." in prompt


def test_prompt_sections_summarize_runtime_and_capabilities() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=HeuristicPlanner(),
        execution_router=MockCryptoExecutionRouter(),
        scenario_inputs={"requestedNotionalUsd": 250000},
    )
    session.working_set["cap-market-basis"] = {"basis_bps": 25}

    sections = assemble_planning_prompt_sections(session, {"cap-market-basis", "cap-exchange-order"})

    assert "Unbounded leverage" in sections.objective
    assert "cap-market-basis" in sections.capability_summary
    assert "Working set data" in sections.runtime_state
    assert "No persistent memory context" in sections.memory_context


# ---------------------------------------------------------------------------
# Token budget tests
# ---------------------------------------------------------------------------


def test_estimate_tokens():
    from aether_forge.prompting import estimate_tokens
    assert estimate_tokens("") == 0
    # ~4 chars/token, so 12 chars = ~3 tokens
    assert estimate_tokens("hello world!") == 3


def test_get_token_budget_known_models():
    from aether_forge.prompting import get_token_budget
    assert get_token_budget("claude-sonnet-4-5") == 150_000  # 75% of 200K
    assert get_token_budget("gpt-4o") == 96_000  # 75% of 128K
    assert get_token_budget("gemma4:latest") == 6_000  # 75% of 8K


def test_get_token_budget_unknown_model():
    from aether_forge.prompting import get_token_budget
    assert get_token_budget("some-future-model") == 8_000
    assert get_token_budget(None) == 8_000


def test_truncate_to_budget_no_truncation_needed():
    from aether_forge.prompting import truncate_to_budget
    short = "Hello world. This is a short prompt."
    assert truncate_to_budget(short, "claude-sonnet-4-5") == short


def test_truncate_to_budget_truncates_when_over_budget():
    from aether_forge.prompting import truncate_to_budget
    # Build a prompt that exceeds gemma4's 8K * 0.75 = 6K budget minus 4K reserve = 2K tokens = ~8K chars
    huge = "x" * 100_000  # ~25K tokens
    truncated = truncate_to_budget(huge, "gemma4")
    assert len(truncated) < len(huge)
    assert "tokens truncated" in truncated
    # Head and tail of original preserved
    assert truncated.startswith("xxx")
    assert truncated.endswith("xxx")

"""Shared pytest fixtures for the Aether Forge test suite.

These fixtures are also useful as a reference for third parties writing
tests for their own extensions (custom planners, routers, data sources).
See ``docs-site/src/content/guides/extending.mdx`` for context.

All fixtures are session-scoped where safe and tmp-path-scoped where state
must be isolated per test.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from aether_forge import (
    HeuristicPlanner,
    InMemoryMemoryStore,
    MockCryptoExecutionRouter,
    NativePolicyGate,
    RuntimeSession,
    SqliteMemoryStore,
    StaticPlanningModel,
    generate_fast_artifact_set,
)
from aether_forge.generator import FastGenerateRequest
from aether_forge.runtime import load_artifact_bundle

LIVE_CAPITAL_ACK = "I_UNDERSTAND_THIS_CAN_MOVE_FUNDS"


def _env_truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _network_enabled() -> bool:
    return _env_truthy("AETHER_FORGE_RUN_NETWORK") or _env_truthy("RUN_NETWORK_TESTS")


def _testnet_enabled() -> bool:
    return _env_truthy("AETHER_FORGE_RUN_TESTNET")


def _live_capital_enabled() -> bool:
    return (
        _env_truthy("AETHER_FORGE_RUN_LIVE_CAPITAL")
        and os.environ.get("AETHER_FORGE_LIVE_CAPITAL_ACK", "") == LIVE_CAPITAL_ACK
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    del config
    skip_network = pytest.mark.skip(
        reason="set AETHER_FORGE_RUN_NETWORK=1 to enable external-network tests"
    )
    skip_testnet = pytest.mark.skip(
        reason="set AETHER_FORGE_RUN_TESTNET=1 to enable public-testnet tests"
    )
    skip_live_capital = pytest.mark.skip(
        reason=(
            "set AETHER_FORGE_RUN_LIVE_CAPITAL=1 and "
            f"AETHER_FORGE_LIVE_CAPITAL_ACK={LIVE_CAPITAL_ACK!r} to enable live-capital tests"
        )
    )

    network_enabled = _network_enabled()
    testnet_enabled = _testnet_enabled()
    live_capital_enabled = _live_capital_enabled()

    for item in items:
        if item.get_closest_marker("live_capital") and not live_capital_enabled:
            item.add_marker(skip_live_capital)
        if item.get_closest_marker("testnet") and not testnet_enabled:
            item.add_marker(skip_testnet)
        if item.get_closest_marker("network") and not network_enabled:
            item.add_marker(skip_network)

# ---------------------------------------------------------------------------
# Agent directory
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_agent_dir(tmp_path: Path) -> Path:
    """A fresh fast-generated agent in a tmp directory.

    Useful for tests that need a complete artifact set on disk
    (validate, eval-pack, runtime smoke). The agent uses the heuristic
    planner so no LLM key is required.
    """
    out = tmp_path / "agent"
    request = FastGenerateRequest(
        name="Fixture Agent",
        idea="test agent for the conftest tmp_agent_dir fixture",
        output_directory=out,
    )
    generate_fast_artifact_set(request)
    return out


# ---------------------------------------------------------------------------
# Memory
# ---------------------------------------------------------------------------

@pytest.fixture
def memory_store(tmp_path: Path) -> SqliteMemoryStore:
    """A clean Layer-3 SqliteMemoryStore in tmp_path/memory.db."""
    store = SqliteMemoryStore(str(tmp_path / "memory.db"))
    yield store
    store.close()


@pytest.fixture
def in_memory_store() -> InMemoryMemoryStore:
    """In-process MemoryStore for tests that don't care about persistence."""
    return InMemoryMemoryStore()


# ---------------------------------------------------------------------------
# Planner / model
# ---------------------------------------------------------------------------

@pytest.fixture
def static_planner() -> HeuristicPlanner:
    """Offline rule-based planner — never calls an LLM, always responds."""
    return HeuristicPlanner()


@pytest.fixture
def static_planning_model() -> StaticPlanningModel:
    """Deterministic LLM stand-in.

    Returns a JSON object with one REASON step that completes the session.
    Use it to test code paths that go through ``PromptDrivenPlanner``
    without an API key. Override ``.response`` if you need a different
    canned reply.
    """
    return StaticPlanningModel(
        response='{"steps": [{"kind": "REASON", "description": "static fixture", "markComplete": true}]}'
    )


# ---------------------------------------------------------------------------
# Execution router
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_router() -> MockCryptoExecutionRouter:
    """Mock execution router — synthetic results for any capability."""
    return MockCryptoExecutionRouter()


# ---------------------------------------------------------------------------
# Policy gate
# ---------------------------------------------------------------------------

@pytest.fixture
def policy_gate() -> NativePolicyGate:
    """Sandbox-permissive policy gate. Override notional caps in your test."""
    return NativePolicyGate()


# ---------------------------------------------------------------------------
# Runtime session — fully wired
# ---------------------------------------------------------------------------

@pytest.fixture
def runtime_session(
    tmp_agent_dir: Path,
    static_planner: HeuristicPlanner,
    mock_router: MockCryptoExecutionRouter,
    policy_gate: NativePolicyGate,
    in_memory_store: InMemoryMemoryStore,
) -> RuntimeSession:
    """Fully wired RuntimeSession ready to ``.run()``.

    Composes ``tmp_agent_dir`` artifacts with the heuristic planner, mock
    router, and an in-memory store. Drop in a different planner /
    router / store via parameter override in your test if you need a
    different combination.
    """
    bundle = load_artifact_bundle(tmp_agent_dir)
    return RuntimeSession(
        artifacts=bundle,
        environment="sandbox",
        planner=static_planner,
        execution_router=mock_router,
        policy_gate=policy_gate,
        memory_store=in_memory_store,
    )


# ---------------------------------------------------------------------------
# Misc — convenience for plugin tests, see tests/test_plugins.py
# ---------------------------------------------------------------------------

@pytest.fixture
def reset_plugin_cache():
    """Clear the entry-point discovery cache before and after a test.

    Useful when a test monkey-patches ``aether_forge.plugins.entry_points``
    and needs the cache invalidated.
    """
    from aether_forge import plugins

    plugins.reset_cache()
    yield
    plugins.reset_cache()

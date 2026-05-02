"""Smoke tests for the shared fixtures in conftest.py.

Also serves as a worked example: third parties writing tests for their own
extensions can crib these patterns.
"""

from __future__ import annotations

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
    validate_artifact_directory,
)


def test_tmp_agent_dir_is_a_valid_agent(tmp_agent_dir: Path) -> None:
    assert (tmp_agent_dir / "agent-spec.json").exists()
    assert (tmp_agent_dir / "capability-manifest.json").exists()
    assert (tmp_agent_dir / "policy-bundle.json").exists()
    assert (tmp_agent_dir / "scenario-pack.json").exists()
    result = validate_artifact_directory(tmp_agent_dir)
    assert result.ok, [f"{i.code}: {i.message}" for i in result.issues]


def test_memory_store_is_clean(memory_store: SqliteMemoryStore) -> None:
    from aether_forge.memory import MemoryQuery

    assert memory_store.read(MemoryQuery(scope="session")) == []


def test_in_memory_store_is_clean(in_memory_store: InMemoryMemoryStore) -> None:
    from aether_forge.memory import MemoryQuery

    assert in_memory_store.read(MemoryQuery(scope="session")) == []


def test_static_planner_is_heuristic(static_planner: HeuristicPlanner) -> None:
    assert isinstance(static_planner, HeuristicPlanner)


def test_static_planning_model_returns_canned_response(
    static_planning_model: StaticPlanningModel,
) -> None:
    out = static_planning_model.complete("any prompt at all")
    assert "REASON" in out
    assert "markComplete" in out


def test_mock_router_is_a_router(mock_router: MockCryptoExecutionRouter) -> None:
    assert hasattr(mock_router, "execute")


def test_policy_gate_is_a_gate(policy_gate: NativePolicyGate) -> None:
    assert hasattr(policy_gate, "evaluate_action")


def test_runtime_session_is_runnable(runtime_session: RuntimeSession) -> None:
    """The composed session can run end-to-end without raising."""
    runtime_session.run(max_steps=3)
    # The HeuristicPlanner + MockRouter combo is well-trodden; this just
    # proves the fixture wires everything together correctly.


def test_reset_plugin_cache_clears(reset_plugin_cache, monkeypatch: pytest.MonkeyPatch) -> None:
    from aether_forge import plugins

    # Cache is fresh inside the fixture; iter_entry_points yields whatever
    # the real environment has installed. We just confirm it doesn't crash.
    list(plugins.iter_entry_points(plugins.GROUP_PLANNERS))

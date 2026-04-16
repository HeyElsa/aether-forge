"""Integration tests for memory subsystem across memory, policy, runtime, and planner."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from aether_forge.crypto import MockCryptoExecutionRouter
from aether_forge.memory import (
    InMemoryMemoryStore,
    MemoryQuery,
    MemoryRecord,
)
from aether_forge.planner import HeuristicPlanner
from aether_forge.policy import NativePolicyGate
from aether_forge.runtime import (
    RuntimeSession,
    SessionStatus,
    StepKind,
    StepProposal,
    load_artifact_bundle,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_record(
    memory_id: str = "mem_test",
    scope: str = "session",
    environment: str = "sandbox",
    sensitivity: str = "internal",
    expires_at: datetime | None = None,
    **kwargs,
) -> MemoryRecord:
    defaults = dict(
        memory_type="observation",
        content={"note": "test"},
        summary="test record",
        source="test",
        confidence=0.9,
        tags=["test"],
    )
    defaults.update(kwargs)
    return MemoryRecord(
        memory_id=memory_id,
        scope=scope,
        environment=environment,
        sensitivity=sensitivity,
        expires_at=expires_at,
        **defaults,
    )


_MEMORY_CAPABILITIES = [
    {
        "capabilityId": "memory.read",
        "kind": "memory-action",
        "provider": "native-memory",
        "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
        "riskLevel": "low",
    },
    {
        "capabilityId": "memory.write",
        "kind": "memory-action",
        "provider": "native-memory",
        "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
        "riskLevel": "low",
    },
    {
        "capabilityId": "memory.promote",
        "kind": "memory-action",
        "provider": "native-memory",
        "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
        "riskLevel": "medium",
    },
]


def _artifacts_with_memory():
    """Load example artifacts and inject memory.* capabilities."""
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    artifacts.capability_manifest["capabilities"] = (
        list(artifacts.capability_manifest["capabilities"]) + _MEMORY_CAPABILITIES
    )
    return artifacts


# ---------------------------------------------------------------------------
# Memory module tests
# ---------------------------------------------------------------------------


def test_memory_read_excludes_expired_records() -> None:
    store = InMemoryMemoryStore()
    expired = _make_record(
        memory_id="mem_expired",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    store.write(expired)

    results = store.read(MemoryQuery(scope="session"))
    assert len(results) == 0


def test_memory_read_includes_expired_when_requested() -> None:
    store = InMemoryMemoryStore()
    expired = _make_record(
        memory_id="mem_expired",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    store.write(expired)

    results = store.read(MemoryQuery(scope="session"), include_expired=True)
    assert len(results) == 1
    assert results[0].memory_id == "mem_expired"


def test_memory_record_serialization_round_trip() -> None:
    original = _make_record(
        memory_id="mem_round_trip",
        expires_at=datetime.now(UTC) + timedelta(days=7),
        tags=["alpha", "beta"],
        metadata={"source_version": "1.2.3"},
    )
    serialized = original.to_dict()
    restored = MemoryRecord.from_dict(serialized)

    assert restored.memory_id == original.memory_id
    assert restored.memory_type == original.memory_type
    assert restored.scope == original.scope
    assert restored.environment == original.environment
    assert restored.content == original.content
    assert restored.summary == original.summary
    assert restored.source == original.source
    assert restored.confidence == original.confidence
    assert restored.sensitivity == original.sensitivity
    assert restored.tags == original.tags
    assert restored.metadata == original.metadata
    # Datetimes survive the round-trip via ISO-format strings.
    assert restored.created_at.isoformat() == original.created_at.isoformat()
    assert restored.expires_at is not None
    assert restored.expires_at.isoformat() == original.expires_at.isoformat()


def test_memory_store_export_and_restore() -> None:
    store = InMemoryMemoryStore()
    store.write(_make_record(memory_id="mem_a", summary="record a"))
    store.write(_make_record(memory_id="mem_b", summary="record b"))

    exported = store.export_records()
    restored_store = InMemoryMemoryStore.from_exported(exported)
    restored = restored_store.read(MemoryQuery(scope="session"))

    assert len(restored) == 2
    ids = {r.memory_id for r in restored}
    assert ids == {"mem_a", "mem_b"}


def test_read_for_environment_filters_sensitivity() -> None:
    store = InMemoryMemoryStore()
    store.write(_make_record(memory_id="mem_pub", sensitivity="public"))
    store.write(_make_record(memory_id="mem_int", sensitivity="internal"))
    store.write(_make_record(memory_id="mem_conf", sensitivity="confidential"))
    store.write(_make_record(memory_id="mem_restr", sensitivity="restricted"))

    results = store.read_for_environment(
        scope="session",
        environment="sandbox",
        sensitivity_at_most="internal",
    )
    result_ids = {r.memory_id for r in results}

    assert "mem_pub" in result_ids
    assert "mem_int" in result_ids
    assert "mem_conf" not in result_ids
    assert "mem_restr" not in result_ids


# ---------------------------------------------------------------------------
# Policy tests
# ---------------------------------------------------------------------------


def _memory_capability(cap_id: str) -> dict:
    return {
        "capabilityId": cap_id,
        "kind": "memory-action",
        "provider": "native-memory",
        "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
    }


def test_policy_denies_restricted_memory_write_in_production() -> None:
    gate = NativePolicyGate()
    decision = gate.evaluate_action(
        capability=_memory_capability("memory.write"),
        credential_handles=[],
        environment="production",
        action_payload={"sensitivity": "restricted"},
    )

    assert decision.final_disposition == "deny"
    assert "memory-sensitivity-exceeds-environment" in decision.reason_ids


def test_policy_holds_memory_promote_requires_approval() -> None:
    gate = NativePolicyGate()
    decision = gate.evaluate_action(
        capability=_memory_capability("memory.promote"),
        credential_handles=[],
        environment="sandbox",
        action_payload={},
    )

    assert decision.final_disposition == "hold"
    assert "memory-promotion-requires-approval" in decision.reason_ids


def test_policy_allows_memory_read_by_default() -> None:
    gate = NativePolicyGate()
    decision = gate.evaluate_action(
        capability=_memory_capability("memory.read"),
        credential_handles=[],
        environment="production",
        action_payload={},
    )

    assert decision.final_disposition == "allow"


def test_policy_allows_memory_write_in_sandbox() -> None:
    gate = NativePolicyGate()
    decision = gate.evaluate_action(
        capability=_memory_capability("memory.write"),
        credential_handles=[],
        environment="sandbox",
        action_payload={"sensitivity": "restricted"},
    )

    assert decision.final_disposition == "allow"


# ---------------------------------------------------------------------------
# Runtime integration tests
# ---------------------------------------------------------------------------


def test_runtime_session_initializes_with_memory_store() -> None:
    artifacts = _artifacts_with_memory()
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=HeuristicPlanner(),
        execution_router=MockCryptoExecutionRouter(),
    )

    assert session.memory_store is not None
    assert isinstance(session.memory_store, InMemoryMemoryStore)


def test_runtime_handles_memory_write_operation() -> None:
    artifacts = _artifacts_with_memory()

    class MemoryWritePlanner:
        def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
            if session.working_set.get("memory.write"):
                return [
                    StepProposal(
                        kind=StepKind.REASON,
                        description="Memory written successfully.",
                        payload={"mark_complete": True},
                    )
                ]
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Write an observation to memory.",
                    capability_id="memory.write",
                    payload={
                        "memory_id": "mem_runtime_write",
                        "memory_type": "observation",
                        "scope": "session",
                        "content": {"note": "runtime wrote this"},
                        "summary": "Runtime write test",
                        "source": "test",
                        "confidence": 0.95,
                        "sensitivity": "internal",
                    },
                )
            ]

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=MemoryWritePlanner(),
        execution_router=MockCryptoExecutionRouter(),
    )

    status = session.run()

    assert status == SessionStatus.COMPLETE
    assert "memory.write" in session.working_set
    assert session.working_set["memory.write"]["status"] == "written"
    # Verify the record is actually in the store.
    records = session.memory_store.read(MemoryQuery(scope="session"))
    assert any(r.memory_id == "mem_runtime_write" for r in records)


def test_runtime_handles_memory_read_operation() -> None:
    artifacts = _artifacts_with_memory()
    store = InMemoryMemoryStore()
    store.write(_make_record(memory_id="mem_preloaded", summary="preloaded context"))

    class MemoryReadPlanner:
        def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
            if session.working_set.get("memory.read"):
                return [
                    StepProposal(
                        kind=StepKind.REASON,
                        description="Memory read done.",
                        payload={"mark_complete": True},
                    )
                ]
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Read memory records.",
                    capability_id="memory.read",
                    payload={"scope": "session"},
                )
            ]

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=MemoryReadPlanner(),
        execution_router=MockCryptoExecutionRouter(),
        memory_store=store,
    )

    status = session.run()

    assert status == SessionStatus.COMPLETE
    read_output = session.working_set.get("memory.read")
    assert read_output is not None
    assert len(read_output["records"]) == 1
    assert read_output["records"][0]["memoryId"] == "mem_preloaded"


def test_runtime_memory_promote_held_by_policy() -> None:
    artifacts = _artifacts_with_memory()
    store = InMemoryMemoryStore()
    store.write(_make_record(memory_id="mem_to_promote", summary="promote me"))

    class MemoryPromotePlanner:
        def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Promote memory to production.",
                    capability_id="memory.promote",
                    payload={
                        "memory_id": "mem_to_promote",
                        "target_environment": "production",
                    },
                )
            ]

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=MemoryPromotePlanner(),
        execution_router=MockCryptoExecutionRouter(),
        memory_store=store,
    )

    status = session.run()

    assert status == SessionStatus.HOLD
    last_entry = session.step_ledger[-1]
    assert "memory-promotion-requires-approval" in (last_entry.message or "")


# ---------------------------------------------------------------------------
# Planner tests
# ---------------------------------------------------------------------------


def test_heuristic_planner_proposes_memory_read_when_store_has_records() -> None:
    artifacts = _artifacts_with_memory()
    store = InMemoryMemoryStore()
    store.write(_make_record(memory_id="mem_plan_ctx", summary="planner should see me"))

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=HeuristicPlanner(),
        execution_router=MockCryptoExecutionRouter(),
        memory_store=store,
    )

    planner = HeuristicPlanner()
    proposals = planner.propose_plan(session)

    assert len(proposals) >= 1
    assert proposals[0].kind == StepKind.USE_CAPABILITY
    assert proposals[0].capability_id == "memory.read"

from __future__ import annotations

from aether_forge.memory import InMemoryMemoryStore, MemoryPromotionRequest, MemoryQuery, MemoryRecord


def test_memory_write_and_read_same_environment() -> None:
    store = InMemoryMemoryStore()
    record = MemoryRecord(
        memory_id="mem_strategy_preference",
        memory_type="strategy-context",
        scope="agent",
        environment="sandbox",
        content={"note": "Prefer explicit unwind triggers over open-ended hold conditions."},
        summary="Use explicit unwind triggers.",
        source="manual",
        confidence=0.8,
        sensitivity="internal",
        tags=["strategy", "risk"],
    )

    store.write(record)
    results = store.read(MemoryQuery(environment="sandbox", memory_type="strategy-context"))

    assert len(results) == 1
    assert results[0].summary == "Use explicit unwind triggers."


def test_memory_promotion_from_sandbox_requires_manual_approval() -> None:
    store = InMemoryMemoryStore()
    record = MemoryRecord(
        memory_id="mem_sandbox_learning",
        memory_type="evaluation-finding",
        scope="agent",
        environment="sandbox",
        content={"finding": "Volatility spike handling prevents unsafe carry trades."},
        summary="Sandbox learning about volatility spike handling.",
        source="sandbox-eval",
        confidence=0.7,
        sensitivity="internal",
    )
    store.write(record)

    result = store.promote(
        MemoryPromotionRequest(
            memory_id="mem_sandbox_learning",
            source_environment="sandbox",
            target_environment="production",
        )
    )

    assert result.promoted is False
    assert "manual approval" in result.reason


def test_memory_promotion_records_provenance_when_approved() -> None:
    store = InMemoryMemoryStore()
    record = MemoryRecord(
        memory_id="mem_operator_pref",
        memory_type="operator-preference",
        scope="agent",
        environment="sandbox",
        content={"format": "concise"},
        summary="Operator prefers concise summaries.",
        source="user",
        confidence=1.0,
        sensitivity="internal",
    )
    store.write(record)

    result = store.promote(
        MemoryPromotionRequest(
            memory_id="mem_operator_pref",
            source_environment="sandbox",
            target_environment="production",
            approval_ref="promo_memory_001",
            requested_by="founder",
        )
    )

    assert result.promoted is True
    assert result.record is not None
    assert result.record.environment == "production"
    assert "mem_operator_pref" in result.record.provenance_refs
    assert "promo_memory_001" in result.record.provenance_refs

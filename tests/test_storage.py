from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from aether_forge.memory import MemoryPromotionRequest, MemoryQuery, MemoryRecord
from aether_forge.storage import SqliteMemoryStore


def _make_record(
    memory_id: str = "mem_test1",
    scope: str = "trading",
    environment: str = "sandbox",
    sensitivity: str = "internal",
    memory_type: str = "strategy-context",
    summary: str = "test record",
    expires_at: datetime | None = None,
    tags: list[str] | None = None,
) -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        memory_type=memory_type,
        scope=scope,
        environment=environment,
        content={"note": "test"},
        summary=summary,
        source="test",
        confidence=0.9,
        sensitivity=sensitivity,
        expires_at=expires_at,
        tags=tags or [],
    )


def test_sqlite_write_and_read(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    store = SqliteMemoryStore(db_path)
    record = _make_record()
    store.write(record)

    results = store.read(MemoryQuery(scope="trading", environment="sandbox"))

    assert len(results) == 1
    assert results[0].memory_id == "mem_test1"
    assert results[0].content == {"note": "test"}
    store.close()


def test_sqlite_persistence_across_sessions(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"

    store1 = SqliteMemoryStore(db_path)
    store1.write(_make_record())
    store1.close()

    store2 = SqliteMemoryStore(db_path)
    results = store2.read(MemoryQuery(scope="trading"))

    assert len(results) == 1
    assert results[0].memory_id == "mem_test1"
    store2.close()


def test_sqlite_upsert_updates_existing_record(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record(summary="version 1"))
    store.write(_make_record(summary="version 2"))

    results = store.read(MemoryQuery(scope="trading"))

    assert len(results) == 1
    assert results[0].summary == "version 2"
    store.close()


def test_sqlite_filters_expired_records(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    expired = _make_record(
        memory_id="mem_expired",
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    active = _make_record(memory_id="mem_active")
    store.write(expired)
    store.write(active)

    results = store.read(MemoryQuery(scope="trading"))
    assert len(results) == 1
    assert results[0].memory_id == "mem_active"

    results_with_expired = store.read(MemoryQuery(scope="trading"), include_expired=True)
    assert len(results_with_expired) == 2
    store.close()


def test_sqlite_filters_by_sensitivity(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record(memory_id="mem_pub", sensitivity="public"))
    store.write(_make_record(memory_id="mem_int", sensitivity="internal"))
    store.write(_make_record(memory_id="mem_conf", sensitivity="confidential"))

    results = store.read(MemoryQuery(scope="trading", sensitivity_at_most="internal"))
    ids = {r.memory_id for r in results}

    assert "mem_pub" in ids
    assert "mem_int" in ids
    assert "mem_conf" not in ids
    store.close()


def test_sqlite_filters_by_tag(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record(memory_id="mem_tagged", tags=["btc", "basis"]))
    store.write(_make_record(memory_id="mem_untagged", tags=["eth"]))

    results = store.read(MemoryQuery(scope="trading", tag="btc"))

    assert len(results) == 1
    assert results[0].memory_id == "mem_tagged"
    store.close()


def test_sqlite_text_search(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record(memory_id="mem_match", summary="BTC basis trade strategy"))
    store.write(_make_record(memory_id="mem_nomatch", summary="ETH staking yield"))

    results = store.read(MemoryQuery(scope="trading", text="basis"))

    assert len(results) == 1
    assert results[0].memory_id == "mem_match"
    store.close()


def test_sqlite_promote_requires_approval(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record())

    result = store.promote(MemoryPromotionRequest(
        memory_id="mem_test1",
        source_environment="sandbox",
        target_environment="paper",
    ))

    assert not result.promoted
    assert "approval" in result.reason
    store.close()


def test_sqlite_promote_with_approval(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record())

    result = store.promote(MemoryPromotionRequest(
        memory_id="mem_test1",
        source_environment="sandbox",
        target_environment="paper",
        approval_ref="approved-by-ops",
    ))

    assert result.promoted
    assert result.record is not None
    assert result.record.environment == "paper"

    # Promoted record should be in the store
    results = store.read(MemoryQuery(environment="paper"))
    assert len(results) == 1
    store.close()


def test_sqlite_read_for_environment(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record(memory_id="mem_sb", environment="sandbox", sensitivity="internal"))
    store.write(_make_record(memory_id="mem_pp", environment="paper", sensitivity="internal"))
    store.write(_make_record(memory_id="mem_secret", environment="sandbox", sensitivity="confidential"))

    results = store.read_for_environment("trading", "sandbox", sensitivity_at_most="internal")

    assert len(results) == 1
    assert results[0].memory_id == "mem_sb"
    store.close()


def test_sqlite_export_records(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record(memory_id="mem_1"))
    store.write(_make_record(memory_id="mem_2"))

    exported = store.export_records()

    assert len(exported) == 2
    ids = {r["memoryId"] for r in exported}
    assert ids == {"mem_1", "mem_2"}
    store.close()


def test_sqlite_from_exported(tmp_path: Path) -> None:
    original = SqliteMemoryStore(tmp_path / "original.db")
    original.write(_make_record())
    exported = original.export_records()
    original.close()

    restored = SqliteMemoryStore.from_exported(exported, tmp_path / "restored.db")
    results = restored.read(MemoryQuery(scope="trading"))

    assert len(results) == 1
    assert results[0].memory_id == "mem_test1"
    restored.close()


def test_sqlite_context_manager(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    with SqliteMemoryStore(db_path) as store:
        store.write(_make_record())
        results = store.read(MemoryQuery(scope="trading"))
        assert len(results) == 1


def test_sqlite_rejects_secret_like_content(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    record = MemoryRecord(
        memory_id="mem_bad",
        memory_type="strategy-context",
        scope="trading",
        environment="sandbox",
        content={"api_key": "secret-value"},
        summary="bad",
        source="test",
        confidence=0.9,
        sensitivity="restricted",
    )
    try:
        store.write(record)
        assert False, "should have raised ValueError"
    except ValueError as e:
        assert "secret-like" in str(e)
    store.close()


def test_sqlite_creates_parent_directories(tmp_path: Path) -> None:
    db_path = tmp_path / "nested" / "dir" / "memory.db"
    store = SqliteMemoryStore(db_path)
    store.write(_make_record())
    results = store.read(MemoryQuery(scope="trading"))
    assert len(results) == 1
    store.close()

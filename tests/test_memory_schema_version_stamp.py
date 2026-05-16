"""Verify SqliteMemoryStore stamps the MemoryRecord schema version into schema_meta.

Sprint 1.3 prep for FP-4 (runtime migration execution): persist the MemoryRecord
schema version alongside the DB schema version so MigrationRunner can route
old rows through transforms without scanning every row.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from aether_forge.memory import MEMORY_RECORD_SCHEMA_VERSION, MemoryRecord
from aether_forge.storage import SqliteMemoryStore


def _read_meta(db_path: Path) -> dict[str, str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("SELECT key, value FROM schema_meta").fetchall()
    finally:
        conn.close()
    return {key: value for key, value in rows}


def test_new_store_stamps_memory_record_schema_version(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    store = SqliteMemoryStore(db_path)
    try:
        meta = _read_meta(db_path)
        assert meta["memory_record_schema_version"] == MEMORY_RECORD_SCHEMA_VERSION
        assert store.memory_record_schema_version() == MEMORY_RECORD_SCHEMA_VERSION
    finally:
        store.close()


def test_existing_store_backfills_memory_record_schema_version(tmp_path: Path) -> None:
    """A database created before this stamping landed must get the row populated on next open."""
    db_path = tmp_path / "legacy.db"
    # Create a database the way an older SqliteMemoryStore would have (only
    # the ``version`` meta row, no ``memory_record_schema_version``).
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO schema_meta (key, value) VALUES ('version', '2')"
    )
    conn.commit()
    conn.close()

    assert "memory_record_schema_version" not in _read_meta(db_path)

    store = SqliteMemoryStore(db_path)
    try:
        meta = _read_meta(db_path)
        assert meta["memory_record_schema_version"] == MEMORY_RECORD_SCHEMA_VERSION
    finally:
        store.close()


def test_memory_record_default_uses_module_constant() -> None:
    """The MemoryRecord dataclass default must reference the module constant so
    a future bump propagates to both the in-code default and the persisted row."""
    record = MemoryRecord(
        memory_id="mem_constant_check",
        memory_type="diagnostic",
        scope="test",
        environment="sandbox",
        content={"check": True},
        summary="constant check",
        source="test",
        confidence=1.0,
        sensitivity="internal",
    )
    assert record.schema_version == MEMORY_RECORD_SCHEMA_VERSION

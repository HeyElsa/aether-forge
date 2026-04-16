"""Persistent memory storage backends for Aether Forge.

Provides a SQLite-backed MemoryStore implementation that satisfies
the MemoryStore protocol while persisting records across sessions.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from .memory import (
    SENSITIVITY_LEVELS,
    MemoryPromotionPolicy,
    MemoryPromotionRequest,
    MemoryPromotionResult,
    MemoryQuery,
    MemoryRecord,
)

_SCHEMA_VERSION = 2

# ---------------------------------------------------------------------------
# Schema migrations
# ---------------------------------------------------------------------------

_MIGRATIONS: dict[int, list[str]] = {
    2: [
        "ALTER TABLE memory_records ADD COLUMN encrypted INTEGER NOT NULL DEFAULT 0",
    ],
}


def _run_migrations(conn: sqlite3.Connection, current_version: int, target_version: int) -> None:
    """Apply schema migrations from current_version to target_version."""
    for version in range(current_version + 1, target_version + 1):
        statements = _MIGRATIONS.get(version, [])
        for sql in statements:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                # Column already exists or migration already applied
                pass
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
            ("version", str(version)),
        )
    conn.commit()

_CREATE_TABLE = """\
CREATE TABLE IF NOT EXISTS memory_records (
    memory_id       TEXT PRIMARY KEY,
    memory_type     TEXT NOT NULL,
    scope           TEXT NOT NULL,
    environment     TEXT NOT NULL,
    content         TEXT NOT NULL,
    summary         TEXT NOT NULL,
    source          TEXT NOT NULL,
    confidence      REAL NOT NULL,
    sensitivity     TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT NOT NULL,
    schema_version  TEXT NOT NULL DEFAULT '1.0.0',
    artifact_type   TEXT NOT NULL DEFAULT 'memory-record',
    owner_agent_id  TEXT,
    artifact_set_id TEXT,
    expires_at      TEXT,
    retention_policy TEXT,
    provenance_refs TEXT NOT NULL DEFAULT '[]',
    tags            TEXT NOT NULL DEFAULT '[]',
    metadata        TEXT NOT NULL DEFAULT '{}'
)"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_memory_scope ON memory_records (scope)",
    "CREATE INDEX IF NOT EXISTS idx_memory_env ON memory_records (environment)",
    "CREATE INDEX IF NOT EXISTS idx_memory_type ON memory_records (memory_type)",
    "CREATE INDEX IF NOT EXISTS idx_memory_updated ON memory_records (updated_at DESC)",
]

_META_TABLE = """\
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
)"""


def _parse_dt(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value)


def _format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _record_to_row(record: MemoryRecord) -> dict[str, Any]:
    return {
        "memory_id": record.memory_id,
        "memory_type": record.memory_type,
        "scope": record.scope,
        "environment": record.environment,
        "content": json.dumps(record.content),
        "summary": record.summary,
        "source": record.source,
        "confidence": record.confidence,
        "sensitivity": record.sensitivity,
        "created_at": _format_dt(record.created_at),
        "updated_at": _format_dt(record.updated_at),
        "schema_version": record.schema_version,
        "artifact_type": record.artifact_type,
        "owner_agent_id": record.owner_agent_id,
        "artifact_set_id": record.artifact_set_id,
        "expires_at": _format_dt(record.expires_at),
        "retention_policy": record.retention_policy,
        "provenance_refs": json.dumps(record.provenance_refs),
        "tags": json.dumps(record.tags),
        "metadata": json.dumps(record.metadata),
    }


def _row_to_record(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        memory_id=row["memory_id"],
        memory_type=row["memory_type"],
        scope=row["scope"],
        environment=row["environment"],
        content=json.loads(row["content"]),
        summary=row["summary"],
        source=row["source"],
        confidence=row["confidence"],
        sensitivity=row["sensitivity"],
        created_at=_parse_dt(row["created_at"]),  # type: ignore[arg-type]
        updated_at=_parse_dt(row["updated_at"]),  # type: ignore[arg-type]
        schema_version=row["schema_version"],
        artifact_type=row["artifact_type"],
        owner_agent_id=row["owner_agent_id"],
        artifact_set_id=row["artifact_set_id"],
        expires_at=_parse_dt(row["expires_at"]),
        retention_policy=row["retention_policy"],
        provenance_refs=json.loads(row["provenance_refs"]),
        tags=json.loads(row["tags"]),
        metadata=json.loads(row["metadata"]),
    )


class MemoryEncryption:
    """Optional Fernet-based encryption for memory content at rest.

    Uses the ``cryptography`` library if available, otherwise raises on init.
    The encryption key should be a URL-safe base64-encoded 32-byte key.

    Generate a key::

        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

    Usage::

        enc = MemoryEncryption(key="your-fernet-key-here")
        store = SqliteMemoryStore("/path/to/memory.db", encryption=enc)
    """

    def __init__(self, key: str) -> None:
        try:
            from cryptography.fernet import Fernet
        except ImportError as error:
            raise RuntimeError(
                "Memory encryption requires the 'cryptography' package. "
                "Install with: pip install cryptography"
            ) from error
        self._fernet = Fernet(key.encode("utf8") if isinstance(key, str) else key)

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode("utf8")).decode("utf8")

    def decrypt(self, ciphertext: str) -> str:
        return self._fernet.decrypt(ciphertext.encode("utf8")).decode("utf8")


class SqliteMemoryStore:
    """SQLite-backed memory store that persists records across sessions.

    Satisfies the ``MemoryStore`` protocol defined in ``memory.py``.

    Usage::

        store = SqliteMemoryStore("/path/to/memory.db")
        store.write(record)
        results = store.read(MemoryQuery(scope="trading"))
        store.close()

    With encryption::

        enc = MemoryEncryption(key="your-fernet-key")
        store = SqliteMemoryStore("/path/to/memory.db", encryption=enc)
    """

    def __init__(
        self,
        db_path: str | Path,
        policy: MemoryPromotionPolicy | None = None,
        encryption: MemoryEncryption | None = None,
    ) -> None:
        self._policy = policy or MemoryPromotionPolicy()
        self._encryption = encryption
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")  # 5s lock timeout (perf audit)
        self._write_count = 0
        self._init_schema()

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(_META_TABLE)
            self._conn.execute(_CREATE_TABLE)
            for idx_sql in _CREATE_INDEXES:
                self._conn.execute(idx_sql)
            self._conn.execute(
                "INSERT OR IGNORE INTO schema_meta (key, value) VALUES (?, ?)",
                ("version", "1"),
            )
        # Check current version and run migrations if needed
        cursor = self._conn.execute("SELECT value FROM schema_meta WHERE key = 'version'")
        row = cursor.fetchone()
        current = int(row["value"]) if row else 1
        if current < _SCHEMA_VERSION:
            logger.info("Migrating memory database from schema v%d to v%d", current, _SCHEMA_VERSION)
            _run_migrations(self._conn, current, _SCHEMA_VERSION)

    def read(self, query: MemoryQuery, *, include_expired: bool = False) -> list[MemoryRecord]:
        logger.debug("Memory query: scope=%s env=%s results=pending", query.scope, query.environment)
        clauses: list[str] = []
        params: list[Any] = []

        if query.scope:
            clauses.append("scope = ?")
            params.append(query.scope)
        if query.environment:
            clauses.append("environment = ?")
            params.append(query.environment)
        if query.memory_type:
            clauses.append("memory_type = ?")
            params.append(query.memory_type)
        if query.tag:
            clauses.append("tags LIKE ?")
            params.append(f'%"{query.tag}"%')
        if query.text:
            clauses.append("(summary LIKE ? OR content LIKE ?)")
            needle = f"%{query.text}%"
            params.extend([needle, needle])
        if query.sensitivity_at_most:
            allowed = SENSITIVITY_LEVELS[: SENSITIVITY_LEVELS.index(query.sensitivity_at_most) + 1]
            placeholders = ", ".join("?" for _ in allowed)
            clauses.append(f"sensitivity IN ({placeholders})")
            params.extend(allowed)
        if not include_expired:
            clauses.append("(expires_at IS NULL OR expires_at > ?)")
            params.append(datetime.now(UTC).isoformat())

        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM memory_records{where} ORDER BY updated_at DESC LIMIT ?"
        params.append(query.limit)

        cursor = self._conn.execute(sql, params)
        results = [self._decrypt_record(_row_to_record(row)) for row in cursor.fetchall()]
        logger.debug("Memory query: scope=%s env=%s results=%d", query.scope, query.environment, len(results))
        return results

    def write(self, record: MemoryRecord) -> MemoryRecord:
        self._validate_record(record)
        from dataclasses import replace
        stored = replace(record, updated_at=datetime.now(UTC))
        row = _record_to_row(stored)
        # Encrypt content if encryption is configured
        if self._encryption is not None:
            row["content"] = self._encryption.encrypt(row["content"])
            row["summary"] = self._encryption.encrypt(row["summary"])
        columns = ", ".join(row.keys())
        placeholders = ", ".join("?" for _ in row)
        conflict_updates = ", ".join(f"{col} = ?" for col in row.keys() if col != "memory_id")
        conflict_values = [v for k, v in row.items() if k != "memory_id"]

        sql = f"INSERT INTO memory_records ({columns}) VALUES ({placeholders}) ON CONFLICT(memory_id) DO UPDATE SET {conflict_updates}"
        with self._conn:
            self._conn.execute(sql, list(row.values()) + conflict_values)
        # Periodic WAL checkpoint to prevent unbounded WAL growth
        # (flagged by performance audit — WAL can grow to 100s of MB over a week).
        self._write_count += 1
        if self._write_count % 500 == 0:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
        logger.debug("Memory written: id=%s type=%s env=%s", stored.memory_id, stored.memory_type, stored.environment)
        return stored

    def promote(self, request: MemoryPromotionRequest) -> MemoryPromotionResult:
        cursor = self._conn.execute(
            "SELECT * FROM memory_records WHERE memory_id = ?",
            (request.memory_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return MemoryPromotionResult(promoted=False, reason="memory record not found")

        record = self._decrypt_record(_row_to_record(row))
        policy_result = self._policy.can_promote(request, record)
        if not policy_result.promoted:
            logger.info("Memory promotion: %s -> %s result=%s", request.source_environment, request.target_environment, policy_result.reason)
            return policy_result

        from dataclasses import replace
        from uuid import uuid4

        promoted_record = replace(
            record,
            memory_id=f"mem_{uuid4().hex}",
            environment=request.target_environment,
            updated_at=datetime.now(UTC),
            provenance_refs=[*record.provenance_refs, record.memory_id, request.approval_ref] if request.approval_ref else [*record.provenance_refs, record.memory_id],
            metadata={
                **record.metadata,
                "promotion": {
                    "source_environment": request.source_environment,
                    "target_environment": request.target_environment,
                    "approval_ref": request.approval_ref,
                    "requested_by": request.requested_by,
                },
            },
        )
        self.write(promoted_record)
        logger.info("Memory promotion: %s -> %s result=promoted", request.source_environment, request.target_environment)
        return MemoryPromotionResult(
            promoted=True,
            reason="memory promoted",
            record=promoted_record,
        )

    def read_for_environment(
        self,
        scope: str,
        environment: str,
        sensitivity_at_most: str = "internal",
    ) -> list[MemoryRecord]:
        max_index = SENSITIVITY_LEVELS.index(sensitivity_at_most)
        allowed = SENSITIVITY_LEVELS[: max_index + 1]
        placeholders = ", ".join("?" for _ in allowed)
        now = datetime.now(UTC).isoformat()

        sql = (
            f"SELECT * FROM memory_records "
            f"WHERE scope = ? AND environment = ? AND sensitivity IN ({placeholders}) "
            f"AND (expires_at IS NULL OR expires_at > ?) "
            f"ORDER BY updated_at DESC"
        )
        params: list[Any] = [scope, environment, *allowed, now]
        cursor = self._conn.execute(sql, params)
        return [self._decrypt_record(_row_to_record(row)) for row in cursor.fetchall()]

    def export_records(self) -> list[dict[str, Any]]:
        cursor = self._conn.execute("SELECT * FROM memory_records ORDER BY updated_at DESC")
        return [self._decrypt_record(_row_to_record(row)).to_dict() for row in cursor.fetchall()]

    @classmethod
    def from_exported(
        cls,
        records: list[dict[str, Any]],
        db_path: str | Path,
        policy: MemoryPromotionPolicy | None = None,
    ) -> SqliteMemoryStore:
        store = cls(db_path, policy=policy)
        for data in records:
            record = MemoryRecord.from_dict(data)
            store.write(record)
        return store

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SqliteMemoryStore:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()

    def _decrypt_record(self, record: MemoryRecord) -> MemoryRecord:
        """Decrypt content and summary if encryption is configured."""
        if self._encryption is None:
            return record
        from dataclasses import replace
        try:
            content = json.loads(self._encryption.decrypt(json.dumps(record.content) if isinstance(record.content, dict) else str(record.content)))
        except Exception:
            # Content wasn't encrypted (e.g., written before encryption was enabled)
            content = record.content
        try:
            summary = self._encryption.decrypt(record.summary)
        except Exception:
            summary = record.summary
        return replace(record, content=content, summary=summary)

    def _validate_record(self, record: MemoryRecord) -> None:
        if not 0.0 <= record.confidence <= 1.0:
            raise ValueError("memory confidence must be between 0.0 and 1.0")
        from .memory import _find_secret_like_paths
        for secret_path in _find_secret_like_paths(record.content):
            raise ValueError(f"memory records must not store secret-like keys or raw credential material: {secret_path}")

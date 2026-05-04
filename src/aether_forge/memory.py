from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

LIVE_ENVIRONMENTS = {"paper", "canary-live", "production"}
SECRET_LIKE_KEY = re.compile(r"(secret|token|private[-_]?key|seed[-_]?phrase|mnemonic|password|api[-_]?key)", re.IGNORECASE)


SENSITIVITY_LEVELS = ["public", "internal", "confidential", "restricted"]

_SENTINEL = object()


@dataclass(slots=True)
class MemoryRecord:
    memory_id: str
    memory_type: str
    scope: str
    environment: str
    content: dict[str, Any]
    summary: str
    source: str
    confidence: float
    sensitivity: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    schema_version: str = "1.0.0"
    artifact_type: str = "memory-record"
    owner_agent_id: str | None = None
    artifact_set_id: str | None = None
    expires_at: datetime | None = None
    retention_policy: str | None = None
    provenance_refs: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize all fields to a plain dictionary with camelCase keys matching the JSON schema."""
        return {
            "memoryId": self.memory_id,
            "memoryType": self.memory_type,
            "scope": self.scope,
            "environment": self.environment,
            "content": self.content,
            "summary": self.summary,
            "source": self.source,
            "confidence": self.confidence,
            "sensitivity": self.sensitivity,
            "createdAt": self.created_at.isoformat(),
            "updatedAt": self.updated_at.isoformat(),
            "schemaVersion": self.schema_version,
            "artifactType": self.artifact_type,
            "ownerAgentId": self.owner_agent_id,
            "artifactSetId": self.artifact_set_id,
            "expiresAt": self.expires_at.isoformat() if self.expires_at else None,
            "retentionPolicy": self.retention_policy,
            "provenanceRefs": list(self.provenance_refs),
            "tags": list(self.tags),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryRecord:
        """Deserialize a dictionary into a MemoryRecord.

        Accepts camelCase keys (as produced by ``to_dict``) with a
        snake_case fallback for backward compatibility.
        """
        def _get(camel: str, snake: str, default: Any = _SENTINEL) -> Any:
            """Return value for *camel* key, falling back to *snake* key."""
            if camel in data:
                return data[camel]
            if snake in data:
                return data[snake]
            if default is not _SENTINEL:
                return default
            raise KeyError(f"missing required key: {camel!r} (or {snake!r})")

        def _parse_dt(value: str | None) -> datetime | None:
            if value is None:
                return None
            return datetime.fromisoformat(value)

        return cls(
            memory_id=_get("memoryId", "memory_id"),
            memory_type=_get("memoryType", "memory_type"),
            scope=data["scope"],
            environment=data["environment"],
            content=data["content"],
            summary=data["summary"],
            source=data["source"],
            confidence=data["confidence"],
            sensitivity=data["sensitivity"],
            created_at=_parse_dt(_get("createdAt", "created_at")),  # type: ignore[arg-type]
            updated_at=_parse_dt(_get("updatedAt", "updated_at")),  # type: ignore[arg-type]
            schema_version=_get("schemaVersion", "schema_version", "1.0.0"),
            artifact_type=_get("artifactType", "artifact_type", "memory-record"),
            owner_agent_id=_get("ownerAgentId", "owner_agent_id", None),
            artifact_set_id=_get("artifactSetId", "artifact_set_id", None),
            expires_at=_parse_dt(_get("expiresAt", "expires_at", None)),
            retention_policy=_get("retentionPolicy", "retention_policy", None),
            provenance_refs=_get("provenanceRefs", "provenance_refs", []),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )


@dataclass(slots=True)
class MemoryQuery:
    scope: str | None = None
    environment: str | None = None
    memory_type: str | None = None
    sensitivity_at_most: str | None = None
    tag: str | None = None
    text: str | None = None
    limit: int = 25


@dataclass(slots=True)
class MemoryPromotionRequest:
    memory_id: str
    source_environment: str
    target_environment: str
    approval_ref: str | None = None
    requested_by: str | None = None


@dataclass(slots=True)
class MemoryPromotionResult:
    promoted: bool
    reason: str
    record: MemoryRecord | None = None


class MemoryStore(Protocol):
    """Layer-3 typed memory backend (durable, per-agent).

    Memory stores hold ``MemoryRecord`` rows scoped by agent, environment, and
    sensitivity. Implementations must:

    - apply the sensitivity ceiling and environment filter inside ``read``
      (the runtime trusts the store, not the caller),
    - upsert by ``memory_id`` in ``write`` (idempotent re-writes during
      replay),
    - never mutate a record in place during ``promote`` — issue a new
      ``memory_id`` with ``provenance_refs`` pointing back at the source so
      the audit trail is preserved.

    Records that fail secret-pattern scans (see
    :func:`memory._find_secret_like_paths`) are rejected before reaching the
    store; implementations do not need to repeat that check.

    Minimum viable implementation::

        class DictStore:
            def __init__(self) -> None: self._rows: dict[str, MemoryRecord] = {}
            def read(self, q): return [r for r in self._rows.values()
                                       if r.scope == q.scope]
            def write(self, r): self._rows[r.memory_id] = r; return r
            def promote(self, req): ...  # see InMemoryMemoryStore

    Built-in implementations: :class:`aether_forge.InMemoryMemoryStore`
    (testing) and :class:`aether_forge.SqliteMemoryStore` (production,
    optional Fernet encryption).
    """

    def read(self, query: MemoryQuery) -> list[MemoryRecord]: ...

    def write(self, record: MemoryRecord) -> MemoryRecord: ...

    def promote(self, request: MemoryPromotionRequest) -> MemoryPromotionResult: ...


class MemoryPromotionPolicy:
    """Secure default policy for governed memory movement.

    V1 keeps cross-environment promotion manual. The non-negotiable case is
    sandbox-to-live promotion, but the default implementation is stricter and
    requires approval for any cross-environment move.
    """

    def requires_manual_approval(self, source_environment: str, target_environment: str) -> bool:
        return source_environment != target_environment

    def can_promote(self, request: MemoryPromotionRequest, record: MemoryRecord) -> MemoryPromotionResult:
        if record.environment != request.source_environment:
            return MemoryPromotionResult(
                promoted=False,
                reason="record environment does not match the promotion source environment",
            )

        if request.source_environment == request.target_environment:
            return MemoryPromotionResult(
                promoted=False,
                reason="source and target environments are identical; use write instead of promote",
            )

        if self.requires_manual_approval(request.source_environment, request.target_environment) and not request.approval_ref:
            if request.source_environment == "sandbox" and request.target_environment in LIVE_ENVIRONMENTS:
                reason = "sandbox memory requires manual approval before promotion to a live-like environment"
            else:
                reason = "cross-environment memory promotion requires manual approval in v1"

            return MemoryPromotionResult(promoted=False, reason=reason)

        return MemoryPromotionResult(promoted=True, reason="promotion approved by policy")


class InMemoryMemoryStore:
    def __init__(self, policy: MemoryPromotionPolicy | None = None) -> None:
        self._policy = policy or MemoryPromotionPolicy()
        self._records: dict[str, MemoryRecord] = {}

    def read(self, query: MemoryQuery, *, include_expired: bool = False) -> list[MemoryRecord]:
        now = datetime.now(UTC)
        results: list[MemoryRecord] = []
        for record in self._records.values():
            if not self._matches_query(record, query):
                continue
            if not include_expired and record.expires_at is not None and record.expires_at <= now:
                continue
            results.append(record)
        results.sort(key=lambda record: record.updated_at, reverse=True)
        return results[: query.limit]

    def write(self, record: MemoryRecord) -> MemoryRecord:
        self._validate_record(record)
        stored = replace(record, updated_at=datetime.now(UTC))
        self._records[stored.memory_id] = stored
        return stored

    def promote(self, request: MemoryPromotionRequest) -> MemoryPromotionResult:
        record = self._records.get(request.memory_id)
        if record is None:
            return MemoryPromotionResult(promoted=False, reason="memory record not found")

        policy_result = self._policy.can_promote(request, record)
        if not policy_result.promoted:
            return policy_result

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
        self._records[promoted_record.memory_id] = promoted_record

        return MemoryPromotionResult(
            promoted=True,
            reason="memory promoted",
            record=promoted_record,
        )

    def export_records(self) -> list[dict[str, Any]]:
        """Serialize all stored records for external persistence."""
        return [record.to_dict() for record in self._records.values()]

    @classmethod
    def from_exported(cls, records: list[dict[str, Any]], policy: MemoryPromotionPolicy | None = None) -> InMemoryMemoryStore:
        """Restore an ``InMemoryMemoryStore`` from previously exported records."""
        store = cls(policy=policy)
        for data in records:
            record = MemoryRecord.from_dict(data)
            store._records[record.memory_id] = record
        return store

    def read_for_environment(
        self,
        scope: str,
        environment: str,
        sensitivity_at_most: str = "internal",
    ) -> list[MemoryRecord]:
        """Return non-expired records filtered by scope, environment, and sensitivity ceiling."""
        max_index = SENSITIVITY_LEVELS.index(sensitivity_at_most)
        now = datetime.now(UTC)
        results: list[MemoryRecord] = []
        for record in self._records.values():
            if record.scope != scope:
                continue
            if record.environment != environment:
                continue
            if record.expires_at is not None and record.expires_at <= now:
                continue
            if SENSITIVITY_LEVELS.index(record.sensitivity) > max_index:
                continue
            results.append(record)
        results.sort(key=lambda record: record.updated_at, reverse=True)
        return results

    def _matches_query(self, record: MemoryRecord, query: MemoryQuery) -> bool:
        if query.scope and record.scope != query.scope:
            return False
        if query.environment and record.environment != query.environment:
            return False
        if query.memory_type and record.memory_type != query.memory_type:
            return False
        if query.tag and query.tag not in record.tags:
            return False
        if query.text:
            haystack = f"{record.summary}\n{record.content}".lower()
            if query.text.lower() not in haystack:
                return False
        if query.sensitivity_at_most:
            ordering = ["public", "internal", "sensitive", "restricted"]
            current_index = ordering.index(record.sensitivity)
            max_index = ordering.index(query.sensitivity_at_most)
            if current_index > max_index:
                return False
        return True

    def _validate_record(self, record: MemoryRecord) -> None:
        if not 0.0 <= record.confidence <= 1.0:
            raise ValueError("memory confidence must be between 0.0 and 1.0")

        for secret_path in _find_secret_like_paths(record.content):
            raise ValueError(f"memory records must not store secret-like keys or raw credential material: {secret_path}")


def _find_secret_like_paths(value: Any, prefix: str = "") -> list[str]:
    if isinstance(value, list):
        matches: list[str] = []
        for index, entry in enumerate(value):
            matches.extend(_find_secret_like_paths(entry, f"{prefix}/{index}"))
        return matches

    if not isinstance(value, dict):
        return []

    matches: list[str] = []
    for key, nested_value in value.items():
        next_prefix = f"{prefix}/{key}"
        if SECRET_LIKE_KEY.search(key):
            matches.append(next_prefix)
        matches.extend(_find_secret_like_paths(nested_value, next_prefix))
    return matches

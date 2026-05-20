"""Runtime execution of migration contracts (FP-4 — v0.22.0+).

The pre-v0.22.0 ``versioning.build_artifact_migration_plan`` could *describe*
the changes between two artifact versions, but executing the plan was a
manual exercise. ``MigrationRunner`` closes that gap: register a transform
callable in :class:`TransformRegistry`, point the runner at a
``migration-contract.schema.json``-compliant document plus the target
artifact or memory store, and the runner applies it under explicit policy
constraints.

Three core invariants this module enforces:

1. **Dry-run by default.** ``apply_to_*`` methods never mutate disk unless
   ``dry_run=False`` is passed. CLI surface mirrors this with ``--apply``.
2. **Lossy fields deny-by-default.** A migration contract whose
   ``lossyFields`` array is non-empty refuses to apply unless the contract's
   ``policy.lossyOk`` is true OR the caller passes ``lossy_ok=True``. This
   mirrors the ``_weakens_criteria`` philosophy from ``evolution.py:423``
   — automatic transforms must not silently delete user state.
3. **Pre-mutation backup.** When the runner touches a SQLite memory
   database, it copies the file to ``<db>.pre-migration-<timestamp>.bak``
   first. Recovery is a file rename away.

Transforms are sync ``Callable[[dict], dict]`` functions registered by
``(from_version, to_version, target)`` triples — ``target`` is one of
``"memory-record"`` (Sprint 2.4) or any artifact type identifier
(``"agent-spec"``, ``"capability-manifest"``, etc.). A missing transform
is a fail-fast condition; the runner returns a report enumerating the
mismatch so the operator can register the transform before re-running.
"""

from __future__ import annotations

import json
import logging
import shutil
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# A transform is a pure function from old row/artifact dict → new dict. It MUST
# NOT mutate its input. The runner deep-copies the output so callers can write
# it to disk safely.
TransformFn = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TransformKey:
    """Lookup key for :class:`TransformRegistry`. ``target`` is either
    ``"memory-record"`` or an artifact type identifier."""

    from_version: str
    to_version: str
    target: str


@dataclass(slots=True)
class TransformRegistry:
    """In-memory registry of ``(from_version, to_version, target) → TransformFn``.

    Test fixtures and downstream packages register entries via :meth:`register`.
    The runner consults it once per source-version cohort, so a single registered
    transform amortizes across thousands of rows.
    """

    _transforms: dict[TransformKey, TransformFn] = field(default_factory=dict)

    def register(
        self,
        *,
        from_version: str,
        to_version: str,
        target: str,
        transform: TransformFn,
    ) -> None:
        key = TransformKey(from_version=from_version, to_version=to_version, target=target)
        if key in self._transforms:
            raise ValueError(
                f"Transform already registered for {target} {from_version} → {to_version}"
            )
        self._transforms[key] = transform

    def lookup(self, key: TransformKey) -> TransformFn | None:
        return self._transforms.get(key)

    def keys(self) -> list[TransformKey]:
        return list(self._transforms.keys())


@dataclass(slots=True)
class MigrationContract:
    """In-memory representation of one ``migration-contract.schema.json``
    document. Schema validation happens up-front in :meth:`from_dict`."""

    from_version: str
    to_version: str
    transform_steps: list[str]
    lossy_fields: list[str]
    validation_checks: list[str]
    transform_ref: str | None = None
    lossy_ok: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MigrationContract:
        required = {"fromVersion", "toVersion", "transformSteps", "lossyFields", "validationChecks"}
        missing = required - data.keys()
        if missing:
            raise ValueError(f"Migration contract missing required fields: {sorted(missing)}")
        policy = data.get("policy") or {}
        if not isinstance(policy, dict):
            raise ValueError("Migration contract policy must be an object if present")
        return cls(
            from_version=str(data["fromVersion"]),
            to_version=str(data["toVersion"]),
            transform_steps=list(data["transformSteps"]),
            lossy_fields=list(data["lossyFields"]),
            validation_checks=list(data["validationChecks"]),
            transform_ref=data.get("transformRef"),
            lossy_ok=bool(policy.get("lossyOk", False)),
        )

    @classmethod
    def from_path(cls, path: str | Path) -> MigrationContract:
        text = Path(path).read_text(encoding="utf8")
        return cls.from_dict(json.loads(text))


@dataclass(slots=True)
class MigrationReport:
    """Outcome of a :meth:`MigrationRunner.apply_to_*` call.

    ``dry_run`` echoes the call mode. ``records_scanned`` is the universe
    examined; ``records_migrated`` is the subset that actually changed (or
    would have changed if ``dry_run=True``). ``backup_path`` is set only when
    the runner copied an on-disk database before mutating it.
    """

    target: str
    from_version: str
    to_version: str
    dry_run: bool
    records_scanned: int
    records_migrated: int
    records_skipped: int
    backup_path: str | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


class MigrationRunner:
    """Executes a :class:`MigrationContract` against an artifact dir or memory store.

    Construct once with a :class:`TransformRegistry`, then call
    :meth:`apply_to_memory_store` or :meth:`apply_to_artifact_file` per
    migration document. Reuses the registry across calls so a single
    ``MigrationRunner`` can drive a multi-step migration chain.
    """

    def __init__(self, registry: TransformRegistry) -> None:
        self._registry = registry

    # ------------------------------------------------------------------
    # Memory store path
    # ------------------------------------------------------------------

    def apply_to_memory_store(
        self,
        store: Any,
        contract: MigrationContract,
        *,
        dry_run: bool = True,
        lossy_ok: bool = False,
    ) -> MigrationReport:
        """Migrate every MemoryRecord whose ``schema_version`` matches
        ``contract.from_version``. The transform output replaces the row in
        place (same ``memory_id``); ``schema_version`` on the new record MUST
        match ``contract.to_version`` or the row is skipped with an issue.

        ``store`` must satisfy a small structural protocol:
        ``iter_records_below(version)`` (or ``iter_records()``), ``write(record)``,
        and ``_db_path``. The bundled :class:`SqliteMemoryStore` qualifies.
        """
        report = MigrationReport(
            target="memory-record",
            from_version=contract.from_version,
            to_version=contract.to_version,
            dry_run=dry_run,
            records_scanned=0,
            records_migrated=0,
            records_skipped=0,
        )

        if not self._check_lossy(contract, lossy_ok, report):
            return report

        transform = self._resolve_transform(contract, "memory-record", report)
        if transform is None:
            return report

        # Take a backup before any mutation. Always — even if it later turns
        # out no rows match, the backup is cheap and the operator can grep it.
        if not dry_run and hasattr(store, "_db_path"):
            try:
                report.backup_path = _backup_sqlite(store._db_path)
            except Exception as error:
                report.issues.append(f"backup failed: {error!r}")
                return report

        rows = list(self._iter_candidate_rows(store, contract.from_version))
        report.records_scanned = len(rows)

        for record in rows:
            old_dict = record.to_dict()
            try:
                new_dict = transform(old_dict)
            except Exception as error:
                report.issues.append(
                    f"transform raised on record {record.memory_id}: {error!r}"
                )
                report.records_skipped += 1
                continue
            if not isinstance(new_dict, dict):
                report.issues.append(
                    f"transform must return a dict; record {record.memory_id} got {type(new_dict).__name__}"
                )
                report.records_skipped += 1
                continue
            new_version = new_dict.get("schemaVersion") or new_dict.get("schema_version")
            if new_version != contract.to_version:
                report.issues.append(
                    f"transform output schemaVersion={new_version!r} does not match contract toVersion={contract.to_version!r} "
                    f"(record {record.memory_id})"
                )
                report.records_skipped += 1
                continue
            report.records_migrated += 1
            if dry_run:
                continue
            # Persist via the store's write path so secret-scan + encryption + WAL
            # checkpoint invariants are honored. Importing locally to avoid a hard
            # dep on memory module structure at file load time.
            from .memory import MemoryRecord

            store.write(MemoryRecord.from_dict(new_dict))

        return report

    # ------------------------------------------------------------------
    # Artifact file path
    # ------------------------------------------------------------------

    def apply_to_artifact_file(
        self,
        artifact_path: str | Path,
        contract: MigrationContract,
        *,
        target: str,
        dry_run: bool = True,
        lossy_ok: bool = False,
    ) -> MigrationReport:
        """Apply a contract to a single JSON artifact file.

        ``target`` is the artifact-type identifier the contract targets
        (``"agent-spec"``, ``"capability-manifest"``, etc.). The file is
        validated as JSON, the transform is applied, and (when not dry-run)
        the file is rewritten in place after a sibling ``.bak`` is created.
        """
        report = MigrationReport(
            target=target,
            from_version=contract.from_version,
            to_version=contract.to_version,
            dry_run=dry_run,
            records_scanned=1,
            records_migrated=0,
            records_skipped=0,
        )

        if not self._check_lossy(contract, lossy_ok, report):
            return report

        transform = self._resolve_transform(contract, target, report)
        if transform is None:
            return report

        artifact_path = Path(artifact_path)
        try:
            data = json.loads(artifact_path.read_text(encoding="utf8"))
        except (json.JSONDecodeError, OSError) as error:
            report.issues.append(f"could not read artifact: {error!r}")
            report.records_skipped = 1
            return report

        current_version = str(data.get("artifactVersion") or data.get("schemaVersion") or "")
        if current_version != contract.from_version:
            report.records_skipped = 1
            report.issues.append(
                f"artifact version {current_version!r} does not match contract fromVersion {contract.from_version!r}"
            )
            return report

        try:
            new_data = transform(data)
        except Exception as error:
            report.issues.append(f"transform raised: {error!r}")
            report.records_skipped = 1
            return report

        if not isinstance(new_data, dict):
            report.issues.append(
                f"transform must return a dict; got {type(new_data).__name__}"
            )
            report.records_skipped = 1
            return report

        new_version = str(new_data.get("artifactVersion") or new_data.get("schemaVersion") or "")
        if new_version != contract.to_version:
            report.issues.append(
                f"transform output version {new_version!r} does not match contract toVersion {contract.to_version!r}"
            )
            report.records_skipped = 1
            return report

        report.records_migrated = 1
        if dry_run:
            return report

        backup = artifact_path.with_suffix(artifact_path.suffix + f".pre-migration-{_timestamp()}.bak")
        try:
            shutil.copy2(artifact_path, backup)
            report.backup_path = str(backup)
            artifact_path.write_text(json.dumps(new_data, indent=2) + "\n", encoding="utf8")
        except OSError as error:
            report.issues.append(f"write failed: {error!r}")
            report.records_skipped = 1
            report.records_migrated = 0
            return report

        return report

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_lossy(
        self,
        contract: MigrationContract,
        lossy_ok: bool,
        report: MigrationReport,
    ) -> bool:
        if not contract.lossy_fields:
            return True
        if contract.lossy_ok or lossy_ok:
            return True
        report.issues.append(
            f"contract {contract.from_version} → {contract.to_version} drops fields {contract.lossy_fields} "
            "but neither contract.policy.lossyOk nor caller lossy_ok=True is set; refusing to apply"
        )
        return False

    def _resolve_transform(
        self,
        contract: MigrationContract,
        target: str,
        report: MigrationReport,
    ) -> TransformFn | None:
        if not contract.transform_ref:
            report.issues.append(
                "contract is documentation-only (no transformRef set); cannot execute"
            )
            return None
        # transformRef is informational at the schema level; the registry is
        # keyed on (from_version, to_version, target). transformRef is captured
        # in the report logs but is not part of the registry lookup.
        key = TransformKey(
            from_version=contract.from_version,
            to_version=contract.to_version,
            target=target,
        )
        transform = self._registry.lookup(key)
        if transform is None:
            report.issues.append(
                f"no transform registered for {target} {contract.from_version} → {contract.to_version} "
                f"(transformRef={contract.transform_ref!r})"
            )
        return transform

    def _iter_candidate_rows(self, store: Any, from_version: str) -> Iterator[Any]:
        if hasattr(store, "iter_records_below"):
            for record in store.iter_records_below(from_version, inclusive=True):
                if record.schema_version == from_version:
                    yield record
            return
        # Fallback: read everything and filter in Python. Slow but correct for
        # stores that don't implement the optimized iterator.
        from .memory import MemoryQuery

        for record in store.read(MemoryQuery(limit=10**9)):
            if record.schema_version == from_version:
                yield record


def _backup_sqlite(db_path: str | Path) -> str:
    """Copy a SQLite database file to a timestamped sibling. Returns the
    backup path as a string. Caller catches IO errors and records them."""
    src = Path(db_path)
    backup = src.with_suffix(src.suffix + f".pre-migration-{_timestamp()}.bak")
    shutil.copy2(src, backup)
    return str(backup)


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

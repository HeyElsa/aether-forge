"""Verify MigrationRunner executes migration contracts safely (Sprint 2.4 / FP-4).

Pins:
- TransformRegistry deduplicates by (from, to, target) key
- MigrationContract.from_dict raises on missing required fields
- MigrationContract.from_dict accepts the v0.22.0 optional fields
- Dry-run never mutates the database or artifact file
- --apply mutates and writes a backup
- Contract with lossyFields refuses to apply unless policy.lossyOk OR caller lossy_ok
- Contract without transformRef refuses to apply (documentation-only)
- Missing transform in registry surfaces a clear issue
- Transform whose output schemaVersion mismatches the contract is rejected
- Transform raising is caught per-record, not propagated
- Memory store iter_records_below + count_records_below
- Artifact-file path validates fromVersion match
- CLI: forge migrate memory dry-run / apply
- CLI: forge migrate artifact dry-run / apply
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from aether_forge.memory import MEMORY_RECORD_SCHEMA_VERSION, MemoryQuery, MemoryRecord
from aether_forge.migrations import (
    MigrationContract,
    MigrationRunner,
    TransformKey,
    TransformRegistry,
)
from aether_forge.storage import SqliteMemoryStore

# ---------------------------------------------------------------------------
# TransformRegistry
# ---------------------------------------------------------------------------


def test_registry_register_and_lookup() -> None:
    reg = TransformRegistry()
    fn = lambda d: d  # noqa: E731
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=fn)
    key = TransformKey(from_version="1.0.0", to_version="1.1.0", target="memory-record")
    assert reg.lookup(key) is fn


def test_registry_refuses_duplicate_registration() -> None:
    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=lambda d: d)
    with pytest.raises(ValueError, match="already registered"):
        reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=lambda d: d)


def test_registry_lookup_returns_none_for_unknown_key() -> None:
    reg = TransformRegistry()
    assert reg.lookup(TransformKey("1.0.0", "1.1.0", "memory-record")) is None


# ---------------------------------------------------------------------------
# MigrationContract parsing
# ---------------------------------------------------------------------------


def _contract_dict(**overrides) -> dict:
    base = {
        "fromVersion": "1.0.0",
        "toVersion": "1.1.0",
        "transformSteps": ["bump"],
        "lossyFields": [],
        "validationChecks": ["round-trip"],
    }
    base.update(overrides)
    return base


def test_contract_from_dict_happy_path() -> None:
    contract = MigrationContract.from_dict(_contract_dict())
    assert contract.from_version == "1.0.0"
    assert contract.to_version == "1.1.0"
    assert contract.transform_ref is None
    assert contract.lossy_ok is False


def test_contract_from_dict_optional_fields() -> None:
    contract = MigrationContract.from_dict(_contract_dict(
        transformRef="my_pkg:bump_v1_0_to_v1_1",
        policy={"lossyOk": True},
    ))
    assert contract.transform_ref == "my_pkg:bump_v1_0_to_v1_1"
    assert contract.lossy_ok is True


def test_contract_from_dict_raises_on_missing_field() -> None:
    payload = _contract_dict()
    payload.pop("validationChecks")
    with pytest.raises(ValueError, match="missing required fields"):
        MigrationContract.from_dict(payload)


def test_contract_from_dict_raises_when_policy_is_not_object() -> None:
    with pytest.raises(ValueError, match="policy must be an object"):
        MigrationContract.from_dict(_contract_dict(policy=["lossy"]))


def test_contract_from_path(tmp_path: Path) -> None:
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(_contract_dict(transformRef="x")), encoding="utf8")
    contract = MigrationContract.from_path(path)
    assert contract.transform_ref == "x"


# ---------------------------------------------------------------------------
# MigrationRunner — memory path
# ---------------------------------------------------------------------------


def _make_record(memory_id: str, *, schema_version: str = "1.0.0", scope: str = "trading") -> MemoryRecord:
    return MemoryRecord(
        memory_id=memory_id,
        memory_type="strategy-context",
        scope=scope,
        environment="sandbox",
        content={"note": "test"},
        summary="test",
        source="test",
        confidence=0.9,
        sensitivity="internal",
        schema_version=schema_version,
    )


def _bump_to_1_1_transform(old: dict) -> dict:
    """Sample transform: adds a 'migrated' tag and bumps schemaVersion."""
    new = dict(old)
    new["schemaVersion"] = "1.1.0"
    tags = list(new.get("tags") or [])
    if "migrated" not in tags:
        tags.append("migrated")
    new["tags"] = tags
    return new


def test_runner_dry_run_does_not_mutate(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record("mem_1"))

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=_bump_to_1_1_transform)

    contract = MigrationContract.from_dict(_contract_dict(transformRef="bump"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=True)

    assert report.dry_run is True
    assert report.records_scanned == 1
    assert report.records_migrated == 1
    assert report.records_skipped == 0
    assert report.ok
    assert report.backup_path is None

    # Confirm the row was NOT mutated
    rows = store.read(MemoryQuery(scope="trading"))
    assert rows[0].schema_version == "1.0.0"
    assert "migrated" not in rows[0].tags
    store.close()


def test_runner_apply_mutates_and_writes_backup(tmp_path: Path) -> None:
    db_path = tmp_path / "memory.db"
    store = SqliteMemoryStore(db_path)
    store.write(_make_record("mem_a"))
    store.write(_make_record("mem_b"))

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=_bump_to_1_1_transform)

    contract = MigrationContract.from_dict(_contract_dict(transformRef="bump"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=False)

    assert report.ok
    assert report.records_migrated == 2
    assert report.backup_path is not None
    assert Path(report.backup_path).exists()

    rows = sorted(store.read(MemoryQuery(scope="trading")), key=lambda r: r.memory_id)
    for row in rows:
        assert row.schema_version == "1.1.0"
        assert "migrated" in row.tags
    store.close()


def test_runner_refuses_lossy_contract_by_default(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=_bump_to_1_1_transform)

    contract = MigrationContract.from_dict(_contract_dict(
        lossyFields=["/legacyField"],
        transformRef="bump",
    ))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=True)

    assert not report.ok
    assert any("refusing to apply" in issue for issue in report.issues)
    store.close()


def test_runner_accepts_lossy_when_caller_overrides(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record("mem_x"))

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=_bump_to_1_1_transform)

    contract = MigrationContract.from_dict(_contract_dict(
        lossyFields=["/legacyField"],
        transformRef="bump",
    ))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=True, lossy_ok=True)

    assert report.ok
    store.close()


def test_runner_accepts_lossy_when_contract_policy_allows(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record("mem_y"))

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=_bump_to_1_1_transform)

    contract = MigrationContract.from_dict(_contract_dict(
        lossyFields=["/legacyField"],
        transformRef="bump",
        policy={"lossyOk": True},
    ))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=True)

    assert report.ok
    store.close()


def test_runner_refuses_contract_without_transform_ref(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    reg = TransformRegistry()
    contract = MigrationContract.from_dict(_contract_dict())  # no transformRef
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=True)

    assert not report.ok
    assert any("documentation-only" in issue for issue in report.issues)
    store.close()


def test_runner_reports_missing_transform(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    reg = TransformRegistry()  # empty registry
    contract = MigrationContract.from_dict(_contract_dict(transformRef="bump"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=True)

    assert not report.ok
    assert any("no transform registered" in issue for issue in report.issues)
    store.close()


def test_runner_skips_row_when_transform_returns_wrong_version(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record("mem_w"))

    def _bad_transform(old: dict) -> dict:
        new = dict(old)
        new["schemaVersion"] = "9.9.9"  # not 1.1.0
        return new

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=_bad_transform)

    contract = MigrationContract.from_dict(_contract_dict(transformRef="bad"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=False)

    assert report.records_scanned == 1
    assert report.records_migrated == 0
    assert report.records_skipped == 1
    assert any("does not match contract toVersion" in issue for issue in report.issues)
    store.close()


def test_runner_skips_row_when_transform_raises(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record("mem_r"))

    def _explode(old: dict) -> dict:
        raise RuntimeError("boom")

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=_explode)

    contract = MigrationContract.from_dict(_contract_dict(transformRef="boom"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=False)

    assert report.records_skipped == 1
    assert any("transform raised" in issue for issue in report.issues)
    store.close()


def test_runner_only_touches_matching_from_version(tmp_path: Path) -> None:
    """A row already at 1.1.0 is below 1.0.0=False, so iter_records_below(1.0.0, inclusive=True)
    only returns rows AT or BELOW 1.0.0 — no double-migration."""
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record("mem_old", schema_version="1.0.0"))
    store.write(_make_record("mem_new", schema_version="1.1.0"))

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="memory-record", transform=_bump_to_1_1_transform)

    contract = MigrationContract.from_dict(_contract_dict(transformRef="bump"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_memory_store(store, contract, dry_run=False)

    assert report.records_scanned == 1  # only mem_old
    assert report.records_migrated == 1
    rows = {r.memory_id: r for r in store.read(MemoryQuery(scope="trading"))}
    assert rows["mem_old"].schema_version == "1.1.0"
    assert rows["mem_new"].schema_version == "1.1.0"  # already at 1.1.0
    store.close()


# ---------------------------------------------------------------------------
# SqliteMemoryStore — iterator + count helpers
# ---------------------------------------------------------------------------


def test_iter_and_count_records_below(tmp_path: Path) -> None:
    store = SqliteMemoryStore(tmp_path / "memory.db")
    store.write(_make_record("mem_v0_9", schema_version="0.9.0"))
    store.write(_make_record("mem_v1_0", schema_version="1.0.0"))
    store.write(_make_record("mem_v1_1", schema_version="1.1.0"))

    below_strict = list(store.iter_records_below("1.0.0"))
    assert {r.memory_id for r in below_strict} == {"mem_v0_9"}
    assert store.count_records_below("1.0.0") == 1

    below_inclusive = list(store.iter_records_below("1.0.0", inclusive=True))
    assert {r.memory_id for r in below_inclusive} == {"mem_v0_9", "mem_v1_0"}
    assert store.count_records_below("1.0.0", inclusive=True) == 2
    store.close()


# ---------------------------------------------------------------------------
# MigrationRunner — artifact file path
# ---------------------------------------------------------------------------


def test_runner_artifact_dry_run(tmp_path: Path) -> None:
    artifact = tmp_path / "agent-spec.json"
    artifact.write_text(json.dumps({"artifactVersion": "1.0.0", "name": "agent"}), encoding="utf8")

    def _bump_artifact(old: dict) -> dict:
        new = dict(old)
        new["artifactVersion"] = "1.1.0"
        new["newField"] = True
        return new

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="agent-spec", transform=_bump_artifact)

    contract = MigrationContract.from_dict(_contract_dict(transformRef="bump-agent-spec"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_artifact_file(artifact, contract, target="agent-spec", dry_run=True)

    assert report.ok
    assert report.records_migrated == 1
    # File untouched
    assert json.loads(artifact.read_text())["artifactVersion"] == "1.0.0"


def test_runner_artifact_apply_writes_backup(tmp_path: Path) -> None:
    artifact = tmp_path / "agent-spec.json"
    artifact.write_text(json.dumps({"artifactVersion": "1.0.0", "name": "agent"}), encoding="utf8")

    reg = TransformRegistry()
    reg.register(
        from_version="1.0.0",
        to_version="1.1.0",
        target="agent-spec",
        transform=lambda old: {**old, "artifactVersion": "1.1.0", "newField": True},
    )

    contract = MigrationContract.from_dict(_contract_dict(transformRef="bump-agent-spec"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_artifact_file(artifact, contract, target="agent-spec", dry_run=False)

    assert report.ok
    assert report.backup_path is not None
    assert Path(report.backup_path).exists()
    assert json.loads(artifact.read_text())["artifactVersion"] == "1.1.0"


def test_runner_artifact_rejects_version_mismatch(tmp_path: Path) -> None:
    artifact = tmp_path / "agent-spec.json"
    artifact.write_text(json.dumps({"artifactVersion": "2.0.0"}), encoding="utf8")

    reg = TransformRegistry()
    reg.register(from_version="1.0.0", to_version="1.1.0", target="agent-spec", transform=lambda old: old)

    contract = MigrationContract.from_dict(_contract_dict(transformRef="bump"))
    runner = MigrationRunner(reg)
    report = runner.apply_to_artifact_file(artifact, contract, target="agent-spec", dry_run=False)

    assert not report.ok
    assert any("does not match contract fromVersion" in issue for issue in report.issues)


# ---------------------------------------------------------------------------
# CLI integration
# ---------------------------------------------------------------------------


def _write_contract(tmp_path: Path, **overrides) -> Path:
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(_contract_dict(**overrides)), encoding="utf8")
    return path


def test_cli_migrate_memory_dry_run(tmp_path: Path, monkeypatch, capsys) -> None:
    """Without --apply, the CLI must report dry-run and not mutate."""
    from aether_forge import plugins
    from aether_forge.cli import main

    plugins.reset_cache()

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    db_path = agent_dir / "memory.db"
    store = SqliteMemoryStore(db_path)
    store.write(_make_record("mem_cli"))
    store.close()

    contract_path = _write_contract(tmp_path, transformRef="bump")

    # CLI loads transforms from entry points — for the test we monkey-patch
    # the registry to inject our transform without registering a real plugin.
    import aether_forge.cli as cli_mod

    def _fake_iter(group):
        if group == "aether_forge.migrations":
            def _register(reg):
                reg.register(
                    from_version="1.0.0",
                    to_version="1.1.0",
                    target="memory-record",
                    transform=_bump_to_1_1_transform,
                )
            yield ("test-bump", _register)
        else:
            return
            yield  # pragma: no cover

    monkeypatch.setattr(plugins, "iter_entry_points", _fake_iter)

    rc = main([
        "migrate", "memory", str(agent_dir),
        "--contract", str(contract_path),
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "dry-run" in captured.out
    assert "scanned=1" in captured.out
    assert "migrated=1" in captured.out

    # No mutation
    store = SqliteMemoryStore(db_path)
    rows = store.read(MemoryQuery(scope="trading"))
    assert rows[0].schema_version == "1.0.0"
    store.close()


def test_cli_migrate_memory_apply(tmp_path: Path, monkeypatch, capsys) -> None:
    import aether_forge.cli as cli_mod
    from aether_forge import plugins
    from aether_forge.cli import main

    plugins.reset_cache()

    agent_dir = tmp_path / "agent"
    agent_dir.mkdir()
    db_path = agent_dir / "memory.db"
    store = SqliteMemoryStore(db_path)
    store.write(_make_record("mem_apply"))
    store.close()

    contract_path = _write_contract(tmp_path, transformRef="bump")

    def _fake_iter(group):
        if group == "aether_forge.migrations":
            def _register(reg):
                reg.register(
                    from_version="1.0.0",
                    to_version="1.1.0",
                    target="memory-record",
                    transform=_bump_to_1_1_transform,
                )
            yield ("test-bump", _register)
        else:
            return
            yield  # pragma: no cover

    monkeypatch.setattr(plugins, "iter_entry_points", _fake_iter)

    rc = main([
        "migrate", "memory", str(agent_dir),
        "--contract", str(contract_path),
        "--apply",
    ])
    captured = capsys.readouterr()
    assert rc == 0
    assert "(apply)" in captured.out
    assert "backup:" in captured.out

    store = SqliteMemoryStore(db_path)
    rows = store.read(MemoryQuery(scope="trading"))
    assert rows[0].schema_version == "1.1.0"
    assert "migrated" in rows[0].tags
    store.close()


def test_cli_migrate_without_subcommand_returns_error(capsys) -> None:
    from aether_forge.cli import main
    rc = main(["migrate"])
    captured = capsys.readouterr()
    assert rc == 2
    assert "requires a sub-command" in captured.err

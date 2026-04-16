from __future__ import annotations

import json
from pathlib import Path
from shutil import copytree, rmtree
from tempfile import mkdtemp

from aether_forge.cli import main
from aether_forge.versioning import SemanticVersion, assess_artifact_set_compatibility, build_artifact_migration_plan

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def test_semantic_version_parse_and_ordering() -> None:
    assert SemanticVersion.parse("1.2.3") < SemanticVersion.parse("2.0.0")
    assert str(SemanticVersion.parse("0.7.0")) == "0.7.0"


def test_artifact_set_compatibility_accepts_backward_compatible_patch_update() -> None:
    previous_dir = _copy_fixture()
    current_dir = _copy_fixture()

    try:
        (previous_dir / "promotion-record.json").unlink(missing_ok=True)
        (current_dir / "promotion-record.json").unlink(missing_ok=True)
        current_agent_spec_path = current_dir / "agent-spec.json"
        current_agent_spec = json.loads(current_agent_spec_path.read_text(encoding="utf8"))
        current_agent_spec["artifactVersion"] = "0.1.1"
        current_agent_spec["compatibility"]["previousArtifactVersion"] = "0.1.0"
        current_agent_spec_path.write_text(f"{json.dumps(current_agent_spec, indent=2)}\n", encoding="utf8")

        result = assess_artifact_set_compatibility(previous_dir, current_dir)

        assert result.ok is True
        assert any(assessment.artifact_type == "agent-spec" for assessment in result.assessments)
    finally:
        rmtree(previous_dir)
        rmtree(current_dir)


def test_artifact_set_compatibility_requires_migration_for_breaking_change() -> None:
    previous_dir = _copy_fixture()
    current_dir = _copy_fixture()

    try:
        (previous_dir / "promotion-record.json").unlink(missing_ok=True)
        (current_dir / "promotion-record.json").unlink(missing_ok=True)
        current_agent_spec_path = current_dir / "agent-spec.json"
        current_agent_spec = json.loads(current_agent_spec_path.read_text(encoding="utf8"))
        current_agent_spec["artifactVersion"] = "1.0.0"
        current_agent_spec["compatibility"]["status"] = "breaking"
        current_agent_spec["compatibility"]["previousArtifactVersion"] = "0.1.0"
        current_agent_spec["compatibility"]["migrationRef"] = None
        current_agent_spec_path.write_text(f"{json.dumps(current_agent_spec, indent=2)}\n", encoding="utf8")

        result = assess_artifact_set_compatibility(previous_dir, current_dir)

        assert result.ok is False
        assert any("migrationRef" in issue for issue in result.issues)
    finally:
        rmtree(previous_dir)
        rmtree(current_dir)


def test_artifact_compat_cli_reports_failure_for_missing_previous_link(capsys) -> None:
    previous_dir = _copy_fixture()
    current_dir = _copy_fixture()

    try:
        (previous_dir / "promotion-record.json").unlink(missing_ok=True)
        (current_dir / "promotion-record.json").unlink(missing_ok=True)
        current_agent_spec_path = current_dir / "agent-spec.json"
        current_agent_spec = json.loads(current_agent_spec_path.read_text(encoding="utf8"))
        current_agent_spec["artifactVersion"] = "0.1.1"
        current_agent_spec["compatibility"]["previousArtifactVersion"] = "0.0.9"
        current_agent_spec_path.write_text(f"{json.dumps(current_agent_spec, indent=2)}\n", encoding="utf8")

        exit_code = main([
            "artifact-compat",
            "--previous",
            str(previous_dir),
            "--current",
            str(current_dir),
        ])

        output = capsys.readouterr().out
        assert exit_code == 1
        assert "previousArtifactVersion" in output
    finally:
        rmtree(previous_dir)
        rmtree(current_dir)


def test_build_artifact_migration_plan_detects_lossy_fields() -> None:
    previous_dir = _copy_fixture()
    current_dir = _copy_fixture()

    try:
        (previous_dir / "promotion-record.json").unlink(missing_ok=True)
        (current_dir / "promotion-record.json").unlink(missing_ok=True)
        current_agent_spec_path = current_dir / "agent-spec.json"
        current_agent_spec = json.loads(current_agent_spec_path.read_text(encoding="utf8"))
        current_agent_spec["artifactVersion"] = "1.0.0"
        current_agent_spec["compatibility"]["status"] = "breaking"
        current_agent_spec["compatibility"]["previousArtifactVersion"] = "0.1.0"
        current_agent_spec["objective"].pop("nonGoals", None)
        current_agent_spec_path.write_text(f"{json.dumps(current_agent_spec, indent=2)}\n", encoding="utf8")

        plan = build_artifact_migration_plan(previous_dir, current_dir, "agent-spec")

        assert plan.contract["fromVersion"] == "0.1.0"
        assert plan.contract["toVersion"] == "1.0.0"
        assert "/objective/nonGoals" in plan.contract["lossyFields"]
        assert any("lossy" in check for check in plan.contract["validationChecks"])
    finally:
        rmtree(previous_dir)
        rmtree(current_dir)


def test_artifact_migration_plan_cli_can_write_contract_file() -> None:
    previous_dir = _copy_fixture()
    current_dir = _copy_fixture()
    output_dir = Path(mkdtemp(prefix="aether-forge-migration-plan-"))
    output_path = output_dir / "agent-spec-migration.json"

    try:
        (previous_dir / "promotion-record.json").unlink(missing_ok=True)
        (current_dir / "promotion-record.json").unlink(missing_ok=True)
        current_agent_spec_path = current_dir / "agent-spec.json"
        current_agent_spec = json.loads(current_agent_spec_path.read_text(encoding="utf8"))
        current_agent_spec["artifactVersion"] = "1.0.0"
        current_agent_spec["compatibility"]["status"] = "breaking"
        current_agent_spec["compatibility"]["previousArtifactVersion"] = "0.1.0"
        current_agent_spec["objective"]["primaryGoal"] = "Changed objective"
        current_agent_spec_path.write_text(f"{json.dumps(current_agent_spec, indent=2)}\n", encoding="utf8")

        exit_code = main([
            "artifact-migration-plan",
            "--previous",
            str(previous_dir),
            "--current",
            str(current_dir),
            "--artifact-type",
            "agent-spec",
            "--output",
            str(output_path),
        ])

        payload = json.loads(output_path.read_text(encoding="utf8"))

        assert exit_code == 0
        assert payload["fromVersion"] == "0.1.0"
        assert payload["toVersion"] == "1.0.0"
        assert any("changed field" in step for step in payload["transformSteps"])
    finally:
        rmtree(previous_dir)
        rmtree(current_dir)
        rmtree(output_dir)


def _copy_fixture() -> Path:
    destination = Path(mkdtemp(prefix="aether-forge-versioning-"))
    copytree(EXAMPLE_DIR, destination, dirs_exist_ok=True)
    return destination

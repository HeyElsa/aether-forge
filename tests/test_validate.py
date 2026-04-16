from __future__ import annotations

import json
from pathlib import Path
from shutil import copytree, rmtree
from tempfile import mkdtemp

from aether_forge.artifacts import validate_artifact_directory


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def test_validates_delta_neutral_example() -> None:
    result = validate_artifact_directory(EXAMPLE_DIR)

    assert result.ok is True
    assert result.issues == []
    assert result.artifact_set_id == "aset_delta_neutral_btc_v001"


def test_rejects_secret_like_keys_in_agent_spec() -> None:
    fixture_dir = _create_temp_fixture()

    try:
        agent_spec_path = fixture_dir / "agent-spec.json"
        agent_spec = json.loads(agent_spec_path.read_text(encoding="utf8"))
        agent_spec["privateKey"] = "should-not-be-here"
        agent_spec_path.write_text(f"{json.dumps(agent_spec, indent=2)}\n", encoding="utf8")

        result = validate_artifact_directory(fixture_dir)

        assert result.ok is False
        assert any(issue.code == "agent-spec.secret-like-key" for issue in result.issues)
    finally:
        rmtree(fixture_dir)


def test_rejects_missing_capability_references() -> None:
    fixture_dir = _create_temp_fixture()

    try:
        agent_spec_path = fixture_dir / "agent-spec.json"
        agent_spec = json.loads(agent_spec_path.read_text(encoding="utf8"))
        agent_spec["capabilityRefs"].append("cap-not-real")
        agent_spec_path.write_text(f"{json.dumps(agent_spec, indent=2)}\n", encoding="utf8")

        result = validate_artifact_directory(fixture_dir)

        assert result.ok is False
        assert any(issue.code == "agent-spec.capability-ref.missing" for issue in result.issues)
    finally:
        rmtree(fixture_dir)


def _create_temp_fixture() -> Path:
    destination = Path(mkdtemp(prefix="aether-forge-artifacts-"))
    copytree(EXAMPLE_DIR, destination, dirs_exist_ok=True)
    return destination

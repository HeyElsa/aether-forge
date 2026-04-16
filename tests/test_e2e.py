"""End-to-end integration tests for the full Aether Forge pipeline.

These tests exercise the complete workflow:
  generate-fast -> validate -> eval-pack -> promote-draft
in a single flow, proving the pipeline works end-to-end.
"""

from __future__ import annotations

import json
from pathlib import Path

from aether_forge.artifacts import validate_artifact_directory
from aether_forge.cli import main
from aether_forge.evals import build_promotion_evidence, create_promotion_record_artifact, evaluate_scenario_pack
from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
from aether_forge.storage import SqliteMemoryStore


def test_e2e_generate_validate_eval_promote_crypto(tmp_path: Path) -> None:
    """Full pipeline for a crypto agent: generate -> validate -> eval -> promote."""
    output_dir = tmp_path / "btc-agent"

    # 1. Generate
    request = FastGenerateRequest(
        name="BTC Test Agent",
        idea="delta-neutral BTC basis capture",
        output_directory=output_dir,
    )
    generated = generate_fast_artifact_set(request)
    assert "crypto" in generated.domain
    assert generated.output_directory == output_dir
    assert (output_dir / "agent-spec.json").exists()
    assert (output_dir / "capability-manifest.json").exists()
    assert (output_dir / "policy-bundle.json").exists()
    assert (output_dir / "scenario-pack.json").exists()
    assert (output_dir / "scaffold.manifest.json").exists()

    # 2. Validate
    validation_result = validate_artifact_directory(output_dir)
    assert validation_result.ok, f"Validation failed: {validation_result.issues}"
    assert len(validation_result.artifacts) >= 5

    # 3. Evaluate scenario pack
    summary, sessions = evaluate_scenario_pack(output_dir)
    assert summary.total_scenarios > 0
    assert summary.counts_by_stage.get("pass", 0) > 0

    # 4. Promote
    evidence = build_promotion_evidence(output_dir, "paper", summary)
    assert evidence["targetEnvironment"] == "paper"

    promotion_record = create_promotion_record_artifact(
        output_dir,
        target_environment="paper",
        approvers=["test-approver"],
    )
    assert promotion_record["promotionDecision"]["decisionOutcome"] in ("approved", "approved-with-limits")
    assert "test-approver" in promotion_record["promotionDecision"]["approvers"]

    # Write and re-validate with promotion record
    promo_path = output_dir / "promotion-record.json"
    promo_path.write_text(json.dumps(promotion_record, indent=2), encoding="utf8")
    final_validation = validate_artifact_directory(output_dir)
    assert final_validation.ok


def test_e2e_generate_validate_eval_promote_general(tmp_path: Path) -> None:
    """Full pipeline for a general agent."""
    output_dir = tmp_path / "general-agent"

    request = FastGenerateRequest(
        name="Research Assistant",
        idea="summarize academic papers and extract key findings",
        output_directory=output_dir,
    )
    generated = generate_fast_artifact_set(request)
    assert "general" in generated.domain

    validation_result = validate_artifact_directory(output_dir)
    assert validation_result.ok

    summary, _ = evaluate_scenario_pack(output_dir)
    assert summary.total_scenarios > 0

    promotion_record = create_promotion_record_artifact(
        output_dir,
        target_environment="paper",
        approvers=["ops-team"],
    )
    assert promotion_record["promotionDecision"]["decisionOutcome"] in ("approved", "approved-with-limits")


def test_e2e_cli_generate_validate_eval(tmp_path: Path) -> None:
    """Full pipeline via CLI entry points."""
    output_dir = tmp_path / "cli-agent"

    # generate-fast
    rc = main([
        "generate-fast",
        "--name", "CLI Test Agent",
        "--idea", "monitor server health metrics",
        "--output", str(output_dir),
    ])
    assert rc == 0
    assert (output_dir / "agent-spec.json").exists()

    # validate
    rc = main(["validate", str(output_dir)])
    assert rc == 0

    # eval-pack
    rc = main(["eval-pack", str(output_dir)])
    assert rc == 0

    # promote-draft
    promo_path = tmp_path / "promotion-record.json"
    rc = main([
        "promote-draft", str(output_dir),
        "--target", "paper",
        "--approver", "test-approver",
        "--output", str(promo_path),
    ])
    assert rc == 0
    assert promo_path.exists()
    promo = json.loads(promo_path.read_text(encoding="utf8"))
    assert promo["promotionDecision"]["decisionOutcome"] in ("approved", "approved-with-limits")


def test_e2e_with_sqlite_memory(tmp_path: Path) -> None:
    """Pipeline with SQLite memory store persists memory across eval scenarios."""
    output_dir = tmp_path / "mem-agent"

    request = FastGenerateRequest(
        name="Memory Test Agent",
        idea="track portfolio positions and remember trading context",
        output_directory=output_dir,
    )
    generate_fast_artifact_set(request)

    db_path = tmp_path / "memory.db"
    memory_store = SqliteMemoryStore(db_path)

    summary, sessions = evaluate_scenario_pack(output_dir, memory_store=memory_store)
    assert summary.total_scenarios > 0

    memory_store.close()

    # Verify DB file was created
    assert db_path.exists()


def test_e2e_generate_with_skills(tmp_path: Path) -> None:
    """Generate with Elsa skills and verify they map to capabilities."""
    output_dir = tmp_path / "skill-agent"

    request = FastGenerateRequest(
        name="DeFi Bot",
        idea="monitor yield opportunities on DeFi protocols",
        output_directory=output_dir,
        skills=["elsa:portfolio"],
    )
    generated = generate_fast_artifact_set(request)

    validation_result = validate_artifact_directory(output_dir)
    assert validation_result.ok

    # Check that skills are referenced in the capability manifest
    manifest = json.loads((output_dir / "capability-manifest.json").read_text(encoding="utf8"))
    cap_ids = {c["capabilityId"] for c in manifest["capabilities"]}
    assert any("elsa" in cid or "portfolio" in cid for cid in cap_ids)

    summary, _ = evaluate_scenario_pack(output_dir)
    assert summary.total_scenarios > 0

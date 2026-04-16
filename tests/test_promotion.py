from __future__ import annotations

import json
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from aether_forge.artifacts import validate_artifact_directory
from aether_forge.evals import create_promotion_record_artifact
from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set


def test_generated_promotion_record_validates_with_generated_artifact_set() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-promotion-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        promotion_record = create_promotion_record_artifact(output_dir, target_environment="paper", approvers=["founder"])
        (output_dir / "promotion-record.json").write_text(f"{json.dumps(promotion_record, indent=2)}\n", encoding="utf8")

        result = validate_artifact_directory(output_dir)

        assert result.ok is True
        assert result.issues == []
        assert promotion_record["promotionDecision"]["decisionOutcome"] == "approved"
    finally:
        rmtree(output_dir)


def test_promotion_record_can_include_runtime_replay_refs() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-promotion-"))
    replay_dir = output_dir / "replays"

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        promotion_record = create_promotion_record_artifact(
            output_dir,
            target_environment="paper",
            approvers=["founder"],
            replay_output_directory=replay_dir,
        )

        replay_refs = promotion_record["evaluationSummary"]["runtimeReplayRefs"]
        assert len(replay_refs) == 2
        for replay_ref in replay_refs:
            assert Path(replay_ref["path"]).exists()
    finally:
        rmtree(output_dir)

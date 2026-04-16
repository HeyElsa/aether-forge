"""Tests for slow-mode autoresearch generation."""

from __future__ import annotations

import json
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from aether_forge.models import StaticPlanningModel
from aether_forge.slow_generate import (
    SlowGenerateRequest,
    SlowGenerateResult,
    _apply_mutations,
    _parse_improvement,
    generate_slow_artifact_set,
)


# ---------------------------------------------------------------------------
# 1. Baseline-only (no research model)
# ---------------------------------------------------------------------------


def test_slow_generate_baseline_only_without_model() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-slow-"))

    try:
        result = generate_slow_artifact_set(
            SlowGenerateRequest(
                name="Baseline Test Agent",
                idea="Build an agent that summarizes documents.",
                output_directory=output_dir,
                research_model=None,
            )
        )

        assert isinstance(result, SlowGenerateResult)
        assert len(result.iterations) == 1
        assert "match_rate" in result.baseline_metrics
        assert result.research_record_path is not None
        assert result.research_record_path.exists()

        record = json.loads(result.research_record_path.read_text(encoding="utf8"))
        assert record["artifactType"] == "research-record"
        assert result.iterations[0].decision_status == "keep"
    finally:
        rmtree(output_dir)


# ---------------------------------------------------------------------------
# 2. Static model runs multiple iterations
# ---------------------------------------------------------------------------


def test_slow_generate_with_static_model_runs_iterations() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-slow-"))

    model_response = json.dumps(
        {
            "hypothesis": "Adding explicit evaluation criteria improves spec clarity",
            "target_artifact": "agent-spec.json",
            "mutations": [
                {
                    "path": "evaluationCriteria.notes",
                    "action": "set",
                    "value": "Refined by autoresearch",
                }
            ],
        }
    )

    try:
        result = generate_slow_artifact_set(
            SlowGenerateRequest(
                name="Iterative Test Agent",
                idea="Build an agent that summarizes documents.",
                output_directory=output_dir,
                max_iterations=2,
                research_model=StaticPlanningModel(response=model_response),
            )
        )

        # baseline + at least 1 iteration
        assert len(result.iterations) > 1

        record = json.loads(result.research_record_path.read_text(encoding="utf8"))
        assert len(record["iterationLedger"]) > 1

        assert result.iterations[-1].decision_status != "keep" or record["stopRationale"]["reason"] in (
            "budget-exhausted",
            "diminishing-returns",
        )
    finally:
        rmtree(output_dir)


# ---------------------------------------------------------------------------
# 3. Bad mutations are discarded / execution-failure
# ---------------------------------------------------------------------------


def test_slow_generate_discards_bad_mutations() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-slow-"))

    model_response = json.dumps(
        {
            "hypothesis": "Target a nonexistent artifact",
            "target_artifact": "nonexistent-artifact.json",
            "mutations": [
                {"path": "foo.bar", "action": "set", "value": "baz"}
            ],
        }
    )

    try:
        result = generate_slow_artifact_set(
            SlowGenerateRequest(
                name="Bad Mutation Agent",
                idea="Build an agent that summarizes documents.",
                output_directory=output_dir,
                max_iterations=1,
                research_model=StaticPlanningModel(response=model_response),
            )
        )

        non_baseline = [e for e in result.iterations if e.candidate_id != "cand_baseline"]
        assert len(non_baseline) >= 1
        assert non_baseline[0].decision_status in ("discard", "execution-failure")
    finally:
        rmtree(output_dir)


# ---------------------------------------------------------------------------
# 4. Research record matches expected schema structure
# ---------------------------------------------------------------------------


def test_slow_generate_research_record_matches_schema_structure() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-slow-"))

    try:
        result = generate_slow_artifact_set(
            SlowGenerateRequest(
                name="Schema Check Agent",
                idea="Build an agent that checks schemas.",
                output_directory=output_dir,
                research_model=None,
            )
        )

        record = json.loads(result.research_record_path.read_text(encoding="utf8"))

        required_keys = [
            "artifactType",
            "schemaVersion",
            "artifactId",
            "artifactSetId",
            "title",
            "researchPlan",
            "evidenceLog",
            "findings",
            "blockers",
            "activeComparisonContract",
            "iterationLedger",
            "stopRationale",
        ]
        for key in required_keys:
            assert key in record, f"Missing required key: {key}"
    finally:
        rmtree(output_dir)


# ---------------------------------------------------------------------------
# 5. Stops on diminishing returns
# ---------------------------------------------------------------------------


def test_slow_generate_stops_on_diminishing_returns() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-slow-"))

    # A no-op mutation that won't improve metrics — targets an inert field
    model_response = json.dumps(
        {
            "hypothesis": "No-op change that will not improve anything",
            "target_artifact": "agent-spec.json",
            "mutations": [
                {
                    "path": "metadata.noop",
                    "action": "set",
                    "value": "unchanged",
                }
            ],
        }
    )

    try:
        result = generate_slow_artifact_set(
            SlowGenerateRequest(
                name="Diminishing Returns Agent",
                idea="Build an agent that summarizes documents.",
                output_directory=output_dir,
                max_iterations=5,
                research_model=StaticPlanningModel(response=model_response),
            )
        )

        record = json.loads(result.research_record_path.read_text(encoding="utf8"))

        # baseline (1) + at most 5 iterations = 6 max; should stop early
        # The loop stops after 2 consecutive discards so we expect <= 4 total
        # (baseline + 2 discards = 3, or baseline + some keep + 2 discards)
        assert len(result.iterations) < 6
        assert record["stopRationale"]["reason"] == "diminishing-returns"
    finally:
        rmtree(output_dir)


# ---------------------------------------------------------------------------
# 6. _parse_improvement handles edge cases
# ---------------------------------------------------------------------------


def test_parse_improvement_handles_malformed_json() -> None:
    # Valid JSON
    valid = json.dumps(
        {
            "hypothesis": "test",
            "target_artifact": "agent-spec.json",
            "mutations": [],
        }
    )
    proposal = _parse_improvement(valid)
    assert proposal is not None
    assert proposal.hypothesis == "test"

    # Invalid JSON
    assert _parse_improvement("not json at all") is None

    # Missing "hypothesis" key
    missing_key = json.dumps({"target_artifact": "agent-spec.json", "mutations": []})
    assert _parse_improvement(missing_key) is None

    # JSON wrapped in markdown fences
    fenced = f"```json\n{valid}\n```"
    proposal2 = _parse_improvement(fenced)
    assert proposal2 is not None
    assert proposal2.hypothesis == "test"


# ---------------------------------------------------------------------------
# 7. _apply_mutations set, add, remove
# ---------------------------------------------------------------------------


def test_apply_mutations_set_and_add() -> None:
    artifact = {
        "objective": "test objective",
        "tags": ["alpha"],
        "nested": {"field": "original"},
    }

    # "set" creates/overwrites a field
    result = _apply_mutations(artifact, [{"path": "nested.field", "action": "set", "value": "updated"}])
    assert result["nested"]["field"] == "updated"

    # "set" creates a new top-level field
    result = _apply_mutations(artifact, [{"path": "newField", "action": "set", "value": 42}])
    assert result["newField"] == 42

    # "add" appends to a list
    result = _apply_mutations(artifact, [{"path": "tags", "action": "add", "value": "beta"}])
    assert result["tags"] == ["alpha", "beta"]

    # "remove" deletes a field
    result = _apply_mutations(artifact, [{"path": "nested.field", "action": "remove"}])
    assert "field" not in result["nested"]

    # Original artifact is not mutated
    assert artifact["nested"]["field"] == "original"
    assert artifact["tags"] == ["alpha"]

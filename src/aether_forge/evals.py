"""Scenario execution helpers for the native Aether Forge runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .crypto import (
    MockCryptoExecutionRouter,
)
from .planner import HeuristicPlanner
from .runtime import (
    ArtifactBundle,
    Planner,
    RuntimeSession,
    SessionStatus,
    load_artifact_bundle,
    write_session_replay_json,
)


@dataclass(slots=True)
class ScenarioEvaluationResult:
    scenario_id: str
    stage_outcome: str
    session_status: str
    blocking_reason_ids: list[str]
    step_count: int
    replay_class: str


@dataclass(slots=True)
class ScenarioPackEvaluationSummary:
    artifact_set_id: str
    total_scenarios: int
    matched_expectations: int
    counts_by_stage: dict[str, int]
    results: list[ScenarioEvaluationResult]
    meets_expectations: bool


def evaluate_scenario(
    artifact_directory: str | Path,
    scenario_id: str,
    memory_store: Any = None,
) -> tuple[ScenarioEvaluationResult, RuntimeSession]:
    return evaluate_scenario_with_planner(artifact_directory, scenario_id, memory_store=memory_store)


def evaluate_scenario_with_planner(
    artifact_directory: str | Path,
    scenario_id: str,
    planner_factory: Callable[[], Planner] | None = None,
    execution_router_factory: Callable[[], Any] | None = None,
    memory_store: Any = None,
) -> tuple[ScenarioEvaluationResult, RuntimeSession]:
    artifacts = load_artifact_bundle(artifact_directory)
    scenario = _find_scenario(artifacts, scenario_id)
    session = RuntimeSession(
        artifacts=artifacts,
        environment=scenario["environmentKind"],
        planner=(planner_factory or HeuristicPlanner)(),
        execution_router=(execution_router_factory or MockCryptoExecutionRouter)(),
        scenario_inputs=scenario.get("inputs", {}),
        memory_store=memory_store,
    )
    status = session.run()

    stage_outcome = _status_to_stage_outcome(status)
    result = ScenarioEvaluationResult(
        scenario_id=scenario_id,
        stage_outcome=stage_outcome,
        session_status=status.value,
        blocking_reason_ids=list(session.session_state.get("blocking_reason_ids", [])),
        step_count=len(session.step_ledger),
        replay_class=scenario.get("replayClass", "audit-only"),
    )
    return result, session


def evaluate_scenario_pack(
    artifact_directory: str | Path,
    environment_kind: str | None = None,
    planner_factory: Callable[[], Planner] | None = None,
    execution_router_factory: Callable[[], Any] | None = None,
    memory_store: Any = None,
) -> tuple[ScenarioPackEvaluationSummary, dict[str, RuntimeSession]]:
    artifacts = load_artifact_bundle(artifact_directory)

    scenario_results: list[ScenarioEvaluationResult] = []
    sessions: dict[str, RuntimeSession] = {}
    matched_expectations = 0
    counts_by_stage = {"pass": 0, "hold": 0, "fail": 0}

    for scenario in artifacts.scenario_pack.get("scenarios", []):
        if environment_kind and scenario.get("environmentKind") != environment_kind:
            continue

        result, session = evaluate_scenario_with_planner(
            artifact_directory,
            scenario["scenarioId"],
            planner_factory=planner_factory,
            execution_router_factory=execution_router_factory,
            memory_store=memory_store,
        )
        scenario_results.append(result)
        sessions[result.scenario_id] = session
        counts_by_stage[result.stage_outcome] = counts_by_stage.get(result.stage_outcome, 0) + 1

        expected_stage = scenario.get("expectedOutcome", {}).get("stageOutcome")
        if expected_stage == result.stage_outcome:
            matched_expectations += 1

    total_scenarios = len(scenario_results)
    summary = ScenarioPackEvaluationSummary(
        artifact_set_id=artifacts.agent_spec["artifactSetId"],
        total_scenarios=total_scenarios,
        matched_expectations=matched_expectations,
        counts_by_stage=counts_by_stage,
        results=scenario_results,
        meets_expectations=(total_scenarios > 0 and matched_expectations == total_scenarios),
    )
    return summary, sessions


def build_promotion_evidence(
    artifact_directory: str | Path,
    target_environment: str,
    summary: ScenarioPackEvaluationSummary,
    runtime_replay_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    artifacts = load_artifact_bundle(artifact_directory)

    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "artifactSetId": artifacts.agent_spec["artifactSetId"],
        "targetEnvironment": target_environment,
        "promotionReady": summary.meets_expectations,
        "artifactRefs": [
            {
                "artifactType": artifacts.agent_spec["artifactType"],
                "artifactId": artifacts.agent_spec["artifactId"],
                "artifactVersion": artifacts.agent_spec["artifactVersion"],
            },
            {
                "artifactType": artifacts.capability_manifest["artifactType"],
                "artifactId": artifacts.capability_manifest["artifactId"],
                "artifactVersion": artifacts.capability_manifest["artifactVersion"],
            },
            {
                "artifactType": artifacts.policy_bundle["artifactType"],
                "artifactId": artifacts.policy_bundle["artifactId"],
                "artifactVersion": artifacts.policy_bundle["artifactVersion"],
            },
            {
                "artifactType": artifacts.scenario_pack["artifactType"],
                "artifactId": artifacts.scenario_pack["artifactId"],
                "artifactVersion": artifacts.scenario_pack["artifactVersion"],
            },
        ],
        "evaluationSummary": {
            "totalScenarios": summary.total_scenarios,
            "matchedExpectations": summary.matched_expectations,
            "countsByStage": summary.counts_by_stage,
            "runtimeReplayRefs": runtime_replay_refs or [],
            "scenarioOutcomes": [
                {
                    "scenarioId": result.scenario_id,
                    "stageOutcome": result.stage_outcome,
                    "blockingReasonIds": result.blocking_reason_ids,
                    "stepCount": result.step_count,
                    "replayClass": result.replay_class,
                }
                for result in summary.results
            ],
        },
    }


def write_eval_pack_replays(
    artifact_directory: str | Path,
    output_directory: str | Path,
    environment_kind: str | None = None,
    planner_factory: Callable[[], Planner] | None = None,
    execution_router_factory: Callable[[], Any] | None = None,
) -> list[dict[str, Any]]:
    summary, sessions = evaluate_scenario_pack(
        artifact_directory,
        environment_kind=environment_kind,
        planner_factory=planner_factory,
        execution_router_factory=execution_router_factory,
    )
    output_path = Path(output_directory)
    output_path.mkdir(parents=True, exist_ok=True)

    replay_refs: list[dict[str, Any]] = []
    for result in summary.results:
        session = sessions[result.scenario_id]
        replay_file = output_path / f"{result.scenario_id}.runtime-replay.json"
        write_session_replay_json(session, replay_file)
        replay_refs.append(
            {
                "scenarioId": result.scenario_id,
                "path": str(replay_file),
                "sessionStatus": result.session_status,
            }
        )

    return replay_refs


def create_promotion_record_artifact(
    artifact_directory: str | Path,
    target_environment: str,
    approvers: list[str],
    replay_output_directory: str | Path | None = None,
    planner_factory: Callable[[], Planner] | None = None,
    execution_router_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    summary, _sessions = evaluate_scenario_pack(
        artifact_directory,
        planner_factory=planner_factory,
        execution_router_factory=execution_router_factory,
    )
    artifacts = load_artifact_bundle(artifact_directory)
    runtime_replay_refs = (
        write_eval_pack_replays(
            artifact_directory,
            replay_output_directory,
            planner_factory=planner_factory,
            execution_router_factory=execution_router_factory,
        )
        if replay_output_directory
        else []
    )
    evidence = build_promotion_evidence(
        artifact_directory,
        target_environment,
        summary,
        runtime_replay_refs=runtime_replay_refs,
    )

    target_decision = "approved" if summary.meets_expectations else "held"
    source_environment = artifacts.agent_spec.get("environmentContract", {}).get("defaultEnvironment", "sandbox")

    return {
        "artifactType": "promotion-record",
        "schemaVersion": "1.0.0",
        "artifactId": f"promo_{artifacts.agent_spec['artifactId']}_{target_environment.replace('-', '_')}",
        "artifactVersion": "0.1.0",
        "artifactSetId": artifacts.agent_spec["artifactSetId"],
        "title": f"Promotion Record for {artifacts.agent_spec['title']}",
        "generator": {
            "name": "aether-forge",
            "version": "0.1.0",
            "inputDigest": f"sha256:{artifacts.agent_spec['artifactSetId']}:promotion:{target_environment}",
        },
        "compatibility": {
            "status": "backward-compatible",
            "previousArtifactVersion": None,
            "migrationRef": None,
        },
        "provenance": {
            "createdAt": evidence["generatedAt"],
            "sourceMode": "manual",
        },
        "artifactRefs": evidence["artifactRefs"],
        "evaluationSummary": evidence["evaluationSummary"],
        "promotionDecision": {
            "sourceEnvironment": source_environment,
            "targetEnvironment": target_environment,
            "decisionOutcome": target_decision,
            "approvers": approvers,
            "policyBundleVersion": artifacts.policy_bundle["artifactVersion"],
            "scenarioPackVersion": artifacts.scenario_pack["artifactVersion"],
            "rolloutLimits": _default_rollout_limits(target_environment),
        },
        "residualRisks": _collect_residual_risks(summary),
        "rolloutPlan": {
            "steps": [f"{target_environment}-review-window"],
            "promotionReady": summary.meets_expectations,
        },
    }


def _default_rollout_limits(target_environment: str) -> dict[str, Any]:
    if target_environment == "paper":
        return {"maxCapitalExposureUsd": 5000, "executionRatePerHour": 10}
    if target_environment == "canary-live":
        return {"maxCapitalExposureUsd": 1000, "executionRatePerHour": 2}
    return {"maxCapitalExposureUsd": 0, "executionRatePerHour": 0}


def _collect_residual_risks(summary: ScenarioPackEvaluationSummary) -> list[dict[str, Any]]:
    residuals: list[dict[str, Any]] = []
    for result in summary.results:
        if result.stage_outcome != "pass":
            residuals.append(
                {
                    "scenarioId": result.scenario_id,
                    "stageOutcome": result.stage_outcome,
                    "blockingReasonIds": result.blocking_reason_ids,
                }
            )
    return residuals


def _find_scenario(artifacts: ArtifactBundle, scenario_id: str) -> dict[str, Any]:
    for scenario in artifacts.scenario_pack.get("scenarios", []):
        if scenario.get("scenarioId") == scenario_id:
            return scenario
    raise ValueError(f"Unknown scenario {scenario_id}")


def _status_to_stage_outcome(status: SessionStatus) -> str:
    if status == SessionStatus.COMPLETE:
        return "pass"
    if status in {SessionStatus.HOLD, SessionStatus.PAUSED}:
        return "hold"
    return "fail"



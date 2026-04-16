from __future__ import annotations

from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from aether_forge.crypto import MockCryptoExecutionRouter
from aether_forge.evals import build_promotion_evidence, evaluate_scenario, evaluate_scenario_pack
from aether_forge.runtime import (
    RuntimeSession,
    SessionStatus,
    StepKind,
    StepProposal,
    export_session_replay,
    hydrate_session_from_replay,
    load_artifact_bundle,
    load_session_replay_json,
    write_session_replay_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def test_baseline_scenario_passes_in_native_runtime() -> None:
    result, session = evaluate_scenario(EXAMPLE_DIR, "scen-baseline-basis-wide")

    assert result.stage_outcome == "pass"
    assert result.session_status == "complete"
    assert session.status == SessionStatus.COMPLETE
    assert len(session.step_ledger) == 3


def test_policy_violation_scenario_holds_on_exposure_limit() -> None:
    result, session = evaluate_scenario(EXAMPLE_DIR, "scen-policy-exposure-breach")

    assert result.stage_outcome == "hold"
    assert result.session_status == "hold"
    assert "exposure-limit" in result.blocking_reason_ids
    assert session.step_ledger[-1].lifecycle.value == "denied"


def test_stress_scenario_holds_on_stale_market_data() -> None:
    result, session = evaluate_scenario(EXAMPLE_DIR, "scen-stale-data-halt")

    assert result.stage_outcome == "hold"
    assert "stale-market-data" in result.blocking_reason_ids
    assert session.step_ledger[-1].lifecycle.value == "denied"


def test_runtime_rejects_undeclared_capabilities() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)

    class BadPlanner:
        def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Try an undeclared capability.",
                    capability_id="cap-not-declared",
                )
            ]

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=BadPlanner(),
        execution_router=MockCryptoExecutionRouter(),
    )

    status = session.run()

    assert status == SessionStatus.FAILED
    assert "not declared" in (session.step_ledger[-1].message or "")


def test_runtime_can_resume_after_manual_approval() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)

    for capability in artifacts.capability_manifest["capabilities"]:
        if capability["capabilityId"] == "cap-exchange-order":
            capability["requiredApproval"] = True

    class ApprovalPlanner:
        def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
            if session.working_set.get("cap-exchange-order"):
                return [
                    StepProposal(
                        kind=StepKind.REASON,
                        description="Order was approved and executed.",
                        payload={"mark_complete": True},
                    )
                ]

            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Attempt an exchange order that requires approval.",
                    capability_id="cap-exchange-order",
                    payload={"requested_notional_usd": 5000},
                )
            ]

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=ApprovalPlanner(),
        execution_router=MockCryptoExecutionRouter(),
    )

    first_status = session.run()
    assert first_status == SessionStatus.HOLD
    assert len(session.pending_approvals) == 1

    resumed = session.approve_pending("approved-token")
    assert resumed is not None

    final_status = session.run()
    assert final_status == SessionStatus.COMPLETE
    assert session.session_state["last_approval_token"] == "approved-token"


def test_eval_pack_summary_and_promotion_evidence() -> None:
    summary, _sessions = evaluate_scenario_pack(EXAMPLE_DIR)

    assert summary.total_scenarios == 4
    assert summary.matched_expectations == 4
    assert summary.meets_expectations is True

    evidence = build_promotion_evidence(EXAMPLE_DIR, "paper", summary)

    assert evidence["promotionReady"] is True
    assert evidence["targetEnvironment"] == "paper"
    assert len(evidence["artifactRefs"]) == 4
    assert evidence["artifactRefs"][2]["artifactType"] == "policy-bundle"


def test_runtime_replay_export_and_hydration_for_held_session() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)

    for capability in artifacts.capability_manifest["capabilities"]:
        if capability["capabilityId"] == "cap-exchange-order":
            capability["requiredApproval"] = True

    class ApprovalPlanner:
        def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
            if session.working_set.get("cap-exchange-order"):
                return [
                    StepProposal(
                        kind=StepKind.REASON,
                        description="Order was approved and executed.",
                        payload={"mark_complete": True},
                    )
                ]
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Attempt an exchange order that requires approval.",
                    capability_id="cap-exchange-order",
                    payload={"requested_notional_usd": 5000},
                )
            ]

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=ApprovalPlanner(),
        execution_router=MockCryptoExecutionRouter(),
    )
    assert session.run() == SessionStatus.HOLD

    replay = export_session_replay(session)
    hydrated = hydrate_session_from_replay(replay, artifacts, ApprovalPlanner(), MockCryptoExecutionRouter())

    assert hydrated.status == SessionStatus.HOLD
    assert len(hydrated.pending_approvals) == 1

    hydrated.approve_pending("hydrated-approval-token")
    assert hydrated.run() == SessionStatus.COMPLETE


def test_cli_replay_file_can_be_loaded() -> None:
    result, session = evaluate_scenario(EXAMPLE_DIR, "scen-baseline-basis-wide")
    assert result.stage_outcome == "pass"

    temp_dir = Path(mkdtemp(prefix="aether-forge-replay-"))
    replay_path = temp_dir / "runtime-replay.json"

    try:
        write_session_replay_json(session, replay_path)
        replay = load_session_replay_json(replay_path)

        assert replay.environment == "sandbox"
        assert replay.session_status == "complete"
        assert len(replay.step_ledger) == 3
    finally:
        rmtree(temp_dir)

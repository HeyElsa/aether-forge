from __future__ import annotations

from pathlib import Path

from aether_forge.crypto import MockCryptoExecutionRouter
from aether_forge.models import StaticPlanningModel
from aether_forge.planner import HeuristicPlanner, PromptDrivenPlanner
from aether_forge.runtime import RuntimeSession, StepKind, load_artifact_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def test_prompt_driven_planner_accepts_valid_declared_capability_steps() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    planner = PromptDrivenPlanner(
        model=StaticPlanningModel(
            '{"steps": ['
            '{"kind": "use-capability", "description": "Read basis.", "capabilityId": "cap-market-basis", "payload": {"basis_bps": 20}},'
            '{"kind": "reason", "description": "Basis read complete.", "payload": {"mark_complete": true}}'
            ']}'
        )
    )
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=HeuristicPlanner(),
        execution_router=MockCryptoExecutionRouter(),
        scenario_inputs={"basisBps": 20},
    )

    proposals = planner.propose_plan(session)

    assert proposals[0].kind == StepKind.USE_CAPABILITY
    assert proposals[0].capability_id == "cap-market-basis"
    assert proposals[1].kind == StepKind.REASON
    assert proposals[1].payload["mark_complete"] is True


def test_prompt_driven_planner_converts_undeclared_capability_to_gap() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    planner = PromptDrivenPlanner(
        model=StaticPlanningModel(
            '{"steps": ['
            '{"kind": "use-capability", "description": "Use undeclared tool.", "capabilityId": "cap-unknown", "payload": {}}'
            ']}'
        )
    )
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=HeuristicPlanner(),
        execution_router=MockCryptoExecutionRouter(),
    )

    proposals = planner.propose_plan(session)

    assert proposals[0].kind == StepKind.REPORT_GAP
    assert proposals[0].payload["requestedCapability"] == "cap-unknown"


def test_prompt_driven_planner_falls_back_when_model_output_is_invalid() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    planner = PromptDrivenPlanner(
        model=StaticPlanningModel("not-json"),
        fallback_planner=HeuristicPlanner(),
    )
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=HeuristicPlanner(),
        execution_router=MockCryptoExecutionRouter(),
        scenario_inputs={"basisBps": 25, "volatilityRegime": "normal"},
    )

    proposals = planner.propose_plan(session)

    assert proposals[0].kind == StepKind.USE_CAPABILITY
    assert proposals[0].capability_id in {"cap-market-btc-price", "cap-market-basis"}

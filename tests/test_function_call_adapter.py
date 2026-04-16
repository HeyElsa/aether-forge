"""Tests for the function-call adapter.

Covers both the translation layer in :mod:`aether_forge.adapters.function_call`
and the end-to-end :class:`FunctionCallPlanner` that wraps a planning model
and parses its JSON output through that translator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from aether_forge.adapters.function_call import (
    FunctionCallResponse,
    FunctionCallTranslator,
    FunctionToolCall,
)
from aether_forge.config import FunctionCallPlanner
from aether_forge.runtime import StepKind

# ---------------------------------------------------------------------------
# Translator layer
# ---------------------------------------------------------------------------

def test_translator_translates_declared_tool_calls() -> None:
    translator = FunctionCallTranslator()

    proposals = translator.translate(
        FunctionCallResponse(
            reasoning="Check basis first, then decide.",
            tool_calls=[FunctionToolCall(name="cap-market-basis", arguments={"basis_bps": 20})],
            final_message="Basis check complete.",
        ),
        declared_capability_ids={"cap-market-basis"},
    )

    assert proposals[0].kind == StepKind.REASON
    assert proposals[1].kind == StepKind.USE_CAPABILITY
    assert proposals[1].capability_id == "cap-market-basis"
    assert proposals[-1].payload["mark_complete"] is True


def test_translator_reports_undeclared_capabilities() -> None:
    translator = FunctionCallTranslator()

    proposals = translator.translate(
        FunctionCallResponse(tool_calls=[FunctionToolCall(name="cap-undeclared", arguments={})]),
        declared_capability_ids={"cap-market-basis"},
    )

    assert proposals[0].kind == StepKind.REPORT_GAP
    assert proposals[0].payload["requestedCapability"] == "cap-undeclared"


def test_translator_can_force_manual_approval_translation() -> None:
    translator = FunctionCallTranslator()

    proposals = translator.translate(
        FunctionCallResponse(
            tool_calls=[FunctionToolCall(name="cap-exchange-order", arguments={"requested_notional_usd": 1000})],
            requires_approval=True,
        ),
        declared_capability_ids={"cap-exchange-order"},
    )

    assert proposals[0].kind == StepKind.REQUEST_APPROVAL


# ---------------------------------------------------------------------------
# End-to-end planner wrapping a mock model
# ---------------------------------------------------------------------------

class _MockModel:
    """Minimal PlanningModel stand-in returning a canned response."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


@dataclass
class _MockArtifacts:
    capability_manifest: dict[str, Any] = field(default_factory=dict)
    agent_spec: dict[str, Any] = field(default_factory=dict)


@dataclass
class _MockSession:
    artifacts: _MockArtifacts = field(default_factory=_MockArtifacts)
    environment: str = "sandbox"
    session_state: dict[str, Any] = field(default_factory=dict)
    working_set: dict[str, Any] = field(default_factory=dict)
    observations: list[Any] = field(default_factory=list)
    step_ledger: list[Any] = field(default_factory=list)
    pending_approvals: list[Any] = field(default_factory=list)
    _step_counter: int = 0
    memory_store: Any = None


def _build_session(declared_caps: list[str]) -> _MockSession:
    manifest = {
        "capabilities": [
            {"capabilityId": cap_id, "kind": "data-source", "description": "test", "riskLevel": "low"}
            for cap_id in declared_caps
        ],
    }
    spec = {
        "objective": {"primaryGoal": "test objective", "nonGoals": []},
        "metadata": {"summary": "test"},
    }
    return _MockSession(
        artifacts=_MockArtifacts(capability_manifest=manifest, agent_spec=spec),
    )


def test_function_call_planner_parses_valid_response() -> None:
    model = _MockModel(
        '{"reasoning": "Fetch price first", '
        '"tool_calls": [{"name": "cap-price", "arguments": {"token": "ETH"}}], '
        '"final_message": "done", "requires_approval": false}'
    )
    planner = FunctionCallPlanner(model=model)
    session = _build_session(["cap-price"])

    proposals = planner.propose_plan(session)

    # Reason + use-capability + final reason(mark_complete=True)
    kinds = [p.kind for p in proposals]
    assert StepKind.REASON in kinds
    assert StepKind.USE_CAPABILITY in kinds
    # Verify the prompt asked for the function-call shape
    assert len(model.prompts) == 1
    assert "reasoning" in model.prompts[0]
    assert "tool_calls" in model.prompts[0]
    assert "final_message" in model.prompts[0]


def test_function_call_planner_strips_markdown_code_fences() -> None:
    model = _MockModel(
        '```json\n'
        '{"reasoning": "bullish", "tool_calls": [{"name": "cap-price"}], "final_message": "done"}\n'
        '```'
    )
    planner = FunctionCallPlanner(model=model)
    session = _build_session(["cap-price"])

    proposals = planner.propose_plan(session)

    assert any(p.kind == StepKind.USE_CAPABILITY for p in proposals)


def test_function_call_planner_falls_back_on_malformed_json(caplog) -> None:
    import logging

    model = _MockModel("this is not json at all")
    planner = FunctionCallPlanner(model=model)
    session = _build_session(["cap-price"])

    with caplog.at_level(logging.WARNING, logger="aether_forge.config"):
        proposals = planner.propose_plan(session)

    # Fallback path — heuristic planner returns at least one proposal
    assert len(proposals) >= 1
    # And the failure was logged, not swallowed silently
    assert any("FunctionCallPlanner failed" in rec.message for rec in caplog.records)



"""Verify provider-native tool-use end-to-end (Sprint 2.1 / FP-1 deepening).

Pins:
- build_tool_schema_from_manifest produces one tool per declared capability
- to_anthropic_tool_schema rewraps OpenAI shape to Anthropic shape
- from_anthropic_tool_use parses mixed text + tool_use blocks
- from_openai_tool_calls parses tool_calls with JSON-string arguments
- from_openai_tool_calls skips malformed arguments gracefully
- AnthropicPlanningModel.complete_with_tools sends correct payload + parses
- OpenAICompatiblePlanningModel.complete_with_tools sends correct payload + parses
- complete_with_tools raises when tools is empty
- PromptDrivenPlanner(tool_mode=True) bypasses string parsing
- PromptDrivenPlanner(tool_mode=True) with a model lacking complete_with_tools
  records the model-error event and falls back to heuristic
- Settings: resolve_planner_settings picks up planner.toolMode from config + env
- Config: tool_mode flows from settings into the planner factory
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.adapters.function_call import (
    FunctionCallResponse,
    FunctionToolCall,
    build_tool_schema_from_manifest,
    from_anthropic_tool_use,
    from_openai_tool_calls,
    to_anthropic_tool_schema,
)
from aether_forge.config import build_planner_factory, resolve_planner_settings
from aether_forge.crypto import MockCryptoExecutionRouter
from aether_forge.models import (
    AnthropicPlanningModel,
    OpenAICompatiblePlanningModel,
    PlanningModelError,
)
from aether_forge.planner import HeuristicPlanner, PromptDrivenPlanner
from aether_forge.runtime import RuntimeSession, StepKind, load_artifact_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


# ---------------------------------------------------------------------------
# build_tool_schema_from_manifest
# ---------------------------------------------------------------------------


def test_build_tool_schema_produces_one_tool_per_capability() -> None:
    manifest = {
        "capabilities": [
            {"capabilityId": "cap-a", "description": "Read A.", "inputSchema": {"type": "object", "properties": {"x": {"type": "number"}}}},
            {"capabilityId": "cap-b", "name": "Cap B fallback"},  # no description, no inputSchema
        ]
    }
    tools = build_tool_schema_from_manifest(manifest)
    assert len(tools) == 2
    assert tools[0]["type"] == "function"
    assert tools[0]["function"]["name"] == "cap-a"
    assert tools[0]["function"]["description"] == "Read A."
    assert tools[0]["function"]["parameters"]["properties"] == {"x": {"type": "number"}}
    # Fallback: no description → name; no inputSchema → empty permissive object
    assert tools[1]["function"]["description"] == "Cap B fallback"
    assert tools[1]["function"]["parameters"]["type"] == "object"


def test_build_tool_schema_skips_capabilities_without_id() -> None:
    manifest = {
        "capabilities": [
            {"description": "missing id"},
            {"capabilityId": "", "description": "empty id"},
            {"capabilityId": "cap-real"},
        ]
    }
    tools = build_tool_schema_from_manifest(manifest)
    assert [t["function"]["name"] for t in tools] == ["cap-real"]


def test_to_anthropic_tool_schema_rewraps_shape() -> None:
    openai_tools = [
        {"type": "function", "function": {"name": "cap-a", "description": "A", "parameters": {"type": "object"}}}
    ]
    anthropic_tools = to_anthropic_tool_schema(openai_tools)
    assert anthropic_tools == [
        {"name": "cap-a", "description": "A", "input_schema": {"type": "object"}}
    ]


# ---------------------------------------------------------------------------
# from_anthropic_tool_use / from_openai_tool_calls
# ---------------------------------------------------------------------------


def test_from_anthropic_tool_use_mixed_blocks() -> None:
    blocks = [
        {"type": "text", "text": "I'll read the basis first."},
        {"type": "tool_use", "id": "toolu_1", "name": "cap-market-basis", "input": {"basis_bps": 25}},
        {"type": "text", "text": "Then decide."},
    ]
    response = from_anthropic_tool_use(blocks)
    assert response.reasoning == "I'll read the basis first.\n\nThen decide."
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "cap-market-basis"
    assert response.tool_calls[0].arguments == {"basis_bps": 25}


def test_from_anthropic_tool_use_handles_empty_blocks() -> None:
    response = from_anthropic_tool_use([])
    assert response.reasoning is None
    assert response.tool_calls == []


def test_from_openai_tool_calls_parses_json_string_arguments() -> None:
    message = {
        "role": "assistant",
        "content": "Reasoning here.",
        "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "cap-a", "arguments": '{"x": 1}'}},
            {"id": "call_2", "type": "function", "function": {"name": "cap-b", "arguments": "{}"}},
        ],
    }
    response = from_openai_tool_calls(message)
    assert response.reasoning == "Reasoning here."
    assert response.tool_calls[0].arguments == {"x": 1}
    assert response.tool_calls[1].arguments == {}


def test_from_openai_tool_calls_skips_malformed_arguments() -> None:
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": "call_bad", "type": "function", "function": {"name": "cap-bad", "arguments": "not-json"}},
            {"id": "call_ok", "type": "function", "function": {"name": "cap-ok", "arguments": "{}"}},
        ],
    }
    response = from_openai_tool_calls(message)
    assert [tc.name for tc in response.tool_calls] == ["cap-ok"]
    assert response.reasoning is None


def test_from_openai_tool_calls_accepts_dict_arguments_directly() -> None:
    """Some OpenAI-compatible servers return arguments as dicts; tolerate both."""
    message = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"id": "c", "type": "function", "function": {"name": "cap-a", "arguments": {"k": "v"}}}
        ],
    }
    response = from_openai_tool_calls(message)
    assert response.tool_calls[0].arguments == {"k": "v"}


# ---------------------------------------------------------------------------
# Provider integration — complete_with_tools
# ---------------------------------------------------------------------------


def test_anthropic_complete_with_tools_sends_correct_payload() -> None:
    captured: dict = {}

    def _fake_request(url, headers, body):
        captured["url"] = url
        captured["payload"] = json.loads(body.decode())
        captured["headers"] = headers
        return {
            "content": [
                {"type": "text", "text": "Plan:"},
                {"type": "tool_use", "id": "toolu_1", "name": "cap-x", "input": {"k": "v"}},
            ]
        }

    model = AnthropicPlanningModel(
        model="claude-sonnet-4-5",
        api_key="sk-ant-test",
        base_url="https://example.invalid",
        request_fn=_fake_request,
    )
    tools = [{"type": "function", "function": {"name": "cap-x", "description": "X", "parameters": {"type": "object"}}}]
    response = model.complete_with_tools("plan please", tools)

    assert captured["url"] == "https://example.invalid/v1/messages"
    assert captured["payload"]["tools"] == [{"name": "cap-x", "description": "X", "input_schema": {"type": "object"}}]
    assert response.reasoning == "Plan:"
    assert response.tool_calls[0].name == "cap-x"


def test_openai_compatible_complete_with_tools_sends_tools_field() -> None:
    captured: dict = {}

    def _fake_request(url, headers, body):
        captured["payload"] = json.loads(body.decode())
        return {
            "choices": [
                {
                    "message": {
                        "content": "ok",
                        "tool_calls": [
                            {"id": "c1", "type": "function", "function": {"name": "cap-y", "arguments": "{}"}}
                        ],
                    }
                }
            ]
        }

    model = OpenAICompatiblePlanningModel(
        model="gpt-4o",
        api_key="sk-openai",
        base_url="https://example.invalid/v1",
        request_fn=_fake_request,
    )
    tools = [{"type": "function", "function": {"name": "cap-y", "description": "Y", "parameters": {"type": "object"}}}]
    response = model.complete_with_tools("plan please", tools)

    assert captured["payload"]["tools"] == tools
    assert captured["payload"]["tool_choice"] == "auto"
    assert response.tool_calls[0].name == "cap-y"


def test_complete_with_tools_raises_on_empty_tools() -> None:
    model = OpenAICompatiblePlanningModel(
        model="gpt-4o",
        api_key="sk-openai",
        base_url="https://example.invalid/v1",
        request_fn=lambda *a, **k: {},
    )
    with pytest.raises(PlanningModelError, match="at least one tool"):
        model.complete_with_tools("plan", [])


# ---------------------------------------------------------------------------
# PromptDrivenPlanner — tool_mode dispatch
# ---------------------------------------------------------------------------


class _StubToolUseModel:
    """Test double — exposes complete_with_tools but not complete()."""

    def __init__(self, response: FunctionCallResponse) -> None:
        self._response = response
        self.received_tools: list[dict] | None = None

    def complete_with_tools(self, prompt: str, tools: list[dict]) -> FunctionCallResponse:
        self.received_tools = tools
        return self._response

    def complete(self, prompt: str) -> str:  # pragma: no cover — must NOT be called
        raise AssertionError("tool_mode=True must not call complete()")


def _fresh_session() -> RuntimeSession:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    return RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=HeuristicPlanner(),  # used as fallback only
        execution_router=MockCryptoExecutionRouter(),
        scenario_inputs={"basisBps": 25},
    )


def test_tool_mode_bypasses_string_parsing() -> None:
    """Round-trip: model returns FunctionCallResponse → translator → proposals.
    String parser must not run, model.complete must not be called."""
    response = FunctionCallResponse(
        reasoning="Read basis",
        tool_calls=[FunctionToolCall(name="cap-market-basis", arguments={"basis_bps": 20})],
    )
    model = _StubToolUseModel(response)
    planner = PromptDrivenPlanner(model=model, tool_mode=True)

    session = _fresh_session()
    proposals = planner.propose_plan(session)

    # Reasoning REASON step + USE_CAPABILITY for the tool call
    kinds = [p.kind for p in proposals]
    assert StepKind.REASON in kinds
    assert StepKind.USE_CAPABILITY in kinds
    use_step = next(p for p in proposals if p.kind == StepKind.USE_CAPABILITY)
    assert use_step.capability_id == "cap-market-basis"
    assert use_step.payload == {"basis_bps": 20}

    # Tools were built from the manifest
    assert model.received_tools is not None
    assert any(t["function"]["name"] == "cap-market-basis" for t in model.received_tools)


def test_tool_mode_undeclared_capability_routes_to_report_gap() -> None:
    response = FunctionCallResponse(
        tool_calls=[FunctionToolCall(name="cap-nonexistent", arguments={})]
    )
    planner = PromptDrivenPlanner(model=_StubToolUseModel(response), tool_mode=True)
    session = _fresh_session()
    proposals = planner.propose_plan(session)
    gap_steps = [p for p in proposals if p.kind == StepKind.REPORT_GAP]
    assert any(p.payload.get("requestedCapability") == "cap-nonexistent" for p in gap_steps)


def test_tool_mode_with_model_lacking_complete_with_tools_records_failure() -> None:
    """A misconfigured model (tool_mode=True but model only has complete) must
    fall back to heuristic AND record the model-error event so it's debuggable."""

    class _LegacyOnlyModel:
        def complete(self, prompt: str) -> str:  # pragma: no cover — must NOT be called by tool_mode path
            return '{"steps": []}'

    planner = PromptDrivenPlanner(model=_LegacyOnlyModel(), tool_mode=True)
    session = _fresh_session()
    proposals = planner.propose_plan(session)
    assert isinstance(proposals, list)

    failure = session.session_state.get("last_planner_parse_failure")
    assert failure is not None
    assert failure["kind"] == "model-error"
    assert "complete_with_tools" in failure["detail"]


def test_tool_mode_empty_response_records_empty_plan() -> None:
    response = FunctionCallResponse(reasoning=None, tool_calls=[])
    planner = PromptDrivenPlanner(model=_StubToolUseModel(response), tool_mode=True)
    session = _fresh_session()
    planner.propose_plan(session)

    failure = session.session_state.get("last_planner_parse_failure")
    assert failure is not None
    assert failure["kind"] == "empty-plan"


def test_tool_mode_model_raise_records_model_error() -> None:
    class _BoomModel:
        def complete_with_tools(self, prompt, tools):
            raise RuntimeError("provider down")

    planner = PromptDrivenPlanner(model=_BoomModel(), tool_mode=True)
    session = _fresh_session()
    planner.propose_plan(session)

    failure = session.session_state.get("last_planner_parse_failure")
    assert failure["kind"] == "model-error"
    assert "provider down" in failure["detail"]


def test_tool_mode_default_off_preserves_legacy_path() -> None:
    """A planner constructed without explicit tool_mode=True keeps the string-
    parsing behavior so existing tests / agents do not regress."""
    from aether_forge.models import StaticPlanningModel

    planner = PromptDrivenPlanner(
        model=StaticPlanningModel(
            '{"steps": [{"kind": "reason", "description": "ok", "payload": {"mark_complete": true}}]}'
        )
    )
    assert planner.tool_mode is False
    session = _fresh_session()
    proposals = planner.propose_plan(session)
    assert proposals[0].kind == StepKind.REASON


# ---------------------------------------------------------------------------
# Settings + factory integration
# ---------------------------------------------------------------------------


def test_resolve_planner_settings_picks_up_tool_mode_from_config() -> None:
    config = {"planner": {"mode": "anthropic", "toolMode": True}}
    settings = resolve_planner_settings(config=config, mode="anthropic", api_key="sk", model="m")
    assert settings.tool_mode is True


def test_resolve_planner_settings_env_var_overrides_config(monkeypatch) -> None:
    monkeypatch.setenv("AETHER_FORGE_PLANNER_TOOL_MODE", "0")
    config = {"planner": {"mode": "anthropic", "toolMode": True}}
    settings = resolve_planner_settings(config=config, mode="anthropic", api_key="sk", model="m")
    # env var "0" → falsy → tool_mode False even though config has true
    assert settings.tool_mode is False


def test_resolve_planner_settings_defaults_to_false() -> None:
    settings = resolve_planner_settings(mode="anthropic", api_key="sk", model="m")
    assert settings.tool_mode is False


def test_planner_factory_threads_tool_mode_into_anthropic_planner() -> None:
    settings = resolve_planner_settings(mode="anthropic", api_key="sk", model="m", config={"planner": {"toolMode": True}})
    factory = build_planner_factory(settings)
    planner = factory()
    assert isinstance(planner, PromptDrivenPlanner)
    assert planner.tool_mode is True


def test_planner_factory_threads_tool_mode_into_openai_compatible_planner() -> None:
    settings = resolve_planner_settings(
        mode="openai-compatible",
        api_key="sk",
        model="m",
        base_url="https://example.invalid/v1",
        config={"planner": {"toolMode": True}},
    )
    factory = build_planner_factory(settings)
    planner = factory()
    assert isinstance(planner, PromptDrivenPlanner)
    assert planner.tool_mode is True

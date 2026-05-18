"""Function-call adapter boundary for the Aether Forge native runtime.

This module defines the translation contract from a JSON function-call style
planning response into native Aether `StepProposal` objects. The shape it
expects from the model is::

    {
      "reasoning": "...",              # optional free-text reasoning
      "tool_calls": [                   # zero or more tool invocations
        {"name": "capability-id", "arguments": {...}}
      ],
      "final_message": "...",          # optional wrap-up message
      "requires_approval": false        # flips tool calls to approval gate
    }

Works with any OpenAI-compatible model that produces JSON in this shape —
models fine-tuned for structured tool use (Hermes-3, Qwen function-calling
variants, Llama 3 tool-calling models) as well as capable general models
(Claude, GPT-4) when instructed to emit strict JSON.

v0.22.0 (FP-1 deepening) adds provider-native tool-use support: the helpers
:func:`build_tool_schema_from_manifest`, :func:`from_anthropic_tool_use`, and
:func:`from_openai_tool_calls` let :class:`PromptDrivenPlanner` bypass JSON
string-parsing entirely when ``tool_mode=True`` and the model speaks the
provider-native tool-use protocol (Anthropic ``tool_use`` content blocks,
OpenAI ``tool_calls`` on the message). Opt-in via ``aether-forge.json``:
``planner.toolMode = true``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from ..runtime import StepKind, StepProposal

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class FunctionToolCall:
    """A single tool invocation extracted from a model's function-call response."""

    name: str
    arguments: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class FunctionCallResponse:
    """Structured shape of a JSON function-call planning response.

    All fields are optional and fall back to empty/default values when the
    model omits them. The translator (see :class:`FunctionCallTranslator`)
    converts this into a list of native Aether step proposals.
    """

    reasoning: str | None = None
    tool_calls: list[FunctionToolCall] = field(default_factory=list)
    final_message: str | None = None
    requires_approval: bool = False


class FunctionCallTranslator:
    """Normalize function-call-style planner output into native Aether steps.

    The translator:

    - Emits a ``REASON`` step for the model's leading reasoning string
    - Validates each tool call against the set of declared capability ids
      and emits ``REPORT_GAP`` for any undeclared capability
    - Emits ``USE_CAPABILITY`` or ``REQUEST_APPROVAL`` for each valid call
    - Emits a trailing ``REASON`` step with ``mark_complete=True`` when the
      model provides a final message
    - Falls back to a single ``REPORT_GAP`` step when the response contains
      nothing actionable
    """

    def __init__(self, max_plan_steps: int = 5) -> None:
        self.max_plan_steps = max_plan_steps

    def translate(
        self,
        response: FunctionCallResponse,
        declared_capability_ids: set[str],
    ) -> list[StepProposal]:
        proposals: list[StepProposal] = []

        if response.reasoning:
            proposals.append(
                StepProposal(
                    kind=StepKind.REASON,
                    description=response.reasoning,
                    payload={"mark_complete": False},
                )
            )

        for tool_call in response.tool_calls[: self.max_plan_steps]:
            if tool_call.name not in declared_capability_ids:
                proposals.append(
                    StepProposal(
                        kind=StepKind.REPORT_GAP,
                        description=f"Planner proposed undeclared capability {tool_call.name}.",
                        payload={"requestedCapability": tool_call.name},
                    )
                )
                continue

            kind = StepKind.REQUEST_APPROVAL if response.requires_approval else StepKind.USE_CAPABILITY
            proposals.append(
                StepProposal(
                    kind=kind,
                    description=f"Execute capability {tool_call.name}.",
                    capability_id=tool_call.name,
                    payload=dict(tool_call.arguments),
                )
            )

        if response.final_message:
            proposals.append(
                StepProposal(
                    kind=StepKind.REASON,
                    description=response.final_message,
                    payload={"mark_complete": True},
                )
            )

        if not proposals:
            proposals.append(
                StepProposal(
                    kind=StepKind.REPORT_GAP,
                    description="Planner response did not contain any actionable plan elements.",
                    payload={"source": "function-call-adapter"},
                )
            )

        return proposals


# ---------------------------------------------------------------------------
# Provider-native tool-use helpers (v0.22.0 / FP-1 deepening)
# ---------------------------------------------------------------------------


def build_tool_schema_from_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    """Project an Aether Forge capability-manifest into provider tool definitions.

    The output shape is OpenAI-tool-use shape::

        [{"type": "function",
          "function": {"name": "cap-id", "description": "…",
                       "parameters": {"type": "object", "properties": {...}}}}, ...]

    Anthropic's tool-use shape only differs in the wrapper (``{name, description,
    input_schema}`` vs ``{type: "function", function: {name, description, parameters}}``)
    — :func:`to_anthropic_tool_schema` adapts the OpenAI shape to Anthropic on
    the way out. Every declared capability becomes one tool. Capabilities
    without an explicit ``inputSchema`` field get an empty ``{"type": "object",
    "properties": {}}`` so the provider doesn't reject the call.
    """
    tools: list[dict[str, Any]] = []
    capabilities = manifest.get("capabilities", []) if isinstance(manifest, dict) else []
    for capability in capabilities:
        if not isinstance(capability, dict):
            continue
        capability_id = capability.get("capabilityId")
        if not isinstance(capability_id, str) or not capability_id:
            continue
        description = capability.get("description") or capability.get("name") or capability_id
        input_schema = capability.get("inputSchema")
        if not isinstance(input_schema, dict):
            input_schema = {"type": "object", "properties": {}, "additionalProperties": True}
        tools.append({
            "type": "function",
            "function": {
                "name": capability_id,
                "description": description,
                "parameters": input_schema,
            },
        })
    return tools


def to_anthropic_tool_schema(openai_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert OpenAI-shaped tool definitions to Anthropic's ``tool_use`` shape."""
    converted: list[dict[str, Any]] = []
    for entry in openai_tools:
        fn = entry.get("function") if isinstance(entry, dict) else None
        if not isinstance(fn, dict) or "name" not in fn:
            continue
        converted.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
        })
    return converted


def from_anthropic_tool_use(content_blocks: list[dict[str, Any]]) -> FunctionCallResponse:
    """Convert Anthropic Messages API ``content`` blocks into a FunctionCallResponse.

    Anthropic returns ``content`` as a list of mixed-type blocks::

        [{"type": "text", "text": "Let me check the basis first."},
         {"type": "tool_use", "id": "toolu_…", "name": "cap-market-basis",
          "input": {"basis_bps": 25}}]

    Text blocks concatenate into ``reasoning``; ``tool_use`` blocks become
    :class:`FunctionToolCall` entries. The translator downstream maps them to
    native ``StepProposal`` objects, validating against the declared capability
    set. Blocks of unknown type are logged and skipped.
    """
    reasoning_parts: list[str] = []
    tool_calls: list[FunctionToolCall] = []
    for block in content_blocks or []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text":
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                reasoning_parts.append(text.strip())
        elif block_type == "tool_use":
            name = block.get("name")
            if not isinstance(name, str) or not name:
                continue
            raw_input = block.get("input")
            arguments = raw_input if isinstance(raw_input, dict) else {}
            tool_calls.append(FunctionToolCall(name=name, arguments=dict(arguments)))
        else:
            logger.debug("Unknown Anthropic content block type %r; skipping", block_type)
    reasoning = "\n\n".join(reasoning_parts) if reasoning_parts else None
    return FunctionCallResponse(reasoning=reasoning, tool_calls=tool_calls)


def from_openai_tool_calls(message: dict[str, Any]) -> FunctionCallResponse:
    """Convert an OpenAI chat-completions ``message`` into a FunctionCallResponse.

    Expects the OpenAI tool-use response shape::

        {"role": "assistant",
         "content": "Optional reasoning text or null",
         "tool_calls": [
             {"id": "call_…", "type": "function",
              "function": {"name": "cap-id", "arguments": "{\"key\": \"value\"}"}}
         ]}

    ``arguments`` is a *string* in the OpenAI protocol — we parse it as JSON.
    Failures on individual tool calls (malformed JSON, missing name) are
    skipped with a warning rather than failing the whole batch, so a partial
    response still produces some proposals.
    """
    if not isinstance(message, dict):
        return FunctionCallResponse()
    raw_reasoning = message.get("content")
    reasoning = raw_reasoning.strip() if isinstance(raw_reasoning, str) and raw_reasoning.strip() else None
    tool_calls: list[FunctionToolCall] = []
    for tc in message.get("tool_calls", []) or []:
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        if not isinstance(name, str) or not name:
            continue
        raw_arguments = fn.get("arguments")
        arguments: dict[str, Any]
        if isinstance(raw_arguments, dict):
            arguments = dict(raw_arguments)
        elif isinstance(raw_arguments, str):
            try:
                parsed = json.loads(raw_arguments) if raw_arguments else {}
            except json.JSONDecodeError:
                logger.warning("OpenAI tool call %r had unparseable arguments JSON; skipping", name)
                continue
            arguments = parsed if isinstance(parsed, dict) else {}
        else:
            arguments = {}
        tool_calls.append(FunctionToolCall(name=name, arguments=arguments))
    return FunctionCallResponse(reasoning=reasoning, tool_calls=tool_calls)

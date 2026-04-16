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
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..runtime import StepKind, StepProposal


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

"""Reusable planner implementations for the native Aether Forge runtime."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger(__name__)

from .memory import MemoryQuery
from .models import error_body_preview
from .prompting import build_planning_prompt_from_session
from .runtime import RuntimeSession, StepKind, StepProposal

# Fenced-code-block opener: ``` optionally followed by a language tag like
# ```json on the same line. Used by ``_extract_json`` to strip the most common
# LLM wrapping pattern before trying ``json.loads``.
_FENCE_OPEN_RE = re.compile(r"^```[a-zA-Z0-9_-]*\s*\n?")
_FENCE_CLOSE_RE = re.compile(r"\n?```\s*$")


class PlannerParseError(ValueError):
    """Raised by ``_extract_json`` when no valid JSON object/array can be
    recovered from a planning-model response. The runtime treats this as a
    *labeled* fallback signal: the parse failure is recorded on the session's
    ``session_state["last_planner_parse_failure"]`` before the heuristic
    planner takes over, so an operator can grep replays for silent regressions.
    """


def _extract_json(response: str) -> Any:
    """Recover a JSON object/array from a (possibly noisy) LLM response.

    Handles, in order:

    1. Surrounding whitespace and a single ```/```json fence pair.
    2. ``json.loads`` on the cleaned string (the happy path).
    3. Balanced-brace scan for the largest top-level ``{...}`` or ``[...]``
       slice that parses — recovers from reasoning preambles
       ("Let me think… {…}"), trailing prose, or extra commentary.

    Raises ``PlannerParseError`` if nothing parses. Returns the parsed
    Python value (dict, list, or scalar) on success.
    """
    if not isinstance(response, str) or not response.strip():
        raise PlannerParseError("planner response was empty or non-string")

    clean = _FENCE_OPEN_RE.sub("", response.strip(), count=1)
    clean = _FENCE_CLOSE_RE.sub("", clean).strip()

    try:
        return json.loads(clean)
    except json.JSONDecodeError:
        pass

    candidate = _largest_balanced_json(clean)
    if candidate is not None:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    raise PlannerParseError("could not recover JSON object or array from planner response")


def _largest_balanced_json(text: str) -> str | None:
    """Return the longest substring of ``text`` that looks like a balanced
    JSON object or array. Linear scan — keeps the outermost object/array
    whose braces close cleanly, ignoring brace-like characters inside strings.

    Used by :func:`_extract_json` as a recovery path when ``json.loads`` on
    the cleaned string fails because of a reasoning preamble or trailing
    prose. Returns ``None`` if no balanced span is found.
    """
    best: tuple[int, int] | None = None
    stack: list[tuple[str, int]] = []
    in_string = False
    escape = False
    for index, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch in "{[":
            stack.append((ch, index))
        elif ch in "}]":
            if not stack:
                continue
            opener, opener_index = stack.pop()
            matches = (opener == "{" and ch == "}") or (opener == "[" and ch == "]")
            if not matches:
                continue
            if not stack:  # closed the outermost open
                span = (opener_index, index + 1)
                if best is None or (span[1] - span[0]) > (best[1] - best[0]):
                    best = span
    if best is None:
        return None
    return text[best[0] : best[1]]


class PlanningModel(Protocol):
    """A text-completion backend used by :class:`PromptDrivenPlanner`.

    The runtime hands the model a fully assembled planning prompt (objective,
    environment, declared capabilities, runtime state, memory, knowledge) and
    expects raw text back. The text must contain a JSON object with a
    ``"steps"`` array — the planner parses, validates, and translates it into
    typed ``StepProposal`` objects. Models that emit invalid or undeclared
    capabilities are tolerated: the planner falls back to a heuristic plan.

    Canonical signature: ``complete(planning_prompt: str) -> str``.

    Minimum viable implementation::

        class StaticModel:
            def __init__(self, response: str) -> None:
                self.response = response
            def complete(self, planning_prompt: str) -> str:
                return self.response

    Reference implementation: :class:`aether_forge.StaticPlanningModel`
    (deterministic tests). Provider implementations are
    :class:`aether_forge.AnthropicPlanningModel`,
    :class:`aether_forge.OpenAICompatiblePlanningModel` (covers OpenAI,
    Ollama, OpenRouter, and any compatible endpoint), and
    :class:`aether_forge.GeminiPlanningModel`.
    """

    def complete(self, planning_prompt: str) -> str: ...


@dataclass(slots=True)
class PromptDrivenPlanner:
    """Planner that asks an external model for typed next steps.

    This planner stays inside the native runtime contract. Model output is only
    advisory and must translate into bounded native step proposals. Any invalid
    or unsafe response falls back to the native heuristic planner.

    ``tool_mode`` (v0.22.0 / FP-1 deepening): when True and the wrapped model
    exposes ``complete_with_tools(prompt, tools)``, the planner skips string
    parsing entirely and uses the provider-native tool-use protocol
    (Anthropic ``tool_use`` content blocks, OpenAI ``tool_calls``). The
    capability-manifest is projected to tool definitions via
    :func:`adapters.function_call.build_tool_schema_from_manifest`. Default
    False — opt in via ``aether-forge.json:planner.toolMode``.
    """

    model: PlanningModel
    fallback_planner: HeuristicPlanner | None = None
    max_plan_steps: int = 5
    tool_mode: bool = False

    def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
        declared_capability_ids = _declared_capability_ids(session)

        # Tool-mode short-circuits the JSON-string parser. The branch is
        # isolated so the legacy string path stays unchanged for back-compat.
        if self.tool_mode:
            return self._propose_plan_tool_mode(session, declared_capability_ids)

        prompt = build_planning_prompt_from_session(session, declared_capability_ids)

        response: str | None = None
        try:
            response = self.model.complete(prompt)
        except Exception as error:
            error_body = error_body_preview(error)
            self._record_planner_failure(
                session, kind="model-error", detail=repr(error), response=error_body
            )
            logger.warning(
                "Prompt-driven planner model raised, falling back to heuristic%s",
                f" — provider said: {error_body.splitlines()[0][:160]}" if error_body else "",
            )
            return self._fallback(session)

        try:
            proposals = self._parse_response(response, declared_capability_ids)
        except PlannerParseError as error:
            self._record_planner_failure(session, kind="parse-failure", detail=str(error), response=response)
            logger.warning("Prompt-driven planner could not parse response, falling back to heuristic")
            return self._fallback(session)
        except Exception as error:
            self._record_planner_failure(session, kind="parse-exception", detail=repr(error), response=response)
            logger.warning("Prompt-driven planner raised on parse, falling back to heuristic")
            return self._fallback(session)

        if proposals:
            logger.debug("Planner proposed %d steps", len(proposals))
            return proposals

        # Parsed cleanly but produced no actionable steps (e.g. ``{"steps": []}``).
        # Distinct from a parse failure — record it separately so operators can
        # tell "model returned empty plan" from "model returned garbage."
        self._record_planner_failure(session, kind="empty-plan", detail=None, response=response)
        return self._fallback(session)

    def _propose_plan_tool_mode(
        self,
        session: RuntimeSession,
        declared_capability_ids: set[str],
    ) -> list[StepProposal]:
        """Provider-native tool-use path. Falls back to heuristic on any error,
        recording the failure kind on session.session_state just like the
        legacy string path."""
        from .adapters.function_call import (
            FunctionCallTranslator,
            build_tool_schema_from_manifest,
        )

        if not hasattr(self.model, "complete_with_tools"):
            self._record_planner_failure(
                session,
                kind="model-error",
                detail=f"tool_mode=True but model {type(self.model).__name__} lacks complete_with_tools",
                response=None,
            )
            logger.warning(
                "tool_mode=True but model lacks complete_with_tools; falling back to heuristic"
            )
            return self._fallback(session)

        tools = build_tool_schema_from_manifest(session.artifacts.capability_manifest)
        prompt = build_planning_prompt_from_session(session, declared_capability_ids)

        try:
            response = self.model.complete_with_tools(prompt, tools)  # type: ignore[attr-defined]
        except Exception as error:
            error_body = error_body_preview(error)
            self._record_planner_failure(
                session, kind="model-error", detail=repr(error), response=error_body
            )
            logger.warning(
                "Tool-mode planner model raised, falling back to heuristic%s",
                f" — provider said: {error_body.splitlines()[0][:160]}" if error_body else "",
            )
            return self._fallback(session)

        translator = FunctionCallTranslator(max_plan_steps=self.max_plan_steps)
        proposals = translator.translate(response, declared_capability_ids)

        # Translator always returns at least one proposal (a REPORT_GAP when
        # nothing actionable). Detect the empty-plan case explicitly so the
        # failure event is recorded the same way as the string path.
        actionable = any(
            p.kind != StepKind.REPORT_GAP or "Planner response did not contain" not in p.description
            for p in proposals
        )
        if not actionable:
            self._record_planner_failure(
                session,
                kind="empty-plan",
                detail="tool-mode response contained no tool_calls",
                response=None,
            )
            return self._fallback(session)

        return proposals

    @staticmethod
    def _record_planner_failure(
        session: RuntimeSession,
        *,
        kind: str,
        detail: str | None,
        response: str | None,
    ) -> None:
        """Stash a structured fallback event on ``session.session_state`` so the
        replay / step ledger can surface why heuristic took over. ``response``
        is truncated to 500 chars to avoid bloating the replay JSON.
        """
        truncated = response if response is None or len(response) <= 500 else f"{response[:500]}…"
        session.session_state["last_planner_parse_failure"] = {
            "kind": kind,
            "detail": detail,
            "responsePreview": truncated,
            "recordedAt": datetime.now(UTC).isoformat(),
        }

    def _parse_response(self, response: str, declared_capability_ids: set[str]) -> list[StepProposal]:
        payload = _extract_json(response)

        raw_steps = payload.get("steps") if isinstance(payload, dict) else payload
        if not isinstance(raw_steps, list):
            return []

        proposals: list[StepProposal] = []
        for raw_step in raw_steps[: self.max_plan_steps]:
            if not isinstance(raw_step, dict):
                continue

            raw_kind = raw_step.get("kind")
            description = raw_step.get("description")
            if not isinstance(raw_kind, str) or not isinstance(description, str) or not description.strip():
                continue

            try:
                kind = StepKind(raw_kind)
            except ValueError:
                continue

            capability_id = raw_step.get("capabilityId") or raw_step.get("capability_id")
            payload = raw_step.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            if kind in {StepKind.USE_CAPABILITY, StepKind.REQUEST_APPROVAL}:
                if not isinstance(capability_id, str):
                    continue
                if capability_id not in declared_capability_ids:
                    proposals.append(
                        StepProposal(
                            kind=StepKind.REPORT_GAP,
                            description=f"Planner proposed undeclared capability {capability_id}.",
                            payload={"requestedCapability": capability_id},
                        )
                    )
                    continue

            proposals.append(
                StepProposal(
                    kind=kind,
                    description=description.strip(),
                    capability_id=capability_id if isinstance(capability_id, str) else None,
                    payload=payload,
                )
            )

        return proposals

    def _fallback(self, session: RuntimeSession) -> list[StepProposal]:
        fallback = self.fallback_planner or HeuristicPlanner()
        return fallback.propose_plan(session)


@dataclass(slots=True)
class HeuristicPlanner:
    """A small native planner that stays inside declared capabilities.

    It is deliberately simple: inspect explicit runtime state, propose a short
    horizon plan, and let policy/runtime decide what is executable.
    """

    def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
        if session.session_state.get("goal_satisfied"):
            return []

        inputs = session.session_state.get("scenario_inputs", {})
        capabilities = {
            capability["capabilityId"]: capability
            for capability in session.artifacts.capability_manifest.get("capabilities", [])
            if "capabilityId" in capability
        }
        working_set = session.working_set

        # Early-step memory hydration: if the session has a memory store with
        # records and we have not yet executed a memory.read step, propose one
        # first so downstream planning has access to persistent context.
        if session._step_counter < 3 and hasattr(session, "memory_store") and session.memory_store is not None:
            already_read = any(
                entry.proposal.capability_id == "memory.read"
                for entry in session.step_ledger
            )
            if not already_read and session.memory_store.read(MemoryQuery(limit=1)):
                current_environment = session.artifacts.agent_spec.get(
                    "environmentContract", {}
                ).get("currentEnvironment", "sandbox")
                return [
                    StepProposal(
                        kind=StepKind.USE_CAPABILITY,
                        description="Load persistent memory context for the current session.",
                        capability_id="memory.read",
                        payload={"scope": "session", "environment": current_environment},
                    )
                ]

        if "cap-context-read" in capabilities and "cap-context-read" not in working_set:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Read declared project context.",
                    capability_id="cap-context-read",
                ),
                StepProposal(
                    kind=StepKind.REASON,
                    description="Summarize the gathered context into the current goal state.",
                    payload={"mark_complete": True},
                ),
            ]

        if "requestedNotionalUsd" in inputs and "cap-exchange-order" in capabilities and "cap-exchange-order" not in working_set:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Attempt the requested hedge order.",
                    capability_id="cap-exchange-order",
                    payload={"requested_notional_usd": inputs["requestedNotionalUsd"]},
                )
            ]

        if "marketDataAgeMs" in inputs and "cap-market-btc-price" in capabilities and "cap-market-btc-price" not in working_set:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Read BTC spot price using the current market data snapshot.",
                    capability_id="cap-market-btc-price",
                    payload={"market_data_age_ms": inputs["marketDataAgeMs"]},
                )
            ]

        if "basisBps" in inputs and "cap-market-basis" in capabilities and "cap-market-basis" not in working_set:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Read current BTC perp basis.",
                    capability_id="cap-market-basis",
                    payload={
                        "basis_bps": inputs["basisBps"],
                        "volatility_regime": inputs.get("volatilityRegime", "normal"),
                    },
                )
            ]

        if "cap-market-btc-price" in capabilities and "cap-market-btc-price" not in working_set:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Read current BTC spot price.",
                    capability_id="cap-market-btc-price",
                    payload={"market_data_age_ms": inputs.get("marketDataAgeMs", 0)},
                )
            ]

        if "cap-market-basis" in capabilities and "cap-market-basis" not in working_set:
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Read current BTC perp basis.",
                    capability_id="cap-market-basis",
                    payload={
                        "basis_bps": inputs.get("basisBps", 0),
                        "volatility_regime": inputs.get("volatilityRegime", "normal"),
                    },
                )
            ]

        if inputs.get("volatilityRegime") == "spike":
            return [
                StepProposal(
                    kind=StepKind.REASON,
                    description="Recommend unwind instead of carry due to volatility spike.",
                    payload={"mark_complete": True},
                )
            ]

        if "cap-exchange-order" in working_set:
            return [
                StepProposal(
                    kind=StepKind.REASON,
                    description="Order attempt completed under governed execution.",
                    payload={"mark_complete": True},
                )
            ]

        if "cap-market-basis" in working_set or "cap-context-read" in working_set:
            return [
                StepProposal(
                    kind=StepKind.REASON,
                    description="Assess that the current plan is complete under sandbox constraints.",
                    payload={"mark_complete": True},
                )
            ]

        return [
            StepProposal(
                kind=StepKind.REPORT_GAP,
                description="No declared capability path can progress the current session.",
                payload={"availableCapabilities": sorted(capabilities.keys())},
            )
        ]
def _declared_capability_ids(session: RuntimeSession) -> set[str]:
    return {
        capability["capabilityId"]
        for capability in session.artifacts.capability_manifest.get("capabilities", [])
        if "capabilityId" in capability
    }

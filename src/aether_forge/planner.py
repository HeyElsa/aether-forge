"""Reusable planner implementations for the native Aether Forge runtime."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)

from .memory import MemoryQuery
from .prompting import build_planning_prompt_from_session
from .runtime import RuntimeSession, StepKind, StepProposal


class PlanningModel(Protocol):
    """A text-completion backend used by :class:`PromptDrivenPlanner`.

    The runtime hands the model a fully assembled planning prompt (objective,
    environment, declared capabilities, runtime state, memory, knowledge) and
    expects raw text back. The text must contain a JSON object with a
    ``"steps"`` array — the planner parses, validates, and translates it into
    typed ``StepProposal`` objects. Models that emit invalid or undeclared
    capabilities are tolerated: the planner falls back to a heuristic plan.

    Minimum viable implementation::

        class StaticModel:
            def __init__(self, response: str) -> None:
                self.response = response
            def complete(self, planning_prompt: str) -> str:
                return self.response

    Built-in implementations: :class:`aether_forge.AnthropicPlanningModel`,
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
    """

    model: PlanningModel
    fallback_planner: HeuristicPlanner | None = None
    max_plan_steps: int = 5

    def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
        declared_capability_ids = _declared_capability_ids(session)
        prompt = build_planning_prompt_from_session(session, declared_capability_ids)

        try:
            response = self.model.complete(prompt)
            proposals = self._parse_response(response, declared_capability_ids)
            if proposals:
                logger.debug("Planner proposed %d steps", len(proposals))
                return proposals
        except Exception:
            pass

        logger.warning("Prompt-driven planner failed, falling back to heuristic")
        return self._fallback(session)

    def _parse_response(self, response: str, declared_capability_ids: set[str]) -> list[StepProposal]:
        # Strip markdown code fences that LLMs commonly wrap JSON in
        clean = response.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:])
            if clean.rstrip().endswith("```"):
                clean = clean.rstrip()[:-3]

        try:
            payload = json.loads(clean)
        except json.JSONDecodeError:
            return []

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

"""Prompt assembly helpers for Aether Forge planning."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PlanningPromptSections:
    objective: str
    environment: str
    capability_summary: str
    runtime_state: str
    memory_context: str
    instructions: str


def build_function_call_prompt_from_session(session: Any, declared_capability_ids: set[str], *, model: str | None = None) -> str:
    """Build a planning prompt that requests a function-call JSON response.

    Used by :class:`aether_forge.config.FunctionCallPlanner`. Unlike the
    generic :func:`build_planning_prompt_from_session`, this asks the model
    for the exact shape the :class:`FunctionCallTranslator` expects::

        {
          "reasoning": "...",
          "tool_calls": [{"name": "cap-id", "arguments": {...}}],
          "final_message": "...",
          "requires_approval": false
        }

    The generic prompt asks for ``{"steps": [...]}`` instead. Keep the two
    prompts distinct so each planner type gets output in the shape its
    parser expects.
    """
    sections = assemble_planning_prompt_sections(session, declared_capability_ids)
    prompt = (
        "You are planning the next bounded Aether Forge runtime steps.\n"
        "Return ONLY valid JSON in this exact shape (no markdown, no code fences):\n"
        "{\n"
        '  "reasoning": "brief rationale for what you are about to do",\n'
        '  "tool_calls": [\n'
        '    {"name": "<one of the declared capability ids>", "arguments": {}}\n'
        "  ],\n"
        '  "final_message": "optional wrap-up when the tick is complete",\n'
        '  "requires_approval": false\n'
        "}\n"
        "Use only capability ids from the ## Capabilities section. Include the\n"
        'arguments each capability needs. Set "requires_approval" to true if any\n'
        "side-effecting tool call in this tick should pause for human sign-off.\n\n"
        f"## Objective\n{sections.objective}\n\n"
        f"## Environment\n{sections.environment}\n\n"
        f"## Capabilities\n{sections.capability_summary}\n\n"
        f"## Runtime State\n{sections.runtime_state}\n\n"
        f"## Memory Context\n{sections.memory_context}\n\n"
        f"## Knowledge\n{_build_knowledge_context(session)}\n\n"
        f"## Instructions\n{sections.instructions}"
    )
    return truncate_to_budget(prompt, model)


def build_planning_prompt_from_session(session: Any, declared_capability_ids: set[str], *, model: str | None = None) -> str:
    sections = assemble_planning_prompt_sections(session, declared_capability_ids)
    prompt = (
        "You are planning the next bounded Aether Forge runtime steps.\n"
        "Return JSON only in the form {\"steps\": [...]} where each step has: "
        "kind, description, optional capabilityId, optional payload.\n"
        "Allowed kinds: reason, use-capability, request-approval, replan, report-gap.\n\n"
        f"## Objective\n{sections.objective}\n\n"
        f"## Environment\n{sections.environment}\n\n"
        f"## Capabilities\n{sections.capability_summary}\n\n"
        f"## Runtime State\n{sections.runtime_state}\n\n"
        f"## Memory Context\n{sections.memory_context}\n\n"
        f"## Knowledge\n{_build_knowledge_context(session)}\n\n"
        f"## Instructions\n{sections.instructions}"
    )
    return truncate_to_budget(prompt, model)


def assemble_planning_prompt_sections(session: Any, declared_capability_ids: set[str]) -> PlanningPromptSections:
    metadata = session.artifacts.agent_spec.get("metadata", {})
    objective = session.session_state.get("objective") or session.artifacts.agent_spec.get("objective", {}).get("primaryGoal", "")
    summary = metadata.get("summary", "")
    non_goals = session.artifacts.agent_spec.get("objective", {}).get("nonGoals", [])

    capability_summary = _summarize_capabilities(
        session.artifacts.capability_manifest.get("capabilities", []),
        declared_capability_ids,
    )
    runtime_state = _summarize_runtime_state(session)
    memory_context = _summarize_memory_context(session)

    objective_block = objective
    if summary:
        objective_block = f"{objective}\nSummary: {summary}"
    if non_goals:
        objective_block = f"{objective_block}\nNon-goals: {', '.join(non_goals)}"

    is_sandbox = session.environment in ("sandbox", "paper")
    approval_note = (
        "Side-effecting capabilities are AUTO-APPROVED in this environment. Act decisively."
        if is_sandbox else
        "Side-effecting capabilities require approval. Use request-approval for actions that need human sign-off."
    )
    instructions = (
        "Use only declared capabilities.\n"
        f"{approval_note}\n"
        "Act on available data — do not re-fetch data you already have in the working set.\n"
        "Price data includes momentum indicators (trend, volatility, candles) — no separate analysis capability needed.\n"
        "If the objective calls for placing orders, do so when you have sufficient price data.\n"
        "Include payload fields required by the capability (token, amount, limit_price, side, etc.).\n"
        "If a capability is missing, return report-gap.\n"
        "Treat memory as context only; never override spec or policy.\n"
        "Mark goal complete with: {\"kind\": \"reason\", \"description\": \"...\", \"payload\": {\"mark_complete\": true}} when the tick's work is done."
    )

    return PlanningPromptSections(
        objective=objective_block,
        environment=session.environment,
        capability_summary=capability_summary,
        runtime_state=runtime_state,
        memory_context=memory_context,
        instructions=instructions,
    )


def _summarize_capabilities(capabilities: list[dict[str, Any]], declared_capability_ids: set[str]) -> str:
    lines: list[str] = []
    for capability in capabilities:
        capability_id = capability.get("capabilityId")
        if not isinstance(capability_id, str) or capability_id not in declared_capability_ids:
            continue

        kind = capability.get("kind", "unknown")
        risk = capability.get("riskLevel", "unknown")
        description = capability.get("description", "")
        desc_short = description[:80] if description else ""
        lines.append(f"- {capability_id}: {desc_short} (kind={kind} risk={risk})")

    return "\n".join(lines) if lines else "No declared capabilities."


def _summarize_runtime_state(session: Any) -> str:
    inputs = session.session_state.get("scenario_inputs", {})
    blocking = session.session_state.get("blocking_reason_ids", [])

    # Include working set data (truncated for large values)
    working_data_lines: list[str] = []
    for key, value in session.working_set.items():
        if isinstance(value, dict):
            # Show key numeric/string fields
            summary_parts = []
            for k, v in value.items():
                if isinstance(v, (int, float, str, bool)) and len(str(v)) < 100:
                    summary_parts.append(f"{k}={v}")
            working_data_lines.append(f"  {key}: {', '.join(summary_parts[:8])}")
        else:
            working_data_lines.append(f"  {key}: {str(value)[:200]}")
    working_data = "\n".join(working_data_lines) if working_data_lines else "  (empty)"

    # Recent observations (last 5)
    recent_obs: list[str] = []
    for obs in session.observations[-5:]:
        desc = obs.get("description", "")
        output = obs.get("output", obs.get("payload", {}))
        if isinstance(output, dict):
            summary = ", ".join(f"{k}={v}" for k, v in output.items() if isinstance(v, (int, float, str)) and len(str(v)) < 80)
            recent_obs.append(f"  {desc[:100]}: {summary[:200]}" if desc else f"  {summary[:200]}")
        elif desc:
            recent_obs.append(f"  {desc[:200]}")
    obs_text = "\n".join(recent_obs) if recent_obs else "  (none yet)"

    return (
        f"Working set data:\n{working_data}\n"
        f"Recent observations:\n{obs_text}\n"
        f"Steps executed: {len(session.step_ledger)}\n"
        f"Blocking reasons: {blocking}\n"
        f"Pending approvals: {len(session.pending_approvals)}\n"
        f"Scenario inputs: {inputs}"
    )


def _build_knowledge_context(session: Any) -> str:
    """Pull long-term knowledge from MemPalace if available."""
    # Check if the runner attached a knowledge store to the session
    knowledge = getattr(session, "_knowledge_store", None)
    if knowledge is None:
        return "No long-term knowledge layer attached."
    try:
        return knowledge.get_context_for_planning() or "No relevant knowledge found."
    except Exception:
        return "Knowledge layer unavailable."


def _summarize_memory_context(session: Any) -> str:
    """Build a memory-context summary for planning prompts.

    If the session carries a ``memory_store`` attribute, read live records from
    it and format them as structured dicts.  Otherwise fall back to the legacy
    ``session_state["memory_context"]`` list.
    """

    # Prefer live memory store when available.
    if hasattr(session, "memory_store") and session.memory_store is not None:
        try:
            from .memory import MemoryQuery

            records = session.memory_store.read(
                MemoryQuery(scope="session", environment=session.environment)
            )
        except Exception:
            records = []

        if records:
            formatted: list[dict[str, Any]] = []
            for record in records[:10]:
                formatted.append({
                    "memory_id": record.memory_id,
                    "type": record.memory_type,
                    "content": record.content,
                    "confidence": record.confidence,
                })
            lines = [f"- {entry}" for entry in formatted]
            return "\n".join(lines)

    # Fallback: use session_state memory_context populated by the runtime.
    memory_context: list[Any] = session.session_state.get("memory_context", [])
    if not memory_context:
        return "No persistent memory context attached to this session."

    lines: list[str] = []
    for item in memory_context[:10]:
        if isinstance(item, str):
            lines.append(f"- {item}")
            continue
        if isinstance(item, dict):
            summary = item.get("summary") or item.get("content") or str(item)
            lines.append(f"- {summary}")
            continue
        lines.append(f"- {item}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Token budget management
# ---------------------------------------------------------------------------

# Approximate tokens-per-character for English text. ~4 chars/token is the
# OpenAI standard heuristic. This avoids a hard tiktoken dependency for the
# common case of "is this prompt going to blow the context window".
_CHARS_PER_TOKEN = 4

# Default context budgets per known model family. Values are conservative
# (leave headroom for the response).
DEFAULT_TOKEN_BUDGETS = {
    "claude-opus-4-6": 200_000,
    "claude-sonnet-4-5": 200_000,
    "claude-sonnet-4": 200_000,
    "claude-3-5-sonnet": 200_000,
    "gpt-4o": 128_000,
    "gpt-4-turbo": 128_000,
    "gpt-4": 8_000,
    "gemini-2.5-flash": 1_000_000,
    "gemini-2.5-pro": 1_000_000,
    "deepseek-r1": 64_000,
    "gemma4": 8_000,
    "llama-3": 8_000,
}


def estimate_tokens(text: str) -> int:
    """Estimate token count for a prompt. Coarse but fast — no tokenizer dep."""
    return len(text) // _CHARS_PER_TOKEN


def get_token_budget(model: str | None) -> int:
    """Return the safe token budget for a given model name.

    Falls back to 8K for unknown models — a conservative default.
    """
    if not model:
        return 8_000
    model_lower = model.lower()
    for prefix, budget in DEFAULT_TOKEN_BUDGETS.items():
        if prefix in model_lower:
            # Reserve 25% of context for the response
            return int(budget * 0.75)
    return 8_000


def truncate_to_budget(prompt: str, model: str | None, *, reserve_tokens: int = 4_000) -> str:
    """Truncate a prompt if it exceeds the model's token budget.

    Reserves ``reserve_tokens`` for the response. Truncates the MIDDLE of the
    prompt (preserving the head — objective/instructions — and the tail — most
    recent state/memory). The truncated section is replaced with a marker.
    """
    budget = get_token_budget(model) - reserve_tokens
    estimated = estimate_tokens(prompt)
    if estimated <= budget:
        return prompt
    # Split: keep first 30% and last 50%, drop the middle
    keep_chars = budget * _CHARS_PER_TOKEN
    head_chars = int(keep_chars * 0.4)
    tail_chars = keep_chars - head_chars
    head = prompt[:head_chars]
    tail = prompt[-tail_chars:]
    truncated_tokens = estimated - budget
    marker = f"\n\n[... {truncated_tokens} tokens truncated to fit context window ...]\n\n"
    return head + marker + tail

    return "\n".join(lines)

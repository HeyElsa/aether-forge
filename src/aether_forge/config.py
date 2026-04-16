"""Configuration helpers for Aether Forge CLI/runtime wiring."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .adapters.function_call import (
    FunctionCallResponse,
    FunctionCallTranslator,
    FunctionToolCall,
)
from .models import AnthropicPlanningModel, GeminiPlanningModel, OpenAICompatiblePlanningModel, StaticPlanningModel

logger = logging.getLogger(__name__)

_PROVIDER_DEFAULTS: dict[str, tuple[str, str]] = {
    "openai": ("https://api.openai.com/v1", "openai-compatible"),
    "openrouter": ("https://openrouter.ai/api/v1", "openai-compatible"),
    "ollama": ("http://localhost:11434/v1", "openai-compatible"),
    "anthropic": ("https://api.anthropic.com", "anthropic"),
    "gemini": ("https://generativelanguage.googleapis.com", "gemini"),
}
from .planner import HeuristicPlanner, PlanningModel, PromptDrivenPlanner
from .prompting import (
    build_function_call_prompt_from_session,
)
from .runtime import Planner, RuntimeSession, StepProposal


@dataclass(slots=True)
class PlannerSettings:
    mode: str = "heuristic"
    static_response_file: str | None = None
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    api_key_env: str | None = None


@dataclass(slots=True)
class RuntimeSettings:
    crypto_router: str = "mock"


def load_config_file(config_path: str | Path | None) -> dict[str, Any]:
    if config_path is None:
        return {}

    path = Path(config_path)
    if not path.exists():
        raise ValueError(f"Config file does not exist: {path}")

    payload = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(payload, dict):
        raise ValueError("Config file must contain a top-level JSON object")
    return payload


def discover_default_config_path(artifact_directory: str | Path | None = None) -> Path | None:
    candidates: list[Path] = []
    if artifact_directory is not None:
        artifact_path = Path(artifact_directory)
        candidates.append(artifact_path / "aether-forge.json")
    candidates.append(Path.cwd() / "aether-forge.json")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def resolve_planner_settings(
    *,
    config: dict[str, Any] | None = None,
    mode: str | None = None,
    static_response_file: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
    api_key_env: str | None = None,
) -> PlannerSettings:
    planner_config = config.get("planner", {}) if isinstance(config, dict) else {}

    resolved_api_key_env = api_key_env or os.getenv("AETHER_FORGE_PLANNER_API_KEY_ENV") or planner_config.get("apiKeyEnv")
    resolved_api_key = api_key or os.getenv("AETHER_FORGE_PLANNER_API_KEY") or planner_config.get("apiKey")
    if resolved_api_key is None and resolved_api_key_env:
        resolved_api_key = os.getenv(resolved_api_key_env)

    resolved_mode = mode or os.getenv("AETHER_FORGE_PLANNER_MODE") or planner_config.get("mode", "heuristic")
    resolved_base_url = base_url or os.getenv("AETHER_FORGE_PLANNER_BASE_URL") or planner_config.get("baseUrl")

    # Auto-detect API key from well-known env vars when using named providers.
    _PROVIDER_KEY_ENV = {
        "openrouter": "OPENROUTER_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "openai": "OPENAI_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "google": "GOOGLE_API_KEY",
    }
    if resolved_api_key is None and resolved_mode in _PROVIDER_KEY_ENV:
        resolved_api_key = os.getenv(_PROVIDER_KEY_ENV[resolved_mode])

    # Resolve named provider shortcuts to their backend mode and default base URL.
    if resolved_mode in _PROVIDER_DEFAULTS:
        default_url, backend_mode = _PROVIDER_DEFAULTS[resolved_mode]
        if not resolved_base_url:
            resolved_base_url = default_url
        resolved_mode = backend_mode

    return PlannerSettings(
        mode=resolved_mode,
        static_response_file=static_response_file or os.getenv("AETHER_FORGE_PLANNER_STATIC_RESPONSE_FILE") or planner_config.get("staticResponseFile"),
        model=model or os.getenv("AETHER_FORGE_PLANNER_MODEL") or planner_config.get("model"),
        base_url=resolved_base_url,
        api_key=resolved_api_key,
        api_key_env=resolved_api_key_env,
    )


def resolve_runtime_settings(
    *,
    config: dict[str, Any] | None = None,
    crypto_router: str | None = None,
) -> RuntimeSettings:
    runtime_config = config.get("runtime", {}) if isinstance(config, dict) else {}
    return RuntimeSettings(
        crypto_router=crypto_router or os.getenv("AETHER_FORGE_CRYPTO_ROUTER") or runtime_config.get("cryptoRouter", "mock"),
    )


class FunctionCallPlanner:
    """Planner that calls a model expecting a JSON function-call response.

    The model is asked for the exact shape
    ``{reasoning, tool_calls, final_message, requires_approval}`` via
    :func:`aether_forge.prompting.build_function_call_prompt_from_session`,
    and the response is translated through :class:`FunctionCallTranslator`
    into native step proposals.

    On any parsing error the planner logs a warning and falls back to
    :class:`HeuristicPlanner` so the tick still makes progress.
    """

    def __init__(
        self,
        model: PlanningModel,
        *,
        max_plan_steps: int = 5,
    ) -> None:
        self.model = model
        self.translator = FunctionCallTranslator(max_plan_steps=max_plan_steps)
        self._fallback = HeuristicPlanner()

    def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
        declared_capability_ids = {
            cap["capabilityId"]
            for cap in session.artifacts.capability_manifest.get("capabilities", [])
            if "capabilityId" in cap
        }
        # Use the dedicated function-call prompt — asks for the exact shape
        # the translator below expects, rather than the generic step-list
        # shape used by PromptDrivenPlanner.
        prompt = build_function_call_prompt_from_session(session, declared_capability_ids)

        try:
            raw = self.model.complete(prompt)
            payload = _parse_function_call_payload(raw)
            response = FunctionCallResponse(
                reasoning=payload.get("reasoning"),
                tool_calls=[
                    FunctionToolCall(name=tc["name"], arguments=tc.get("arguments", {}))
                    for tc in payload.get("tool_calls", [])
                    if isinstance(tc, dict) and "name" in tc
                ],
                final_message=payload.get("final_message"),
                requires_approval=payload.get("requires_approval", False),
            )
            proposals = self.translator.translate(response, declared_capability_ids)
            if proposals:
                return proposals
        except Exception as error:
            logger.warning(
                "FunctionCallPlanner failed to parse model response, "
                "falling back to heuristic planner: %s",
                error,
            )

        return self._fallback.propose_plan(session)


def _parse_function_call_payload(raw: str) -> dict[str, Any]:
    """Best-effort extraction of a JSON function-call object from a model response.

    Strips markdown code fences if present, then parses. Raises ValueError on
    anything unparseable so the caller's exception handler can log it.
    """
    text = raw.strip()
    if text.startswith("```"):
        # Strip leading ```json or ``` and trailing ```
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return json.loads(text)


def build_planner_factory(
    settings: PlannerSettings,
    *,
    request_fn: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None,
) -> Callable[[], Planner]:
    if settings.mode == "heuristic":
        return HeuristicPlanner

    if settings.mode == "static":
        if not settings.static_response_file:
            raise ValueError("static planner mode requires a static response file")

        response = Path(settings.static_response_file).read_text(encoding="utf8")
        return lambda: PromptDrivenPlanner(
            model=StaticPlanningModel(response),
            fallback_planner=HeuristicPlanner(),
        )

    if settings.mode == "openai-compatible":
        # Ollama and local endpoints don't require an API key
        is_local = settings.base_url and ("localhost" in settings.base_url or "127.0.0.1" in settings.base_url)
        required_fields: dict[str, str | None] = {"model": settings.model, "base_url": settings.base_url}
        if not is_local:
            required_fields["api_key"] = settings.api_key
        missing = [name for name, value in required_fields.items() if not value]
        if missing:
            missing_display = ", ".join(missing)
            raise ValueError(f"openai-compatible planner mode is missing required settings: {missing_display}")

        return lambda: PromptDrivenPlanner(
            model=OpenAICompatiblePlanningModel(
                model=settings.model or "",
                api_key=settings.api_key or "",
                base_url=settings.base_url or "",
                request_fn=request_fn,
            ),
            fallback_planner=HeuristicPlanner(),
        )

    if settings.mode == "anthropic":
        missing = [
            field_name
            for field_name, value in {
                "model": settings.model,
                "api_key": settings.api_key,
            }.items()
            if not value
        ]
        if missing:
            missing_display = ", ".join(missing)
            raise ValueError(f"anthropic planner mode is missing required settings: {missing_display}")

        return lambda: PromptDrivenPlanner(
            model=AnthropicPlanningModel(
                model=settings.model or "",
                api_key=settings.api_key or "",
                base_url=settings.base_url or "https://api.anthropic.com",
                request_fn=request_fn,
            ),
            fallback_planner=HeuristicPlanner(),
        )

    if settings.mode == "gemini":
        missing = [
            field_name
            for field_name, value in {
                "model": settings.model,
                "api_key": settings.api_key,
            }.items()
            if not value
        ]
        if missing:
            missing_display = ", ".join(missing)
            raise ValueError(f"gemini planner mode is missing required settings: {missing_display}")

        return lambda: PromptDrivenPlanner(
            model=GeminiPlanningModel(
                model=settings.model or "",
                api_key=settings.api_key or "",
                base_url=settings.base_url or "https://generativelanguage.googleapis.com",
                request_fn=request_fn,
            ),
            fallback_planner=HeuristicPlanner(),
        )

    if settings.mode == "function-call":
        # Local endpoints (Ollama, LM Studio, vLLM on localhost) don't need
        # an API key. Matches the openai-compatible branch above.
        is_local = settings.base_url and (
            "localhost" in settings.base_url or "127.0.0.1" in settings.base_url
        )
        required_fields: dict[str, str | None] = {
            "model": settings.model,
            "base_url": settings.base_url,
        }
        if not is_local:
            required_fields["api_key"] = settings.api_key
        missing = [name for name, value in required_fields.items() if not value]
        if missing:
            missing_display = ", ".join(missing)
            raise ValueError(
                f"function-call planner mode is missing required settings: {missing_display}"
            )

        def _function_call_factory() -> FunctionCallPlanner:
            model = OpenAICompatiblePlanningModel(
                model=settings.model or "",
                api_key=settings.api_key or "",
                base_url=settings.base_url or "",
                request_fn=request_fn,
            )
            return FunctionCallPlanner(model=model)

        return _function_call_factory

    raise ValueError(f"Unsupported planner mode: {settings.mode}")

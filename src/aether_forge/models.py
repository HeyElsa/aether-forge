"""Provider-facing planning model abstractions for Aether Forge."""

from __future__ import annotations

import json
import logging
import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC
from typing import Any
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)


class PlanningModelError(RuntimeError):
    pass


# Default retry envelope shared by every built-in PlanningModel. Stdlib-only:
# bounded retries on transient network/5xx/429 errors with jittered exponential
# backoff. Honors HTTP Retry-After when the server provides it. Opt out by
# setting ``retry_attempts=0`` on the model.
_DEFAULT_RETRY_ATTEMPTS = 3
_DEFAULT_BACKOFF_BASE_SECONDS = 0.5
_DEFAULT_BACKOFF_CAP_SECONDS = 8.0
# HTTP status codes that should trigger a retry. 408 = request timeout,
# 425 = too early, 429 = too many requests, 5xx = server error.
_RETRY_HTTP_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})


def _retry_after_seconds(error: HTTPError) -> float | None:
    """Parse the Retry-After header on an HTTPError. Returns ``None`` if the
    header is absent or malformed. Supports both the seconds-int form and
    HTTP-date form (HTTP-date is rare from LLM providers but cheap to handle).
    """
    headers = getattr(error, "headers", None)
    if headers is None:
        return None
    value = headers.get("Retry-After")
    if value is None:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        from datetime import datetime
        from email.utils import parsedate_to_datetime

        when = parsedate_to_datetime(value)
        now = datetime.now(UTC) if when.tzinfo else datetime.utcnow()
        delta = (when - now).total_seconds()
        return max(0.0, delta)
    except (TypeError, ValueError):
        return None


def error_body_preview(error: Exception, *, limit: int = 500) -> str | None:
    """Best-effort body of an HTTP error response, for diagnostics.

    Provider 4xx/5xx bodies usually carry the actionable message ("credit
    balance is too low", "insufficient_quota", "model not found") that the
    status line alone hides — without it, every provider failure collapses
    into an opaque ``HTTPError 400/429``. Returns ``None`` for non-HTTP
    errors, empty bodies, or any read failure; never raises. Note that
    reading consumes the underlying response — callers should treat the
    error as spent afterwards.
    """
    if not isinstance(error, HTTPError):
        return None
    try:
        raw = error.read()
    except Exception:  # noqa: BLE001 — closed/detached file-like ends here
        return None
    if not raw:
        return None
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        return None
    return text if len(text) <= limit else f"{text[:limit]}…"


def _backoff_seconds(attempt: int) -> float:
    """Jittered exponential backoff: base * 2^attempt, capped, ±20% jitter."""
    raw = _DEFAULT_BACKOFF_BASE_SECONDS * (2 ** attempt)
    capped = min(raw, _DEFAULT_BACKOFF_CAP_SECONDS)
    jitter = capped * 0.2 * (random.random() * 2 - 1)
    return max(0.0, capped + jitter)


def _with_retry(
    call: Callable[[], Any],
    *,
    attempts: int,
    sleep: Callable[[float], None] = time.sleep,
) -> Any:
    """Retry ``call()`` up to ``attempts`` times on transient errors.

    Retries on: ``URLError`` (network), ``TimeoutError``, and ``HTTPError``
    whose status is in :data:`_RETRY_HTTP_STATUS`. Honors ``Retry-After`` on
    429/503 responses. Re-raises the last exception when retries are exhausted
    or when an error is not transient.

    Pass ``attempts=0`` (or ``attempts=1``) on the model to disable retries —
    the wrapper still runs ``call`` exactly once.
    """
    total = max(1, attempts)
    last_error: Exception | None = None
    for attempt in range(total):
        try:
            return call()
        except HTTPError as error:
            if error.code not in _RETRY_HTTP_STATUS or attempt == total - 1:
                raise
            wait = _retry_after_seconds(error)
            if wait is None:
                wait = _backoff_seconds(attempt)
            body = error_body_preview(error, limit=160)
            logger.warning(
                "planning model HTTP %s%s; retrying in %.2fs (attempt %d/%d)",
                error.code,
                f" — {body.splitlines()[0]}" if body else "",
                wait,
                attempt + 1,
                total,
            )
            last_error = error
            sleep(wait)
        except (URLError, TimeoutError) as error:
            if attempt == total - 1:
                raise
            wait = _backoff_seconds(attempt)
            logger.warning(
                "planning model network error %s; retrying in %.2fs (attempt %d/%d)",
                type(error).__name__,
                wait,
                attempt + 1,
                total,
            )
            last_error = error
            sleep(wait)
    if last_error is not None:
        raise last_error
    raise PlanningModelError("retry helper exited without invoking the callable")


@dataclass(slots=True)
class StaticPlanningModel:
    response: str

    def complete(self, planning_prompt: str) -> str:
        return self.response


@dataclass(slots=True)
class OpenAICompatiblePlanningModel:
    model: str
    api_key: str
    base_url: str
    temperature: float = 0.0
    request_fn: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None
    # Total attempts (including the first try) when the provider returns a
    # transient error (network, 429, 5xx). Set to 1 to disable retries.
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS

    def complete(self, planning_prompt: str) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": "Return only JSON for bounded next-step planning.",
                },
                {
                    "role": "user",
                    "content": planning_prompt,
                },
            ],
        }
        body = json.dumps(payload).encode("utf8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = self._request(f"{self.base_url.rstrip('/')}/chat/completions", headers, body)

        try:
            return response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as error:
            raise PlanningModelError("Planning model response did not contain a chat completion message.") from error

    def _request(self, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            if self.request_fn is not None:
                return self.request_fn(url, headers, body)
            req = urllib_request.Request(url, data=body, headers=headers, method="POST")
            with urllib_request.urlopen(req) as response:  # noqa: S310 - provider URL is user-configured by design.
                return json.loads(response.read().decode("utf8"))

        return _with_retry(_call, attempts=self.retry_attempts)

    def complete_with_tools(self, planning_prompt: str, tools: list[dict[str, Any]]):
        """Provider-native tool-use path (v0.22.0 / FP-1 deepening).

        Sends the OpenAI ``tools=[…]`` shape and parses the response's
        ``tool_calls`` array into a :class:`FunctionCallResponse` via
        :func:`adapters.function_call.from_openai_tool_calls`. The model is
        instructed to emit zero-or-more tool calls; partial responses are
        tolerated. Falls through to the same retry envelope as ``complete``.

        Empty ``tools`` raises — opting into tool_mode without a manifest is a
        configuration error, not a degenerate-but-valid case.
        """
        from .adapters.function_call import from_openai_tool_calls

        if not tools:
            raise PlanningModelError(
                "complete_with_tools requires at least one tool. "
                "Did the capability-manifest produce zero capabilities?"
            )
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "system",
                    "content": "Plan bounded next steps by calling the provided tools. Avoid free-form prose unless needed for reasoning.",
                },
                {"role": "user", "content": planning_prompt},
            ],
            "tools": tools,
            # Let the model decide whether to call tools — never force a call
            # since the bounded-step planner may legitimately conclude no
            # action is appropriate this tick.
            "tool_choice": "auto",
        }
        body = json.dumps(payload).encode("utf8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = self._request(f"{self.base_url.rstrip('/')}/chat/completions", headers, body)
        try:
            message = response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            raise PlanningModelError(
                "OpenAI tool-use response did not contain a message."
            ) from error
        return from_openai_tool_calls(message)


@dataclass(slots=True)
class AnthropicPlanningModel:
    """Planning model that speaks the Anthropic Messages API natively."""

    model: str
    api_key: str
    base_url: str = "https://api.anthropic.com"
    temperature: float = 0.0
    max_tokens: int = 4096
    request_fn: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS

    def complete(self, planning_prompt: str) -> str:
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": "Return only JSON for bounded next-step planning.",
            "messages": [
                {
                    "role": "user",
                    "content": planning_prompt,
                },
            ],
        }
        body = json.dumps(payload).encode("utf8")
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        response = self._request(f"{self.base_url.rstrip('/')}/v1/messages", headers, body)

        try:
            return response["content"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            raise PlanningModelError("Anthropic response did not contain a text content block.") from error

    def _request(self, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            if self.request_fn is not None:
                return self.request_fn(url, headers, body)
            req = urllib_request.Request(url, data=body, headers=headers, method="POST")
            with urllib_request.urlopen(req) as response:  # noqa: S310
                return json.loads(response.read().decode("utf8"))

        return _with_retry(_call, attempts=self.retry_attempts)

    def complete_with_tools(self, planning_prompt: str, tools: list[dict[str, Any]]):
        """Provider-native tool-use path (v0.22.0 / FP-1 deepening).

        Adapts the OpenAI-shaped tools to Anthropic's ``input_schema`` shape
        via :func:`adapters.function_call.to_anthropic_tool_schema`, sends
        the Messages API ``tools`` field, and parses the response's content
        blocks via :func:`adapters.function_call.from_anthropic_tool_use`.
        Mixed ``text`` + ``tool_use`` blocks both carry information; the
        translator preserves them as ``reasoning`` and ``tool_calls``
        respectively.
        """
        from .adapters.function_call import (
            from_anthropic_tool_use,
            to_anthropic_tool_schema,
        )

        if not tools:
            raise PlanningModelError(
                "complete_with_tools requires at least one tool. "
                "Did the capability-manifest produce zero capabilities?"
            )
        anthropic_tools = to_anthropic_tool_schema(tools)
        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "system": "Plan bounded next steps by calling the provided tools.",
            "messages": [{"role": "user", "content": planning_prompt}],
            "tools": anthropic_tools,
        }
        body = json.dumps(payload).encode("utf8")
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        response = self._request(f"{self.base_url.rstrip('/')}/v1/messages", headers, body)
        try:
            content = response["content"]
        except (KeyError, TypeError) as error:
            raise PlanningModelError(
                "Anthropic tool-use response did not contain content blocks."
            ) from error
        return from_anthropic_tool_use(content)


@dataclass(slots=True)
class GeminiPlanningModel:
    """Planning model that speaks the Google Gemini generateContent API natively."""

    model: str
    api_key: str
    base_url: str = "https://generativelanguage.googleapis.com"
    temperature: float = 0.0
    request_fn: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None
    retry_attempts: int = _DEFAULT_RETRY_ATTEMPTS

    def complete(self, planning_prompt: str) -> str:
        payload = {
            "contents": [
                {
                    "parts": [{"text": planning_prompt}],
                },
            ],
            "systemInstruction": {
                "parts": [{"text": "Return only JSON for bounded next-step planning."}],
            },
            "generationConfig": {
                "temperature": self.temperature,
            },
        }
        body = json.dumps(payload).encode("utf8")
        headers = {
            "content-type": "application/json",
        }
        url = f"{self.base_url.rstrip('/')}/v1beta/models/{self.model}:generateContent?key={self.api_key}"
        response = self._request(url, headers, body)

        try:
            return response["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            raise PlanningModelError("Gemini response did not contain a text part.") from error

    def _request(self, url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        def _call() -> dict[str, Any]:
            if self.request_fn is not None:
                return self.request_fn(url, headers, body)
            req = urllib_request.Request(url, data=body, headers=headers, method="POST")
            with urllib_request.urlopen(req) as response:  # noqa: S310
                return json.loads(response.read().decode("utf8"))

        return _with_retry(_call, attempts=self.retry_attempts)


# ---------------------------------------------------------------------------
# Model discovery
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ModelInfo:
    """Normalized model metadata from any provider."""

    id: str
    name: str
    provider: str
    context_length: int | None = None
    modality: str | None = None
    prompt_price: str | None = None
    completion_price: str | None = None
    parameter_size: str | None = None
    quantization: str | None = None


def list_models(
    provider: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    query: str | None = None,
    request_fn: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
) -> list[ModelInfo]:
    """List available models from a provider.

    Supported providers: ``openrouter``, ``ollama``, ``openai``.
    """
    fetcher = request_fn or _default_get_request
    provider_key = provider.lower()

    if provider_key == "openrouter":
        return _list_openrouter_models(fetcher, api_key=api_key, base_url=base_url, query=query)
    if provider_key == "ollama":
        return _list_ollama_models(fetcher, base_url=base_url, query=query)
    if provider_key == "openai":
        return _list_openai_models(fetcher, api_key=api_key, base_url=base_url, query=query)
    raise ValueError(f"Model listing not supported for provider: {provider}")


def _default_get_request(url: str, headers: dict[str, str]) -> dict[str, Any]:
    req = urllib_request.Request(url, headers=headers, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=15) as resp:  # noqa: S310
            return json.loads(resp.read().decode("utf8"))
    except (URLError, TimeoutError) as error:
        raise PlanningModelError(f"Failed to fetch models from {url}: {error}") from error


def _list_openrouter_models(
    fetcher: Callable,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    query: str | None = None,
) -> list[ModelInfo]:
    url = f"{(base_url or 'https://openrouter.ai/api/v1').rstrip('/')}/models"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = fetcher(url, headers)

    models: list[ModelInfo] = []
    for entry in data.get("data", []):
        model_id = entry.get("id", "")
        name = entry.get("name", model_id)

        if query and query.lower() not in f"{model_id} {name}".lower():
            continue

        pricing = entry.get("pricing", {})
        models.append(ModelInfo(
            id=model_id,
            name=name,
            provider="openrouter",
            context_length=entry.get("context_length"),
            modality=entry.get("architecture", {}).get("modality"),
            prompt_price=pricing.get("prompt"),
            completion_price=pricing.get("completion"),
        ))
    return models


def _list_ollama_models(
    fetcher: Callable,
    *,
    base_url: str | None = None,
    query: str | None = None,
) -> list[ModelInfo]:
    url = f"{(base_url or 'http://localhost:11434').rstrip('/')}/api/tags"
    data = fetcher(url, {})

    models: list[ModelInfo] = []
    for entry in data.get("models", []):
        model_name = entry.get("name", "")
        details = entry.get("details", {})

        if query and query.lower() not in model_name.lower():
            continue

        models.append(ModelInfo(
            id=model_name,
            name=model_name,
            provider="ollama",
            parameter_size=details.get("parameter_size"),
            quantization=details.get("quantization_level"),
        ))
    return models


def _list_openai_models(
    fetcher: Callable,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    query: str | None = None,
) -> list[ModelInfo]:
    url = f"{(base_url or 'https://api.openai.com/v1').rstrip('/')}/models"
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    data = fetcher(url, headers)

    models: list[ModelInfo] = []
    for entry in data.get("data", []):
        model_id = entry.get("id", "")

        if query and query.lower() not in model_id.lower():
            continue

        models.append(ModelInfo(
            id=model_id,
            name=model_id,
            provider="openai",
        ))
    models.sort(key=lambda m: m.id)
    return models

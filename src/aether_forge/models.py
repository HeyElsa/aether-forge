"""Provider-facing planning model abstractions for Aether Forge."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib import request as urllib_request
from urllib.error import URLError


class PlanningModelError(RuntimeError):
    pass


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
        if self.request_fn is not None:
            return self.request_fn(url, headers, body)

        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        with urllib_request.urlopen(req) as response:  # noqa: S310 - provider URL is user-configured by design.
            return json.loads(response.read().decode("utf8"))


@dataclass(slots=True)
class AnthropicPlanningModel:
    """Planning model that speaks the Anthropic Messages API natively."""

    model: str
    api_key: str
    base_url: str = "https://api.anthropic.com"
    temperature: float = 0.0
    max_tokens: int = 4096
    request_fn: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None

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
        if self.request_fn is not None:
            return self.request_fn(url, headers, body)

        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        with urllib_request.urlopen(req) as response:  # noqa: S310
            return json.loads(response.read().decode("utf8"))


@dataclass(slots=True)
class GeminiPlanningModel:
    """Planning model that speaks the Google Gemini generateContent API natively."""

    model: str
    api_key: str
    base_url: str = "https://generativelanguage.googleapis.com"
    temperature: float = 0.0
    request_fn: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None

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
        if self.request_fn is not None:
            return self.request_fn(url, headers, body)

        req = urllib_request.Request(url, data=body, headers=headers, method="POST")
        with urllib_request.urlopen(req) as response:  # noqa: S310
            return json.loads(response.read().decode("utf8"))


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

from __future__ import annotations

import json

from aether_forge.models import AnthropicPlanningModel, GeminiPlanningModel, ModelInfo, OpenAICompatiblePlanningModel, StaticPlanningModel, list_models


def test_static_planning_model_returns_fixed_response() -> None:
    model = StaticPlanningModel('{"steps": []}')

    assert model.complete("plan please") == '{"steps": []}'


def test_openai_compatible_planning_model_uses_expected_request_shape() -> None:
    captured: dict[str, object] = {}

    def fake_request(url: str, headers: dict[str, str], body: bytes) -> dict[str, object]:
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json.loads(body.decode("utf8"))
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"steps": [{"kind": "reason", "description": "done", "payload": {"mark_complete": true}}]}'
                    }
                }
            ]
        }

    model = OpenAICompatiblePlanningModel(
        model="hermes-3",
        api_key="test-key",
        base_url="https://example.invalid/v1",
        request_fn=fake_request,
    )

    response = model.complete("bounded planning prompt")

    assert captured["url"] == "https://example.invalid/v1/chat/completions"
    assert captured["headers"] == {
        "Authorization": "Bearer test-key",
        "Content-Type": "application/json",
    }
    assert captured["payload"] == {
        "model": "hermes-3",
        "temperature": 0.0,
        "messages": [
            {
                "role": "system",
                "content": "Return only JSON for bounded next-step planning.",
            },
            {
                "role": "user",
                "content": "bounded planning prompt",
            },
        ],
    }
    assert response.startswith('{"steps"')


def test_anthropic_planning_model_uses_messages_api_shape() -> None:
    captured: dict[str, object] = {}

    def fake_request(url: str, headers: dict[str, str], body: bytes) -> dict[str, object]:
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json.loads(body.decode("utf8"))
        return {
            "content": [
                {"text": '{"steps": []}'}
            ]
        }

    model = AnthropicPlanningModel(
        model="claude-sonnet-4-20250514",
        api_key="sk-ant-test",
        base_url="https://example.invalid",
        request_fn=fake_request,
    )

    response = model.complete("bounded planning prompt")

    assert captured["url"] == "https://example.invalid/v1/messages"
    assert captured["headers"]["x-api-key"] == "sk-ant-test"
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    payload = captured["payload"]
    assert payload["model"] == "claude-sonnet-4-20250514"
    assert payload["system"] == "Return only JSON for bounded next-step planning."
    assert payload["messages"] == [{"role": "user", "content": "bounded planning prompt"}]
    assert payload["max_tokens"] == 4096
    assert response == '{"steps": []}'


def test_gemini_planning_model_uses_generate_content_api_shape() -> None:
    captured: dict[str, object] = {}

    def fake_request(url: str, headers: dict[str, str], body: bytes) -> dict[str, object]:
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json.loads(body.decode("utf8"))
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [{"text": '{"steps": []}'}]
                    }
                }
            ]
        }

    model = GeminiPlanningModel(
        model="gemini-2.5-pro",
        api_key="AIza-test",
        base_url="https://example.invalid",
        request_fn=fake_request,
    )

    response = model.complete("bounded planning prompt")

    assert captured["url"] == "https://example.invalid/v1beta/models/gemini-2.5-pro:generateContent?key=AIza-test"
    payload = captured["payload"]
    assert payload["contents"] == [{"parts": [{"text": "bounded planning prompt"}]}]
    assert payload["systemInstruction"] == {"parts": [{"text": "Return only JSON for bounded next-step planning."}]}
    assert payload["generationConfig"]["temperature"] == 0.0
    assert response == '{"steps": []}'


def test_list_models_openrouter_parses_response() -> None:
    def fake_fetcher(url: str, headers: dict[str, str]) -> dict:
        assert "openrouter.ai" in url
        return {
            "data": [
                {
                    "id": "meta-llama/llama-3-70b-instruct",
                    "name": "Meta: Llama 3 70B Instruct",
                    "context_length": 8192,
                    "architecture": {"modality": "text->text"},
                    "pricing": {"prompt": "0.0000008", "completion": "0.0000008"},
                },
                {
                    "id": "anthropic/claude-sonnet-4",
                    "name": "Anthropic: Claude Sonnet 4",
                    "context_length": 200000,
                    "architecture": {"modality": "text+image->text"},
                    "pricing": {"prompt": "0.000003", "completion": "0.000015"},
                },
            ]
        }

    models = list_models("openrouter", request_fn=fake_fetcher)
    assert len(models) == 2
    assert models[0].id == "meta-llama/llama-3-70b-instruct"
    assert models[0].context_length == 8192
    assert models[1].provider == "openrouter"


def test_list_models_openrouter_filters_by_query() -> None:
    def fake_fetcher(url: str, headers: dict[str, str]) -> dict:
        return {
            "data": [
                {"id": "meta-llama/llama-3-70b", "name": "Llama 3 70B", "pricing": {}},
                {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "pricing": {}},
            ]
        }

    models = list_models("openrouter", query="llama", request_fn=fake_fetcher)
    assert len(models) == 1
    assert models[0].id == "meta-llama/llama-3-70b"


def test_list_models_ollama_parses_response() -> None:
    def fake_fetcher(url: str, headers: dict[str, str]) -> dict:
        assert "/api/tags" in url
        return {
            "models": [
                {
                    "name": "llama3:latest",
                    "details": {"parameter_size": "8.0B", "quantization_level": "Q4_K_M"},
                },
            ]
        }

    models = list_models("ollama", request_fn=fake_fetcher)
    assert len(models) == 1
    assert models[0].id == "llama3:latest"
    assert models[0].parameter_size == "8.0B"
    assert models[0].quantization == "Q4_K_M"


def test_list_models_openai_parses_response() -> None:
    def fake_fetcher(url: str, headers: dict[str, str]) -> dict:
        assert headers.get("Authorization") == "Bearer test-key"
        return {
            "data": [
                {"id": "gpt-4o"},
                {"id": "gpt-4o-mini"},
            ]
        }

    models = list_models("openai", api_key="test-key", request_fn=fake_fetcher)
    assert len(models) == 2
    assert models[0].id == "gpt-4o"

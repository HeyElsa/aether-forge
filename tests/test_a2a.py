"""Tests for A2A server + client end-to-end.

Spins up a real A2A server on a random port, sends tasks from the client,
and verifies the full round-trip: Agent Card discovery → SendMessage →
task result.
"""

from __future__ import annotations

import json
import time
from typing import Any
from urllib import request as urllib_request

import pytest

from aether_forge.a2a_server import A2AServer, build_agent_card

pytestmark = pytest.mark.integration

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Find an available TCP port."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


@pytest.fixture
def agent_card() -> dict[str, Any]:
    spec = {
        "metadata": {"name": "test-agent", "summary": "A test agent"},
        "objective": {"primaryGoal": "test"},
    }
    manifest = {
        "artifactVersion": "0.1.0",
        "capabilities": [
            {"capabilityId": "cap-ping", "kind": "tool", "description": "Ping test"},
            {"capabilityId": "cap-echo", "kind": "data-source", "description": "Echo text"},
        ],
    }
    return build_agent_card(spec, manifest, port=0)


def _echo_handler(task: dict[str, Any]) -> dict[str, Any]:
    """Simple handler that echoes the first message back."""
    history = task.get("history", [])
    text = ""
    if history:
        parts = history[0].get("parts", [])
        if parts:
            text = parts[0].get("text", "") if isinstance(parts[0], dict) else str(parts[0])
    return {
        "state": "completed",
        "artifacts": [
            {"parts": [{"type": "text", "text": f"echo: {text}"}]}
        ],
    }


@pytest.fixture
def server(agent_card: dict[str, Any]):
    port = _free_port()
    agent_card["url"] = f"http://localhost:{port}"
    srv = A2AServer(port=port, agent_card=agent_card, task_handler=_echo_handler)
    srv.start()
    time.sleep(0.3)  # let the server bind
    yield srv, port
    srv.stop()


# ---------------------------------------------------------------------------
# Agent Card
# ---------------------------------------------------------------------------

def test_build_agent_card_has_correct_fields(agent_card: dict[str, Any]) -> None:
    assert agent_card["name"] == "test-agent"
    assert agent_card["description"] == "A test agent"
    assert agent_card["protocolVersion"] == "2024-11-05"
    skills = agent_card["skills"]
    assert len(skills) == 2
    assert {s["id"] for s in skills} == {"cap-ping", "cap-echo"}


def test_build_agent_card_empty_capabilities() -> None:
    card = build_agent_card(
        {"metadata": {"name": "empty"}},
        {"capabilities": []},
        port=8090,
    )
    assert card["skills"] == []
    assert card["name"] == "empty"


# ---------------------------------------------------------------------------
# A2A Server — Agent Card endpoint
# ---------------------------------------------------------------------------

def test_server_serves_agent_card(server) -> None:
    srv, port = server
    url = f"http://localhost:{port}/.well-known/a2a-card"
    resp = urllib_request.urlopen(url, timeout=5)
    card = json.loads(resp.read().decode("utf8"))
    assert card["name"] == "test-agent"
    assert len(card["skills"]) == 2


def test_server_health_endpoint(server) -> None:
    srv, port = server
    url = f"http://localhost:{port}/health"
    resp = urllib_request.urlopen(url, timeout=5)
    body = json.loads(resp.read().decode("utf8"))
    assert body["status"] == "ok"
    assert body["a2a"] is True


# ---------------------------------------------------------------------------
# A2A Server — JSON-RPC SendMessage
# ---------------------------------------------------------------------------

def _json_rpc_call(port: int, method: str, params: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params,
    }).encode("utf8")
    req = urllib_request.Request(
        f"http://localhost:{port}/",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    resp = urllib_request.urlopen(req, timeout=5)
    return json.loads(resp.read().decode("utf8"))


def test_send_message_returns_completed_task(server) -> None:
    srv, port = server
    response = _json_rpc_call(port, "message/send", {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "hello"}],
            "metadata": {},
        }
    })
    result = response["result"]
    assert result["status"]["state"] == "completed"
    assert len(result["artifacts"]) > 0
    artifact_text = result["artifacts"][0]["parts"][0]["text"]
    assert "echo: " in artifact_text


def test_get_task_after_send(server) -> None:
    srv, port = server
    # Send a task
    send_resp = _json_rpc_call(port, "message/send", {
        "message": {
            "role": "user",
            "parts": [{"type": "text", "text": "test"}],
        }
    })
    task_id = send_resp["result"]["id"]

    # Retrieve it
    get_resp = _json_rpc_call(port, "tasks/get", {"id": task_id})
    assert get_resp["result"]["id"] == task_id
    assert get_resp["result"]["status"]["state"] == "completed"


def test_list_tasks(server) -> None:
    srv, port = server
    # Send two tasks
    _json_rpc_call(port, "message/send", {
        "message": {"role": "user", "parts": [{"text": "a"}]}
    })
    _json_rpc_call(port, "message/send", {
        "message": {"role": "user", "parts": [{"text": "b"}]}
    })
    # List
    resp = _json_rpc_call(port, "tasks/list", {})
    tasks = resp["result"]["tasks"]
    assert len(tasks) == 2


def test_cancel_task(server) -> None:
    srv, port = server
    send_resp = _json_rpc_call(port, "message/send", {
        "message": {"role": "user", "parts": [{"text": "c"}]}
    })
    task_id = send_resp["result"]["id"]
    cancel_resp = _json_rpc_call(port, "tasks/cancel", {"id": task_id})
    assert cancel_resp["result"]["status"]["state"] == "canceled"


def test_unknown_method_returns_error(server) -> None:
    srv, port = server
    resp = _json_rpc_call(port, "nonexistent/method", {})
    assert "error" in resp
    assert resp["error"]["code"] == -32601


def test_get_nonexistent_task_returns_error(server) -> None:
    srv, port = server
    resp = _json_rpc_call(port, "tasks/get", {"id": "no-such-task"})
    assert "error" in resp
    assert resp["error"]["code"] == -32602


# ---------------------------------------------------------------------------
# A2A Server — error handler in task execution
# ---------------------------------------------------------------------------

def test_failing_handler_sets_task_failed() -> None:
    port = _free_port()

    def bad_handler(task):
        raise ValueError("intentional failure")

    card = build_agent_card({"metadata": {"name": "bad"}}, {"capabilities": []}, port=port)
    card["url"] = f"http://localhost:{port}"
    srv = A2AServer(port=port, agent_card=card, task_handler=bad_handler)
    srv.start()
    time.sleep(0.3)
    try:
        resp = _json_rpc_call(port, "message/send", {
            "message": {"role": "user", "parts": [{"text": "trigger failure"}]}
        })
        assert resp["result"]["status"]["state"] == "failed"
    finally:
        srv.stop()

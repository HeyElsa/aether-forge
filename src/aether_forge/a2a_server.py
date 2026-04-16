"""A2A (Agent-to-Agent) server for Aether Forge agents.

A lightweight HTTP server that exposes a running agent's capabilities via
the A2A protocol (JSON-RPC 2.0 over HTTP). Handles:

- ``GET /.well-known/a2a-card`` — serves the agent's A2A Agent Card
- ``POST /`` — JSON-RPC endpoint for ``SendMessage``, ``GetTask``, etc.

Uses the stdlib ``http.server`` module (same pattern as the runner's health
server) so there are no external dependencies. The server runs in a daemon
thread alongside the agent's tick loop.

Usage::

    from aether_forge.a2a_server import A2AServer, build_agent_card

    card = build_agent_card(agent_spec, capability_manifest, port=8090)
    server = A2AServer(port=8090, agent_card=card, task_handler=my_handler)
    server.start()
    # ... agent runs ...
    server.stop()
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent Card builder — converts Aether Forge specs to A2A Agent Card JSON
# ---------------------------------------------------------------------------


def build_agent_card(
    agent_spec: dict[str, Any],
    capability_manifest: dict[str, Any],
    *,
    port: int,
    host: str = "localhost",
) -> dict[str, Any]:
    """Build an A2A-compatible Agent Card from Aether Forge spec artifacts.

    Maps the capability manifest's declared capabilities to A2A "skills"
    so that remote A2A clients can discover what this agent can do.
    """
    metadata = agent_spec.get("metadata", {})
    name = metadata.get("name", "aether-forge-agent")
    description = metadata.get("summary", "") or agent_spec.get("objective", {}).get("primaryGoal", "")

    capabilities = capability_manifest.get("capabilities", [])
    skills = []
    for cap in capabilities:
        cap_id = cap.get("capabilityId", "")
        if not cap_id:
            continue
        skills.append({
            "id": cap_id,
            "name": cap_id,
            "description": cap.get("description", ""),
            "tags": [cap.get("kind", "tool")],
            "examples": [],
        })

    return {
        "name": name,
        "description": description,
        "url": f"http://{host}:{port}",
        "version": capability_manifest.get("artifactVersion", "0.1.0"),
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
        "skills": skills,
        "defaultInputModes": ["application/json", "text/plain"],
        "defaultOutputModes": ["application/json", "text/plain"],
        "provider": {
            "organization": metadata.get("organization", "aether-forge"),
            "url": "",
        },
    }


# ---------------------------------------------------------------------------
# Task store — in-memory storage of A2A tasks for this server
# ---------------------------------------------------------------------------


class _TaskStore:
    """Simple in-memory task store for the A2A server.

    Security: enforces a max task count and per-client rate limit to prevent
    DoS via task flooding (flagged as HIGH by security audit).
    """

    MAX_TASKS = 1000  # reject new tasks if store exceeds this
    MAX_TASKS_PER_MINUTE = 60  # per-client rate limit

    def __init__(self) -> None:
        self._tasks: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._request_counts: dict[str, list[float]] = {}  # ip → timestamps

    def _check_rate_limit(self, client_ip: str = "") -> bool:
        """Return True if the client is within rate limits."""
        if not client_ip:
            return True
        now = time.time()
        window = now - 60
        with self._lock:
            timestamps = self._request_counts.get(client_ip, [])
            timestamps = [t for t in timestamps if t > window]
            if len(timestamps) >= self.MAX_TASKS_PER_MINUTE:
                return False
            timestamps.append(now)
            self._request_counts[client_ip] = timestamps
        return True

    def is_full(self) -> bool:
        return len(self._tasks) >= self.MAX_TASKS

    def _cleanup_old_tasks(self) -> None:
        """Purge completed/failed/canceled tasks older than 1 hour.

        Prevents unbounded memory growth in long-running agents
        (flagged by performance audit — old tasks never purged).
        """
        cutoff = time.time() - 3600  # 1 hour
        terminal_states = {"completed", "failed", "canceled", "rejected"}
        with self._lock:
            to_delete = []
            for task_id, task in self._tasks.items():
                status = task.get("status", {})
                state = status.get("state", "")
                ts = status.get("timestamp", "")
                if state in terminal_states and ts:
                    try:
                        from datetime import datetime
                        task_time = datetime.fromisoformat(ts).timestamp()
                        if task_time < cutoff:
                            to_delete.append(task_id)
                    except (ValueError, TypeError):
                        pass
            for task_id in to_delete:
                del self._tasks[task_id]
            if to_delete:
                logger.debug("Purged %d old tasks from A2A task store", len(to_delete))

    def create_task(self, message: dict[str, Any]) -> dict[str, Any]:
        # Opportunistic cleanup on every create
        self._cleanup_old_tasks()
        task_id = str(uuid.uuid4())
        task = {
            "id": task_id,
            "status": {"state": "submitted", "timestamp": datetime.now(UTC).isoformat()},
            "history": [message],
            "artifacts": [],
            "metadata": message.get("metadata", {}),
        }
        with self._lock:
            self._tasks[task_id] = task
        return task

    def get_task(self, task_id: str) -> dict[str, Any] | None:
        return self._tasks.get(task_id)

    def update_task(
        self,
        task_id: str,
        *,
        state: str,
        artifacts: list[dict[str, Any]] | None = None,
        message: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            task["status"] = {"state": state, "timestamp": datetime.now(UTC).isoformat()}
            if artifacts:
                task["artifacts"] = artifacts
            if message:
                task["history"].append(message)
            return task

    def list_tasks(self) -> list[dict[str, Any]]:
        return list(self._tasks.values())


# ---------------------------------------------------------------------------
# Task handler type — the bridge between A2A and the agent's planner
# ---------------------------------------------------------------------------

# The task handler is called when a remote agent sends a task via A2A.
# It receives the task dict and should return a result dict with
# "state" (completed/failed) and optional "artifacts".
TaskHandler = Callable[[dict[str, Any]], dict[str, Any]]


def _default_task_handler(task: dict[str, Any]) -> dict[str, Any]:
    """Default handler that acknowledges receipt but doesn't execute."""
    return {
        "state": "completed",
        "artifacts": [
            {
                "parts": [
                    {"type": "text", "text": f"Task {task['id']} acknowledged but no executor configured."}
                ],
            }
        ],
    }


# ---------------------------------------------------------------------------
# HTTP handler — routes to Agent Card + JSON-RPC
# ---------------------------------------------------------------------------


class _A2AHandler(BaseHTTPRequestHandler):
    """HTTP handler that implements the A2A protocol over JSON-RPC 2.0."""

    server: _A2AHTTPServer

    def log_message(self, format, *args):
        logger.debug("A2A server: %s", format % args)

    def do_GET(self) -> None:
        if self.path == "/.well-known/a2a-card":
            body = json.dumps(self.server.agent_card).encode("utf8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if self.path in ("/health", "/status"):
            body = json.dumps({
                "status": "ok",
                "a2a": True,
                "tasks": len(self.server.task_store.list_tasks()),
            }).encode("utf8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_error(404)

    _MAX_BODY_SIZE = 1_048_576  # 1 MB

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > self._MAX_BODY_SIZE:
            self.send_error(413, "Request body too large")
            return
        body = self.rfile.read(content_length).decode("utf8") if content_length > 0 else ""

        try:
            request = json.loads(body)
        except json.JSONDecodeError:
            self._json_rpc_error(None, -32700, "Parse error")
            return

        method = request.get("method")
        msg_id = request.get("id")
        params = request.get("params", {})

        if method == "message/send":
            self._handle_send_message(msg_id, params)
        elif method == "tasks/get":
            self._handle_get_task(msg_id, params)
        elif method == "tasks/list":
            self._handle_list_tasks(msg_id)
        elif method == "tasks/cancel":
            self._handle_cancel_task(msg_id, params)
        else:
            self._json_rpc_error(msg_id, -32601, f"Method not found: {method}")

    def _handle_send_message(self, msg_id: Any, params: dict[str, Any]) -> None:
        # Rate limiting + queue bounds (security audit: HIGH — DoS prevention)
        client_ip = self.client_address[0] if self.client_address else ""
        if not self.server.task_store._check_rate_limit(client_ip):
            self._json_rpc_error(msg_id, -32000, "Rate limit exceeded (max 60 tasks/min)")
            return
        if self.server.task_store.is_full():
            self._json_rpc_error(msg_id, -32000, "Task queue full (max 1000 tasks)")
            return

        message = params.get("message", params)
        task = self.server.task_store.create_task(message)

        # Execute the task via the registered handler
        try:
            self.server.task_store.update_task(task["id"], state="working")
            result = self.server.task_handler(task)
            state = result.get("state", "completed")
            artifacts = result.get("artifacts", [])
            updated = self.server.task_store.update_task(
                task["id"], state=state, artifacts=artifacts,
            )
            self._json_rpc_result(msg_id, updated or task)
        except Exception as error:
            logger.warning("A2A task handler failed: %s", error)
            self.server.task_store.update_task(
                task["id"],
                state="failed",
                message={"role": "agent", "parts": [{"type": "text", "text": str(error)}]},
            )
            failed = self.server.task_store.get_task(task["id"])
            self._json_rpc_result(msg_id, failed or task)

    def _handle_get_task(self, msg_id: Any, params: dict[str, Any]) -> None:
        task_id = params.get("id") or params.get("taskId")
        task = self.server.task_store.get_task(task_id) if task_id else None
        if task is None:
            self._json_rpc_error(msg_id, -32602, f"Task not found: {task_id}")
            return
        self._json_rpc_result(msg_id, task)

    def _handle_list_tasks(self, msg_id: Any) -> None:
        tasks = self.server.task_store.list_tasks()
        self._json_rpc_result(msg_id, {"tasks": tasks})

    def _handle_cancel_task(self, msg_id: Any, params: dict[str, Any]) -> None:
        task_id = params.get("id") or params.get("taskId")
        task = self.server.task_store.get_task(task_id) if task_id else None
        if task is None:
            self._json_rpc_error(msg_id, -32602, f"Task not found: {task_id}")
            return
        self.server.task_store.update_task(task_id, state="canceled")
        self._json_rpc_result(msg_id, self.server.task_store.get_task(task_id))

    def _json_rpc_result(self, msg_id: Any, result: Any) -> None:
        body = json.dumps({"jsonrpc": "2.0", "id": msg_id, "result": result}).encode("utf8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_rpc_error(self, msg_id: Any, code: int, message: str) -> None:
        body = json.dumps({
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": code, "message": message},
        }).encode("utf8")
        self.send_response(200)  # JSON-RPC errors are still 200
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _A2AHTTPServer(HTTPServer):
    """HTTPServer subclass that carries A2A state for the handler."""

    agent_card: dict[str, Any]
    task_store: _TaskStore
    task_handler: TaskHandler


# ---------------------------------------------------------------------------
# Public A2A server class
# ---------------------------------------------------------------------------


class A2AServer:
    """A2A-compatible HTTP server for an Aether Forge agent.

    Runs in a daemon thread alongside the agent's tick loop. Exposes:
    - ``GET /.well-known/a2a-card`` — the agent's A2A Agent Card
    - ``POST /`` — JSON-RPC endpoint for SendMessage, GetTask, etc.
    - ``GET /health`` — health check (same as the runner's health server)
    """

    def __init__(
        self,
        port: int,
        agent_card: dict[str, Any],
        task_handler: TaskHandler | None = None,
    ) -> None:
        self.port = port
        self.agent_card = agent_card
        self.task_handler = task_handler or _default_task_handler
        self._server: _A2AHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the A2A server in a daemon thread."""
        self._server = _A2AHTTPServer(("127.0.0.1", self.port), _A2AHandler)
        self._server.agent_card = self.agent_card
        self._server.task_store = _TaskStore()
        self._server.task_handler = self.task_handler

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info(
            "A2A server started on port %d — Agent Card at http://localhost:%d/.well-known/a2a-card",
            self.port, self.port,
        )

    def stop(self) -> None:
        """Stop the A2A server."""
        if self._server is not None:
            self._server.shutdown()
            self._server = None
        self._thread = None
        logger.info("A2A server stopped")

    @property
    def task_store(self) -> _TaskStore | None:
        return self._server.task_store if self._server else None

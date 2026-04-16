"""A2A (Agent-to-Agent) client for Aether Forge.

Wraps the ``a2a-sdk`` Python package to let one Aether Forge agent call
another agent's capabilities via the A2A protocol (JSON-RPC 2.0 over HTTP).

The a2a-sdk v0.3.26+ uses async APIs internally, so this client bridges
to sync via ``asyncio.run()`` for Aether Forge's synchronous runtime.

Usage::

    from aether_forge.a2a_client import A2AForgeClient

    client = A2AForgeClient("http://localhost:8090")
    card = client.get_agent_card()
    print(card.name, [s.name for s in card.skills])

    result = client.send_task(
        capability="get-token-price",
        arguments={"token": "ETH", "chain": "base"},
    )
    print(result)

Requires: ``pip install a2a-sdk`` (or ``pip install aether-forge[a2a]``).
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    """Run an async coroutine synchronously.

    Handles the case where an event loop is already running (e.g., inside
    Jupyter or an ASGI server) by creating a new thread with its own loop.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None and loop.is_running():
        # Already in an async context — use a thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(timeout=30)
    else:
        return asyncio.run(coro)


class A2AForgeClient:
    """Thin Aether Forge wrapper around the a2a-sdk client.

    Provides a simplified synchronous interface for the most common
    agent-to-agent operations: fetch the Agent Card, send a task, and
    check availability. All a2a-sdk async calls are bridged to sync
    via ``asyncio.run()``.
    """

    def __init__(self, endpoint: str, *, timeout: float = 30.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.timeout = timeout

    def get_agent_card(self) -> Any:
        """Fetch the remote agent's A2A Agent Card.

        Returns the ``AgentCard`` pydantic model from a2a-sdk.
        """
        try:
            from a2a.client.card_resolver import A2ACardResolver

            resolver = A2ACardResolver(
                url=self.endpoint,
                agent_card_path="/.well-known/a2a-card",
            )
            # a2a-sdk v0.3.26 — get_agent_card() is async
            card = _run_async(resolver.get_agent_card())
            return card
        except ImportError as error:
            raise RuntimeError(
                "a2a-sdk is not installed. Install with: pip install 'aether-forge[a2a]'"
            ) from error

    def send_task(
        self,
        capability: str,
        arguments: dict[str, Any] | None = None,
        *,
        text: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a task to the remote agent and wait for the result.

        This is a synchronous call — it blocks until the task completes,
        fails, or times out.

        Args:
            capability: The skill/capability name to invoke.
            arguments: Typed arguments for the capability.
            text: Optional plain-text message to send alongside.
            metadata: Optional key-value metadata (e.g. payment info).

        Returns:
            A dict with ``task_id``, ``status``, ``artifacts``, and ``history``.
        """
        # Build the JSON-RPC request directly (avoids async SDK complexity)
        parts: list[dict[str, Any]] = []
        if text:
            parts.append({"type": "text", "text": text})
        payload = {"capability": capability, **(arguments or {})}
        parts.append({"type": "text", "text": json.dumps(payload)})

        message = {
            "role": "user",
            "parts": parts,
            "metadata": metadata or {},
            "message_id": str(uuid.uuid4()),
        }

        # Direct JSON-RPC call to avoid async SDK issues
        from urllib import error as urllib_error
        from urllib import request as urllib_request

        body = json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {"message": message},
        }).encode("utf8")

        req = urllib_request.Request(
            f"{self.endpoint}/",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read().decode("utf8"))
                if "error" in result:
                    raise RuntimeError(f"A2A error: {result['error']}")
                return result.get("result", {})
        except urllib_error.URLError as error:
            raise RuntimeError(f"A2A call to {self.endpoint} failed: {error}") from error

    def is_available(self) -> bool:
        """Check if the remote agent is reachable and returns a valid Agent Card."""
        try:
            card = self.get_agent_card()
            return card is not None and hasattr(card, "name")
        except Exception:
            return False

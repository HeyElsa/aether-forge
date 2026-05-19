"""Model Context Protocol (MCP) client for Aether Forge.

A minimal, pure-stdlib client for talking to MCP servers over both the
stdio and streamable-HTTP transports. Supports the three operations Aether
Forge needs at runtime:

- ``initialize`` — handshake with the server
- ``tools/list`` — discover the tools the server exposes
- ``tools/call`` — invoke a tool by name with a typed argument payload

The client is intentionally small. It does not implement the full MCP
specification (resources, prompts, completion, subscriptions, sampling).
Those can be added when Aether Forge needs them.

MCP reference: https://modelcontextprotocol.io/

Example — spawning a local stdio MCP server::

    from aether_forge.mcp_client import McpStdioClient, McpServerConfig

    config = McpServerConfig(
        name="hermes",
        command="hermes",
        args=["mcp", "serve"],
    )
    with McpStdioClient(config) as client:
        tools = client.list_tools()
        for tool in tools:
            print(tool["name"], tool["description"])

        result = client.call_tool("messages_send", {"platform": "telegram", "text": "hi"})
        print(result)

Example — connecting to a remote HTTP MCP server::

    from aether_forge.mcp_client import McpHttpClient, McpServerConfig

    config = McpServerConfig(
        name="example",
        url="https://mcp.example.com/mcp",
        headers={"Authorization": "Bearer ..."},
    )
    client = McpHttpClient(config)
    client.initialize()
    tools = client.list_tools()
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

from ._version import __version__

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class McpServerConfig:
    """Declarative configuration for one MCP server.

    A server is either a subprocess invoked via ``command`` + ``args`` (stdio
    transport) or a remote HTTP endpoint addressed by ``url``. Exactly one
    of those two groups must be provided.

    ``tools_include`` and ``tools_exclude`` let you whitelist or blacklist
    specific tools by name. Both default to "allow everything the server
    exposes". ``env`` is passed through to stdio subprocesses only.
    """

    name: str
    # Stdio transport
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # HTTP transport
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    # Tool filtering
    tools_include: list[str] | None = None
    tools_exclude: list[str] = field(default_factory=list)
    # How long to wait for each RPC response
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        has_command = bool(self.command)
        has_url = bool(self.url)
        if has_command == has_url:
            raise ValueError(
                f"McpServerConfig[{self.name}]: exactly one of 'command' or 'url' must be set"
            )

    @property
    def transport(self) -> str:
        return "stdio" if self.command else "http"

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> McpServerConfig:
        """Build a config from a parsed JSON/YAML block.

        Expected shape (matches the ``mcp_servers:`` block in
        ``aether-forge.json``)::

            {
              "command": "npx",
              "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
              "env": {"FOO": "bar"},
              "tools": {"include": ["read_file"], "exclude": []}
            }
        """
        tools_block = data.get("tools", {}) if isinstance(data.get("tools"), dict) else {}
        return cls(
            name=name,
            command=data.get("command"),
            args=list(data.get("args", [])),
            env=dict(data.get("env", {})),
            url=data.get("url"),
            headers=dict(data.get("headers", {})),
            tools_include=list(tools_block["include"]) if "include" in tools_block else None,
            tools_exclude=list(tools_block.get("exclude", [])),
            timeout_seconds=float(data.get("timeout_seconds", 30.0)),
        )


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class McpError(RuntimeError):
    """Base class for MCP client errors."""


class McpProtocolError(McpError):
    """The server returned a malformed or error JSON-RPC response."""


class McpTimeoutError(McpError):
    """The server did not respond within the configured timeout."""


# ---------------------------------------------------------------------------
# Base client
# ---------------------------------------------------------------------------


class _McpClientBase:
    """Shared initialize / list / call helpers used by both transports."""

    PROTOCOL_VERSION = "2024-11-05"

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self._initialized = False
        self._next_id = 0
        self._lock = threading.Lock()
        self._server_info: dict[str, Any] = {}

    def _allocate_id(self) -> int:
        with self._lock:
            self._next_id += 1
            return self._next_id

    def _filter_tool(self, tool: dict[str, Any]) -> bool:
        name = tool.get("name", "")
        if self.config.tools_include is not None and name not in self.config.tools_include:
            return False
        if name in self.config.tools_exclude:
            return False
        return True

    # ----- public ------------------------------------------------------
    def initialize(self) -> dict[str, Any]:
        """Perform the MCP handshake. Returns the server's info dict."""
        response = self._rpc(
            "initialize",
            {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                    "clientInfo": {"name": "aether-forge", "version": __version__},
            },
        )
        self._server_info = response.get("serverInfo", {})
        self._initialized = True
        # Some MCP servers require the initialized notification after the
        # initialize response. Spec-compliant clients send it; many servers
        # work without it but we're spec-compliant for good measure.
        try:
            self._send_notification("notifications/initialized", {})
        except Exception as error:
            logger.debug("MCP initialized notification failed (non-fatal): %s", error)
        return self._server_info

    def list_tools(self) -> list[dict[str, Any]]:
        """Return the list of tool descriptors the server exposes."""
        if not self._initialized:
            self.initialize()
        response = self._rpc("tools/list", {})
        tools = response.get("tools", [])
        return [t for t in tools if self._filter_tool(t)]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a tool by name with a typed argument payload."""
        if not self._initialized:
            self.initialize()
        response = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return response

    # ----- transport hooks --------------------------------------------
    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        raise NotImplementedError

    def close(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Stdio transport
# ---------------------------------------------------------------------------


class McpStdioClient(_McpClientBase):
    """MCP client that communicates with a server over stdio.

    Use as a context manager to guarantee the subprocess is cleaned up::

        with McpStdioClient(config) as client:
            tools = client.list_tools()
    """

    def __init__(self, config: McpServerConfig) -> None:
        if config.transport != "stdio":
            raise ValueError(f"McpStdioClient requires command-based config, got {config.transport}")
        super().__init__(config)
        self._process: subprocess.Popen | None = None

    def __enter__(self) -> McpStdioClient:
        self._spawn()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def __del__(self) -> None:
        """Kill the subprocess if the client is garbage-collected without close().

        Prevents zombie MCP processes from accumulating across agent restarts.
        (Flagged as HIGH by performance audit — 100+ zombies after a week.)
        """
        try:
            self.close()
        except Exception:
            pass

    def _spawn(self) -> None:
        if self._process is not None:
            return
        # Stdio servers inherit a safe baseline env plus whatever the caller
        # declared in config.env. Do not leak the full parent environment
        # (matches Hermes Agent's own stdio hardening).
        safe_env = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "HOME", "USER", "SHELL", "LANG", "LC_ALL", "TERM"}
        }
        # Filter out known secret env vars from the user-declared env block.
        # Even if the config explicitly passes API keys, strip them to prevent
        # a malicious MCP server from exfiltrating them.
        # (Flagged as CRITICAL by security audit — MCP can read process environ.)
        _SECRET_VARS = {
            "OWS_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "GOOGLE_API_KEY", "GEMINI_API_KEY", "OPENROUTER_API_KEY",
            "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
            "AETHER_FORGE_PLANNER_API_KEY",
        }
        filtered_env = {
            k: v for k, v in self.config.env.items()
            if k.upper() not in _SECRET_VARS
        }
        stripped = set(self.config.env.keys()) - set(filtered_env.keys())
        if stripped:
            logger.warning(
                "MCP server %s: stripped %d secret env var(s) for safety: %s",
                self.config.name, len(stripped), ", ".join(sorted(stripped)),
            )
        safe_env.update(filtered_env)
        # Some npx/uvx wrappers need PATH; don't override it.
        logger.info("Spawning MCP stdio server: %s %s", self.config.command, " ".join(self.config.args))
        self._process = subprocess.Popen(
            [self.config.command or "", *self.config.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=safe_env,
            text=True,
            bufsize=1,  # line-buffered
        )

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self._process is None:
            self._spawn()
        proc = self._process
        assert proc is not None and proc.stdin is not None and proc.stdout is not None

        msg_id = self._allocate_id()
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }
        payload = json.dumps(request) + "\n"

        with self._lock:
            try:
                proc.stdin.write(payload)
                proc.stdin.flush()
            except BrokenPipeError as error:
                raise McpError(f"MCP server {self.config.name} closed stdin: {error}") from error

            # Read with a timeout to prevent hanging forever if the MCP
            # server gets stuck (flagged as HIGH by security audit).
            try:
                import select
                timeout_sec = self.config.timeout_seconds
                ready, _, _ = select.select([proc.stdout], [], [], timeout_sec)
                if not ready:
                    raise McpTimeoutError(
                        f"MCP server {self.config.name} did not respond within "
                        f"{timeout_sec}s. Stderr: {self._drain_stderr()}"
                    )
            except (TypeError, ValueError, OSError):
                # select() doesn't work on mock file objects or Windows pipes.
                # Fall through to blocking readline() in those cases.
                pass
            line = proc.stdout.readline()

        if not line:
            raise McpError(
                f"MCP server {self.config.name} produced empty response (exited?). "
                f"Stderr: {self._drain_stderr()}"
            )

        try:
            response = json.loads(line)
        except json.JSONDecodeError as error:
            raise McpProtocolError(
                f"MCP server {self.config.name} returned non-JSON: {line[:200]!r}"
            ) from error

        if "error" in response:
            err = response["error"]
            raise McpProtocolError(
                f"MCP server {self.config.name} {method} error: {err.get('message', err)}"
            )
        return response.get("result", {})

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if self._process is None:
            self._spawn()
        proc = self._process
        assert proc is not None and proc.stdin is not None
        payload = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n"
        with self._lock:
            try:
                proc.stdin.write(payload)
                proc.stdin.flush()
            except BrokenPipeError:
                pass

    def _drain_stderr(self) -> str:
        if self._process is None or self._process.stderr is None:
            return ""
        try:
            return self._process.stderr.read() or ""
        except Exception:
            return ""

    def close(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.kill()
        except Exception:
            pass
        self._process = None


# ---------------------------------------------------------------------------
# HTTP transport (simple request/response, no SSE/streaming)
# ---------------------------------------------------------------------------


class McpHttpClient(_McpClientBase):
    """MCP client that communicates with a server over HTTP.

    This implements the plain request/response shape of streamable-HTTP
    MCP transport, not the full streaming spec. Good enough for most
    server-exposed REST endpoints.
    """

    def __init__(
        self,
        config: McpServerConfig,
        *,
        request_fn: Callable[[str, dict[str, str], bytes], dict[str, Any]] | None = None,
    ) -> None:
        if config.transport != "http":
            raise ValueError(f"McpHttpClient requires url-based config, got {config.transport}")
        super().__init__(config)
        self._request_fn = request_fn

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        msg_id = self._allocate_id()
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params,
        }
        body = json.dumps(request).encode("utf8")
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self.config.headers,
        }

        if self._request_fn is not None:
            response = self._request_fn("POST", dict(headers), body)
            return self._parse_http_response(response, method)

        req = urllib_request.Request(
            self.config.url or "",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.config.timeout_seconds) as resp:
                raw = resp.read().decode("utf8")
                return self._parse_http_response({"status": resp.status, "body": raw}, method)
        except urllib_error.HTTPError as error:
            raise McpError(
                f"MCP server {self.config.name} HTTP error: {error.code} {error.reason}"
            ) from error
        except urllib_error.URLError as error:
            raise McpError(
                f"MCP server {self.config.name} unreachable: {error.reason}"
            ) from error

    def _parse_http_response(self, response: dict[str, Any], method: str) -> dict[str, Any]:
        raw = response.get("body", "")
        if isinstance(raw, (dict, list)):
            parsed = raw
        else:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as error:
                raise McpProtocolError(
                    f"MCP server {self.config.name} returned non-JSON: {str(raw)[:200]!r}"
                ) from error

        if "error" in parsed:
            err = parsed["error"]
            raise McpProtocolError(
                f"MCP server {self.config.name} {method} error: {err.get('message', err)}"
            )
        return parsed.get("result", {})

    def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        # Notifications are fire-and-forget; we still POST but ignore the
        # response (HTTP MCP servers typically return 204 No Content).
        body = json.dumps({"jsonrpc": "2.0", "method": method, "params": params}).encode("utf8")
        headers = {"Content-Type": "application/json", **self.config.headers}
        req = urllib_request.Request(
            self.config.url or "",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib_request.urlopen(req, timeout=self.config.timeout_seconds):
                pass
        except Exception as error:
            logger.debug("MCP notification failed (non-fatal): %s", error)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_mcp_client(config: McpServerConfig) -> _McpClientBase:
    """Return the right client implementation for the given server config."""
    if config.transport == "stdio":
        return McpStdioClient(config)
    return McpHttpClient(config)

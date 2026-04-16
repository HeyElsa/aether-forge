"""Tests for the MCP client and McpDataSource.

The tests drive both clients through mock subprocess I/O and mock HTTP
responses so nothing actually needs a real MCP server running.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from aether_forge.data_layer import DataRouter, McpDataSource, build_mcp_source
from aether_forge.mcp_client import (
    McpHttpClient,
    McpProtocolError,
    McpServerConfig,
    McpStdioClient,
    build_mcp_client,
)

# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_config_requires_command_or_url() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        McpServerConfig(name="bad")


def test_config_rejects_both_command_and_url() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        McpServerConfig(name="bad", command="foo", url="https://example.com")


def test_config_reports_transport() -> None:
    stdio = McpServerConfig(name="a", command="foo")
    http = McpServerConfig(name="b", url="https://example.com")
    assert stdio.transport == "stdio"
    assert http.transport == "http"


def test_config_from_dict_parses_tools_filter() -> None:
    config = McpServerConfig.from_dict(
        "github",
        {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"TOKEN": "abc"},
            "tools": {"include": ["list_issues"], "exclude": ["delete_repo"]},
            "timeout_seconds": 45.0,
        },
    )
    assert config.name == "github"
    assert config.command == "npx"
    assert config.args == ["-y", "@modelcontextprotocol/server-github"]
    assert config.env == {"TOKEN": "abc"}
    assert config.tools_include == ["list_issues"]
    assert config.tools_exclude == ["delete_repo"]
    assert config.timeout_seconds == 45.0


def test_build_mcp_client_picks_right_transport() -> None:
    stdio = McpServerConfig(name="a", command="foo")
    http = McpServerConfig(name="b", url="https://example.com")
    assert isinstance(build_mcp_client(stdio), McpStdioClient)
    assert isinstance(build_mcp_client(http), McpHttpClient)


# ---------------------------------------------------------------------------
# Stdio client — driven by a fake Popen
# ---------------------------------------------------------------------------


def _fake_stdio_client(response_lines: list[str]) -> McpStdioClient:
    """Build a stdio client whose subprocess is a mock emitting canned JSON."""
    config = McpServerConfig(name="fake", command="/bin/echo")
    client = McpStdioClient(config)

    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    # readline() returns each queued line in order, then empty string
    iterator = iter(response_lines + [""])
    mock_proc.stdout.readline = lambda: next(iterator, "")
    mock_proc.stderr = MagicMock()
    mock_proc.stderr.read = MagicMock(return_value="")
    client._process = mock_proc
    return client


def test_stdio_client_initialize() -> None:
    init_response = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"serverInfo": {"name": "test-server", "version": "1.0"}},
        }
    )
    client = _fake_stdio_client([init_response])

    info = client.initialize()

    assert info == {"name": "test-server", "version": "1.0"}
    assert client._initialized is True


def test_stdio_client_list_tools_auto_initializes() -> None:
    responses = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "t"}}}),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {
                    "tools": [
                        {"name": "read_file", "description": "Read a file", "inputSchema": {}},
                        {"name": "write_file", "description": "Write a file", "inputSchema": {}},
                    ]
                },
            }
        ),
    ]
    client = _fake_stdio_client(responses)

    tools = client.list_tools()

    assert len(tools) == 2
    assert {t["name"] for t in tools} == {"read_file", "write_file"}


def test_stdio_client_call_tool_returns_result() -> None:
    responses = [
        json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "t"}}}),
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"content": [{"type": "text", "text": "file contents"}]},
            }
        ),
    ]
    client = _fake_stdio_client(responses)

    result = client.call_tool("read_file", {"path": "/tmp/foo"})

    assert "content" in result
    assert result["content"][0]["text"] == "file contents"


def test_stdio_client_raises_on_protocol_error() -> None:
    responses = [
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "error": {"code": -32601, "message": "method not found"},
            }
        )
    ]
    client = _fake_stdio_client(responses)

    with pytest.raises(McpProtocolError, match="method not found"):
        client.initialize()


def test_stdio_client_tools_filter_include() -> None:
    config = McpServerConfig(
        name="fake",
        command="/bin/echo",
        tools_include=["read_file"],
    )
    client = McpStdioClient(config)
    mock_proc = MagicMock()
    mock_proc.stdin = MagicMock()
    mock_proc.stdout = MagicMock()
    responses = iter(
        [
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {}}}),
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "result": {
                        "tools": [
                            {"name": "read_file"},
                            {"name": "write_file"},
                            {"name": "delete_file"},
                        ]
                    },
                }
            ),
            "",
        ]
    )
    mock_proc.stdout.readline = lambda: next(responses, "")
    mock_proc.stderr.read = MagicMock(return_value="")
    client._process = mock_proc

    tools = client.list_tools()

    assert [t["name"] for t in tools] == ["read_file"]


# ---------------------------------------------------------------------------
# HTTP client — driven by a fake request_fn
# ---------------------------------------------------------------------------


def test_http_client_initialize() -> None:
    config = McpServerConfig(name="remote", url="https://mcp.example.com/mcp")
    queued: list[dict[str, Any]] = [
        {"status": 200, "body": json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "remote"}}})}
    ]
    def fake_request(method: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        return queued.pop(0)
    client = McpHttpClient(config, request_fn=fake_request)

    info = client.initialize()

    assert info == {"name": "remote"}


def test_http_client_call_tool() -> None:
    config = McpServerConfig(name="remote", url="https://mcp.example.com/mcp")
    queued = [
        {"status": 200, "body": json.dumps({"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {}}})},
        {
            "status": 200,
            "body": json.dumps(
                {"jsonrpc": "2.0", "id": 2, "result": {"value": 42}}
            ),
        },
    ]
    def fake_request(method: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        return queued.pop(0)
    client = McpHttpClient(config, request_fn=fake_request)

    result = client.call_tool("get_answer", {})

    assert result == {"value": 42}


def test_http_client_raises_on_error_response() -> None:
    config = McpServerConfig(name="remote", url="https://mcp.example.com/mcp")
    queued = [
        {
            "status": 200,
            "body": json.dumps(
                {"jsonrpc": "2.0", "id": 1, "error": {"message": "bad params"}}
            ),
        }
    ]
    def fake_request(method: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
        return queued.pop(0)
    client = McpHttpClient(config, request_fn=fake_request)

    with pytest.raises(McpProtocolError, match="bad params"):
        client.initialize()


# ---------------------------------------------------------------------------
# McpDataSource
# ---------------------------------------------------------------------------


class _FakeMcpClient:
    """Stand-in for an MCP client used by McpDataSource tests."""

    def __init__(self, tools: list[dict[str, Any]], responses: dict[str, Any]) -> None:
        self._tools = tools
        self._responses = responses
        self.initialized = False
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def initialize(self) -> dict[str, Any]:
        self.initialized = True
        return {"name": "fake"}

    def list_tools(self) -> list[dict[str, Any]]:
        return list(self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((name, arguments))
        return self._responses.get(name, {})

    def close(self) -> None:
        pass


def test_mcp_data_source_discovers_tools_and_reports_supports(monkeypatch) -> None:
    tools = [
        {"name": "messages_send", "description": "Send a message"},
        {"name": "messages_list", "description": "List messages"},
    ]
    fake = _FakeMcpClient(tools, {"messages_send": {"ok": True}})

    def build(config):  # noqa
        return fake

    monkeypatch.setattr("aether_forge.mcp_client.build_mcp_client", build)

    config = McpServerConfig(name="hermes", command="hermes", args=["mcp", "serve"])
    source = McpDataSource(config)

    assert source.supports("messages_send") is True
    assert source.supports("unknown_tool") is False
    assert len(source.available_tools()) == 2


def test_mcp_data_source_fetch_routes_to_call_tool(monkeypatch) -> None:
    tools = [{"name": "messages_send"}]
    fake = _FakeMcpClient(tools, {"messages_send": {"status": "sent"}})

    def build(config):  # noqa
        return fake

    monkeypatch.setattr("aether_forge.mcp_client.build_mcp_client", build)

    config = McpServerConfig(name="hermes", command="hermes", args=["mcp", "serve"])
    source = McpDataSource(config)

    result = source.fetch("messages_send", platform="telegram", text="hi")

    assert result.source == "hermes"
    assert result.capability == "messages_send"
    assert result.data == {"status": "sent"}
    assert result.cost.amount_usd == 0.0
    assert fake.calls == [("messages_send", {"platform": "telegram", "text": "hi"})]


def test_mcp_data_source_unknown_tool_raises(monkeypatch) -> None:
    fake = _FakeMcpClient([{"name": "foo"}], {})

    def build(config):  # noqa
        return fake

    monkeypatch.setattr("aether_forge.mcp_client.build_mcp_client", build)

    config = McpServerConfig(name="fake", command="/bin/echo")
    source = McpDataSource(config)

    with pytest.raises(ValueError, match="does not expose tool"):
        source.fetch("bar")


def test_data_router_dispatches_to_mcp_source(monkeypatch) -> None:
    tools = [{"name": "read_file"}]
    fake = _FakeMcpClient(tools, {"read_file": {"content": "hello"}})

    def build(config):  # noqa
        return fake

    monkeypatch.setattr("aether_forge.mcp_client.build_mcp_client", build)

    mcp = McpDataSource(McpServerConfig(name="fs", command="/bin/echo"))
    router = DataRouter([mcp])

    result = router.fetch("read_file", path="/tmp/foo")

    assert result.data == {"content": "hello"}
    assert result.source == "fs"


def test_build_mcp_source_from_dict(monkeypatch) -> None:
    source = build_mcp_source(
        {"command": "hermes", "args": ["mcp", "serve"]},
        name="hermes",
    )
    assert isinstance(source, McpDataSource)
    assert source.name == "hermes"


def test_build_mcp_source_from_config() -> None:
    config = McpServerConfig(name="x", url="https://example.com")
    source = build_mcp_source(config)
    assert source.name == "x"


def test_build_mcp_source_rejects_bad_inputs() -> None:
    with pytest.raises(TypeError):
        build_mcp_source(42)
    with pytest.raises(ValueError, match="requires a 'name'"):
        build_mcp_source({"command": "foo"})

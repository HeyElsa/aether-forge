"""Generic data layer for Aether Forge agents.

Unified abstraction over any data source:
- Free REST APIs (Binance, CoinGecko, etc.)
- Paid x402 endpoints (Elsa, future providers)
- WebSocket streams (real-time prices, order book)
- Custom sources (your own APIs, databases, files)

Single interface ``DataRouter`` routes capability calls to the right source,
tracks costs uniformly, and supports fallback chains. Works whether the
source is free, paid-per-call, or subscription-based.

Usage::

    from aether_forge.data_layer import DataRouter, HTTPDataSource, X402DataSource

    router = DataRouter([
        HTTPDataSource("binance", base_url="https://api.binance.com"),
        X402DataSource("elsa", base_url="https://x402-api.heyelsa.ai", agent_directory=Path("./my-agent")),
    ])

    # Capability dispatch — router picks the right source
    result = router.fetch("eth-price", token="ETH")

    # Or call a specific source
    result = router.call_source("binance", "/api/v3/ticker/price?symbol=ETHUSDT")

    # Stream subscription
    router.subscribe("eth-trades", lambda msg: print(msg))
"""

from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core types
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class DataSourceCost:
    """Tracks cost of a single data fetch."""

    amount_usd: float = 0.0
    paid: bool = False
    payment_method: str = "free"  # free | x402 | subscription | gas


@dataclass(slots=True)
class DataResult:
    """Result of a data fetch — uniform across sources."""

    source: str
    capability: str
    data: Any
    cost: DataSourceCost = field(default_factory=DataSourceCost)
    timestamp: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(UTC).isoformat()


class Subscription(Protocol):
    """A long-lived subscription handle (websocket, SSE, etc.)."""

    def stop(self) -> None: ...

    @property
    def active(self) -> bool: ...


# ---------------------------------------------------------------------------
# DataSource base
# ---------------------------------------------------------------------------

class DataSource(ABC):
    """Abstract base for all data sources."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.total_cost_usd: float = 0.0
        self.fetch_count: int = 0
        self.error_count: int = 0

    @abstractmethod
    def supports(self, capability: str) -> bool:
        """Return True if this source can handle the given capability."""

    @abstractmethod
    def fetch(self, capability: str, **params: Any) -> DataResult:
        """Synchronous request/response fetch."""

    def subscribe(self, capability: str, callback: Callable[[Any], None], **params: Any) -> Subscription | None:
        """Subscribe to a streaming source. Returns None if not supported."""
        return None

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total_cost_usd": round(self.total_cost_usd, 6),
            "fetch_count": self.fetch_count,
            "error_count": self.error_count,
        }


# ---------------------------------------------------------------------------
# HTTP REST data source
# ---------------------------------------------------------------------------

class HTTPDataSource(DataSource):
    """Generic HTTP REST data source for free APIs.

    Maps capabilities to URL templates with parameter substitution.

    Usage::

        binance = HTTPDataSource(
            "binance",
            base_url="https://api.binance.com",
            capabilities={
                "spot-price": ("GET", "/api/v3/ticker/price?symbol={symbol}"),
                "candles": ("GET", "/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"),
            },
        )
        result = binance.fetch("spot-price", symbol="ETHUSDT")
    """

    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        capabilities: dict[str, tuple[str, str]] | None = None,
        headers: dict[str, str] | None = None,
        request_fn: Callable[[str, str, dict[str, str], bytes | None], dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(name)
        self.base_url = base_url.rstrip("/")
        self.capabilities = capabilities or {}
        self.headers = headers or {}
        self._request_fn = request_fn

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def fetch(self, capability: str, **params: Any) -> DataResult:
        if capability not in self.capabilities:
            raise ValueError(f"HTTPDataSource[{self.name}] does not support capability: {capability}")

        method, path_template = self.capabilities[capability]
        url = self.base_url + path_template.format(**params)
        body = params.get("_body")

        try:
            response = self._do_request(method, url, self.headers, body)
            self.fetch_count += 1
            return DataResult(
                source=self.name,
                capability=capability,
                data=response.get("body", response),
                cost=DataSourceCost(amount_usd=0.0, paid=False, payment_method="free"),
                metadata={"http_status": response.get("status"), "url": url},
            )
        except Exception as error:
            self.error_count += 1
            logger.warning("HTTPDataSource[%s] fetch failed for %s: %s", self.name, capability, error)
            raise

    def _do_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | dict | None,
    ) -> dict[str, Any]:
        if self._request_fn is not None:
            return self._request_fn(method, url, headers, body)

        if isinstance(body, dict):
            body = json.dumps(body).encode("utf8")
            headers = {**headers, "Content-Type": "application/json"}

        req = urllib_request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib_request.urlopen(req, timeout=15) as resp:
                raw = resp.read().decode("utf8")
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = raw
                return {"status": resp.status, "body": parsed, "headers": dict(resp.headers)}
        except urllib_error.HTTPError as e:
            raw = e.read().decode("utf8") if e.readable() else ""
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw
            return {"status": e.code, "body": parsed, "headers": dict(e.headers)}


# ---------------------------------------------------------------------------
# x402 paid data source
# ---------------------------------------------------------------------------

class X402DataSource(DataSource):
    """x402 paid data source — pays per call from agent's wallet.

    Wraps the framework's X402Client and handles capability-to-endpoint routing.
    """

    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        agent_directory: Path | str,
        capabilities: dict[str, tuple[str, str]] | None = None,
        max_per_call_usd: float = 0.10,
        max_session_usd: float = 1.0,
        chain: str = "base",
        confirmed: bool = False,
    ) -> None:
        super().__init__(name)
        self.base_url = base_url.rstrip("/")
        self.capabilities = capabilities or {}
        self._client = None
        self._client_args = {
            "agent_directory": Path(agent_directory),
            "max_per_call_usd": max_per_call_usd,
            "max_session_usd": max_session_usd,
            "chain": chain,
            "confirmed": confirmed,
        }

    def _get_client(self):
        if self._client is None:
            from .x402_client import X402Client, X402Config
            config = X402Config(
                max_per_call_usd=self._client_args["max_per_call_usd"],
                max_session_usd=self._client_args["max_session_usd"],
                chain=self._client_args["chain"],
                confirmed=self._client_args["confirmed"],
            )
            self._client = X402Client(
                agent_directory=self._client_args["agent_directory"],
                config=config,
            )
        return self._client

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def fetch(self, capability: str, **params: Any) -> DataResult:
        if capability not in self.capabilities:
            raise ValueError(f"X402DataSource[{self.name}] does not support capability: {capability}")

        method, path_template = self.capabilities[capability]
        url = self.base_url + path_template.format(**{k: v for k, v in params.items() if k != "_body"})
        body = params.get("_body", {})

        client = self._get_client()
        try:
            if method.upper() == "POST":
                response = client.post(url, body=body)
            else:
                response = client.get(url)

            self.fetch_count += 1

            # Track cost from the latest payment
            status = client.status()
            session_total = status.get("session_spent_usd", 0)
            cost_this_call = max(0, session_total - self.total_cost_usd)
            self.total_cost_usd = session_total

            return DataResult(
                source=self.name,
                capability=capability,
                data=response.get("body", response),
                cost=DataSourceCost(
                    amount_usd=cost_this_call,
                    paid=cost_this_call > 0,
                    payment_method="x402",
                ),
                metadata={"http_status": response.get("status"), "url": url, "session_total_usd": session_total},
            )
        except Exception as error:
            self.error_count += 1
            logger.warning("X402DataSource[%s] fetch failed for %s: %s", self.name, capability, error)
            raise

    def status(self) -> dict[str, Any]:
        base = super().status()
        if self._client is not None:
            base["x402_status"] = self._client.status()
        return base


# ---------------------------------------------------------------------------
# WebSocket data source (optional dep)
# ---------------------------------------------------------------------------

@dataclass
class _WSSubscription:
    thread: threading.Thread
    stop_event: threading.Event
    ws: Any = None

    def stop(self) -> None:
        self.stop_event.set()
        if self.ws is not None:
            try:
                self.ws.close()
            except Exception:
                pass

    @property
    def active(self) -> bool:
        return not self.stop_event.is_set() and self.thread.is_alive()


class WebSocketDataSource(DataSource):
    """WebSocket streaming data source.

    Requires: pip install websocket-client

    Usage::

        ws = WebSocketDataSource(
            "binance-ws",
            base_url="wss://stream.binance.com:9443",
            capabilities={
                "trades": "/ws/{symbol}@trade",
                "klines": "/ws/{symbol}@kline_{interval}",
            },
        )
        sub = ws.subscribe("trades", lambda msg: print(msg), symbol="ethusdt")
        time.sleep(10)
        sub.stop()
    """

    def __init__(
        self,
        name: str,
        *,
        base_url: str,
        capabilities: dict[str, str] | None = None,
    ) -> None:
        super().__init__(name)
        self.base_url = base_url.rstrip("/")
        self.capabilities = capabilities or {}

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def fetch(self, capability: str, **params: Any) -> DataResult:
        """Single-message snapshot from a streaming source."""
        result_holder = {"data": None}
        done = threading.Event()

        def callback(msg):
            if result_holder["data"] is None:
                result_holder["data"] = msg
                done.set()

        sub = self.subscribe(capability, callback, **params)
        if sub is None:
            raise RuntimeError(f"WebSocketDataSource[{self.name}] subscribe failed")

        done.wait(timeout=10)
        sub.stop()

        if result_holder["data"] is None:
            self.error_count += 1
            raise TimeoutError(f"WebSocket {self.name}/{capability} timed out")

        self.fetch_count += 1
        return DataResult(
            source=self.name,
            capability=capability,
            data=result_holder["data"],
            cost=DataSourceCost(amount_usd=0.0, paid=False, payment_method="free"),
        )

    def subscribe(
        self,
        capability: str,
        callback: Callable[[Any], None],
        **params: Any,
    ) -> Subscription | None:
        if capability not in self.capabilities:
            raise ValueError(f"WebSocketDataSource[{self.name}] does not support capability: {capability}")

        try:
            from importlib import import_module
            websocket = import_module("websocket")
        except ModuleNotFoundError:
            logger.warning("websocket-client not installed — WebSocketDataSource is disabled. Install with: pip install websocket-client")
            return None

        path_template = self.capabilities[capability]
        url = self.base_url + path_template.format(**params)

        stop_event = threading.Event()
        sub = _WSSubscription(thread=None, stop_event=stop_event)

        def on_message(_ws, message):
            try:
                parsed = json.loads(message) if isinstance(message, str) else message
            except json.JSONDecodeError:
                parsed = message
            try:
                callback(parsed)
            except Exception as error:
                logger.warning("WebSocket callback error: %s", error)

        def on_error(_ws, error):
            logger.warning("WebSocket error: %s", error)
            self.error_count += 1

        def run():
            ws = websocket.WebSocketApp(
                url,
                on_message=on_message,
                on_error=on_error,
            )
            sub.ws = ws
            while not stop_event.is_set():
                try:
                    ws.run_forever(ping_interval=30, ping_timeout=10)
                except Exception as error:
                    logger.warning("WebSocket run_forever error: %s", error)
                    break
                if stop_event.is_set():
                    break
                time.sleep(1)  # Reconnect backoff

        thread = threading.Thread(target=run, daemon=True)
        sub.thread = thread
        thread.start()
        return sub


# ---------------------------------------------------------------------------
# MCP (Model Context Protocol) data source
# ---------------------------------------------------------------------------

class McpDataSource(DataSource):
    """Data source backed by an MCP (Model Context Protocol) server.

    Discovers tools at init time via ``tools/list``, then routes ``fetch()``
    calls through ``tools/call``. The capability namespace is whatever the
    MCP server exposes — read-only tools, write tools, anything with a
    declared schema.

    Usage::

        from aether_forge.mcp_client import McpServerConfig
        from aether_forge.data_layer import McpDataSource

        config = McpServerConfig(name="hermes", command="hermes", args=["mcp", "serve"])
        mcp = McpDataSource(config)
        mcp.connect()  # spawns the subprocess and runs tools/list

        result = mcp.fetch("messages_send", platform="telegram", text="hello")

    By default the `McpDataSource` does NOT connect eagerly — call
    :meth:`connect` explicitly or run inside a context manager. The data
    router can also lazily call :meth:`supports` to probe capability names,
    which will auto-connect.
    """

    def __init__(self, config: Any) -> None:
        # `config` is an McpServerConfig but we accept Any to avoid a hard
        # import cycle with mcp_client — import is deferred to connect().
        super().__init__(config.name)
        self._config = config
        self._client: Any = None
        self._tools: dict[str, dict[str, Any]] = {}
        self._connected = False

    def connect(self) -> None:
        if self._connected:
            return
        from .mcp_client import build_mcp_client  # deferred

        self._client = build_mcp_client(self._config)
        try:
            tools = self._client.list_tools()
        except Exception as error:
            self.error_count += 1
            logger.warning("McpDataSource[%s] failed to list tools: %s", self.name, error)
            raise
        self._tools = {t.get("name", ""): t for t in tools if t.get("name")}
        self._connected = True
        logger.info(
            "McpDataSource[%s] connected — %d tools discovered: %s",
            self.name,
            len(self._tools),
            ", ".join(sorted(self._tools.keys())[:10]) + ("..." if len(self._tools) > 10 else ""),
        )

    def supports(self, capability: str) -> bool:
        if not self._connected:
            try:
                self.connect()
            except Exception:
                return False
        return capability in self._tools

    def fetch(self, capability: str, **params: Any) -> DataResult:
        if not self._connected:
            self.connect()
        if capability not in self._tools:
            raise ValueError(
                f"McpDataSource[{self.name}] does not expose tool: {capability}"
            )
        try:
            # MCP tools take a single 'arguments' dict. Strip reserved
            # keys that come from the DataRouter convention.
            arguments = {k: v for k, v in params.items() if k != "_body"}
            body = params.get("_body")
            if isinstance(body, dict):
                arguments = {**arguments, **body}
            response = self._client.call_tool(capability, arguments)
            self.fetch_count += 1
            return DataResult(
                source=self.name,
                capability=capability,
                data=response,
                cost=DataSourceCost(amount_usd=0.0, paid=False, payment_method="free"),
                metadata={"transport": self._config.transport},
            )
        except Exception as error:
            self.error_count += 1
            logger.warning("McpDataSource[%s] tool_call failed for %s: %s", self.name, capability, error)
            raise

    def tool_schema(self, capability: str) -> dict[str, Any] | None:
        """Return the MCP tool descriptor (name, description, inputSchema)."""
        return self._tools.get(capability)

    def available_tools(self) -> list[dict[str, Any]]:
        """Return the list of tool descriptors the server advertised."""
        if not self._connected:
            self.connect()
        return list(self._tools.values())

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
        self._connected = False
        self._client = None

    def status(self) -> dict[str, Any]:
        base = super().status()
        base["transport"] = self._config.transport
        base["connected"] = self._connected
        base["tool_count"] = len(self._tools)
        return base


# ---------------------------------------------------------------------------
# Mock data source (for tests)
# ---------------------------------------------------------------------------

class MockDataSource(DataSource):
    """Mock data source for tests — returns canned responses."""

    def __init__(self, name: str = "mock", responses: dict[str, Any] | None = None) -> None:
        super().__init__(name)
        self.responses = responses or {}

    def supports(self, capability: str) -> bool:
        return capability in self.responses

    def fetch(self, capability: str, **params: Any) -> DataResult:
        if capability not in self.responses:
            raise ValueError(f"MockDataSource[{self.name}] has no response for: {capability}")
        self.fetch_count += 1
        return DataResult(
            source=self.name,
            capability=capability,
            data=self.responses[capability],
        )


# ---------------------------------------------------------------------------
# Router — capability dispatch with fallback
# ---------------------------------------------------------------------------

class DataRouter:
    """Routes capability calls to the right data source.

    Tries sources in order until one succeeds (fallback chain).
    Tracks total cost across all sources.
    """

    def __init__(self, sources: list[DataSource]) -> None:
        self.sources = sources

    def add_source(self, source: DataSource) -> None:
        self.sources.append(source)

    def fetch(self, capability: str, **params: Any) -> DataResult:
        """Fetch from the first source that supports the capability and succeeds."""
        errors: list[str] = []
        for source in self.sources:
            if not source.supports(capability):
                continue
            try:
                return source.fetch(capability, **params)
            except Exception as error:
                errors.append(f"{source.name}: {error}")
                continue
        if not errors:
            raise ValueError(f"No source supports capability: {capability}")
        raise RuntimeError(f"All sources failed for {capability}: {' | '.join(errors)}")

    def subscribe(
        self,
        capability: str,
        callback: Callable[[Any], None],
        **params: Any,
    ) -> Subscription | None:
        """Subscribe via the first source that supports streaming for this capability."""
        for source in self.sources:
            if source.supports(capability):
                sub = source.subscribe(capability, callback, **params)
                if sub is not None:
                    return sub
        return None

    def call_source(self, source_name: str, capability: str, **params: Any) -> DataResult:
        """Call a specific source by name."""
        for source in self.sources:
            if source.name == source_name:
                return source.fetch(capability, **params)
        raise ValueError(f"No source named: {source_name}")

    @property
    def total_cost_usd(self) -> float:
        return sum(s.total_cost_usd for s in self.sources)

    def status(self) -> dict[str, Any]:
        return {
            "total_cost_usd": round(self.total_cost_usd, 6),
            "sources": [s.status() for s in self.sources],
        }


# ---------------------------------------------------------------------------
# Common pre-built sources
# ---------------------------------------------------------------------------

def build_binance_source() -> HTTPDataSource:
    """Free Binance public market data source."""
    return HTTPDataSource(
        "binance",
        base_url="https://api.binance.com",
        capabilities={
            "spot-price": ("GET", "/api/v3/ticker/price?symbol={symbol}"),
            "ticker-24h": ("GET", "/api/v3/ticker/24hr?symbol={symbol}"),
            "candles": ("GET", "/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"),
            "order-book": ("GET", "/api/v3/depth?symbol={symbol}&limit={limit}"),
        },
    )


def build_coingecko_source() -> HTTPDataSource:
    """Free CoinGecko price source."""
    return HTTPDataSource(
        "coingecko",
        base_url="https://api.coingecko.com",
        capabilities={
            "spot-price": ("GET", "/api/v3/simple/price?ids={ids}&vs_currencies=usd"),
            "coin-info": ("GET", "/api/v3/coins/{coin_id}"),
        },
    )


def build_elsa_source(
    agent_directory: Path | str,
    *,
    confirmed: bool = False,
    max_per_call_usd: float = 0.10,
    max_session_usd: float = 1.0,
    chain: str = "base",
) -> X402DataSource:
    """Elsa x402 paid data source. Requires --confirm-live to actually pay."""
    return X402DataSource(
        "elsa",
        base_url="https://x402-api.heyelsa.ai",
        agent_directory=agent_directory,
        confirmed=confirmed,
        max_per_call_usd=max_per_call_usd,
        max_session_usd=max_session_usd,
        chain=chain,
        capabilities={
            "search-token":         ("POST", "/api/search_token"),
            "get-token-price":      ("POST", "/api/get_token_price"),
            "get-balances":         ("POST", "/api/get_balances"),
            "get-portfolio":        ("POST", "/api/get_portfolio"),
            "analyze-wallet":       ("POST", "/api/analyze_wallet"),
            "get-pnl-report":       ("POST", "/api/get_pnl_report"),
            "get-swap-quote":       ("POST", "/api/get_swap_quote"),
            "execute-swap":         ("POST", "/api/execute_swap"),
            "create-limit-order":   ("POST", "/api/create_limit_order"),
            "get-limit-orders":     ("POST", "/api/get_limit_orders"),
            "cancel-limit-order":   ("POST", "/api/cancel_limit_order"),
            "get-perp-positions":   ("POST", "/api/get_perp_positions"),
            "open-perp-position":   ("POST", "/api/open_perp_position"),
            "close-perp-position":  ("POST", "/api/close_perp_position"),
            "get-stake-balances":   ("POST", "/api/get_stake_balances"),
            "get-yield-suggestions":("POST", "/api/get_yield_suggestions"),
            "check-airdrop":        ("POST", "/api/check_airdrop"),
            "claim-airdrop":        ("POST", "/api/claim_airdrop"),
            "get-transaction-history": ("POST", "/api/get_transaction_history"),
            "get-transaction-status":  ("POST", "/api/get_transaction_status"),
            "get-gas-prices":       ("POST", "/api/get_gas_prices"),
        },
    )


def build_mcp_source(config_or_dict: Any, *, name: str | None = None) -> McpDataSource:
    """Build an MCP data source from either an ``McpServerConfig`` or a
    plain dict (e.g. the ``mcp_servers:`` block from ``aether-forge.json``).

    Usage::

        from aether_forge.data_layer import build_mcp_source

        # From an McpServerConfig
        mcp = build_mcp_source(config)

        # From a raw dict
        mcp = build_mcp_source(
            {"command": "hermes", "args": ["mcp", "serve"]},
            name="hermes",
        )
    """
    from .mcp_client import McpServerConfig

    if isinstance(config_or_dict, McpServerConfig):
        return McpDataSource(config_or_dict)
    if not isinstance(config_or_dict, dict):
        raise TypeError(
            f"build_mcp_source expects McpServerConfig or dict, got {type(config_or_dict).__name__}"
        )
    if name is None:
        raise ValueError("build_mcp_source from a dict requires a 'name' argument")
    config = McpServerConfig.from_dict(name, config_or_dict)
    return McpDataSource(config)


def build_binance_websocket_source() -> WebSocketDataSource:
    """Free Binance public websocket streams."""
    return WebSocketDataSource(
        "binance-ws",
        base_url="wss://stream.binance.com:9443",
        capabilities={
            "trades": "/ws/{symbol}@trade",
            "klines": "/ws/{symbol}@kline_{interval}",
            "depth":  "/ws/{symbol}@depth",
            "ticker": "/ws/{symbol}@ticker",
        },
    )

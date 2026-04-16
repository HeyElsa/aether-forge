"""Tests for the generic data layer."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.data_layer import (
    DataResult,
    DataRouter,
    DataSourceCost,
    HTTPDataSource,
    MockDataSource,
    WebSocketDataSource,
    X402DataSource,
    build_binance_source,
    build_coingecko_source,
    build_elsa_source,
)


# ---------------------------------------------------------------------------
# HTTPDataSource
# ---------------------------------------------------------------------------

def test_http_source_supports_capability() -> None:
    source = HTTPDataSource(
        "test",
        base_url="https://api.example.com",
        capabilities={"price": ("GET", "/price/{symbol}")},
    )
    assert source.supports("price")
    assert not source.supports("missing")


def test_http_source_fetch_with_mock() -> None:
    def fake_request(method, url, headers, body):
        return {"status": 200, "body": {"price": 100}, "headers": {}}

    source = HTTPDataSource(
        "test",
        base_url="https://api.example.com",
        capabilities={"price": ("GET", "/price/{symbol}")},
        request_fn=fake_request,
    )
    result = source.fetch("price", symbol="ETH")
    assert result.source == "test"
    assert result.capability == "price"
    assert result.data == {"price": 100}
    assert result.cost.amount_usd == 0.0
    assert result.cost.payment_method == "free"
    assert source.fetch_count == 1


def test_http_source_unsupported_capability_raises() -> None:
    source = HTTPDataSource("test", base_url="https://api.example.com", capabilities={})
    with pytest.raises(ValueError, match="does not support"):
        source.fetch("missing")


def test_http_source_url_substitution() -> None:
    captured = {}

    def fake_request(method, url, headers, body):
        captured["url"] = url
        captured["method"] = method
        return {"status": 200, "body": {}}

    source = HTTPDataSource(
        "test",
        base_url="https://api.example.com",
        capabilities={"candles": ("GET", "/api/v3/klines?symbol={symbol}&interval={interval}")},
        request_fn=fake_request,
    )
    source.fetch("candles", symbol="ETHUSDT", interval="30m")
    assert captured["url"] == "https://api.example.com/api/v3/klines?symbol=ETHUSDT&interval=30m"


def test_http_source_status() -> None:
    source = HTTPDataSource("test", base_url="https://example.com", capabilities={})
    status = source.status()
    assert status["name"] == "test"
    assert status["fetch_count"] == 0
    assert status["error_count"] == 0
    assert status["total_cost_usd"] == 0.0


# ---------------------------------------------------------------------------
# X402DataSource
# ---------------------------------------------------------------------------

def test_x402_source_supports_capability(tmp_path: Path) -> None:
    source = X402DataSource(
        "elsa",
        base_url="https://x402.example.com",
        agent_directory=tmp_path,
        capabilities={"get-token-price": ("POST", "/api/get_token_price")},
    )
    assert source.supports("get-token-price")
    assert not source.supports("missing")


def test_x402_source_fetch_with_mock_payment_flow(tmp_path: Path, monkeypatch) -> None:
    """Wire X402DataSource to a mocked X402Client and verify call flow."""
    # Create wallet config
    (tmp_path / "wallet.json").write_text(json.dumps({
        "walletId": "test",
        "walletName": "test",
        "provider": "ows",
        "addresses": {"evm": "0x" + "a" * 40},
    }))

    source = X402DataSource(
        "elsa",
        base_url="https://x402.example.com",
        agent_directory=tmp_path,
        confirmed=True,
        capabilities={"get-token-price": ("POST", "/api/get_token_price")},
    )

    # Patch the lazy-loaded X402Client
    from aether_forge.x402_client import X402Client

    def fake_post(self, url, body=None, headers=None):
        return {"status": 200, "body": {"price": 2186.0}, "headers": {}}

    monkeypatch.setattr(X402Client, "post", fake_post)
    monkeypatch.setattr(X402Client, "status", lambda self: {"session_spent_usd": 0.002})

    result = source.fetch("get-token-price", _body={"token": "ETH", "chain": "base"})
    assert result.source == "elsa"
    assert result.data == {"price": 2186.0}
    assert result.cost.payment_method == "x402"
    assert source.total_cost_usd > 0


# ---------------------------------------------------------------------------
# MockDataSource
# ---------------------------------------------------------------------------

def test_mock_source_returns_canned() -> None:
    source = MockDataSource("mock", responses={"price": {"value": 100}})
    result = source.fetch("price")
    assert result.data == {"value": 100}
    assert source.fetch_count == 1


def test_mock_source_unsupported_raises() -> None:
    source = MockDataSource("mock")
    with pytest.raises(ValueError):
        source.fetch("missing")


# ---------------------------------------------------------------------------
# DataRouter
# ---------------------------------------------------------------------------

def test_router_routes_to_supporting_source() -> None:
    a = MockDataSource("a", responses={"x": "from-a"})
    b = MockDataSource("b", responses={"y": "from-b"})
    router = DataRouter([a, b])

    assert router.fetch("x").data == "from-a"
    assert router.fetch("y").data == "from-b"


def test_router_falls_back_on_failure() -> None:
    class FailingSource(MockDataSource):
        def fetch(self, capability, **params):
            raise RuntimeError("intentional failure")

    failing = FailingSource("failing", responses={"price": "should not return"})
    backup = MockDataSource("backup", responses={"price": "from-backup"})
    router = DataRouter([failing, backup])

    result = router.fetch("price")
    assert result.data == "from-backup"


def test_router_raises_when_all_fail() -> None:
    class FailingSource(MockDataSource):
        def fetch(self, capability, **params):
            raise RuntimeError("fail")

    a = FailingSource("a", responses={"price": "x"})
    b = FailingSource("b", responses={"price": "x"})
    router = DataRouter([a, b])

    with pytest.raises(RuntimeError, match="All sources failed"):
        router.fetch("price")


def test_router_unsupported_capability() -> None:
    a = MockDataSource("a", responses={"x": "x"})
    router = DataRouter([a])
    with pytest.raises(ValueError, match="No source supports"):
        router.fetch("missing")


def test_router_call_specific_source() -> None:
    a = MockDataSource("a", responses={"price": "from-a"})
    b = MockDataSource("b", responses={"price": "from-b"})
    router = DataRouter([a, b])

    assert router.call_source("b", "price").data == "from-b"
    assert router.call_source("a", "price").data == "from-a"


def test_router_total_cost_aggregates() -> None:
    a = MockDataSource("a", responses={"x": "x"})
    b = MockDataSource("b", responses={"y": "y"})
    a.total_cost_usd = 0.001
    b.total_cost_usd = 0.005
    router = DataRouter([a, b])
    assert router.total_cost_usd == pytest.approx(0.006)


def test_router_status_includes_all_sources() -> None:
    a = MockDataSource("a")
    b = MockDataSource("b")
    router = DataRouter([a, b])
    status = router.status()
    assert len(status["sources"]) == 2
    assert "total_cost_usd" in status


def test_router_add_source() -> None:
    router = DataRouter([])
    router.add_source(MockDataSource("new", responses={"x": "y"}))
    assert router.fetch("x").data == "y"


# ---------------------------------------------------------------------------
# Pre-built sources
# ---------------------------------------------------------------------------

def test_build_binance_source_has_capabilities() -> None:
    source = build_binance_source()
    assert source.name == "binance"
    assert source.supports("spot-price")
    assert source.supports("candles")
    assert source.supports("ticker-24h")


def test_build_coingecko_source() -> None:
    source = build_coingecko_source()
    assert source.name == "coingecko"
    assert source.supports("spot-price")


def test_build_elsa_source(tmp_path: Path) -> None:
    source = build_elsa_source(tmp_path, max_per_call_usd=0.01)
    assert source.name == "elsa"
    assert source.supports("get-token-price")
    assert source.supports("execute-swap")
    assert source.supports("get-gas-prices")


# ---------------------------------------------------------------------------
# WebSocket source (without websocket-client installed)
# ---------------------------------------------------------------------------

def test_websocket_source_returns_none_without_lib() -> None:
    """Subscribe should return None when websocket-client is not installed."""
    source = WebSocketDataSource(
        "test-ws",
        base_url="wss://example.com",
        capabilities={"trades": "/ws/{symbol}@trade"},
    )
    # Test will skip if websocket-client IS installed
    try:
        import websocket  # noqa: F401
        pytest.skip("websocket-client is installed; test only validates fallback")
    except ImportError:
        pass

    sub = source.subscribe("trades", lambda msg: None, symbol="ethusdt")
    assert sub is None


def test_websocket_source_supports() -> None:
    source = WebSocketDataSource(
        "binance-ws",
        base_url="wss://example.com",
        capabilities={"trades": "/ws/{symbol}@trade"},
    )
    assert source.supports("trades")
    assert not source.supports("missing")

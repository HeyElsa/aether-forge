"""Tests for the market data venue abstraction."""

from __future__ import annotations

import pytest

from aether_forge.market_data import (
    BinanceVenue,
    CoinGeckoVenue,
    MarketDataError,
    MarketDataRouter,
    MockVenue,
    build_market_data_router,
)


def test_mock_venue_returns_static_prices() -> None:
    venue = MockVenue(prices={"BTCUSDT": 70000.0})
    result = venue.fetch_spot_price("BTC/USDT")
    assert result["price"] == 70000.0
    assert result["venue"] == "mock"


def test_mock_venue_basis() -> None:
    venue = MockVenue()
    result = venue.fetch_basis("BTC-PERP")
    assert "basis_bps" in result
    assert "mark_price" in result


def test_binance_venue_spot_uses_request_fn() -> None:
    def fake_request(url: str) -> dict:
        assert "binance.com" in url
        assert "BTCUSDT" in url
        return {"symbol": "BTCUSDT", "price": "65123.45"}

    venue = BinanceVenue(request_fn=fake_request)
    result = venue.fetch_spot_price("BTC/USDT")
    assert result["price"] == 65123.45
    assert result["venue"] == "binance"


def test_binance_venue_basis_uses_request_fn() -> None:
    def fake_request(url: str) -> dict:
        assert "fapi.binance.com" in url
        return {
            "symbol": "BTCUSDT",
            "markPrice": "65100.0",
            "indexPrice": "65000.0",
            "lastFundingRate": "0.0001",
        }

    venue = BinanceVenue(request_fn=fake_request)
    result = venue.fetch_basis("BTCUSDT")
    assert result["basis_bps"] == pytest.approx(15.38, abs=0.1)
    assert result["mark_price"] == 65100.0


def test_coingecko_venue_spot_uses_request_fn() -> None:
    def fake_request(url: str) -> dict:
        assert "coingecko.com" in url
        assert "bitcoin" in url
        return {"bitcoin": {"usd": 65000.0}}

    venue = CoinGeckoVenue(request_fn=fake_request)
    result = venue.fetch_spot_price("BTC/USDT")
    assert result["price"] == 65000.0
    assert result["venue"] == "coingecko"


def test_coingecko_venue_basis_raises() -> None:
    venue = CoinGeckoVenue()
    with pytest.raises(MarketDataError, match="does not support"):
        venue.fetch_basis("BTCUSDT")


def test_router_tries_venues_in_order() -> None:
    def fail_request(url: str) -> dict:
        raise MarketDataError("venue down")

    failing = BinanceVenue(request_fn=fail_request)
    mock = MockVenue(prices={"BTCUSDT": 99999.0})

    router = MarketDataRouter([failing, mock])
    result = router.fetch_spot_price("BTC/USDT")
    assert result["venue"] == "mock"
    assert result["price"] == 99999.0


def test_router_raises_when_all_fail() -> None:
    def fail_request(url: str) -> dict:
        raise MarketDataError("down")

    router = MarketDataRouter([BinanceVenue(request_fn=fail_request)])
    with pytest.raises(MarketDataError, match="All venues failed"):
        router.fetch_spot_price("BTC/USDT")


def test_build_market_data_router_mock() -> None:
    router = build_market_data_router(["mock"])
    assert router.venue_names == ["mock"]
    result = router.fetch_spot_price("BTC/USDT")
    assert result["venue"] == "mock"


def test_build_market_data_router_multiple() -> None:
    router = build_market_data_router(["binance", "coingecko", "mock"])
    assert router.venue_names == ["binance", "coingecko", "mock"]


def test_build_market_data_router_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown"):
        build_market_data_router(["nonexistent-venue"])


def test_router_venue_names_property() -> None:
    router = MarketDataRouter([MockVenue(), BinanceVenue()])
    assert "mock" in router.venue_names
    assert "binance" in router.venue_names

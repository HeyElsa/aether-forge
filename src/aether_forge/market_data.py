"""Market data venue abstraction for Aether Forge.

Provides a pluggable interface for fetching market data from multiple
venues, decoupling the runtime from any single exchange.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any, Protocol
from urllib import request as urllib_request
from urllib.error import URLError

logger = logging.getLogger(__name__)


class MarketDataError(RuntimeError):
    """Raised when a market data request fails."""


class MarketDataVenue(Protocol):
    """Protocol for market data providers."""

    @property
    def venue_name(self) -> str: ...

    def fetch_spot_price(self, symbol: str) -> dict[str, Any]: ...

    def fetch_basis(self, symbol: str) -> dict[str, Any]: ...


def _default_json_get(url: str) -> dict[str, Any]:
    req = urllib_request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib_request.urlopen(req, timeout=10) as response:  # noqa: S310
            return json.loads(response.read().decode("utf8"))
    except (URLError, TimeoutError) as error:
        raise MarketDataError(f"Market data request failed: {url}: {error}") from error


def _normalize_symbol(symbol: str) -> str:
    return symbol.replace("/", "").replace("-", "")


class BinanceVenue:
    """Binance spot and futures market data."""

    def __init__(self, request_fn: Callable[[str], dict[str, Any]] | None = None) -> None:
        self._request = request_fn or _default_json_get

    @property
    def venue_name(self) -> str:
        return "binance"

    def fetch_spot_price(self, symbol: str) -> dict[str, Any]:
        normalized = _normalize_symbol(symbol)
        logger.debug("Fetching Binance spot price: %s", normalized)
        payload = self._request(f"https://api.binance.com/api/v3/ticker/price?symbol={normalized}")
        return {
            "venue": self.venue_name,
            "symbol": payload.get("symbol", normalized),
            "price": float(payload["price"]),
        }

    def fetch_basis(self, symbol: str) -> dict[str, Any]:
        normalized = _normalize_symbol(symbol)
        if normalized.endswith("PERP"):
            normalized = normalized.replace("PERP", "USDT")
        logger.debug("Fetching Binance basis: %s", normalized)
        payload = self._request(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={normalized}")
        mark_price = float(payload["markPrice"])
        index_price = float(payload["indexPrice"])
        basis_bps = ((mark_price - index_price) / index_price) * 10000 if index_price else 0.0
        return {
            "venue": self.venue_name,
            "symbol": payload.get("symbol", normalized),
            "mark_price": mark_price,
            "index_price": index_price,
            "basis_bps": basis_bps,
            "last_funding_rate": float(payload.get("lastFundingRate", 0.0)),
        }


class CoinGeckoVenue:
    """CoinGecko free API for spot prices (no API key required)."""

    def __init__(self, request_fn: Callable[[str], dict[str, Any]] | None = None) -> None:
        self._request = request_fn or _default_json_get

    @property
    def venue_name(self) -> str:
        return "coingecko"

    def fetch_spot_price(self, symbol: str) -> dict[str, Any]:
        coin_id = _coingecko_coin_id(symbol)
        logger.debug("Fetching CoinGecko spot price: %s -> %s", symbol, coin_id)
        payload = self._request(
            f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        )
        price = payload.get(coin_id, {}).get("usd")
        if price is None:
            raise MarketDataError(f"CoinGecko returned no price for {coin_id}")
        return {
            "venue": self.venue_name,
            "symbol": symbol,
            "price": float(price),
        }

    def fetch_basis(self, symbol: str) -> dict[str, Any]:
        raise MarketDataError("CoinGecko does not support basis/funding data")


class MockVenue:
    """Mock venue for testing — returns static prices."""

    def __init__(self, prices: dict[str, float] | None = None) -> None:
        self._prices = prices or {"BTCUSDT": 65000.0, "ETHUSDT": 3500.0}

    @property
    def venue_name(self) -> str:
        return "mock"

    def fetch_spot_price(self, symbol: str) -> dict[str, Any]:
        normalized = _normalize_symbol(symbol)
        price = self._prices.get(normalized, 100.0)
        return {"venue": self.venue_name, "symbol": normalized, "price": price}

    def fetch_basis(self, symbol: str) -> dict[str, Any]:
        return {
            "venue": self.venue_name,
            "symbol": _normalize_symbol(symbol),
            "mark_price": 65000.0,
            "index_price": 64950.0,
            "basis_bps": 7.7,
            "last_funding_rate": 0.0001,
        }


class MarketDataRouter:
    """Routes market data requests to the appropriate venue.

    Falls back through venues in order until one succeeds.

    Usage::

        router = MarketDataRouter([BinanceVenue(), CoinGeckoVenue()])
        price = router.fetch_spot_price("BTC/USDT")
    """

    def __init__(self, venues: list[MarketDataVenue] | None = None) -> None:
        self._venues = venues or [MockVenue()]

    @property
    def venue_names(self) -> list[str]:
        return [v.venue_name for v in self._venues]

    def fetch_spot_price(self, symbol: str) -> dict[str, Any]:
        errors: list[str] = []
        for venue in self._venues:
            try:
                result = venue.fetch_spot_price(symbol)
                logger.debug("Spot price from %s: %s", venue.venue_name, result.get("price"))
                return result
            except (MarketDataError, Exception) as error:
                logger.debug("Venue %s failed for spot %s: %s", venue.venue_name, symbol, error)
                errors.append(f"{venue.venue_name}: {error}")
        raise MarketDataError(f"All venues failed for spot price {symbol}: {'; '.join(errors)}")

    def fetch_basis(self, symbol: str) -> dict[str, Any]:
        errors: list[str] = []
        for venue in self._venues:
            try:
                result = venue.fetch_basis(symbol)
                logger.debug("Basis from %s: %s bps", venue.venue_name, result.get("basis_bps"))
                return result
            except (MarketDataError, Exception) as error:
                logger.debug("Venue %s failed for basis %s: %s", venue.venue_name, symbol, error)
                errors.append(f"{venue.venue_name}: {error}")
        raise MarketDataError(f"All venues failed for basis {symbol}: {'; '.join(errors)}")


def build_market_data_router(
    venues: list[str] | None = None,
    request_fn: Callable[[str], dict[str, Any]] | None = None,
) -> MarketDataRouter:
    """Build a market data router from venue names.

    Supported venues: ``binance``, ``coingecko``, ``mock``.
    Defaults to ``[mock]`` if no venues specified.
    """
    venue_names = venues or ["mock"]
    venue_objects: list[MarketDataVenue] = []
    for name in venue_names:
        lower = name.lower()
        if lower == "binance":
            venue_objects.append(BinanceVenue(request_fn=request_fn))
        elif lower == "coingecko":
            venue_objects.append(CoinGeckoVenue(request_fn=request_fn))
        elif lower == "mock":
            venue_objects.append(MockVenue())
        else:
            raise ValueError(f"Unknown market data venue: {name}")
    return MarketDataRouter(venue_objects)


_COINGECKO_SYMBOL_MAP = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "SOL": "solana",
    "USDT": "tether",
    "USDC": "usd-coin",
    "BNB": "binancecoin",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "AVAX": "avalanche-2",
    "DOT": "polkadot",
    "LINK": "chainlink",
    "MATIC": "matic-network",
    "UNI": "uniswap",
    "AAVE": "aave",
}


def _coingecko_coin_id(symbol: str) -> str:
    """Convert a trading pair or ticker to a CoinGecko coin ID."""
    clean = symbol.upper().replace("/", "").replace("-", "").replace("USDT", "").replace("USD", "")
    return _COINGECKO_SYMBOL_MAP.get(clean, clean.lower())

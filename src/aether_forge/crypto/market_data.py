"""Public market data backends."""

from __future__ import annotations

from typing import Any

from .types import RequestFn
from .utils import _default_json_request, _normalize_perp_symbol, _normalize_spot_symbol


class BinancePublicMarketDataBackend:
    def __init__(self, request_fn: RequestFn | None = None) -> None:
        self.request_fn = request_fn or _default_json_request

    def fetch_spot_price(self, symbol: str) -> dict[str, Any]:
        provider_symbol = _normalize_spot_symbol(symbol)
        payload = self.request_fn(
            f"https://api.binance.com/api/v3/ticker/price?symbol={provider_symbol}"
        )
        return {
            "symbol": payload.get("symbol", provider_symbol),
            "price": float(payload["price"]),
        }

    def fetch_basis(self, symbol: str) -> dict[str, Any]:
        provider_symbol = _normalize_perp_symbol(symbol)
        payload = self.request_fn(
            f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={provider_symbol}"
        )
        mark_price = float(payload["markPrice"])
        index_price = float(payload["indexPrice"])
        basis_bps = ((mark_price - index_price) / index_price) * 10000 if index_price else 0.0
        return {
            "symbol": payload.get("symbol", provider_symbol),
            "mark_price": mark_price,
            "index_price": index_price,
            "basis_bps": basis_bps,
            "last_funding_rate": float(payload.get("lastFundingRate", 0.0)),
        }

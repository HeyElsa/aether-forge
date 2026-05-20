"""Exchange adapters for crypto capabilities."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from .types import CredentialLease, PaperPosition


class LiveExchangeAdapter(Protocol):
    def place_order(
        self,
        *,
        venue: str,
        symbol: str,
        requested_notional_usd: float,
        side: str,
        credential_lease: CredentialLease,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def cancel_order(
        self,
        *,
        venue: str,
        order_id: str,
        credential_lease: CredentialLease,
    ) -> dict[str, Any]: ...

    def get_account_snapshot(
        self,
        *,
        venue: str,
        credential_lease: CredentialLease,
    ) -> dict[str, Any]: ...


class DisabledLiveExchangeAdapter:
    """Safe default live exchange adapter.

    The framework exposes the interface but refuses live execution until a
    developer supplies an explicit adapter implementation.
    """

    def _raise(self, venue: str) -> None:
        raise RuntimeError(
            f"Live exchange adapter for venue {venue} is disabled by default. "
            "Implement LiveExchangeAdapter and wire it explicitly before enabling live execution."
        )

    def place_order(
        self,
        *,
        venue: str,
        symbol: str,
        requested_notional_usd: float,
        side: str,
        credential_lease: CredentialLease,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._raise(venue)

    def cancel_order(
        self,
        *,
        venue: str,
        order_id: str,
        credential_lease: CredentialLease,
    ) -> dict[str, Any]:
        self._raise(venue)

    def get_account_snapshot(
        self,
        *,
        venue: str,
        credential_lease: CredentialLease,
    ) -> dict[str, Any]:
        self._raise(venue)


class InMemoryPaperExchangeAdapter:
    def __init__(self, starting_balance_usd: float = 20_000.0) -> None:
        self.starting_balance_usd = starting_balance_usd
        self.balance_usd = starting_balance_usd
        self.total_notional_usd = 0.0
        self.positions: dict[str, PaperPosition] = {}
        self.orders: list[dict[str, Any]] = []

    def place_order(
        self,
        *,
        venue: str,
        symbol: str,
        requested_notional_usd: float,
        side: str,
        credential_lease: CredentialLease,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        order_id = f"paper_order_{uuid4().hex}"
        self.total_notional_usd += requested_notional_usd
        self.positions[symbol] = PaperPosition(symbol=symbol, notional_usd=requested_notional_usd, side=side)
        safe_metadata = dict(metadata or {})
        self.orders.append(
            {
                "orderId": order_id,
                "venue": venue,
                "symbol": symbol,
                "requestedNotionalUsd": requested_notional_usd,
                "side": side,
                "credentialHandleId": credential_lease.handle_id,
                "metadata": safe_metadata,
            }
        )
        return {
            "submitted": True,
            "order_id": order_id,
            "venue": venue,
            "symbol": symbol,
            "requested_notional_usd": requested_notional_usd,
            "side": side,
            "paper": True,
            "metadata": safe_metadata,
        }

    def get_account_snapshot(self, *, venue: str, credential_lease: CredentialLease) -> dict[str, Any]:
        return {
            "venue": venue,
            "balance_usd": self.balance_usd,
            "total_notional_usd": self.total_notional_usd,
            "positions": [
                {
                    "symbol": position.symbol,
                    "notional_usd": position.notional_usd,
                    "side": position.side,
                }
                for position in self.positions.values()
            ],
            "order_count": len(self.orders),
            "credentialHandleId": credential_lease.handle_id,
            "paper": True,
        }


def canonical_order_result(
    raw: dict[str, Any],
    *,
    execution_mode: str,
    venue: str,
    symbol: str,
    requested_notional_usd: float,
    side: str,
) -> dict[str, Any]:
    """Return a stable paper/live order result shape while preserving raw fields."""
    order_id = raw.get("order_id") or raw.get("orderId") or raw.get("venue_order_id") or raw.get("client_order_id")
    canonical = {
        **raw,
        "submitted": bool(raw.get("submitted", bool(order_id))),
        "order_id": str(order_id or ""),
        "venue": str(raw.get("venue", venue)),
        "symbol": str(raw.get("symbol", symbol)),
        "requested_notional_usd": float(raw.get("requested_notional_usd", raw.get("requestedNotionalUsd", requested_notional_usd))),
        "side": str(raw.get("side", side)),
        "execution_mode": execution_mode,
    }
    return canonical


def canonical_account_snapshot(
    raw: dict[str, Any],
    *,
    execution_mode: str,
    venue: str,
) -> dict[str, Any]:
    """Return a stable paper/live account snapshot shape while preserving raw fields."""
    positions = raw.get("positions", [])
    if not isinstance(positions, list):
        positions = []
    return {
        **raw,
        "venue": str(raw.get("venue", venue)),
        "balance_usd": float(raw.get("balance_usd", raw.get("balanceUsd", 0.0))),
        "total_notional_usd": float(raw.get("total_notional_usd", raw.get("totalNotionalUsd", 0.0))),
        "positions": positions,
        "order_count": int(raw.get("order_count", raw.get("orderCount", 0))),
        "execution_mode": execution_mode,
    }

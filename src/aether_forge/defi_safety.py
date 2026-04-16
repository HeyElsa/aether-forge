"""DeFi safety utilities for autonomous agents.

This module provides defense-in-depth helpers for agents that move real
money on-chain:

- ``simulate_tx()``           — eth_call before signing to detect reverts
- ``check_slippage()``        — verify a swap quote's min-out is within bounds
- ``ExposureTracker``         — track per-protocol portfolio concentration
- ``check_position_health()`` — monitor lending position liquidation risk

All functions are pure-stdlib (no web3.py dep) and return typed results so
the runtime can act on them via the policy gate.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any
from urllib import request as urllib_request

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transaction simulation (eth_call)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SimulationResult:
    """Result of an eth_call simulation against an unsigned tx."""

    success: bool
    return_data: str = ""           # hex-encoded return data
    revert_reason: str = ""         # decoded revert string if available
    estimated_gas: int = 0          # from eth_estimateGas if requested


def simulate_tx(
    rpc_url: str,
    *,
    from_address: str,
    to_address: str,
    data: str,
    value: str = "0x0",
    timeout_seconds: float = 10.0,
) -> SimulationResult:
    """Simulate a transaction via eth_call before signing.

    Returns a :class:`SimulationResult`. If the call would revert, the result
    has ``success=False`` and a (best-effort) decoded ``revert_reason``.

    This is the primary safety check before signing any swap, transfer, or
    contract interaction. Catches: reverts, out-of-gas, broken contract state,
    incorrect calldata.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "eth_call",
        "params": [
            {
                "from": from_address,
                "to": to_address,
                "data": data,
                "value": value,
            },
            "latest",
        ],
    }
    try:
        req = urllib_request.Request(
            rpc_url,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib_request.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            body = json.loads(response.read())
    except Exception as error:
        logger.warning("simulate_tx RPC error: %s", error)
        return SimulationResult(success=False, revert_reason=f"RPC error: {error}")

    if "error" in body:
        msg = body["error"].get("message", "unknown error")
        # Standard "execution reverted: <reason>" pattern
        return SimulationResult(success=False, revert_reason=msg)

    return SimulationResult(success=True, return_data=body.get("result", ""))


# ---------------------------------------------------------------------------
# Slippage protection
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SwapQuote:
    """A swap quote returned by a router."""

    token_in: str
    token_out: str
    amount_in: int           # raw units of token_in
    amount_out: int          # raw units of token_out (expected)
    min_amount_out: int      # raw units of token_out (minimum acceptable)
    price_impact_pct: float  # how much this trade moves the market


@dataclass(slots=True)
class SlippageCheck:
    safe: bool
    reason: str = ""


def check_slippage(
    quote: SwapQuote,
    *,
    max_slippage_pct: float = 1.0,
    max_price_impact_pct: float = 3.0,
) -> SlippageCheck:
    """Verify a swap quote is within acceptable slippage bounds.

    Two checks:
    1. ``min_amount_out`` is at least ``(1 - max_slippage_pct/100) * amount_out``.
       Catches routers that promise X but accept far less.
    2. ``price_impact_pct`` doesn't exceed ``max_price_impact_pct``.
       Catches thin-liquidity pools where the trade itself moves price badly.
    """
    if quote.amount_out <= 0:
        return SlippageCheck(safe=False, reason="quote has zero amount_out")

    expected_min = quote.amount_out * (100 - max_slippage_pct) / 100
    if quote.min_amount_out < expected_min:
        actual_slippage = (quote.amount_out - quote.min_amount_out) / quote.amount_out * 100
        return SlippageCheck(
            safe=False,
            reason=f"slippage tolerance {actual_slippage:.2f}% exceeds max {max_slippage_pct}%",
        )

    if quote.price_impact_pct > max_price_impact_pct:
        return SlippageCheck(
            safe=False,
            reason=f"price impact {quote.price_impact_pct:.2f}% exceeds max {max_price_impact_pct}%",
        )

    return SlippageCheck(safe=True)


# ---------------------------------------------------------------------------
# Exposure tracking — concentration risk
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class ExposureTracker:
    """Tracks portfolio concentration across protocols and tokens.

    The agent records each position via ``record_position()``. Before opening
    a new position, call ``check_concentration()`` to verify it doesn't push
    a single protocol or token above the configured limit.
    """

    max_per_protocol_pct: float = 30.0
    max_per_token_pct: float = 50.0
    positions: dict[str, dict[str, float]] = field(default_factory=dict)
    # positions[protocol_or_token]["usd_value"]

    def record_position(self, key: str, usd_value: float) -> None:
        """Record or update a position. Use protocol name (e.g., 'aave') or
        token symbol ('ETH') as the key."""
        self.positions[key] = {"usd_value": usd_value}

    def total_value(self) -> float:
        return sum(p.get("usd_value", 0.0) for p in self.positions.values())

    def concentration_pct(self, key: str) -> float:
        """Percentage of portfolio in a given protocol/token."""
        total = self.total_value()
        if total <= 0:
            return 0.0
        return self.positions.get(key, {}).get("usd_value", 0.0) / total * 100

    def check_concentration(
        self,
        key: str,
        new_usd_value: float,
        *,
        is_protocol: bool = False,
    ) -> tuple[bool, str]:
        """Check if adding ``new_usd_value`` to ``key`` would breach concentration.

        Returns (allowed, reason). Use ``is_protocol=True`` for protocol-level
        checks (max_per_protocol_pct), False for token-level (max_per_token_pct).
        """
        future_total = self.total_value() + new_usd_value
        future_position = self.positions.get(key, {}).get("usd_value", 0.0) + new_usd_value
        if future_total <= 0:
            return (True, "no portfolio yet")
        future_pct = future_position / future_total * 100
        limit = self.max_per_protocol_pct if is_protocol else self.max_per_token_pct
        if future_pct > limit:
            return (
                False,
                f"would put {future_pct:.1f}% in {key}, exceeds {limit}% limit",
            )
        return (True, "ok")


# ---------------------------------------------------------------------------
# Lending position health (liquidation monitoring)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PositionHealth:
    """Health metrics for a lending position."""

    health_factor: float    # Aave/Compound style: <1.0 = liquidatable
    collateral_usd: float
    debt_usd: float
    liquidation_threshold: float  # e.g., 0.83 for 83%

    @property
    def at_risk(self) -> bool:
        """True if health factor is within 20% of liquidation threshold."""
        return self.health_factor < 1.2

    @property
    def critical(self) -> bool:
        """True if health factor is within 5% of liquidation threshold."""
        return self.health_factor < 1.05


def check_position_health(
    *,
    collateral_usd: float,
    debt_usd: float,
    liquidation_threshold: float = 0.83,
) -> PositionHealth:
    """Compute health factor for a lending position.

    health_factor = (collateral * liquidation_threshold) / debt

    A health factor below 1.0 means the position can be liquidated. The
    framework treats <1.2 as "at risk" (warning) and <1.05 as "critical"
    (immediate action needed).
    """
    if debt_usd <= 0:
        # No debt = no liquidation risk
        return PositionHealth(
            health_factor=float("inf"),
            collateral_usd=collateral_usd,
            debt_usd=0.0,
            liquidation_threshold=liquidation_threshold,
        )
    health_factor = (collateral_usd * liquidation_threshold) / debt_usd
    return PositionHealth(
        health_factor=health_factor,
        collateral_usd=collateral_usd,
        debt_usd=debt_usd,
        liquidation_threshold=liquidation_threshold,
    )

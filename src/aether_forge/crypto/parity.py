"""Paper/live exchange parity helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ORDER_RESULT_KEYS = {
    "submitted",
    "order_id",
    "venue",
    "symbol",
    "requested_notional_usd",
    "side",
    "execution_mode",
}

ACCOUNT_SNAPSHOT_KEYS = {
    "venue",
    "balance_usd",
    "total_notional_usd",
    "positions",
    "order_count",
    "execution_mode",
}


@dataclass(slots=True)
class ParityReport:
    """Shape-level parity report for paper/live adapter outputs."""

    ok: bool
    mismatches: list[str] = field(default_factory=list)


def compare_order_result_shape(paper: dict[str, Any], live: dict[str, Any]) -> ParityReport:
    return _compare_shape("order", paper, live, ORDER_RESULT_KEYS)


def compare_account_snapshot_shape(paper: dict[str, Any], live: dict[str, Any]) -> ParityReport:
    return _compare_shape("account", paper, live, ACCOUNT_SNAPSHOT_KEYS)


def _compare_shape(
    label: str,
    paper: dict[str, Any],
    live: dict[str, Any],
    required_keys: set[str],
) -> ParityReport:
    mismatches: list[str] = []
    for side, payload in (("paper", paper), ("live", live)):
        missing = sorted(required_keys - set(payload))
        if missing:
            mismatches.append(f"{label}.{side} missing keys: {missing}")
    for key in sorted(required_keys & set(paper) & set(live)):
        if key == "execution_mode":
            continue
        paper_type = type(paper[key])
        live_type = type(live[key])
        if paper_type is not live_type:
            mismatches.append(
                f"{label}.{key} type differs: paper={paper_type.__name__}, live={live_type.__name__}"
            )
    return ParityReport(ok=not mismatches, mismatches=mismatches)

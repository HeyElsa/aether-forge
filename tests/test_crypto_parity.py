from __future__ import annotations

from pathlib import Path
from typing import Any

from aether_forge.crypto import (
    AuthenticatedPaperTradingCryptoExecutionRouter,
    InMemoryPaperExchangeAdapter,
    compare_account_snapshot_shape,
    compare_order_result_shape,
)
from aether_forge.runtime import RuntimeSession, StepKind, StepProposal, load_artifact_bundle

REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


class FakeLiveExchangeAdapter:
    def __init__(self) -> None:
        self.orders: list[dict[str, Any]] = []

    def place_order(
        self,
        *,
        venue: str,
        symbol: str,
        requested_notional_usd: float,
        side: str,
        credential_lease,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.orders.append(dict(metadata or {}))
        return {
            "venue_order_id": "live-order-1",
            "submitted": True,
            "venue": venue,
            "symbol": symbol,
            "requestedNotionalUsd": requested_notional_usd,
            "side": side,
            "credentialHandleId": credential_lease.handle_id,
        }

    def cancel_order(self, *, venue: str, order_id: str, credential_lease) -> dict[str, Any]:
        return {"cancelled": True, "venue": venue, "order_id": order_id}

    def get_account_snapshot(self, *, venue: str, credential_lease) -> dict[str, Any]:
        return {
            "venue": venue,
            "balanceUsd": 20_000.0,
            "totalNotionalUsd": 2_500.0,
            "positions": [{"symbol": "BTCUSDT", "notional_usd": 2500.0, "side": "sell"}],
            "orderCount": 1,
            "credentialHandleId": credential_lease.handle_id,
        }


def _session_and_caps():
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    order_capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-exchange-order"
    )
    balance_capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-exchange-balance"
    )
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=lambda session: [],
        execution_router=AuthenticatedPaperTradingCryptoExecutionRouter(),
    )
    return session, order_capability, balance_capability


def test_paper_and_live_order_results_share_canonical_shape() -> None:
    session, order_capability, _balance_capability = _session_and_caps()
    paper_adapter = InMemoryPaperExchangeAdapter()
    live_adapter = FakeLiveExchangeAdapter()
    router = AuthenticatedPaperTradingCryptoExecutionRouter(
        paper_exchange_adapter=paper_adapter,
        live_exchange_adapter=live_adapter,
    )
    payload = {"requested_notional_usd": 2500, "side": "sell"}

    paper = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Paper order.",
            capability_id="cap-exchange-order",
            payload=payload,
        ),
        order_capability,
    )
    live = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Live order.",
            capability_id="cap-exchange-order",
            payload={**payload, "execution_mode": "live"},
        ),
        order_capability,
    )

    assert paper.success is True
    assert live.success is True
    report = compare_order_result_shape(paper.output, live.output)
    assert report.ok, report.mismatches
    assert paper.output["execution_mode"] == "paper"
    assert live.output["execution_mode"] == "live"
    assert live.output["order_id"] == "live-order-1"
    assert live_adapter.orders == [{"capabilityId": "cap-exchange-order"}]


def test_paper_and_live_account_snapshots_share_canonical_shape() -> None:
    session, order_capability, balance_capability = _session_and_caps()
    paper_adapter = InMemoryPaperExchangeAdapter()
    live_adapter = FakeLiveExchangeAdapter()
    router = AuthenticatedPaperTradingCryptoExecutionRouter(
        paper_exchange_adapter=paper_adapter,
        live_exchange_adapter=live_adapter,
    )
    router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Seed paper order.",
            capability_id="cap-exchange-order",
            payload={"requested_notional_usd": 2500, "side": "sell"},
        ),
        order_capability,
    )

    paper = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Paper account.",
            capability_id="cap-exchange-balance",
            payload={},
        ),
        balance_capability,
    )
    live = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Live account.",
            capability_id="cap-exchange-balance",
            payload={"execution_mode": "live"},
        ),
        balance_capability,
    )

    assert paper.success is True
    assert live.success is True
    report = compare_account_snapshot_shape(paper.output, live.output)
    assert report.ok, report.mismatches
    assert paper.output["execution_mode"] == "paper"
    assert live.output["execution_mode"] == "live"

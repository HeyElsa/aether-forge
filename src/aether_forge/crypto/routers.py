"""Crypto execution routers."""

from __future__ import annotations

from typing import Any

from ..runtime import ExecutionResult, RuntimeSession, StepProposal
from .credentials import CredentialResolver, ManifestCredentialResolver
from .exchanges import (
    DisabledLiveExchangeAdapter,
    InMemoryPaperExchangeAdapter,
    LiveExchangeAdapter,
    canonical_account_snapshot,
    canonical_order_result,
)
from .market_data import BinancePublicMarketDataBackend
from .types import RequestFn
from .wallets import InMemorySimWalletAdapter, OpenWalletStandardAdapter


class MockCryptoExecutionRouter:
    """Mock crypto execution used by native runtime evals.

    This keeps crypto-specific behavior out of the generic eval module while the
    first real adapter layer is still being built.
    """

    def execute(
        self,
        session: RuntimeSession,
        proposal: StepProposal,
        capability: dict[str, Any],
    ) -> ExecutionResult:
        inputs = session.session_state.get("scenario_inputs", {})
        capability_id = proposal.capability_id

        if capability_id == "cap-market-btc-price":
            return ExecutionResult(
                success=True,
                output={
                    "symbol": capability.get("providerConstraints", {}).get("symbol", "BTC/USDT"),
                    "price": 65000,
                    "market_data_age_ms": proposal.payload.get("market_data_age_ms", inputs.get("marketDataAgeMs", 0)),
                },
            )

        if capability_id == "cap-market-basis":
            return ExecutionResult(
                success=True,
                output={
                    "symbol": capability.get("providerConstraints", {}).get("symbol", "BTC-PERP"),
                    "basis_bps": proposal.payload.get("basis_bps", inputs.get("basisBps", 0)),
                    "volatility_regime": proposal.payload.get("volatility_regime", inputs.get("volatilityRegime", "normal")),
                },
            )

        if capability_id == "cap-exchange-order":
            return ExecutionResult(
                success=True,
                output={
                    "submitted": True,
                    "requested_notional_usd": proposal.payload.get("requested_notional_usd"),
                    "venue": capability.get("providerConstraints", {}).get("venue", "unknown"),
                    "market_type": capability.get("providerConstraints", {}).get("marketType", "unknown"),
                },
            )

        if capability_id == "cap-exchange-balance":
            return ExecutionResult(
                success=True,
                output={
                    "balance_usd": 20000,
                    "positions": [],
                },
            )

        if capability_id == "cap-context-read":
            return ExecutionResult(
                success=True,
                output={
                    "context": "Project context loaded successfully.",
                },
            )

        return ExecutionResult(success=False, failure_reason=f"No mock crypto router for capability {capability_id}")


class PublicMarketDataCryptoExecutionRouter:
    """Hybrid router: real public market data, mocked stateful/private actions."""

    def __init__(self, request_fn: RequestFn | None = None) -> None:
        self.backend = BinancePublicMarketDataBackend(request_fn=request_fn)
        self.mock_router = MockCryptoExecutionRouter()

    def execute(
        self,
        session: RuntimeSession,
        proposal: StepProposal,
        capability: dict[str, Any],
    ) -> ExecutionResult:
        capability_id = proposal.capability_id
        provider = capability.get("provider")
        constraints = capability.get("providerConstraints", {})

        if capability_id == "cap-market-btc-price" and provider == "binance-spot-public":
            market_data = self.backend.fetch_spot_price(str(constraints.get("symbol", "BTC/USDT")))
            return ExecutionResult(
                success=True,
                output={
                    **market_data,
                    "market_data_age_ms": proposal.payload.get(
                        "market_data_age_ms",
                        session.session_state.get("scenario_inputs", {}).get("marketDataAgeMs", 0),
                    ),
                },
            )

        if capability_id == "cap-market-basis" and provider == "binance-futures-public":
            basis_data = self.backend.fetch_basis(str(constraints.get("symbol", "BTCUSDT")))
            return ExecutionResult(
                success=True,
                output={
                    **basis_data,
                    "volatility_regime": proposal.payload.get(
                        "volatility_regime",
                        session.session_state.get("scenario_inputs", {}).get("volatilityRegime", "normal"),
                    ),
                },
            )

        return self.mock_router.execute(session, proposal, capability)


class AuthenticatedPaperTradingCryptoExecutionRouter:
    """Hybrid router for private paper execution plus public market reads."""

    def __init__(
        self,
        *,
        credential_resolver: CredentialResolver | None = None,
        paper_exchange_adapter: InMemoryPaperExchangeAdapter | None = None,
        live_exchange_adapter: LiveExchangeAdapter | None = None,
        fallback_router: PublicMarketDataCryptoExecutionRouter | None = None,
    ) -> None:
        self.credential_resolver = credential_resolver or ManifestCredentialResolver()
        self.paper_exchange_adapter = paper_exchange_adapter or InMemoryPaperExchangeAdapter()
        self.live_exchange_adapter = live_exchange_adapter or DisabledLiveExchangeAdapter()
        self.fallback_router = fallback_router or PublicMarketDataCryptoExecutionRouter()

    def execute(
        self,
        session: RuntimeSession,
        proposal: StepProposal,
        capability: dict[str, Any],
    ) -> ExecutionResult:
        kind = capability.get("kind")
        handle_id = capability.get("credentialHandleId")
        venue = capability.get("providerConstraints", {}).get("venue", capability.get("provider", "paper-exchange"))

        if kind == "exchange-action" and isinstance(handle_id, str):
            lease = self.credential_resolver.resolve(handle_id, session.environment, session.artifacts.capability_manifest)
            symbol = str(capability.get("providerConstraints", {}).get("symbol", proposal.payload.get("symbol", "BTCUSDT")))
            requested_notional_usd = float(proposal.payload.get("requested_notional_usd", 0.0))
            side = str(proposal.payload.get("side", "sell"))
            execution_mode = str(proposal.payload.get("execution_mode", capability.get("providerConstraints", {}).get("executionMode", "paper")))

            if execution_mode == "live":
                raw_output = self.live_exchange_adapter.place_order(
                    venue=str(venue),
                    symbol=symbol,
                    requested_notional_usd=requested_notional_usd,
                    side=side,
                    credential_lease=lease,
                    metadata={"capabilityId": capability.get("capabilityId")},
                )
                return ExecutionResult(
                    success=True,
                    output=canonical_order_result(
                        raw_output,
                        execution_mode="live",
                        venue=str(venue),
                        symbol=symbol,
                        requested_notional_usd=requested_notional_usd,
                        side=side,
                    ),
                )

            raw_output = self.paper_exchange_adapter.place_order(
                venue=str(venue),
                symbol=symbol,
                requested_notional_usd=requested_notional_usd,
                side=side,
                credential_lease=lease,
                metadata={"capabilityId": capability.get("capabilityId")},
            )
            return ExecutionResult(
                success=True,
                output=canonical_order_result(
                    raw_output,
                    execution_mode="paper",
                    venue=str(venue),
                    symbol=symbol,
                    requested_notional_usd=requested_notional_usd,
                    side=side,
                ),
            )

        fields = capability.get("providerConstraints", {}).get("fields", [])
        if kind == "data-source" and isinstance(handle_id, str) and isinstance(fields, list) and any(field in {"balances", "positions"} for field in fields):
            lease = self.credential_resolver.resolve(handle_id, session.environment, session.artifacts.capability_manifest)
            execution_mode = str(proposal.payload.get("execution_mode", capability.get("providerConstraints", {}).get("executionMode", "paper")))

            if execution_mode == "live":
                raw_output = self.live_exchange_adapter.get_account_snapshot(
                    venue=str(venue),
                    credential_lease=lease,
                )
                return ExecutionResult(
                    success=True,
                    output=canonical_account_snapshot(
                        raw_output,
                        execution_mode="live",
                        venue=str(venue),
                    ),
                )

            raw_output = self.paper_exchange_adapter.get_account_snapshot(
                venue=str(venue),
                credential_lease=lease,
            )
            return ExecutionResult(
                success=True,
                output=canonical_account_snapshot(
                    raw_output,
                    execution_mode="paper",
                    venue=str(venue),
                ),
            )

        return self.fallback_router.execute(session, proposal, capability)


class SimWalletCryptoExecutionRouter:
    """Hybrid router that adds simulated wallet actions on top of paper trading/public data."""

    def __init__(
        self,
        *,
        credential_resolver: CredentialResolver | None = None,
        wallet_adapter: InMemorySimWalletAdapter | None = None,
        fallback_router: AuthenticatedPaperTradingCryptoExecutionRouter | None = None,
    ) -> None:
        self.credential_resolver = credential_resolver or ManifestCredentialResolver()
        self.wallet_adapter = wallet_adapter or InMemorySimWalletAdapter()
        self.fallback_router = fallback_router or AuthenticatedPaperTradingCryptoExecutionRouter(
            credential_resolver=self.credential_resolver,
        )

    def execute(
        self,
        session: RuntimeSession,
        proposal: StepProposal,
        capability: dict[str, Any],
    ) -> ExecutionResult:
        kind = capability.get("kind")
        handle_id = capability.get("credentialHandleId")
        constraints = capability.get("providerConstraints", {})
        chain = str(constraints.get("chain", proposal.payload.get("chain", "ethereum")))

        if kind == "wallet-action" and isinstance(handle_id, str):
            lease = self.credential_resolver.resolve(handle_id, session.environment, session.artifacts.capability_manifest)
            action = str(proposal.payload.get("wallet_action", "get-account"))

            if action == "create-account":
                return ExecutionResult(
                    success=True,
                    output=self.wallet_adapter.create_account(chain=chain, alias=proposal.payload.get("alias")),
                )

            if action == "send-transaction":
                return ExecutionResult(
                    success=True,
                    output=self.wallet_adapter.send_transaction(
                        chain=chain,
                        to_address=str(proposal.payload.get("to_address", "sim_unknown")),
                        amount=float(proposal.payload.get("amount", 0.0)),
                        credential_lease=lease,
                    ),
                )

            return ExecutionResult(
                success=True,
                output=self.wallet_adapter.get_account(
                    chain=chain,
                    address=proposal.payload.get("address"),
                ),
            )

        return self.fallback_router.execute(session, proposal, capability)


class OWSWalletCryptoExecutionRouter:
    """Wallet-action router backed by Open Wallet Standard bindings."""

    def __init__(
        self,
        *,
        credential_resolver: CredentialResolver | None = None,
        wallet_adapter: OpenWalletStandardAdapter | None = None,
        fallback_router: SimWalletCryptoExecutionRouter | None = None,
    ) -> None:
        self.credential_resolver = credential_resolver or ManifestCredentialResolver()
        self.wallet_adapter = wallet_adapter or OpenWalletStandardAdapter()
        self.fallback_router = fallback_router or SimWalletCryptoExecutionRouter(
            credential_resolver=self.credential_resolver,
        )

    def execute(
        self,
        session: RuntimeSession,
        proposal: StepProposal,
        capability: dict[str, Any],
    ) -> ExecutionResult:
        kind = capability.get("kind")
        provider = capability.get("provider")
        handle_id = capability.get("credentialHandleId")
        constraints = capability.get("providerConstraints", {})

        if kind == "wallet-action" and provider == "ows-wallet" and isinstance(handle_id, str):
            _lease = self.credential_resolver.resolve(handle_id, session.environment, session.artifacts.capability_manifest)
            chain = str(constraints.get("chain", proposal.payload.get("chain", "evm")))
            wallet_name = str(constraints.get("walletName", proposal.payload.get("wallet_name", "agent-wallet")))
            action = str(proposal.payload.get("wallet_action", "get-account"))

            if action == "create-wallet":
                return ExecutionResult(success=True, output=self.wallet_adapter.create_wallet(wallet_name))

            if action == "sign-message":
                return ExecutionResult(
                    success=True,
                    output=self.wallet_adapter.sign_message(
                        wallet_name,
                        chain,
                        str(proposal.payload.get("message", "")),
                    ),
                )

            if action == "sign-transaction":
                return ExecutionResult(
                    success=True,
                    output=self.wallet_adapter.sign_transaction(
                        wallet_name,
                        chain,
                        str(proposal.payload.get("tx_hex", "")),
                        send=bool(proposal.payload.get("send", False)),
                        rpc_url=proposal.payload.get("rpc_url"),
                    ),
                )

            return ExecutionResult(success=True, output=self.wallet_adapter.get_account(wallet_name, chain))

        return self.fallback_router.execute(session, proposal, capability)

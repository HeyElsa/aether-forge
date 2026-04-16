from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from aether_forge.crypto import (
    AuthenticatedPaperTradingCryptoExecutionRouter,
    DisabledLiveExchangeAdapter,
    InMemoryPaperExchangeAdapter,
    InMemorySimWalletAdapter,
    ManifestCredentialResolver,
    MockCryptoExecutionRouter,
    OWSWalletCryptoExecutionRouter,
    OpenWalletStandardAdapter,
    PublicMarketDataCryptoExecutionRouter,
    SimWalletCryptoExecutionRouter,
    load_crypto_capabilities,
)
from aether_forge.runtime import RuntimeSession, StepKind, StepProposal, load_artifact_bundle


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def test_load_crypto_capabilities_extracts_declared_descriptors() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)

    descriptors = load_crypto_capabilities(artifacts.capability_manifest)

    assert "cap-exchange-order" in descriptors
    assert descriptors["cap-exchange-order"].kind == "exchange-action"
    assert descriptors["cap-exchange-order"].effect_semantics is not None


def test_mock_crypto_router_executes_declared_market_capability() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-market-btc-price"
    )

    class DummySession:
        session_state = {"scenario_inputs": {"marketDataAgeMs": 1000}}

    result = MockCryptoExecutionRouter().execute(
        DummySession(),
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Read BTC spot price.",
            capability_id="cap-market-btc-price",
            payload={"market_data_age_ms": 1000},
        ),
        capability,
    )

    assert result.success is True
    assert result.output["symbol"] == "BTC/USDT"


def test_public_market_data_router_translates_spot_price_request() -> None:
    requested_urls: list[str] = []

    def fake_request(url: str) -> dict[str, object]:
        requested_urls.append(url)
        return {"symbol": "BTCUSDT", "price": "65000.00"}

    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-market-btc-price"
    )

    class DummySession:
        session_state = {"scenario_inputs": {"marketDataAgeMs": 1000}}

    result = PublicMarketDataCryptoExecutionRouter(request_fn=fake_request).execute(
        DummySession(),
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Read BTC spot price.",
            capability_id="cap-market-btc-price",
            payload={"market_data_age_ms": 1000},
        ),
        capability,
    )

    assert requested_urls == ["https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"]
    assert result.success is True
    assert result.output["price"] == 65000.0


def test_public_market_data_router_translates_basis_request() -> None:
    requested_urls: list[str] = []

    def fake_request(url: str) -> dict[str, object]:
        requested_urls.append(url)
        return {
            "symbol": "BTCUSDT",
            "markPrice": "65100.0",
            "indexPrice": "65000.0",
            "lastFundingRate": "0.0001",
        }

    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-market-basis"
    )

    class DummySession:
        session_state = {"scenario_inputs": {"volatilityRegime": "normal"}}

    result = PublicMarketDataCryptoExecutionRouter(request_fn=fake_request).execute(
        DummySession(),
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Read BTC basis.",
            capability_id="cap-market-basis",
            payload={},
        ),
        capability,
    )

    assert requested_urls == ["https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT"]
    assert result.success is True
    assert round(result.output["basis_bps"], 4) == round(((65100.0 - 65000.0) / 65000.0) * 10000, 4)


def test_public_market_data_router_falls_back_to_mock_for_non_public_capabilities() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-exchange-balance"
    )

    class DummySession:
        session_state = {"scenario_inputs": {}}

    result = PublicMarketDataCryptoExecutionRouter(request_fn=lambda url: {}).execute(
        DummySession(),
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Read balances.",
            capability_id="cap-exchange-balance",
            payload={},
        ),
        capability,
    )

    assert result.success is True
    assert result.output["balance_usd"] == 20000


def test_manifest_credential_resolver_enforces_environment_scope() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    resolver = ManifestCredentialResolver()

    lease = resolver.resolve("cred_market_data", "sandbox", artifacts.capability_manifest)

    assert lease.handle_id == "cred_market_data"
    assert lease.environment == "sandbox"


def test_paper_trading_router_executes_authenticated_exchange_order() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    adapter = InMemoryPaperExchangeAdapter()
    router = AuthenticatedPaperTradingCryptoExecutionRouter(
        paper_exchange_adapter=adapter,
        fallback_router=PublicMarketDataCryptoExecutionRouter(request_fn=lambda url: {"symbol": "BTCUSDT", "price": "65000.0"}),
    )
    capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-exchange-order"
    )

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=lambda session: [],
        execution_router=router,
    )
    result = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Place paper hedge order.",
            capability_id="cap-exchange-order",
            payload={"requested_notional_usd": 2500, "side": "sell"},
        ),
        capability,
    )

    assert result.success is True
    assert result.output["paper"] is True
    assert result.output["requested_notional_usd"] == 2500


def test_paper_trading_router_reads_authenticated_account_snapshot() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    adapter = InMemoryPaperExchangeAdapter()
    router = AuthenticatedPaperTradingCryptoExecutionRouter(
        paper_exchange_adapter=adapter,
        fallback_router=PublicMarketDataCryptoExecutionRouter(request_fn=lambda url: {"symbol": "BTCUSDT", "price": "65000.0"}),
    )

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
        execution_router=router,
    )
    router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Place paper hedge order.",
            capability_id="cap-exchange-order",
            payload={"requested_notional_usd": 3000, "side": "sell"},
        ),
        order_capability,
    )
    balance_result = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Read paper account state.",
            capability_id="cap-exchange-balance",
            payload={},
        ),
        balance_capability,
    )

    assert balance_result.success is True
    assert balance_result.output["paper"] is True
    assert balance_result.output["order_count"] == 1


def test_sim_wallet_adapter_creates_account_and_reads_it_back() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    artifacts.capability_manifest["credentialHandles"].append(
        {
            "handleId": "cred_sim_wallet",
            "kind": "wallet-session",
            "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
            "maximumAccessScope": {"resources": ["wallet:create", "wallet:read", "wallet:send"]},
            "rotationExpectation": "session",
            "ttlPolicy": {"maxSessionMinutes": 15},
        }
    )
    wallet_capability = {
        "capabilityId": "cap-wallet-manage",
        "kind": "wallet-action",
        "provider": "sim-wallet",
        "riskLevel": "medium",
        "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
        "requiredApproval": False,
        "credentialHandleId": "cred_sim_wallet",
        "providerConstraints": {"chain": "ethereum"},
        "effectSemantics": {
            "idempotencyClass": "conditionally-idempotent",
            "duplicateSubmitBehavior": "none",
            "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
            "compensationClass": "compensatable",
        },
    }

    wallet_adapter = InMemorySimWalletAdapter()
    router = SimWalletCryptoExecutionRouter(wallet_adapter=wallet_adapter)
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=lambda session: [],
        execution_router=router,
    )

    create_result = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Create a simulated wallet account.",
            capability_id="cap-wallet-manage",
            payload={"wallet_action": "create-account", "alias": "treasury"},
        ),
        wallet_capability,
    )
    read_result = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Read the simulated wallet account.",
            capability_id="cap-wallet-manage",
            payload={"wallet_action": "get-account", "address": create_result.output["address"]},
        ),
        wallet_capability,
    )

    assert create_result.success is True
    assert create_result.output["paper"] is True
    assert read_result.success is True
    assert read_result.output["address"] == create_result.output["address"]


def test_sim_wallet_router_can_send_simulated_transaction() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    artifacts.capability_manifest["credentialHandles"].append(
        {
            "handleId": "cred_sim_wallet",
            "kind": "wallet-session",
            "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
            "maximumAccessScope": {"resources": ["wallet:create", "wallet:read", "wallet:send"]},
            "rotationExpectation": "session",
            "ttlPolicy": {"maxSessionMinutes": 15},
        }
    )
    wallet_capability = {
        "capabilityId": "cap-wallet-manage",
        "kind": "wallet-action",
        "provider": "sim-wallet",
        "riskLevel": "high",
        "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
        "requiredApproval": False,
        "credentialHandleId": "cred_sim_wallet",
        "providerConstraints": {"chain": "ethereum"},
        "effectSemantics": {
            "idempotencyClass": "conditionally-idempotent",
            "duplicateSubmitBehavior": "none",
            "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
            "compensationClass": "compensatable",
        },
    }

    wallet_adapter = InMemorySimWalletAdapter()
    router = SimWalletCryptoExecutionRouter(wallet_adapter=wallet_adapter)
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=lambda session: [],
        execution_router=router,
    )

    router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Create a simulated wallet account.",
            capability_id="cap-wallet-manage",
            payload={"wallet_action": "create-account"},
        ),
        wallet_capability,
    )
    send_result = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Send a simulated wallet transaction.",
            capability_id="cap-wallet-manage",
            payload={
                "wallet_action": "send-transaction",
                "to_address": "sim_receiver_123",
                "amount": 1.25,
            },
        ),
        wallet_capability,
    )

    assert send_result.success is True
    assert send_result.output["paper"] is True
    assert send_result.output["to_address"] == "sim_receiver_123"


def test_open_wallet_standard_adapter_uses_bindings_contract() -> None:
    class FakeOWSBindings:
        def create_wallet(self, name: str, passphrase=None, words=12, vault_path=None):
            return {
                "id": "wallet-1",
                "name": name,
                "accounts": [
                    {
                        "chain_id": "eip155:1",
                        "address": "0xabc",
                        "derivation_path": "m/44'/60'/0'/0/0",
                    }
                ],
            }

        def get_wallet(self, name_or_id: str, vault_path=None):
            return self.create_wallet(name_or_id)

        def list_wallets(self, vault_path=None):
            return [self.create_wallet("agent-treasury")]

        def sign_message(self, wallet: str, chain: str, message: str, passphrase=None, encoding=None, index=None, vault_path=None):
            return {"signature": "sig-123", "recovery_id": 1}

        def sign_transaction(self, wallet: str, chain: str, tx_hex: str, passphrase=None, index=None, vault_path=None):
            return {"signature": "tx-sig", "recovery_id": 0}

        def sign_and_send(self, wallet: str, chain: str, tx_hex: str, passphrase=None, index=None, rpc_url=None, vault_path=None):
            return {"tx_hash": "0xdeadbeef"}

    adapter = OpenWalletStandardAdapter(bindings=FakeOWSBindings())

    created = adapter.create_wallet("agent-treasury")
    account = adapter.get_account("agent-treasury", "evm")
    sig = adapter.sign_message("agent-treasury", "evm", "hello")
    signed_tx = adapter.sign_transaction("agent-treasury", "evm", "0xabc")
    sent_tx = adapter.sign_transaction("agent-treasury", "evm", "0xabc", send=True, rpc_url="https://rpc.example")

    assert created["name"] == "agent-treasury"
    assert account["address"] == "0xabc"
    assert sig["signature"] == "sig-123"
    assert signed_tx["signature"] == "tx-sig"
    assert sent_tx["tx_hash"] == "0xdeadbeef"


def test_ows_wallet_router_executes_wallet_actions_with_fake_bindings() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    artifacts.capability_manifest["credentialHandles"].append(
        {
            "handleId": "cred_wallet_access",
            "kind": "wallet-session",
            "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
            "maximumAccessScope": {"resources": ["wallet:create", "wallet:read", "wallet:sign"]},
            "rotationExpectation": "session",
            "ttlPolicy": {"maxSessionMinutes": 15},
        }
    )
    wallet_capability = {
        "capabilityId": "cap-wallet-manage",
        "kind": "wallet-action",
        "provider": "ows-wallet",
        "riskLevel": "high",
        "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
        "requiredApproval": False,
        "credentialHandleId": "cred_wallet_access",
        "providerConstraints": {"chain": "evm", "walletName": "agent-treasury"},
        "effectSemantics": {
            "idempotencyClass": "conditionally-idempotent",
            "duplicateSubmitBehavior": "none",
            "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
            "compensationClass": "compensatable",
        },
    }

    class FakeOWSBindings:
        def create_wallet(self, name: str, passphrase=None, words=12, vault_path=None):
            return {
                "id": "wallet-1",
                "name": name,
                "accounts": [
                    {
                        "chain_id": "eip155:1",
                        "address": "0xabc",
                        "derivation_path": "m/44'/60'/0'/0/0",
                    }
                ],
            }

        def get_wallet(self, name_or_id: str, vault_path=None):
            return self.create_wallet(name_or_id)

        def list_wallets(self, vault_path=None):
            return [self.create_wallet("agent-treasury")]

        def sign_message(self, wallet: str, chain: str, message: str, passphrase=None, encoding=None, index=None, vault_path=None):
            return {"signature": "sig-123", "recovery_id": 1}

        def sign_transaction(self, wallet: str, chain: str, tx_hex: str, passphrase=None, index=None, vault_path=None):
            return {"signature": "tx-sig", "recovery_id": 0}

        def sign_and_send(self, wallet: str, chain: str, tx_hex: str, passphrase=None, index=None, rpc_url=None, vault_path=None):
            return {"tx_hash": "0xdeadbeef"}

    router = OWSWalletCryptoExecutionRouter(
        wallet_adapter=OpenWalletStandardAdapter(bindings=FakeOWSBindings()),
    )
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=lambda session: [],
        execution_router=router,
    )

    create_result = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Create an OWS wallet.",
            capability_id="cap-wallet-manage",
            payload={"wallet_action": "create-wallet"},
        ),
        wallet_capability,
    )
    sign_result = router.execute(
        session,
        StepProposal(
            kind=StepKind.USE_CAPABILITY,
            description="Sign a message with OWS.",
            capability_id="cap-wallet-manage",
            payload={"wallet_action": "sign-message", "message": "hello"},
        ),
        wallet_capability,
    )

    assert create_result.success is True
    assert create_result.output["name"] == "agent-treasury"
    assert sign_result.success is True
    assert sign_result.output["signature"] == "sig-123"


def test_load_ows_bindings_accepts_open_wallet_standard_module_name(monkeypatch) -> None:
    import aether_forge.crypto.utils as crypto_utils

    def fake_import(name: str):
        if name == "ows":
            return SimpleNamespace(create_wallet=lambda *args, **kwargs: {"id": "wallet-1"})
        raise ModuleNotFoundError(name)

    monkeypatch.setattr(crypto_utils, "import_module", fake_import)

    bindings = crypto_utils._load_ows_bindings()

    assert hasattr(bindings, "create_wallet")


def test_disabled_live_exchange_adapter_raises_by_default() -> None:
    lease = ManifestCredentialResolver().resolve(
        "cred_binance_trade",
        "sandbox",
        load_artifact_bundle(EXAMPLE_DIR).capability_manifest,
    )

    adapter = DisabledLiveExchangeAdapter()

    try:
        adapter.place_order(
            venue="binance",
            symbol="BTCUSDT",
            requested_notional_usd=1000,
            side="sell",
            credential_lease=lease,
        )
    except RuntimeError as error:
        assert "disabled by default" in str(error)
    else:
        raise AssertionError("Expected live exchange adapter to be disabled by default")


def test_authenticated_router_uses_disabled_live_exchange_adapter_for_live_mode() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)
    router = AuthenticatedPaperTradingCryptoExecutionRouter()
    capability = next(
        capability
        for capability in artifacts.capability_manifest["capabilities"]
        if capability["capabilityId"] == "cap-exchange-order"
    )
    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=lambda session: [],
        execution_router=router,
    )

    try:
        router.execute(
            session,
            StepProposal(
                kind=StepKind.USE_CAPABILITY,
                description="Attempt a live exchange action.",
                capability_id="cap-exchange-order",
                payload={
                    "requested_notional_usd": 1000,
                    "execution_mode": "live",
                },
            ),
            capability,
        )
    except RuntimeError as error:
        assert "disabled by default" in str(error)
    else:
        raise AssertionError("Expected router to fail when live exchange adapter is not supplied")

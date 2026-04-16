"""Crypto capability layer for Aether Forge."""

from __future__ import annotations

from .credentials import CredentialResolver, ManifestCredentialResolver
from .exchanges import DisabledLiveExchangeAdapter, InMemoryPaperExchangeAdapter, LiveExchangeAdapter
from .market_data import BinancePublicMarketDataBackend
from .routers import (
    AuthenticatedPaperTradingCryptoExecutionRouter,
    MockCryptoExecutionRouter,
    OWSWalletCryptoExecutionRouter,
    PublicMarketDataCryptoExecutionRouter,
    SimWalletCryptoExecutionRouter,
)
from .types import CRYPTO_KINDS, CredentialLease, CryptoCapabilityDescriptor, PaperPosition, RequestFn, SimWalletAccount
from .utils import (
    _default_json_request,
    _load_ows_bindings,
    _normalize_perp_symbol,
    _normalize_spot_symbol,
    _ows_chain_matches,
    load_crypto_capabilities,
)
from .wallets import InMemorySimWalletAdapter, OpenWalletStandardAdapter, OWSBindings

__all__ = [
    "CRYPTO_KINDS",
    "RequestFn",
    "CryptoCapabilityDescriptor",
    "CredentialLease",
    "PaperPosition",
    "SimWalletAccount",
    "CredentialResolver",
    "ManifestCredentialResolver",
    "LiveExchangeAdapter",
    "DisabledLiveExchangeAdapter",
    "InMemoryPaperExchangeAdapter",
    "OWSBindings",
    "InMemorySimWalletAdapter",
    "OpenWalletStandardAdapter",
    "MockCryptoExecutionRouter",
    "PublicMarketDataCryptoExecutionRouter",
    "AuthenticatedPaperTradingCryptoExecutionRouter",
    "SimWalletCryptoExecutionRouter",
    "OWSWalletCryptoExecutionRouter",
    "BinancePublicMarketDataBackend",
    "load_crypto_capabilities",
]

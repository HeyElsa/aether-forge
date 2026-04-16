"""Crypto capability layer for Aether Forge."""

from __future__ import annotations

from .types import CryptoCapabilityDescriptor, CredentialLease, PaperPosition, SimWalletAccount, CRYPTO_KINDS, RequestFn
from .credentials import CredentialResolver, ManifestCredentialResolver
from .exchanges import LiveExchangeAdapter, DisabledLiveExchangeAdapter, InMemoryPaperExchangeAdapter
from .wallets import OWSBindings, InMemorySimWalletAdapter, OpenWalletStandardAdapter
from .routers import (
    MockCryptoExecutionRouter,
    PublicMarketDataCryptoExecutionRouter,
    AuthenticatedPaperTradingCryptoExecutionRouter,
    SimWalletCryptoExecutionRouter,
    OWSWalletCryptoExecutionRouter,
)
from .market_data import BinancePublicMarketDataBackend
from .utils import load_crypto_capabilities, _default_json_request, _normalize_spot_symbol, _normalize_perp_symbol, _load_ows_bindings, _ows_chain_matches

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

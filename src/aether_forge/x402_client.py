"""Generic x402 payment client for Aether Forge agents.

Implements the x402 protocol (https://x402.org) for paying API endpoints
with EIP-3009 transferWithAuthorization signatures. Chain-agnostic, works
with any x402-protected endpoint (Elsa, future providers, custom APIs).

Flow:
1. Make request → get 402 response
2. Parse PaymentRequirement
3. Check budget cap
4. Sign EIP-3009 payment authorization via OWS wallet
5. Encode X-Payment header (base64 JSON)
6. Retry request with payment
7. Audit log
"""

from __future__ import annotations

import base64
import json
import logging
import secrets
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

# USDC contract addresses by chain
USDC_CONTRACTS = {
    "base": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
    "base-sepolia": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "ethereum": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
    "polygon": "0x3c499c542cEF5E3811e1192ce70d8cC03d5c3359",
    "arbitrum": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",
    "optimism": "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85",
}

# Chain IDs (CAIP-2)
CHAIN_IDS = {
    "base": 8453,
    "base-sepolia": 84532,
    "ethereum": 1,
    "polygon": 137,
    "arbitrum": 42161,
    "optimism": 10,
}


# Sprint 2.3 helpers — used by _sign_authorization to build the SigningIntent
# passed through the DelegatedSigner protocol. ``network`` here is the x402
# network identifier as it appears in PaymentRequirement (string-form chain
# slug like "base", "ethereum"). Returns None when unknown so the constrained
# signer can refuse fail-closed.


def _chain_id_for_network(network: str | None) -> int | None:
    if not network:
        return None
    return CHAIN_IDS.get(network.lower())


def _network_key(network: str | None) -> str | None:
    if not network:
        return None
    raw = network.lower()
    if raw in CHAIN_IDS:
        return raw
    if raw.startswith("eip155:"):
        try:
            chain_id = int(raw.split(":", 1)[1])
        except ValueError:
            return None
        for name, known_id in CHAIN_IDS.items():
            if chain_id == known_id:
                return name
    return None


def _network_matches(target_network: str, offered_network: str) -> bool:
    target_key = _network_key(target_network)
    offered_key = _network_key(offered_network)
    return target_key is not None and offered_key is not None and target_key == offered_key


def _looks_like_hex(value: str) -> bool:
    return all(char in "0123456789abcdefABCDEF" for char in value)


def _looks_like_evm_address(value: str) -> bool:
    return value.startswith("0x") and len(value) == 42 and _looks_like_hex(value[2:])


def _micros_to_usd(micros: int) -> float:
    """Convert USDC's 6-decimal integer units into a USD float for SigningIntent.
    Pure helper — does NOT replace ``_micro_to_usd`` if one exists elsewhere
    for transport accounting."""
    return micros / 1_000_000.0


class X402Error(RuntimeError):
    """Base exception for x402 client errors."""


class PaymentBudgetError(X402Error):
    """Raised when a payment would exceed budget caps."""


class HaltedError(X402Error):
    """Raised when the kill switch (halt file) is active."""


class PaymentSigningError(X402Error):
    """Raised when EIP-3009 signing fails."""


@dataclass(slots=True)
class X402Config:
    """Hard safety configuration for x402 client."""

    max_per_call_usd: float = 0.10  # First-run cap
    max_session_usd: float = 1.00  # Per-session total cap
    max_daily_usd: float = 5.00  # Per-day cap
    chain: str = "base"
    require_confirm: bool = True  # Require explicit confirmation flag
    confirmed: bool = False  # Set by --confirm-live
    halt_file: str = "halt"  # Kill switch path (relative to agent dir)
    audit_log_path: str | None = None  # Defaults to agent_dir/x402_audit.jsonl
    check_balance: bool = True  # Query on-chain USDC balance before signing
    rpc_url: str | None = None  # Override RPC for balance checks


@dataclass(slots=True)
class X402State:
    """Mutable state — persisted across runs."""

    session_spent_usd: float = 0.0
    daily_spent_usd: dict[str, float] = field(default_factory=dict)
    total_calls: int = 0
    total_payments: int = 0
    total_failures: int = 0


@dataclass(slots=True)
class PaymentRequirement:
    """Parsed x402 payment requirement from a 402 response."""

    scheme: str  # "exact" for EIP-3009
    network: str  # CAIP-2 like "eip155:8453" or chain name
    max_amount_required: str  # In smallest unit (wei for ETH, 6-decimal for USDC)
    pay_to: str  # Recipient address
    asset: str  # Token contract address
    resource: str  # The URL being paid for
    description: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def amount_usd(self) -> float:
        """Convert maxAmountRequired to USD (assumes USDC, 6 decimals)."""
        try:
            return float(self.max_amount_required) / 1_000_000
        except (ValueError, TypeError):
            return 0.0


class X402Client:
    """Production x402 payment client.

    Usage::

        client = X402Client(
            agent_directory=Path("./my-agent"),
            config=X402Config(max_per_call_usd=0.10, confirmed=True),
        )
        response = client.get("https://api.elsa.dev/v1/get-gas-prices")
        # Returns dict with the API response, after handling 402 + payment

    Safety:
    - Halt file check before every call
    - Per-call budget cap
    - Session + daily caps
    - Audit log entry for every attempt
    - Requires confirmed=True (set by --confirm-live)
    """

    def __init__(
        self,
        *,
        agent_directory: Path | str,
        config: X402Config,
        request_fn: Callable | None = None,
        sign_typed_data_fn: Callable | None = None,
        signer: Any | None = None,
    ) -> None:
        """Construct an X402Client.

        ``signer`` (v0.22.0+, Sprint 2.3 / FP-3) is the recommended hook for
        delegated / browser-relay / HSM-backed signing. Must satisfy the
        :class:`aether_forge.crypto.signers.DelegatedSigner` protocol. When
        both ``signer`` and ``sign_typed_data_fn`` are passed, ``signer``
        wins; ``sign_typed_data_fn`` is logged as deprecated.
        """
        self.agent_directory = Path(agent_directory).resolve()
        self.config = config
        self._request_fn = request_fn  # Injectable for testing
        self._sign_typed_data_fn = sign_typed_data_fn  # Injectable (deprecated; use ``signer``)
        if sign_typed_data_fn is not None and signer is None:
            logger.warning(
                "X402Client(sign_typed_data_fn=...) is deprecated. "
                "Pass a DelegatedSigner via signer= instead (aether_forge.crypto.signers). "
                "The legacy callable will be removed in v0.24.0."
            )
        self._signer = signer

        # Audit log
        if config.audit_log_path:
            self._audit_path = Path(config.audit_log_path)
        else:
            self._audit_path = self.agent_directory / "x402_audit.jsonl"
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)

        self._halt_path = self.agent_directory / config.halt_file

        # Persistent state — survives restarts
        self._state_path = self.agent_directory / "x402_state.json"
        self._state_lock_path = self.agent_directory / "x402_state.lock"
        self.state = self._load_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> dict[str, Any]:
        """GET request with x402 payment handling."""
        return self._call(method="GET", url=url, headers=headers, body=None)

    def post(
        self,
        url: str,
        *,
        body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """POST request with x402 payment handling."""
        return self._call(method="POST", url=url, headers=headers, body=body)

    def status(self) -> dict[str, Any]:
        """Current state for monitoring."""
        today = datetime.now(UTC).date().isoformat()
        return {
            "session_spent_usd": round(self.state.session_spent_usd, 6),
            "daily_spent_usd": round(self.state.daily_spent_usd.get(today, 0.0), 6),
            "total_calls": self.state.total_calls,
            "total_payments": self.state.total_payments,
            "total_failures": self.state.total_failures,
            "session_remaining_usd": round(self.config.max_session_usd - self.state.session_spent_usd, 6),
            "daily_remaining_usd": round(self.config.max_daily_usd - self.state.daily_spent_usd.get(today, 0.0), 6),
            "halted": self._halt_path.exists(),
            "confirmed": self.config.confirmed,
            "chain": self.config.chain,
        }

    # ------------------------------------------------------------------
    # Internal request handling
    # ------------------------------------------------------------------

    def _call(
        self,
        *,
        method: str,
        url: str,
        headers: dict[str, str] | None,
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Core request flow with x402 handling."""
        # 1. Pre-flight checks
        self._preflight()

        self.state.total_calls += 1
        headers = dict(headers or {})

        # 2. Initial request
        first = self._do_request(method, url, headers, body)

        if first.get("status") != 402:
            return first

        # 3. Parse payment requirement
        try:
            requirement = self._parse_402_response(first, url)
        except Exception as error:
            self.state.total_failures += 1
            self._audit("payment_parse_failed", {"url": url, "error": str(error)})
            raise X402Error(f"Could not parse 402 response: {error}") from error

        # Budget check, payment execution, and state mutation are one critical
        # section. This prevents concurrent processes from using stale budget
        # state to overspend the same x402 session or daily cap.
        with self._state_lock():
            self.state = self._load_state()
            self.state.total_calls += 1
            return self._execute_paid_call(method, url, headers, body, requirement)

    def _execute_paid_call(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None,
        requirement: PaymentRequirement,
    ) -> dict[str, Any]:
        # 4. Budget check
        amount_usd = requirement.amount_usd
        self._check_budget(amount_usd, requirement)

        # 5. Build and sign payment
        try:
            authorization = self._build_authorization(requirement)
            signature = self._sign_authorization(authorization, requirement)
        except Exception as error:
            self.state.total_failures += 1
            self._audit("payment_sign_failed", {
                "url": url,
                "amount_usd": amount_usd,
                "error": str(error),
            })
            raise PaymentSigningError(f"Payment signing failed: {error}") from error

        # 6. Pre-payment audit
        self._audit("payment_attempted", {
            "url": url,
            "amount_usd": amount_usd,
            "amount_raw": requirement.max_amount_required,
            "asset": requirement.asset,
            "pay_to": requirement.pay_to,
            "network": requirement.network,
        })

        # 7. Encode X-PAYMENT header (uppercase per x402 spec)
        x_payment = self._encode_payment_header(authorization, signature, requirement)
        retry_headers = {**headers, "X-PAYMENT": x_payment}

        # 8. Retry request with payment
        try:
            second = self._do_request(method, url, retry_headers, body)
        except Exception as error:
            self.state.total_failures += 1
            self._audit("payment_retry_failed", {"url": url, "error": str(error)})
            raise X402Error(f"Retry after payment failed: {error}") from error

        if second.get("status") in (200, 201, 202):
            self.state.total_payments += 1
            self.state.session_spent_usd += amount_usd
            today = datetime.now(UTC).date().isoformat()
            self.state.daily_spent_usd[today] = self.state.daily_spent_usd.get(today, 0.0) + amount_usd
            self._save_state()  # Persist after every payment

            self._audit("payment_settled", {
                "url": url,
                "amount_usd": amount_usd,
                "session_total_usd": round(self.state.session_spent_usd, 6),
                "response_status": second.get("status"),
            })
            return second
        else:
            self.state.total_failures += 1
            self._save_state()  # Persist failure count
            # Capture response body (truncated) so failures are debuggable
            body_snippet = second.get("body")
            if isinstance(body_snippet, (dict, list)):
                body_snippet = json.dumps(body_snippet)[:500]
            elif isinstance(body_snippet, str):
                body_snippet = body_snippet[:500]
            self._audit("payment_rejected", {
                "url": url,
                "response_status": second.get("status"),
                "amount_usd": amount_usd,
                "response_body": body_snippet,
            })
            raise X402Error(
                f"Endpoint rejected payment: HTTP {second.get('status')} — {body_snippet}"
            )

    # ------------------------------------------------------------------
    # Safety
    # ------------------------------------------------------------------

    def _preflight(self) -> None:
        """Check halt file, confirmation, and basic config."""
        if self._halt_path.exists():
            raise HaltedError(
                f"Kill switch active: {self._halt_path} exists. "
                f"Run 'forge resume {self.agent_directory}' to clear after manual review."
            )

        if self.config.require_confirm and not self.config.confirmed:
            raise X402Error(
                "X402Client not confirmed. Pass --confirm-live or set config.confirmed=True. "
                "This prevents accidental real-money calls."
            )

    # Default RPCs by chain (used when no override)
    DEFAULT_RPCS = {
        "base": "https://mainnet.base.org",
        "base-sepolia": "https://sepolia.base.org",
        "ethereum": "https://eth.llamarpc.com",
        "arbitrum": "https://arb1.arbitrum.io/rpc",
        "polygon": "https://polygon-rpc.com",
        "optimism": "https://mainnet.optimism.io",
    }

    def _check_balance(self, requirement: PaymentRequirement) -> float:
        """Query on-chain USDC balance for the agent's wallet.

        Returns balance in USDC. Raises if RPC call fails or insufficient.
        """
        from .wallet import load_agent_wallet
        wallet_config = load_agent_wallet(self.agent_directory)
        from_address = wallet_config.get("addresses", {}).get("evm", "")
        if not from_address:
            raise PaymentBudgetError("Agent wallet has no EVM address")

        rpc_url = self.config.rpc_url or self.DEFAULT_RPCS.get(self.config.chain)
        if not rpc_url:
            raise PaymentBudgetError(f"No RPC URL configured for balance check on chain {self.config.chain}")

        # ERC-20 balanceOf(address) — function selector 0x70a08231 + 32-byte address
        addr_no_prefix = from_address.lower().replace("0x", "")
        calldata = "0x70a08231" + "0" * 24 + addr_no_prefix

        payload = {
            "jsonrpc": "2.0",
            "method": "eth_call",
            "params": [{"to": requirement.asset, "data": calldata}, "latest"],
            "id": 1,
        }
        try:
            req = urllib_request.Request(
                rpc_url,
                data=json.dumps(payload).encode("utf8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib_request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode("utf8"))
            hex_balance = result.get("result", "0x0")
            if hex_balance == "0x" or not hex_balance:
                hex_balance = "0x0"
            raw_balance = int(hex_balance, 16)
            # USDC has 6 decimals
            return raw_balance / 1_000_000
        except Exception as error:
            raise PaymentBudgetError(f"Balance check failed for {from_address}: {error}") from error

    def _check_budget(self, amount_usd: float, requirement: PaymentRequirement) -> None:
        if amount_usd <= 0:
            raise PaymentBudgetError(f"Invalid payment amount: ${amount_usd}")

        if amount_usd > self.config.max_per_call_usd:
            raise PaymentBudgetError(
                f"Payment ${amount_usd:.6f} exceeds per-call cap ${self.config.max_per_call_usd:.6f}"
            )

        if self.state.session_spent_usd + amount_usd > self.config.max_session_usd:
            raise PaymentBudgetError(
                f"Payment would push session total to ${self.state.session_spent_usd + amount_usd:.6f}, "
                f"exceeds session cap ${self.config.max_session_usd:.6f}"
            )

        today = datetime.now(UTC).date().isoformat()
        daily = self.state.daily_spent_usd.get(today, 0.0)
        if daily + amount_usd > self.config.max_daily_usd:
            raise PaymentBudgetError(
                f"Payment would push daily total to ${daily + amount_usd:.6f}, "
                f"exceeds daily cap ${self.config.max_daily_usd:.6f}"
            )

        # On-chain balance check (can be disabled for testing)
        if self.config.check_balance:
            balance_usdc = self._check_balance(requirement)
            if balance_usdc != float("inf") and balance_usdc < amount_usd:
                raise PaymentBudgetError(
                    f"Insufficient on-chain balance: have ${balance_usdc:.6f} USDC, need ${amount_usd:.6f}"
                )

    # ------------------------------------------------------------------
    # 402 parsing
    # ------------------------------------------------------------------

    def _parse_402_response(self, response: dict[str, Any], url: str) -> PaymentRequirement:
        """Parse a 402 response into a PaymentRequirement.

        x402 spec: response body or X-Payment-Required header contains
        an `accepts` array of payment options. We pick the first matching
        our configured chain.
        """
        body = response.get("body", {})
        if isinstance(body, str):
            try:
                body = json.loads(body)
            except json.JSONDecodeError:
                body = {}

        # Check for accepts array
        accepts = body.get("accepts", []) if isinstance(body, dict) else []
        if not accepts and "X-Payment-Required" in response.get("headers", {}):
            try:
                req_data = json.loads(response["headers"]["X-Payment-Required"])
                accepts = req_data.get("accepts", [req_data])
            except json.JSONDecodeError:
                pass

        if not accepts:
            raise X402Error("No payment options in 402 response")

        # Pick option matching our chain. Do not silently fall back to another
        # network; that could sign a valid authorization for the wrong asset.
        target_network = self.config.chain
        chosen = None
        for option in accepts:
            if not isinstance(option, dict):
                continue
            net = str(option.get("network", ""))
            if _network_matches(target_network, net):
                chosen = option
                break
        if chosen is None:
            networks = [
                str(option.get("network", "<missing>"))
                for option in accepts
                if isinstance(option, dict)
            ]
            raise X402Error(
                f"No payment option matched configured chain {target_network!r}; "
                f"offered networks: {networks}"
            )

        scheme = chosen.get("scheme")
        if scheme != "exact":
            raise X402Error(f"Unsupported x402 payment scheme: {scheme}")

        amount_raw = str(chosen.get("maxAmountRequired", chosen.get("amount", "0")))
        try:
            amount_int = int(amount_raw)
        except (TypeError, ValueError) as error:
            raise X402Error(f"Invalid payment amount: {amount_raw!r}") from error
        if amount_int <= 0:
            raise X402Error(f"Invalid payment amount: {amount_raw!r}")

        pay_to = str(chosen.get("payTo", chosen.get("recipient", "")))
        if not _looks_like_evm_address(pay_to):
            raise X402Error(f"Invalid payment recipient address: {pay_to!r}")

        expected_asset = USDC_CONTRACTS.get(target_network)
        asset = str(chosen.get("asset", chosen.get("token", "")))
        if not asset:
            raise X402Error("Payment option missing USDC asset address")
        if expected_asset and asset.lower() != expected_asset.lower():
            raise X402Error(
                f"Payment option asset {asset} does not match configured "
                f"{target_network} USDC contract {expected_asset}"
            )

        return PaymentRequirement(
            scheme=scheme,
            network=chosen.get("network", target_network),
            max_amount_required=amount_raw,
            pay_to=pay_to,
            asset=asset,
            resource=chosen.get("resource", url),
            description=chosen.get("description", ""),
            extra=chosen.get("extra", {}),
        )

    # ------------------------------------------------------------------
    # EIP-3009 authorization
    # ------------------------------------------------------------------

    def _build_authorization(self, requirement: PaymentRequirement) -> dict[str, Any]:
        """Build EIP-3009 transferWithAuthorization payload."""
        now = int(time.time())
        # Valid window: now to 1 hour from now
        valid_after = "0"
        valid_before = str(now + 3600)
        # Random nonce (32 bytes)
        nonce = "0x" + secrets.token_hex(32)

        # Get the agent's wallet address
        from .wallet import load_agent_wallet
        wallet_config = load_agent_wallet(self.agent_directory)
        from_address = wallet_config.get("addresses", {}).get("evm", "")
        if not from_address:
            raise PaymentSigningError("Agent wallet has no EVM address")

        return {
            "from": from_address,
            "to": requirement.pay_to,
            "value": requirement.max_amount_required,
            "validAfter": valid_after,
            "validBefore": valid_before,
            "nonce": nonce,
        }

    def _sign_authorization(
        self,
        authorization: dict[str, Any],
        requirement: PaymentRequirement,
    ) -> str:
        """Sign EIP-3009 typed data via OWS wallet."""
        chain_id = CHAIN_IDS.get(self.config.chain, 8453)

        # Token domain — use extra.name/version from requirement, default to USDC
        token_name = requirement.extra.get("name", "USD Coin") if isinstance(requirement.extra, dict) else "USD Coin"
        token_version = requirement.extra.get("version", "2") if isinstance(requirement.extra, dict) else "2"

        typed_data = {
            "domain": {
                "name": token_name,
                "version": token_version,
                "chainId": chain_id,
                "verifyingContract": requirement.asset,
            },
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "TransferWithAuthorization": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"},
                    {"name": "validAfter", "type": "uint256"},
                    {"name": "validBefore", "type": "uint256"},
                    {"name": "nonce", "type": "bytes32"},
                ],
            },
            "primaryType": "TransferWithAuthorization",
            "message": authorization,
        }

        # Sprint 2.3 / FP-3: dispatch via the DelegatedSigner protocol so
        # browser-relay, HSM, and constrained-session-key signers can all plug
        # in through the same seam. ``signer`` wins; legacy callable runs
        # next; OWS fallback only when neither is wired.
        from .crypto.signers import (
            LegacyCallableSigner,
            OwsSigner,
            SigningError,
            SigningIntent,
        )

        # Build an intent for SessionKeyConstrainedSigner / audit downstream.
        intent = SigningIntent(
            chain_id=_chain_id_for_network(requirement.network),
            contract_address=requirement.asset or None,
            spend_usd=_micros_to_usd(int(requirement.max_amount_required or 0)),
            purpose="x402-payment",
        )

        if self._signer is not None:
            try:
                return self._signer.sign_typed_data(typed_data, intent=intent)
            except SigningError as error:
                raise PaymentSigningError(str(error)) from error

        if self._sign_typed_data_fn is not None:
            shim = LegacyCallableSigner(self._sign_typed_data_fn)
            try:
                return shim.sign_typed_data(typed_data, intent=intent)
            except SigningError as error:
                raise PaymentSigningError(str(error)) from error

        # Default fallback: today's OWS path, now extracted into OwsSigner.
        try:
            return OwsSigner(agent_directory=str(self.agent_directory)).sign_typed_data(
                typed_data,
                intent=intent,
            )
        except SigningError as error:
            raise PaymentSigningError(str(error)) from error

    def _encode_payment_header(
        self,
        authorization: dict[str, Any],
        signature: str,
        requirement: PaymentRequirement,
    ) -> str:
        """Encode the X-Payment header per x402 spec."""
        payload = {
            "x402Version": 1,
            "scheme": requirement.scheme,
            "network": requirement.network,
            "payload": {
                "signature": signature if signature.startswith("0x") else f"0x{signature}",
                "authorization": authorization,
            },
        }
        return base64.b64encode(json.dumps(payload).encode("utf8")).decode("utf8")

    # ------------------------------------------------------------------
    # HTTP transport
    # ------------------------------------------------------------------

    def _do_request(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Execute HTTP request, return normalized response dict."""
        if self._request_fn is not None:
            return self._request_fn(method, url, headers, body)

        data = json.dumps(body).encode("utf8") if body else None
        req_headers = dict(headers)
        if data:
            req_headers.setdefault("Content-Type", "application/json")

        req = urllib_request.Request(url, data=data, headers=req_headers, method=method)
        try:
            with urllib_request.urlopen(req, timeout=15) as resp:
                resp_body = resp.read().decode("utf8")
                try:
                    parsed = json.loads(resp_body)
                except json.JSONDecodeError:
                    parsed = resp_body
                return {
                    "status": resp.status,
                    "headers": dict(resp.headers),
                    "body": parsed,
                }
        except urllib_error.HTTPError as e:
            error_body = e.read().decode("utf8") if e.readable() else ""
            try:
                parsed = json.loads(error_body)
            except json.JSONDecodeError:
                parsed = error_body
            return {
                "status": e.code,
                "headers": dict(e.headers),
                "body": parsed,
            }
        except urllib_error.URLError as e:
            raise X402Error(f"Network error: {e.reason}") from e

    # ------------------------------------------------------------------
    # Audit log
    # ------------------------------------------------------------------

    def _audit(self, event: str, payload: dict[str, Any]) -> None:
        # Sanitize the payload before persistence — strip any field that
        # could be a mnemonic, private key, signature, or API token even
        # if a caller accidentally passed one in.
        try:
            from .security_hardening import sanitize_dict
            safe_payload = sanitize_dict(payload)
        except Exception:
            safe_payload = payload
        entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            **safe_payload,
        }
        try:
            new_file = not self._audit_path.exists()
            with self._audit_path.open("a", encoding="utf8") as f:
                f.write(json.dumps(entry) + "\n")
            if new_file:
                # Lock the audit log down on first write
                try:
                    from .security_hardening import lock_down_file
                    lock_down_file(self._audit_path)
                except Exception:
                    pass
        except Exception as error:
            logger.warning("X402 audit log write failed: %s", error)

    # ------------------------------------------------------------------
    # Persistent state
    # ------------------------------------------------------------------

    @contextmanager
    def _state_lock(self) -> Iterator[None]:
        """Hold an interprocess lock across budget check and payment submit."""
        import fcntl

        self._state_lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self._state_lock_path.open("a+", encoding="utf8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_state(self) -> X402State:
        """Load persisted state from disk, or return fresh state."""
        if not self._state_path.exists():
            return X402State()
        try:
            data = json.loads(self._state_path.read_text(encoding="utf8"))
            return X402State(
                session_spent_usd=float(data.get("session_spent_usd", 0)),
                daily_spent_usd=dict(data.get("daily_spent_usd", {})),
                total_calls=int(data.get("total_calls", 0)),
                total_payments=int(data.get("total_payments", 0)),
                total_failures=int(data.get("total_failures", 0)),
            )
        except Exception as error:
            logger.warning("Failed to load x402 state, starting fresh: %s", error)
            return X402State()

    def _save_state(self) -> None:
        """Persist state to disk after every payment."""
        try:
            data = {
                "session_spent_usd": self.state.session_spent_usd,
                "daily_spent_usd": self.state.daily_spent_usd,
                "total_calls": self.state.total_calls,
                "total_payments": self.state.total_payments,
                "total_failures": self.state.total_failures,
                "saved_at": datetime.now(UTC).isoformat(),
            }
            tmp = self._state_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf8")
            tmp.replace(self._state_path)
            try:
                from .security_hardening import lock_down_file
                lock_down_file(self._state_path)
            except Exception:
                pass
        except Exception as error:
            logger.warning("Failed to persist x402 state: %s", error)

    def reset_session(self) -> None:
        """Reset session counter (e.g., when starting a new trading day)."""
        self.state.session_spent_usd = 0.0
        self._save_state()
        self._audit("session_reset", {})

    def read_audit_log(self, *, limit: int | None = None) -> list[dict[str, Any]]:
        if not self._audit_path.exists():
            return []
        entries = []
        with self._audit_path.open("r", encoding="utf8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries[-limit:] if limit else entries

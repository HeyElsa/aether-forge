"""x402 HTTP payment protocol — PaymentRequired (402) negotiation."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from urllib import error as urllib_error
from urllib import request as urllib_request


@dataclass(slots=True)
class PaymentRequirement:
    """A payment requirement extracted from a 402 response."""

    scheme: str  # e.g. "exact", "tip", "stream"
    network: str  # e.g. "base-sepolia", "base"
    max_amount_required: int  # smallest token unit
    resource: str  # URL of the paid resource
    description: str = ""
    mime_type: str = ""
    pay_to: str = ""  # wallet / contract address
    required_deadline_seconds: int = 0
    output_schema: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_header(self) -> str:
        """Serialize the requirement to a JSON string suitable for an HTTP header."""
        data: dict[str, Any] = {
            "scheme": self.scheme,
            "network": self.network,
            "maxAmountRequired": self.max_amount_required,
            "resource": self.resource,
            "description": self.description,
            "mimeType": self.mime_type,
            "payTo": self.pay_to,
            "requiredDeadlineSeconds": self.required_deadline_seconds,
        }
        if self.output_schema is not None:
            data["outputSchema"] = self.output_schema
        if self.extra:
            data["extra"] = self.extra
        return json.dumps(data, separators=(",", ":"))

    @classmethod
    def from_header(cls, header: str) -> PaymentRequirement:
        """Deserialize a requirement from a JSON header string."""
        data = json.loads(header)
        return cls(
            scheme=data.get("scheme", "exact"),
            network=data.get("network", ""),
            max_amount_required=int(data.get("maxAmountRequired", 0)),
            resource=data.get("resource", ""),
            description=data.get("description", ""),
            mime_type=data.get("mimeType", ""),
            pay_to=data.get("payTo", ""),
            required_deadline_seconds=int(data.get("requiredDeadlineSeconds", 0)),
            output_schema=data.get("outputSchema"),
            extra=data.get("extra", {}),
        )


@dataclass(slots=True)
class PaymentPayload:
    """Payload sent to fulfil a payment requirement."""

    scheme: str
    network: str
    amount: int
    from_address: str
    to_address: str
    token: str = ""
    nonce: str = ""
    signature: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "scheme": self.scheme,
            "network": self.network,
            "amount": self.amount,
            "fromAddress": self.from_address,
            "toAddress": self.to_address,
            "token": self.token,
            "nonce": self.nonce,
            "signature": self.signature,
        }


@dataclass(slots=True)
class PaymentReceipt:
    """Receipt returned after a successful payment."""

    tx_hash: str
    amount: int
    network: str
    status: str = "confirmed"

    def to_json(self) -> dict[str, Any]:
        return {
            "txHash": self.tx_hash,
            "amount": self.amount,
            "network": self.network,
            "status": self.status,
        }


class X402Client:
    """Client for x402 payment negotiation.

    Builds data structures for payment flows.  Actual HTTP or on-chain
    interaction is left to the caller.
    """

    def __init__(self, rpc_url: str | None = None) -> None:
        self.rpc_url = rpc_url

    def build_payment_payload(
        self,
        requirement: PaymentRequirement,
        from_address: str,
    ) -> PaymentPayload:
        return PaymentPayload(
            scheme=requirement.scheme,
            network=requirement.network,
            amount=requirement.max_amount_required,
            from_address=from_address,
            to_address=requirement.pay_to,
        )


def parse_402_response(
    status_code: int,
    headers: dict[str, str],
) -> PaymentRequirement | None:
    """Parse a 402 Payment Required response.

    Returns *None* when the status code is not 402 or the expected header
    is missing.
    """
    if status_code != 402:
        return None
    raw = headers.get("X-Payment") or headers.get("x-payment")
    if not raw:
        return None
    return PaymentRequirement.from_header(raw)


def search_402_directory(
    base_url: str = "https://x402.org/directory",
) -> list[dict[str, Any]]:
    """Search the x402 public directory for payment-enabled services.

    Without network access this returns an empty list.  When a real
    HTTP client is wired up the caller should pass a fetched JSON payload.
    """
    # Placeholder: real implementation would issue an HTTP GET.
    return []


class X402PaymentFlow:
    """End-to-end x402 payment flow integrating wallet and budget controls.

    Usage::

        flow = X402PaymentFlow(wallet_adapter=ows_adapter, budget_limit_usd=50.0)
        result = flow.pay_and_retry("https://api.example.com/data", original_headers={})
    """

    def __init__(
        self,
        *,
        wallet_adapter: Any = None,
        wallet_name: str = "agent-wallet",
        chain: str = "evm",
        budget_limit_usd: float = 50.0,
        request_fn: Callable[[str, dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self.wallet_adapter = wallet_adapter
        self.wallet_name = wallet_name
        self.chain = chain
        self.budget_limit_usd = budget_limit_usd
        self.total_spent_usd = 0.0
        self.payment_log: list[dict[str, Any]] = []
        self._request_fn = request_fn

    def pay_and_retry(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        method: str = "GET",
    ) -> dict[str, Any]:
        """Execute a request, handle 402, pay, and retry.

        Returns a dict with keys: success, status, data, payment (if paid).
        Raises ValueError if budget exceeded.
        """
        headers = headers or {}

        # Step 1: Make the original request
        first_response = self._make_request(url, headers, method)

        if first_response.get("status") != 402:
            return {"success": True, "status": first_response.get("status", 200), "data": first_response}

        # Step 2: Parse 402 payment requirements
        resp_headers = first_response.get("headers", {})
        requirement = parse_402_response(402, resp_headers)
        if requirement is None:
            return {"success": False, "status": 402, "error": "Could not parse payment requirements"}

        # Step 3: Check budget
        amount_usd = _estimate_usd(requirement)
        if self.total_spent_usd + amount_usd > self.budget_limit_usd:
            raise ValueError(
                f"x402 payment would exceed budget: "
                f"${self.total_spent_usd:.2f} + ${amount_usd:.2f} > ${self.budget_limit_usd:.2f}"
            )

        # Step 4: Build and sign payment
        payment = self._build_payment(requirement)

        # Step 5: Retry with payment proof
        retry_headers = {
            **headers,
            "X-Payment-Token": payment.get("token", ""),
            "X-Payment-Signature": payment.get("signature", ""),
        }
        retry_response = self._make_request(url, retry_headers, method)

        # Step 6: Record
        self.total_spent_usd += amount_usd
        self.payment_log.append({
            "url": url,
            "amount_usd": amount_usd,
            "requirement": {
                "scheme": requirement.scheme,
                "network": requirement.network,
                "max_amount_required": requirement.max_amount_required,
                "pay_to": requirement.pay_to,
            },
            "success": retry_response.get("status", 200) != 402,
        })

        return {
            "success": retry_response.get("status", 200) != 402,
            "status": retry_response.get("status", 200),
            "data": retry_response,
            "payment": {"amount_usd": amount_usd, "total_spent_usd": self.total_spent_usd},
        }

    def _make_request(self, url: str, headers: dict[str, str], method: str) -> dict[str, Any]:
        if self._request_fn is not None:
            return self._request_fn(url, headers)
        # Default: use urllib
        import json as _json
        req = urllib_request.Request(url, headers=headers, method=method)
        try:
            with urllib_request.urlopen(req, timeout=10) as resp:
                return {"status": resp.status, "data": _json.loads(resp.read().decode("utf8"))}
        except urllib_error.HTTPError as e:
            if e.code == 402:
                body = e.read().decode("utf8") if e.readable() else ""
                return {"status": 402, "headers": dict(e.headers), "body": body}
            return {"status": e.code, "error": str(e)}
        except Exception as e:
            return {"status": 0, "error": str(e)}

    def _build_payment(self, requirement: PaymentRequirement) -> dict[str, Any]:
        """Build a payment payload using the wallet adapter."""
        if self.wallet_adapter is None:
            return {"token": "simulated-payment-token", "signature": "simulated-sig", "simulated": True}

        # Sign a payment message with the wallet
        message = f"x402-payment:{requirement.pay_to}:{requirement.max_amount_required}:{requirement.network}"
        try:
            sig = self.wallet_adapter.sign_message(self.wallet_name, self.chain, message)
            return {"token": message, "signature": sig.get("signature", ""), "simulated": False}
        except Exception:
            return {"token": "payment-failed", "signature": "", "simulated": True, "error": True}


def _estimate_usd(requirement: PaymentRequirement) -> float:
    """Estimate USD value from a payment requirement.

    Assumes USDC/USDT at 1:1 ratio. For other tokens, returns the raw amount
    with a conversion factor placeholder.
    """
    try:
        amount = float(requirement.max_amount_required)
    except (ValueError, TypeError):
        return 0.0

    # USDC and USDT on most chains use 6 decimals
    network_lower = (requirement.network or "").lower()
    pay_to_lower = (requirement.pay_to or "").lower()
    token_hint = network_lower + pay_to_lower
    if "usdc" in token_hint or "usdt" in token_hint:
        return amount / 1_000_000

    # For raw amounts that look like they're already in USD
    if amount < 100:
        return amount

    # Default: assume 6-decimal stablecoin
    return amount / 1_000_000

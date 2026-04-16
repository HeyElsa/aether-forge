"""Tests for the generic x402 payment client."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from aether_forge.x402_client import (
    HaltedError,
    PaymentBudgetError,
    PaymentRequirement,
    X402Client,
    X402Config,
    X402Error,
)


def _make_wallet_config(tmp_path: Path) -> None:
    """Create a fake wallet.json so the client can read the agent's address."""
    wallet = {
        "walletId": "test-wallet",
        "walletName": "forge-test",
        "provider": "ows",
        "addresses": {
            "evm": "0x" + "a" * 40,
            "solana": "",
            "bitcoin": "",
        },
    }
    (tmp_path / "wallet.json").write_text(json.dumps(wallet))


def _make_client(tmp_path: Path, **config_overrides) -> X402Client:
    _make_wallet_config(tmp_path)
    config = X402Config(
        max_per_call_usd=0.10,
        max_session_usd=1.0,
        max_daily_usd=5.0,
        chain="base",
        confirmed=True,
        check_balance=False,  # Tests use fake wallet, skip RPC check
        audit_log_path=str(tmp_path / "x402_audit.jsonl"),
    )
    for k, v in config_overrides.items():
        setattr(config, k, v)

    fake_responses = []

    def fake_request(method, url, headers, body):
        if not fake_responses:
            return {"status": 500, "headers": {}, "body": "no response queued"}
        return fake_responses.pop(0)

    def fake_sign(typed_data):
        return "0x" + "ab" * 65

    client = X402Client(
        agent_directory=tmp_path,
        config=config,
        request_fn=fake_request,
        sign_typed_data_fn=fake_sign,
    )
    client._fake_responses = fake_responses
    return client


def test_simple_get_no_402(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    client._fake_responses.append({"status": 200, "headers": {}, "body": {"result": "ok"}})

    response = client.get("https://api.example.com/data")
    assert response["status"] == 200
    assert response["body"] == {"result": "ok"}


def test_402_with_payment_flow(tmp_path: Path) -> None:
    client = _make_client(tmp_path)

    # First response: 402 with payment requirement
    client._fake_responses.append({
        "status": 402,
        "headers": {},
        "body": {
            "accepts": [{
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "1000",  # 0.001 USDC
                "payTo": "0x" + "b" * 40,
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "resource": "https://api.example.com/data",
            }],
        },
    })
    # Second response: 200 after payment
    client._fake_responses.append({"status": 200, "headers": {}, "body": {"data": "paid"}})

    response = client.get("https://api.example.com/data")
    assert response["status"] == 200
    assert response["body"] == {"data": "paid"}
    assert client.state.session_spent_usd == pytest.approx(0.001)
    assert client.state.total_payments == 1


def test_per_call_cap_blocks_expensive_payment(tmp_path: Path) -> None:
    client = _make_client(tmp_path, max_per_call_usd=0.005)
    client._fake_responses.append({
        "status": 402,
        "headers": {},
        "body": {
            "accepts": [{
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "10000",  # 0.01 USDC
                "payTo": "0x" + "b" * 40,
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "resource": "https://api.example.com/data",
            }],
        },
    })

    with pytest.raises(PaymentBudgetError, match="exceeds per-call cap"):
        client.get("https://api.example.com/data")


def test_session_cap_blocks_repeated_payments(tmp_path: Path) -> None:
    client = _make_client(tmp_path, max_session_usd=0.003)

    def add_402_pair():
        client._fake_responses.append({
            "status": 402,
            "headers": {},
            "body": {
                "accepts": [{
                    "scheme": "exact",
                    "network": "base",
                    "maxAmountRequired": "2000",  # 0.002 USDC
                    "payTo": "0x" + "b" * 40,
                    "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                    "resource": "https://api.example.com/data",
                }],
            },
        })
        client._fake_responses.append({"status": 200, "headers": {}, "body": {"data": "paid"}})

    add_402_pair()
    client.get("https://api.example.com/data")  # 0.002 spent
    add_402_pair()
    with pytest.raises(PaymentBudgetError, match="session cap"):
        client.get("https://api.example.com/data")


def test_halt_file_blocks_calls(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    (tmp_path / "halt").write_text("kill switch active")

    with pytest.raises(HaltedError, match="Kill switch active"):
        client.get("https://api.example.com/data")


def test_unconfirmed_blocks_calls(tmp_path: Path) -> None:
    client = _make_client(tmp_path, confirmed=False)
    with pytest.raises(X402Error, match="not confirmed"):
        client.get("https://api.example.com/data")


def test_audit_log_records_payment_attempt(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    client._fake_responses.append({
        "status": 402,
        "headers": {},
        "body": {
            "accepts": [{
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "1000",
                "payTo": "0x" + "b" * 40,
                "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
                "resource": "https://api.example.com/data",
            }],
        },
    })
    client._fake_responses.append({"status": 200, "headers": {}, "body": {"data": "paid"}})

    client.get("https://api.example.com/data")

    log = client.read_audit_log()
    events = [e["event"] for e in log]
    assert "payment_attempted" in events
    assert "payment_settled" in events


def test_audit_log_sanitizes_secret_fields(tmp_path: Path) -> None:
    """Audit log must redact mnemonics, private keys, signatures even if a
    caller accidentally passes them in via the payload."""
    client = _make_client(tmp_path)
    # Directly invoke the audit writer with a payload containing secret-like
    # fields — these should be redacted before being written to disk.
    client._audit("test_event", {
        "mnemonic": "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
        "private_key": "0x" + "a" * 64,
        "wallet_id": "test-wallet",
        "amount_usd": 0.001,
    })
    log_text = (tmp_path / "x402_audit.jsonl").read_text(encoding="utf8")
    assert "abandon abandon abandon" not in log_text
    assert "a" * 64 not in log_text
    assert "[REDACTED]" in log_text
    assert "test-wallet" in log_text  # Non-secret fields preserved
    assert "0.001" in log_text


def test_audit_log_file_locked_down(tmp_path: Path) -> None:
    """The audit log file must be created with 0600 permissions."""
    client = _make_client(tmp_path)
    client._audit("test_event", {"foo": "bar"})
    audit_path = tmp_path / "x402_audit.jsonl"
    assert audit_path.exists()
    mode = audit_path.stat().st_mode & 0o777
    assert mode & 0o077 == 0, f"Expected 0600-style perms, got {oct(mode)}"


def test_status_reports_state(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    status = client.status()
    assert status["session_spent_usd"] == 0
    assert status["confirmed"] is True
    assert status["chain"] == "base"
    assert status["halted"] is False
    assert status["session_remaining_usd"] == 1.0


def test_payment_requirement_amount_usd() -> None:
    req = PaymentRequirement(
        scheme="exact",
        network="base",
        max_amount_required="1000000",  # 1 USDC
        pay_to="0x123",
        asset="0xUSDC",
        resource="url",
    )
    assert req.amount_usd == 1.0


def test_x_payment_header_encoding(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    auth = {
        "from": "0x" + "a" * 40,
        "to": "0x" + "b" * 40,
        "value": "1000",
        "validAfter": "0",
        "validBefore": "9999999999",
        "nonce": "0x" + "c" * 64,
    }
    req = PaymentRequirement(
        scheme="exact",
        network="base",
        max_amount_required="1000",
        pay_to="0x" + "b" * 40,
        asset="0xUSDC",
        resource="url",
    )
    header = client._encode_payment_header(auth, "0x" + "ab" * 65, req)
    decoded = json.loads(base64.b64decode(header))
    assert decoded["x402Version"] == 1
    assert decoded["scheme"] == "exact"
    assert decoded["network"] == "base"
    assert decoded["payload"]["authorization"] == auth


def test_invalid_402_no_accepts(tmp_path: Path) -> None:
    client = _make_client(tmp_path)
    client._fake_responses.append({
        "status": 402,
        "headers": {},
        "body": {"error": "no accepts"},
    })
    with pytest.raises(X402Error, match="parse 402"):
        client.get("https://api.example.com/data")

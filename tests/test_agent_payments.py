"""Tests for agent-to-agent payment protocol."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.agent_payments import (
    PaymentRequest,
    PaymentResult,
    build_escrow_fund_tx,
    build_transfer_tx,
    check_budget,
    execute_payment,
)


# ---------------------------------------------------------------------------
# PaymentRequest
# ---------------------------------------------------------------------------

def test_payment_request_roundtrip() -> None:
    pr = PaymentRequest(method="x402", budget_usd=0.05, pay_to="0xabc", x402_endpoint="http://agent-b/x402")
    d = pr.to_dict()
    loaded = PaymentRequest.from_dict(d)
    assert loaded.method == "x402"
    assert loaded.budget_usd == 0.05
    assert loaded.pay_to == "0xabc"
    assert loaded.x402_endpoint == "http://agent-b/x402"


def test_payment_request_defaults() -> None:
    pr = PaymentRequest.from_dict({"method": "transfer", "budget_usd": 1.0})
    assert pr.asset == "USDC"
    assert pr.chain == "base"
    assert pr.pay_to == ""


# ---------------------------------------------------------------------------
# PaymentResult
# ---------------------------------------------------------------------------

def test_payment_result_has_timestamp() -> None:
    result = PaymentResult(success=True, method="x402", amount_usd=0.001)
    assert result.timestamp
    assert "T" in result.timestamp  # ISO format


def test_payment_result_to_dict() -> None:
    result = PaymentResult(success=False, method="transfer", amount_usd=0, error="insufficient funds")
    d = result.to_dict()
    assert d["success"] is False
    assert d["error"] == "insufficient funds"


# ---------------------------------------------------------------------------
# Budget enforcement
# ---------------------------------------------------------------------------

def test_check_budget_within_limits(tmp_path: Path) -> None:
    allowed, reason = check_budget(tmp_path, 0.05, max_per_call_usd=0.10, max_session_usd=1.0)
    assert allowed is True
    assert reason == "ok"


def test_check_budget_exceeds_per_call(tmp_path: Path) -> None:
    allowed, reason = check_budget(tmp_path, 0.20, max_per_call_usd=0.10)
    assert allowed is False
    assert "per-call cap" in reason


def test_check_budget_exceeds_session(tmp_path: Path) -> None:
    # Write a state file showing existing spend
    state = {"session_spent_usd": 0.95}
    (tmp_path / "x402_state.json").write_text(json.dumps(state))

    allowed, reason = check_budget(tmp_path, 0.10, max_per_call_usd=0.20, max_session_usd=1.0)
    assert allowed is False
    assert "session cap" in reason


def test_check_budget_no_state_file(tmp_path: Path) -> None:
    # No x402_state.json — should assume zero spend
    allowed, reason = check_budget(tmp_path, 0.05)
    assert allowed is True


# ---------------------------------------------------------------------------
# Transfer tx building
# ---------------------------------------------------------------------------

def test_build_transfer_tx_base() -> None:
    tx = build_transfer_tx("0x" + "a" * 40, 0.05, chain="base")
    assert tx["to"] == "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"  # USDC on Base
    assert tx["data"].startswith("0xa9059cbb")  # transfer(address,uint256) selector
    assert tx["value"] == "0x0"
    assert tx["chainId"] == hex(8453)


def test_build_transfer_tx_encodes_amount() -> None:
    tx = build_transfer_tx("0x" + "b" * 40, 1.0, chain="base")
    # 1.0 USDC = 1,000,000 raw = 0xF4240
    assert "f4240" in tx["data"].lower()


def test_build_transfer_tx_ethereum() -> None:
    tx = build_transfer_tx("0x" + "c" * 40, 0.01, chain="ethereum")
    assert tx["to"] == "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"  # USDC on Ethereum
    assert tx["chainId"] == hex(1)


# ---------------------------------------------------------------------------
# Escrow tx building
# ---------------------------------------------------------------------------

def test_build_escrow_no_contract() -> None:
    result = build_escrow_fund_tx("job_1", 1.0, "0xprovider")
    assert "error" in result
    assert "not yet deployed" in result["error"]


def test_build_escrow_with_contract() -> None:
    result = build_escrow_fund_tx(
        "job_2", 1.0, "0xprovider",
        escrow_contract="0x" + "e" * 40,
    )
    assert result["to"] == "0x" + "e" * 40
    assert "description" in result


# ---------------------------------------------------------------------------
# Payment dispatcher
# ---------------------------------------------------------------------------

def test_execute_payment_budget_check_fails(tmp_path: Path) -> None:
    payment = PaymentRequest(method="transfer", budget_usd=999.0, pay_to="0xabc")
    result = execute_payment(tmp_path, payment)
    assert result.success is False
    assert "Budget check failed" in result.error


def test_execute_payment_x402_no_endpoint(tmp_path: Path) -> None:
    payment = PaymentRequest(method="x402", budget_usd=0.01)
    result = execute_payment(tmp_path, payment)
    assert result.success is False
    assert "No x402_endpoint" in result.error


def test_execute_payment_transfer_no_address(tmp_path: Path) -> None:
    payment = PaymentRequest(method="transfer", budget_usd=0.01)
    result = execute_payment(tmp_path, payment)
    assert result.success is False
    assert "No pay_to" in result.error


def test_execute_payment_transfer_builds_tx(tmp_path: Path) -> None:
    payment = PaymentRequest(method="transfer", budget_usd=0.05, pay_to="0x" + "a" * 40)
    result = execute_payment(tmp_path, payment)
    assert result.success is True
    assert result.method == "transfer"
    assert result.amount_usd == 0.05


def test_execute_payment_escrow_no_contract(tmp_path: Path) -> None:
    payment = PaymentRequest(method="escrow", budget_usd=0.05, pay_to="0x" + "a" * 40)
    result = execute_payment(tmp_path, payment)
    assert result.success is False
    assert "not yet deployed" in result.error


def test_execute_payment_unknown_method(tmp_path: Path) -> None:
    payment = PaymentRequest(method="bitcoin", budget_usd=0.01)
    result = execute_payment(tmp_path, payment)
    assert result.success is False
    assert "Unknown payment method" in result.error

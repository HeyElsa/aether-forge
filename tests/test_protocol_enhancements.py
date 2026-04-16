from __future__ import annotations

import json

from aether_forge.protocols.erc8004 import AgentCard, ERC8004Client, _encode_register_call
from aether_forge.protocols.x402 import PaymentRequirement, X402PaymentFlow, _estimate_usd


def test_erc8004_build_register_tx():
    client = ERC8004Client()
    card = AgentCard(name="TestAgent", description="A test agent", services=[], x402_support=True)
    tx = client.build_register_tx(card, registry_address="0x1234567890abcdef")
    assert tx["to"] == "0x1234567890abcdef"
    assert tx["chainId"] == 8453
    assert tx["data"].startswith("0x")
    assert tx["type"] == "erc8004.register"

def test_erc8004_build_update_tx():
    client = ERC8004Client()
    card = AgentCard(name="TestAgent", description="Updated", services=[], x402_support=True)
    tx = client.build_update_tx("agent-123", card, registry_address="0xabcdef")
    assert tx["type"] == "erc8004.update"
    assert tx["agentId"] == "agent-123"

def test_encode_register_call_produces_hex():
    result = _encode_register_call("MyAgent", '{"name":"MyAgent"}')
    assert result.startswith("0x")
    assert len(result) > 10

def test_x402_payment_flow_non_402():
    def fake_request(url, headers):
        return {"status": 200, "data": {"result": "ok"}}

    flow = X402PaymentFlow(request_fn=fake_request)
    result = flow.pay_and_retry("https://api.example.com/data")
    assert result["success"]
    assert result["status"] == 200
    assert flow.total_spent_usd == 0.0

def test_x402_payment_flow_402_with_payment():
    call_count = {"n": 0}
    def fake_request(url, headers):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # Return a 402 with X-Payment header matching PaymentRequirement.from_header format
            return {
                "status": 402,
                "headers": {
                    "X-Payment": json.dumps({
                        "scheme": "exact",
                        "network": "base",
                        "maxAmountRequired": 10000,
                        "resource": url,
                        "payTo": "0xvendor",
                    })
                },
                "body": "",
            }
        return {"status": 200, "data": {"result": "paid"}}

    flow = X402PaymentFlow(request_fn=fake_request, budget_limit_usd=100.0)
    result = flow.pay_and_retry("https://api.example.com/paid")
    assert result["success"]
    assert flow.total_spent_usd > 0
    assert len(flow.payment_log) == 1

def test_x402_payment_flow_budget_exceeded():
    def fake_request(url, headers):
        return {
            "status": 402,
            "headers": {
                "X-Payment": json.dumps({
                    "scheme": "exact",
                    "network": "base",
                    "maxAmountRequired": 1000000000,
                    "resource": url,
                    "payTo": "0xvendor",
                })
            },
            "body": "",
        }

    flow = X402PaymentFlow(request_fn=fake_request, budget_limit_usd=0.01)
    import pytest
    with pytest.raises(ValueError, match="exceed budget"):
        flow.pay_and_retry("https://expensive.api.com")

def test_estimate_usd_stablecoin():
    req = PaymentRequirement(
        scheme="exact", network="base", max_amount_required=1000000,
        resource="https://example.com", pay_to="0xUSDC_address",
    )
    # pay_to contains "usdc" so should be treated as 6-decimal stablecoin
    assert _estimate_usd(req) == 1.0

def test_estimate_usd_small_amount():
    req = PaymentRequirement(
        scheme="exact", network="unknown", max_amount_required=5,
        resource="https://example.com", pay_to="0x1",
    )
    # amount < 100, treated as raw USD
    assert _estimate_usd(req) == 5.0

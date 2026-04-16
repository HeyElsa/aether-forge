"""Trigger one A→B payment manually for the marketplace demo.

Usage:
    DEMO_DIR=/tmp/two-agent-marketplace python3 pay-once.py
"""
import json
import os
import sys
from pathlib import Path

DEMO_DIR = Path(os.environ.get("DEMO_DIR", "/tmp/two-agent-marketplace"))

# Lazy imports so the file is readable even without the framework installed
try:
    from aether_forge.agent_payments import PaymentRequest, execute_payment
except ImportError:
    sys.exit("aether-forge not installed. pip install -e ../..")


def main() -> int:
    buyer_dir = DEMO_DIR / "buyer"
    oracle_dir = DEMO_DIR / "oracle"

    if not buyer_dir.exists() or not oracle_dir.exists():
        sys.exit(f"Agents not found in {DEMO_DIR}. Run ./setup.sh first.")

    # Load OWS_API_KEY for the buyer
    env = (buyer_dir / ".env").read_text()
    for line in env.splitlines():
        if line.startswith("OWS_API_KEY="):
            os.environ["OWS_API_KEY"] = line.split("=", 1)[1].strip()
            break

    # Get oracle's address
    oracle_cfg = json.loads((oracle_dir / "wallet.json").read_text())
    accounts = oracle_cfg.get("accounts", []) or oracle_cfg.get("addresses", {})
    if isinstance(accounts, dict):
        oracle_addr = accounts.get("evm")
    else:
        evm = next((a for a in accounts if a.get("chain") == "evm"), None)
        oracle_addr = evm["address"] if evm else None

    if not oracle_addr:
        sys.exit("Could not determine oracle EVM address")

    # Build the payment request
    amount = float(os.environ.get("AMOUNT_USD", "0.001"))
    print(f"Buyer →  Oracle: ${amount} USDC on Base")
    print(f"  to: {oracle_addr}")
    print()

    req = PaymentRequest(
        method="transfer",
        budget_usd=amount,
        asset="USDC",
        chain="base",
        pay_to=oracle_addr,
    )

    result = execute_payment(buyer_dir, req)
    print(f"  success:  {result.success}")
    print(f"  amount:   ${result.amount_usd}")
    print(f"  tx_hash:  {result.tx_hash or '(none)'}")
    if result.error:
        print(f"  error:    {result.error}")
    print()
    print(f"  basescan: https://basescan.org/tx/{result.tx_hash}" if result.tx_hash else "")
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())

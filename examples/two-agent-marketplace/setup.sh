#!/usr/bin/env bash
# Generate Agent A (buyer) and Agent B (oracle) with proper policies for
# agent-to-agent payments.
set -e

DEMO_DIR="${DEMO_DIR:-/tmp/two-agent-marketplace}"
PLANNER_MODE="${DEMO_PLANNER_MODE:-openrouter}"
PLANNER_MODEL="${DEMO_PLANNER_MODEL:-anthropic/claude-sonnet-4}"

echo "Generating two agents in $DEMO_DIR"
rm -rf "$DEMO_DIR"
mkdir -p "$DEMO_DIR"

# --- Agent B (oracle) — generate first so we know its address for Agent A's policy ---
echo ""
echo "=== Generating Agent B (oracle) ==="
forge generate-fast \
  --name "oracle" \
  --idea "Sells ETH price data via x402 — $0.001 per query" \
  --wallet \
  --planner-mode "$PLANNER_MODE" \
  --planner-model "$PLANNER_MODEL" \
  --output "$DEMO_DIR/oracle"

ORACLE_ADDR=$(jq -r '.accounts[] | select(.chain=="evm") | .address' "$DEMO_DIR/oracle/wallet.json" 2>/dev/null \
              || jq -r '.addresses.evm' "$DEMO_DIR/oracle/wallet.json")
echo ""
echo "  Oracle wallet: $ORACLE_ADDR"

# --- Agent A (buyer) ---
echo ""
echo "=== Generating Agent A (buyer) ==="
forge generate-fast \
  --name "buyer" \
  --idea "Buys ETH price data from oracle agents via A2A + x402" \
  --wallet \
  --planner-mode "$PLANNER_MODE" \
  --planner-model "$PLANNER_MODEL" \
  --output "$DEMO_DIR/buyer"

BUYER_ADDR=$(jq -r '.accounts[] | select(.chain=="evm") | .address' "$DEMO_DIR/buyer/wallet.json" 2>/dev/null \
             || jq -r '.addresses.evm' "$DEMO_DIR/buyer/wallet.json")
echo ""
echo "  Buyer wallet:  $BUYER_ADDR"

# --- Patch Agent A's policy to allow direct transfers to Agent B ---
echo ""
echo "=== Patching Agent A policy: allow transfers to oracle ==="
python3 - <<PYEOF
import json
from pathlib import Path
policy_path = Path("$DEMO_DIR/buyer/policy-bundle.json")
policy = json.loads(policy_path.read_text())
policy["agentPayments"] = {
    "directTransferEnabled": True,
    "maxPerTransferUsd": 0.10,
    "allowedRecipients": ["$ORACLE_ADDR"],
    "allowedChains": ["base"]
}
policy_path.write_text(json.dumps(policy, indent=2))
print(f"  Policy patched: maxPerTransferUsd=0.10, recipient=$ORACLE_ADDR")
PYEOF

echo ""
echo "=================================================================="
echo "  Setup complete."
echo ""
echo "  Buyer wallet:  $BUYER_ADDR"
echo "  Oracle wallet: $ORACLE_ADDR"
echo ""
echo "  TO RUN WITH REAL MONEY:"
echo "  1. Send ~\$0.50 ETH (for gas) + ~\$0.10 USDC to:"
echo "       $BUYER_ADDR"
echo "  2. ./run.sh"
echo "  3. Open http://localhost:5000"
echo "=================================================================="

# Two-Agent Marketplace Example

A complete end-to-end demo where:

- **Agent A** (`buyer`) — needs ETH price data
- **Agent B** (`oracle`) — sells ETH price data via x402 ($0.001/call)

Agent A discovers Agent B via A2A, calls Agent B's paid endpoint, pays in real
USDC on Base mainnet, receives the price data. A live web dashboard shows both
agents' state, the x402 audit log, and a feed of all payments.

## Architecture

```
                 ┌────────────────────────────────────────┐
                 │   Dashboard (Flask, http://:5000)      │
                 │   /metrics + /audit + /balance feeds   │
                 └─────────┬────────────────────┬─────────┘
                           │ scrapes            │ scrapes
              ┌────────────▼─────────┐  ┌──────▼─────────────┐
              │ Agent A "buyer"      │  │ Agent B "oracle"   │
              │ A2A :9001            │  │ A2A :9002          │
              │ Health :8001         │  │ Health :8002       │
              │ Wallet 0xA...        │  │ Wallet 0xB...      │
              └────────┬─────────────┘  └──────┬─────────────┘
                       │ x402 pay $0.001 USDC │
                       └──────────────────────►│
                                                ▼
                                       Base mainnet (USDC)
```

## Files

- `setup.sh` — generates both agents with wallets and policies
- `run.sh` — starts both agents + the dashboard
- `dashboard.py` — Flask web app
- `pay-once.py` — script that triggers one A→B payment manually
- `test_marketplace.py` — pytest end-to-end test (mocked + optional live)

## Quick start

```bash
# 1. Generate both agents (one-time)
./setup.sh

# 2. Fund Agent A's wallet on Base mainnet
#    (the setup script prints the address — send ~$0.50 ETH and ~$0.10 USDC)

# 3. Start everything
./run.sh

# 4. Open the dashboard
open http://localhost:5000

# 5. Trigger a payment manually
python3 pay-once.py
```

## Mocked E2E test

```bash
pytest test_marketplace.py -v
```

This runs the full A→B flow without real money — uses mock wallets and a stub
RPC, but exercises every code path in the framework.

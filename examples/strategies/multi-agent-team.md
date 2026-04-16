# Multi-Agent Trading Team

## Architecture
Three specialized agents coordinating via A2A on Base:

```
price-oracle (port 9001)  ─── Provides ETH/BTC/SOL prices, momentum
risk-engine  (port 9002)  ─── Computes risk scores per token+side
alpha-trader (port 9003)  ─── Orchestrates: queries peers, executes trades
```

## Agent 1 — price-oracle

### Mission
Serve real-time price + momentum data to other agents. Charge $0.001 USDC
per query via x402 to fund operating costs.

### Capabilities
- `get-token-price` — current price + 5-min momentum
- `get-token-trend` — 24h trend label (bullish/bearish/sideways)
- `get-multi-token-snapshot` — batch query for ETH, BTC, SOL

### Pricing
- Free: `get-token-price` for ETH (loss leader)
- Paid: $0.001 for any other token
- Paid: $0.005 for `get-multi-token-snapshot`

## Agent 2 — risk-engine

### Mission
Score the risk of a proposed trade on a 0.0–1.0 scale. Higher = riskier.
Charge $0.002 per score request.

### Inputs
- Token, side (buy/sell), size, current price

### Risk factors
- Volatility (last 24h)
- Liquidity depth
- Recent price action (momentum continuation vs reversal)
- Time of day (prefer high-liquidity windows)

### Output
```json
{ "score": 0.32, "label": "moderate", "concerns": ["thin order book"] }
```

## Agent 3 — alpha-trader

### Mission
Make trading decisions by consulting price-oracle and risk-engine. Trade ETH
swing patterns. Pay both peers in x402 USDC.

### Workflow per tick
1. Query price-oracle for ETH price + momentum
2. If trend is bullish AND we have no position:
   - Query risk-engine for `risk-score(buy ETH 0.001)`
   - If score < 0.4, place buy order
   - Otherwise, log "skipped: risk too high"
3. If we have a position, check exit conditions:
   - +4% profit → SELL
   - -2% loss → SELL
   - momentum flipped bearish → SELL

### Budget
- Max $0.10/day on x402 to peers (configured in `x402_budget`)
- Max $50 per trade
- Max 3 concurrent positions

## Setup

```bash
# Generate each agent
forge generate-fast --name price-oracle --idea "Serve token prices via A2A" \
  --strategy-file examples/strategies/multi-agent-team.md \
  --wallet --output ./price-oracle

forge generate-fast --name risk-engine --idea "Compute risk scores via A2A" \
  --strategy-file examples/strategies/multi-agent-team.md \
  --wallet --output ./risk-engine

forge generate-fast --name alpha-trader --idea "Trade ETH using oracle+risk peers" \
  --strategy-file examples/strategies/multi-agent-team.md \
  --wallet --autonomous --output ./alpha-trader

# Run each in its own terminal
forge run ./price-oracle --mode paper --a2a-port 9001 --auto-approve
forge run ./risk-engine  --mode paper --a2a-port 9002 --auto-approve
forge run ./alpha-trader --mode paper --a2a-port 9003 --auto-approve
```

## Verification
- price-oracle's wallet should accumulate USDC from peer payments
- risk-engine's wallet should accumulate USDC from peer payments
- alpha-trader's `x402_audit.jsonl` shows outgoing payments to both peers

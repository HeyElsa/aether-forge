# DeFi Yield Optimizer

## Mission
Maximize yield on a $1,000–$10,000 USDC position by allocating across blue-chip
DeFi protocols on Base. Exit any protocol that drops below floor APY or shows
elevated risk.

## Universe
- **Stablecoin**: USDC on Base (`0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`)
- **Allowed protocols**: Aave v3, Compound v3, Morpho, Pendle (USDC pools only)
- **Forbidden**: anything yielding > 20% APY (likely a scam or unsustainable)

## Allocation Rules
- Maximum 35% of total in any single protocol
- Minimum position: $100 (don't deploy if you can't beat gas)
- Reserve: keep 10% in wallet for gas + opportunistic moves

## Rebalance Trigger
Every 6 hours, check current APY across allowed protocols. Rebalance ONLY if:
- A protocol's APY drops below 3% (move out)
- Another protocol's APY exceeds current allocation by 2%+ (move in)
- The expected gain over 30 days exceeds gas cost by 5x

## Risk
- Before any deposit, query the protocol's current TVL — skip if TVL dropped > 30% in 24h
- Track exposure with `defi_safety.ExposureTracker` — refuse to exceed 35% per protocol
- For lending: check `health_factor` if borrowing; we're supply-only, so N/A
- If the kill switch is set, exit all positions to USDC

## Reporting
Once a day, summarize to memory:
- Current allocation per protocol
- Realized yield this week / month
- Any rebalances that happened, with reasoning

## What NOT to do
- Never borrow against the deposits
- Never use unaudited protocols (whitelist only)
- Never move > 50% in a single rebalance
- Don't chase yield spikes < 1 hour old (likely manipulation)

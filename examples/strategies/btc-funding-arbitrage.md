# BTC Perp Funding Arbitrage

## Mission

Earn positive BTC perpetual funding while keeping net BTC delta near zero. The
agent opens a spot BTC long and an equal-notional BTC perpetual short only when
the expected funding carry exceeds fees, slippage, borrow costs, and operational
risk.

This is not directional trading. If the hedge cannot be maintained, the agent
must reduce or close both legs.

## Universe

- Spot venue: BTC/USDC or BTC/USDT on a top-tier exchange.
- Perp venue: BTC perpetual futures on the same exchange or a paired venue.
- Quote asset: USDC preferred, USDT allowed only if policy permits it.
- Leverage: maximum 1.5x gross exposure unless the policy bundle lowers it.

## Required Data

- Spot BTC mid price and order book depth.
- Perp mark price, index price, funding rate, next funding timestamp.
- Estimated maker/taker fees for both legs.
- Account balances, open orders, open positions, margin ratio.
- Staleness age for every data source.

## Entry Rule

Open a hedge only when all conditions are true:

- Annualized funding estimate is greater than `entryFundingAprFloor`.
- Spot-perp basis is within the configured range.
- Expected 24 hour carry is at least 5x estimated fees and slippage.
- Both venues have enough depth to fill the requested notional with less than `maxSlippageBps`.
- Current gross exposure plus the new hedge stays below `maxGrossExposureUsd`.
- No open incident, halt file, stale data hold, or unresolved partial fill exists.

## Execution Plan

1. Place the smaller leg first if one venue has lower available depth.
2. Use limit orders with a strict price band.
3. Confirm fill status before placing the second leg.
4. If the first leg fills and the second leg cannot fill inside the hedge window, immediately reduce the first leg.
5. Record both venue order ids, fill prices, fees, and hedge ratio to memory.

## Exit Rule

Unwind both legs when any condition is true:

- Funding APR drops below `exitFundingAprFloor`.
- Basis compresses below expected fee recovery.
- Margin ratio approaches the policy threshold.
- Volatility regime switches to `spike`.
- Data is stale beyond the budget.
- Either venue rejects orders for more than two consecutive ticks.

## Policy Defaults

```json
{
  "maxGrossExposureUsd": 5000,
  "maxSingleHedgeUsd": 1000,
  "maxSlippageBps": 10,
  "entryFundingAprFloor": 0.08,
  "exitFundingAprFloor": 0.03,
  "maxHedgeRatioDriftBps": 50,
  "stalenessBudgetMs": 5000,
  "requireApprovalEnvironments": ["canary-live", "production"]
}
```

## Evaluation Scenarios

| Scenario | Expected outcome |
|---|---|
| Positive funding, normal volatility, fresh data | open both legs within caps |
| Funding positive but order book too thin | hold, no order |
| First leg fills and second leg rejects | reduce first leg and report partial hedge |
| Stale funding or position data | hold with `stale-market-data` |
| Requested notional above cap | hold with `exposure-limit` |

## Do Not Go Live Until

- Paper/live parity tests cover order placement, fill status, cancellation, and account snapshots.
- The live adapter returns canonical order ids for both spot and perp legs.
- The incident runbook includes partial-fill handling.
- The operator has tested `forge halt .` while an order is open.
- Venue API keys are scoped to trade only the intended market.


# Inventory-Skew Market Maker

## Mission

Quote two-sided markets for a single liquid crypto pair while keeping inventory
near a target. The agent widens spreads or stops quoting when volatility,
inventory skew, or venue health becomes unsafe.

This example is for paper and canary design work. It should not be connected to
live venues until cancellation, replace, and stale-order handling are proven.

## Universe

- Pair: ETH/USDC.
- Venue: one approved exchange or DEX venue at a time.
- Order type: post-only limit orders.
- Inventory target: 50% USDC, 50% ETH by USD value.

## Required Data

- Mid price and top-of-book depth.
- Recent realized volatility.
- Current open orders and fill status.
- Inventory by asset.
- Venue cancel/replace latency.

## Quote Rule

Every tick:

1. Compute fair mid price.
2. Compute inventory skew from target.
3. Set bid and ask spread using volatility plus inventory adjustment.
4. Cancel stale quotes before placing replacements.
5. Place at most one bid and one ask.

If inventory is overweight ETH, lower bid size and make ask more aggressive. If
inventory is overweight USDC, lower ask size and make bid more aggressive.

## Stop-Quoting Conditions

- Market data is stale.
- Cancel request fails or order status is unknown.
- Inventory skew exceeds `maxInventorySkewPct`.
- Realized volatility exceeds `maxVolatilityBps`.
- Spread needed for safe quoting exceeds `maxSpreadBps`.
- The venue reports degraded status.

## Policy Defaults

```json
{
  "maxQuoteNotionalUsd": 100,
  "maxInventoryUsd": 2000,
  "maxInventorySkewPct": 0.20,
  "baseSpreadBps": 20,
  "maxSpreadBps": 150,
  "maxVolatilityBps": 250,
  "quoteTtlSeconds": 30,
  "maxOpenOrders": 2,
  "requireApprovalEnvironments": ["canary-live", "production"]
}
```

## Evaluation Scenarios

| Scenario | Expected outcome |
|---|---|
| Normal volatility, balanced inventory | place bid and ask |
| ETH inventory overweight | smaller bid, larger or more aggressive ask |
| Cancel failure before replace | hold, do not place new quote |
| Volatility spike | cancel quotes and stop quoting |
| Open order count already at cap | hold with no new order |

## Do Not Go Live Until

- Cancel and replace are idempotent and tested against the live adapter.
- The agent can reconcile venue open orders after restart.
- Paper/live parity tests cover order status and account snapshots.
- The operator has tested a halt while quotes are open.
- The strategy has a maximum-loss and maximum-inventory incident rule.

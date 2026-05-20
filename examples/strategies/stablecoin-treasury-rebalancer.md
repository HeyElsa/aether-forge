# Stablecoin Treasury Rebalancer

## Mission

Maintain a conservative treasury split across approved stablecoins and venues.
The agent rebalances USDC, USDT, and DAI exposure when drift exceeds policy
limits or when venue risk changes. It optimizes for capital preservation, not
yield.

## Universe

- Assets: USDC, USDT, DAI.
- Networks: Base and Ethereum mainnet, unless policy narrows the set.
- Venues: wallet balances, approved centralized exchange accounts, and
  whitelisted swap routes.
- Forbidden: algorithmic stables, bridged assets not listed in policy, leverage,
  borrowing, and unaudited yield venues.

## Target Allocation

| Asset | Target | Allowed band |
|---|---:|---:|
| USDC | 70% | 60-85% |
| USDT | 20% | 10-30% |
| DAI | 10% | 0-15% |

## Required Data

- Wallet balances by chain.
- Exchange balances by asset.
- Stablecoin price deviations from $1.00.
- Swap quote, route, expected slippage, gas estimate.
- Venue health status and withdrawal status.

## Rebalance Rule

Rebalance only when:

- allocation drift exceeds the allowed band,
- the expected slippage plus gas is below `maxRebalanceCostBps`,
- the source and destination assets are both policy-approved,
- the route does not pass through a forbidden token,
- balances and quotes are fresh.

## Risk Controls

- Maximum single rebalance: 20% of treasury.
- Maximum daily rebalance volume: 40% of treasury.
- Never swap into an asset trading below $0.995 or above $1.005 unless the operator approves a depeg response.
- If any stablecoin deviates beyond 1%, stop normal rebalancing and enter incident mode.
- Keep at least `gasReserveUsd` worth of native gas token on each active chain.

## Policy Defaults

```json
{
  "allowedChains": ["base", "ethereum"],
  "allowedAssets": ["USDC", "USDT", "DAI"],
  "maxSingleRebalancePct": 0.20,
  "maxDailyRebalancePct": 0.40,
  "maxRebalanceCostBps": 5,
  "maxStablecoinDeviationBps": 50,
  "gasReserveUsd": 25,
  "requireApprovalEnvironments": ["canary-live", "production"]
}
```

## Evaluation Scenarios

| Scenario | Expected outcome |
|---|---|
| USDC overweight by 20%, normal quotes | rebalance to target band |
| USDT depeg to $0.985 | halt normal rebalance, report incident |
| Route includes forbidden bridge token | deny route |
| Gas estimate exceeds max cost | skip and retry later |
| Chain id missing from signing intent | deny signing |

## Do Not Go Live Until

- Wallet backup is encrypted and recovery tested.
- Swap simulation is enabled before signing.
- Stablecoin depeg alerts reach the operator.
- The agent can prove daily volume caps from replay evidence.
- The operator has a manual depeg playbook.


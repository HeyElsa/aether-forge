# Examples

These examples show Aether Forge's current product shape: spec-first artifacts, policy-governed execution, and SDK-readable contracts.

## Reference Agents

| Example | Use it for |
|---|---|
| [`delta-neutral-btc/`](./delta-neutral-btc/) | Full crypto-native artifact set: spec, capabilities, policy, scenarios, research, and promotion evidence |
| [`two-agent-marketplace/`](./two-agent-marketplace/) | Agent-to-agent discovery, x402 payment flow, wallet isolation, and marketplace dashboard |
| [`strategies/`](./strategies/) | Strategy prompts and policy sketches for common agent patterns |

## Strategy Library

The strategy briefs under [`strategies/`](./strategies/) are intentionally more detailed than prompt snippets. Each one names the asset universe, required data, policy defaults, evaluation scenarios, and go-live blockers.

| Strategy | What it demonstrates |
|---|---|
| [`btc-funding-arbitrage.md`](./strategies/btc-funding-arbitrage.md) | Delta-neutral spot/perp carry, hedge-ratio control, partial-fill recovery |
| [`stablecoin-treasury-rebalancer.md`](./strategies/stablecoin-treasury-rebalancer.md) | Conservative stablecoin allocation, depeg response, route controls |
| [`inventory-skew-market-maker.md`](./strategies/inventory-skew-market-maker.md) | Two-sided quoting, inventory skew, cancel/replace safety |
| [`dca-eth.md`](./strategies/dca-eth.md) | Scheduled accumulation with gas and spend controls |
| [`yield-optimizer.md`](./strategies/yield-optimizer.md) | Whitelisted supply-only DeFi allocation |
| [`multi-agent-team.md`](./strategies/multi-agent-team.md) | A2A oracle/risk/trader coordination with x402 budgets |

Use them as `--strategy-file` inputs, then convert the critical rules into typed policies and scenario tests before live use.

## Validate From TypeScript

JavaScript and TypeScript hosts can validate example artifacts without running the Python runtime:

```ts
import { validateArtifactBundle } from "@aether-forge/sdk";

const result = validateArtifactBundle({
  agentSpec,
  capabilityManifest,
  policyBundle,
  scenarioPack,
});

if (!result.ok) {
  console.error(result.results);
}
```

The SDK is intentionally validation and interface-only in v0.1.x. Use Python for runtime execution, policy enforcement, memory stores, autoresearch, and signer implementations.

## Safety Defaults

- Generated artifacts are the contract; do not put secrets in specs, prompts, replays, or memory.
- Side-effecting capabilities default to deny until policy explicitly allows them.
- x402 and agent-to-agent payments share the same budget controls.
- Session-key policies with `allowed_chains` fail closed when a signing intent lacks a chain id.
- Production promotion should be evidence-backed with scenario results and replays.

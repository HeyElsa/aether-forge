# Examples

These examples show Aether Forge's current product shape: spec-first artifacts, policy-governed execution, and SDK-readable contracts.

## Reference Agents

| Example | Use it for |
|---|---|
| [`delta-neutral-btc/`](./delta-neutral-btc/) | Full crypto-native artifact set: spec, capabilities, policy, scenarios, research, and promotion evidence |
| [`two-agent-marketplace/`](./two-agent-marketplace/) | Agent-to-agent discovery, x402 payment flow, wallet isolation, and marketplace dashboard |
| [`strategies/`](./strategies/) | Strategy prompts and policy sketches for common agent patterns |

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

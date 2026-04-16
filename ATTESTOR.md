# Aether Forge Framework Attestor

This document defines the framework attestor — the identity used to verify that an agent was genuinely created by Aether Forge.

## The impersonation problem

The ERC-8004 on-chain agent registry is **public and general**. Anyone can register an agent with metadata claiming `framework=aether-forge`. Since the framework is open-source, there's no secret embedded in the code that a copycat couldn't extract.

## Two-layer defense

### Layer 1 — Self-attestation (automatic)

Every agent generated through `forge generate-fast` signs an EIP-712 attestation at creation time using its own OWS wallet. The attestation links the agent's `artifactSetId`, `capabilitiesHash`, and `agentAddress` into a verifiable signature saved as `attestation.json` in the agent directory.

**What this proves:** the wallet owner authorized this agent's creation with these specific capabilities.

**What this doesn't prove:** that Aether Forge generated it (any code could sign the same type).

### Layer 2 — Framework attestation (opt-in)

The Aether Forge project maintains a well-known **attestor wallet**. After an agent registers on-chain, the attestor verifies the agent's artifacts and signs a framework attestation. This is the only signature an impersonator cannot produce — they would need the project team's private key.

## Framework attestor address

> **Status: NOT YET PUBLISHED**
>
> The attestor address will be set once the project team generates and funds the attestor wallet on Base mainnet. This document and the `FRAMEWORK_ATTESTOR_ADDRESS` constant in `src/aether_forge/attestation.py` will be updated simultaneously.
>
> When published, the address will also be registered as on-chain metadata on the ERC-8004 registry so it's verifiable without trusting this Git repository.

## Trust tiers

| Tier | Meaning | How a verifier checks |
|---|---|---|
| **Verified** | Framework attestor signed it | `getMetadata(agentId, "aether_forge_verified")` returns a valid signature from the published attestor address |
| **Self-attested** | Agent's own wallet signed it | `attestation.json` has a valid EIP-712 signature and `tier=self-attested` |
| **Unverified** | Just metadata tags | `framework=aether-forge` in metadata but no valid signatures — treat with caution |

`forge agent-discover` shows the trust tier for every discovered agent:

```bash
forge agent-discover --capability get-token-price --verified-only
```

## Verification process (Layer 2)

When the attestor is operational, the verification flow will be:

1. Agent owner runs `forge agent-register <id>` to register on-chain
2. Agent owner requests verification (exact mechanism TBD — could be a CLI command, a GitHub issue, or an automated check)
3. The attestor:
   - Fetches the agent's metadata URI from the registry
   - Validates the capability manifest against Aether Forge JSON schemas
   - Checks that the A2A endpoint serves a valid Agent Card
   - Optionally runs `forge validate` against the published artifacts
4. If all checks pass, the attestor calls `setMetadata(agentId, "aether_forge_verified", <signature>)` on-chain
5. The agent is now discoverable with tier = **Verified**

## For framework contributors

If you're working on the attestation system:

- **Attestation module:** `src/aether_forge/attestation.py`
- **EIP-712 types:** `ATTESTATION_TYPES` and `ATTESTATION_DOMAIN` constants in the same file
- **Self-attestation creation:** `create_self_attestation()` — called automatically at generation time
- **Verification functions:** `verify_self_attestation()`, `verify_framework_attestation()`, `determine_trust_tier()`
- **On-chain registry client:** `src/aether_forge/onchain_registry.py`
- **Tests:** `tests/test_attestation.py`

The attestor address constant is `FRAMEWORK_ATTESTOR_ADDRESS` in `attestation.py`. Set it to the real address once the attestor wallet is generated.

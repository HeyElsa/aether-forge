# Aether Forge Product Requirements Document

Version: `v0.9.0`
Status: `Draft`
Date: `2026-04-07`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.8.0.md`
Base PRD: `docs/prd/aether-forge-prd-v0.8.0.md`
Supporting design:

- `docs/plans/2026-04-06-aether-forge-schema-design.md`

## 1. Status

This PRD version inherits all unchanged requirements from `v0.8.0`.

`v0.9.0` is a major capability expansion that transforms Aether Forge from a standalone agent builder into a participant in the open agent economy. It adds:

- Open agent economy protocols: ERC-8004, ERC-8126, ERC-8183, x402 (new)
- Defense-in-depth security hardening (new)
- Full OWS wallet support expanded from 6 to 21 SDK functions (updated)
- Skills integration with multiple registries (updated)

## 2. Summary Of Changes

Compared with `v0.8.0`, this version:

1. adds four open agent economy protocol modules (ERC-8004, ERC-8126, ERC-8183, x402) that allow every forge agent to register identity, establish trust, transact work, and make micropayments on-chain
2. adds a defense-in-depth security module with session key policies, budget controls with circuit breakers, prompt injection detection, rate limiting, audit logging, and environment-tiered defaults
3. expands OWS wallet support from 6 to 21 SDK functions covering the full wallet lifecycle, signing, policy management, API key management, and utilities
4. updates skills integration with additional registries and the `bankr:skill-name` shorthand

## 3. Open Agent Economy Protocols (New)

Every forge agent is a first-class participant in the open agent economy via four Ethereum standards. All protocol modules are implemented as stdlib-only Python with no web3 dependency in core.

### 3.1 ERC-8004 -- Agent Identity & Registry

Agents register on-chain with an Agent Card that declares their name, description, services, and x402 support. The Agent Card is the canonical identity artifact for any forge agent participating in the open economy.

- `generate_agent_card_from_artifacts()` builds Agent Cards from forge artifact bundles (agent spec, capability manifest, scenario pack)
- Identity registries allow other agents and humans to discover and validate agent identities
- Reputation registries track agent performance and reliability over time
- Validation registries confirm agent capabilities against declared services
- Module: `src/aether_forge/protocols/erc8004.py`

### 3.2 ERC-8126 -- Agent Trust & Verification

Multi-dimensional trust scoring enables agents to assess each other before entering into work agreements or payments.

- Four verification types:
  - **ETV** (Execution Trust Verification): measures reliability of task execution
  - **SCV** (Security Compliance Verification): measures adherence to security policies
  - **WAV** (Wallet Activity Verification): measures wallet transaction history and patterns
  - **WV** (Work Verification): measures quality and completeness of delivered work
- Risk scoring on a 0-100 scale with five tiers:
  - Low: 0-20
  - Moderate: 21-40
  - Elevated: 41-60
  - High: 61-80
  - Critical: 81-100
- `assess_agent_trust()` performs offline trust assessment from forge artifacts without requiring on-chain calls
- Trust scores feed into promotion decisions: agents must achieve acceptable trust scores before promotion to production
- Module: `src/aether_forge/protocols/erc8126.py`

### 3.3 ERC-8183 -- Agentic Commerce

Job primitives enable agent-to-agent work agreements with escrowed payment and structured lifecycle management.

- Job operations: create, fund, submit, evaluate, complete, reject
- Escrowed payment model with a dedicated evaluator role that judges submitted work
- Job lifecycle states:
  - **Open**: job created, waiting for funding
  - **Funded**: payment escrowed, waiting for worker submission
  - **Submitted**: work delivered, waiting for evaluator judgment
  - **Completed**: evaluator approved, payment released to worker
  - **Rejected**: evaluator rejected, payment returned to creator
  - **Expired**: job timed out without completion
- Job primitives integrate with the capability manifest: creating or funding a job is a side-effecting capability subject to policy governance
- Module: `src/aether_forge/protocols/erc8183.py`

### 3.4 x402 -- HTTP Micropayments

Agents discover and pay for services using the x402 HTTP micropayment protocol.

- Agents discover paid endpoints via the `402index.io` directory
- Automatic 402 payment flow:
  1. Agent sends request to a paid endpoint
  2. Endpoint returns HTTP 402 with payment requirements
  3. Agent parses payment requirements (amount, token, chain, recipient)
  4. Agent executes payment via OWS wallet
  5. Agent retries the original request with payment proof
- Budget controls integrated with the security module (Section 4) to prevent runaway spending
- Multiple registries supported:
  - `skills.sh` -- general-purpose paid skills
  - `bankr.bot` -- crypto and DeFi focused paid services
  - Any x402-enabled API endpoint
- x402 payments are audit-logged and subject to session key spending caps
- Module: `src/aether_forge/protocols/x402.py`

### 3.5 Protocol Safety Rules

The following rules apply to all open agent economy protocol interactions:

1. Protocol modules must remain stdlib-only with no web3 dependency in core
2. All on-chain interactions must go through the OWS wallet layer, never raw key material
3. Agent Cards must not contain secret material; credential handles must be used where authentication is needed
4. Trust assessments must be reproducible from artifact bundles without requiring live network calls
5. Job funding and payment operations are side-effecting capabilities subject to default-deny policy
6. x402 payments must respect budget controls and circuit breakers defined in the security module
7. All protocol operations must be audit-logged

## 4. Security Hardening (New)

Defense-in-depth security for autonomous agents operating in the open economy. The security module provides layered protections that apply across all agent operations.

Module: `src/aether_forge/security.py`

### 4.1 Session Key Policies

Scoped session keys prevent agents from having unrestricted wallet access.

- Contract allowlists: session keys can only interact with specified contract addresses
- Chain allowlists: session keys are restricted to specified chains
- Per-transaction spending caps: maximum value per individual transaction
- Per-day spending caps: cumulative daily spending limit
- Expiry: session keys automatically expire after a configured duration
- Session keys must never grant master wallet access

### 4.2 Budget Controls with Circuit Breakers

Automatic spending velocity monitoring prevents runaway costs.

- Rolling average spending velocity tracked per agent per environment
- Circuit breaker triggers when spending exceeds 3x the rolling average
- Circuit breaker auto-pauses all payment operations until manual review
- Budget controls apply to both x402 micropayments and ERC-8183 job funding
- Per-environment budget ceilings configurable independently

### 4.3 Prompt Injection Detection

12 compiled regex patterns detect common prompt injection attack vectors:

- Instruction override attempts
- Role impersonation
- Jailbreak patterns
- Delimiter injection
- Hidden content insertion
- Base64-encoded payloads
- Zero-width unicode characters

Prompt injection scanning must be enabled in canary and production environments. Sandbox environments may optionally disable scanning for testing purposes.

### 4.4 Rate Limiting

Token-bucket rate limiter for all agent operations.

- Configurable bucket size and refill rate per operation type
- Applies to wallet operations, protocol interactions, and external API calls
- Prevents burst abuse and ensures fair resource usage

### 4.5 Audit Logging

Append-only audit log for all security-sensitive operations:

- `wallet.sign` -- all signing operations
- `x402.payment` -- all micropayment transactions
- `job.create` -- all job creation operations
- `job.fund` -- all job funding operations
- `trust.assess` -- all trust assessment operations
- `session_key.create` -- all session key creation
- `session_key.use` -- all session key usage

Audit log entries include timestamp, agent identity, operation type, parameters, environment, and outcome.

### 4.6 Environment-Tiered Defaults

Security defaults are tiered by environment from most permissive to strictest:

| Setting | Sandbox | Paper | Canary | Production |
|---|---|---|---|---|
| Session key required | No | Yes | Yes | Yes |
| Budget circuit breaker | Off | On | On | On |
| Prompt injection scan | Off | Off | On | On |
| Rate limiting | Relaxed | Moderate | Strict | Strict |
| Audit logging | Optional | Required | Required | Required |
| Max tx value | Unlimited | $100 | $1,000 | Configurable |

These defaults can be overridden by explicit policy, but overrides are audit-logged.

## 5. Full OWS Wallet Support (Updated)

The OWS wallet integration is expanded from 6 to 21 SDK functions, covering the complete wallet lifecycle.

### 5.1 Wallet Lifecycle

- `create_wallet()` -- create a new wallet
- `import_wallet_mnemonic()` -- import wallet from mnemonic phrase
- `import_wallet_private_key()` -- import wallet from private key
- `delete_wallet()` -- delete a wallet (requires confirmation)
- `export_wallet()` -- export wallet credentials (requires confirmation, audit-logged)
- `rename_wallet()` -- rename an existing wallet

### 5.2 Signing Operations

- `sign_message()` -- sign an arbitrary message
- `sign_transaction()` -- sign a transaction without broadcasting
- `sign_typed_data()` -- sign EIP-712 typed data
- `sign_and_send()` -- sign and broadcast a transaction

### 5.3 Policy Management

- `create_policy()` -- create a new wallet policy (spending limits, contract allowlists)
- `list_policies()` -- list all policies for a wallet
- `get_policy()` -- retrieve a specific policy by ID
- `delete_policy()` -- delete a wallet policy

### 5.4 API Key Management

- `create_api_key()` -- create a new API key for wallet access
- `list_api_keys()` -- list all API keys
- `revoke_api_key()` -- revoke an existing API key

### 5.5 Utilities

- `generate_mnemonic()` -- generate a new BIP-39 mnemonic phrase
- `derive_address()` -- derive an address from a mnemonic or private key

### 5.6 New CLI Commands

- `forge wallet-import` -- import a wallet from mnemonic or private key
- `forge wallet-delete` -- delete a wallet
- `forge wallet-export` -- export wallet credentials

### 5.7 Wallet Safety Rules

All wallet safety rules from earlier PRD versions remain in force. Additionally:

1. All wallet operations must go through the audit log
2. Session keys must never grant master wallet access
3. Wallet export operations require explicit user confirmation and are always audit-logged
4. Wallet import operations must validate input before creating wallet state
5. Private key material must never appear in specs, prompts, traces, or persisted state

## 6. Skills Integration (Updated)

Skills integration is updated from `v0.8.0` with additional registry support and convenience features.

### 6.1 Multiple Registries

Skills can be sourced from multiple registries:

- `skills.sh` -- general-purpose skills registry
- `bankr.bot` -- crypto and DeFi focused skills registry (also accessible as `skills.bankr.bot`)
- Any GitHub repository containing `SKILL.md` files

### 6.2 Registry Shorthand

The `bankr:skill-name` shorthand resolves to the BankrBot/skills repository for convenience. This shorthand is available in all CLI commands that accept skill sources.

### 6.3 Capability Manifest Mapping

Skills from all registries are mapped to forge capabilities in the capability manifest. The mapping ensures that skill-sourced capabilities are subject to the same governance as built-in capabilities, including:

- Default-deny policy enforcement
- Environment-scoped permission checks
- Sensitivity classification
- Side-effect governance (idempotency, retry, compensation semantics)

All skills safety rules from v0.8.0 Section 4.5 remain in force.

## 7. Implementation Status Updates

### 7.1 Protocol Modules

The following protocol modules are implemented:

- `src/aether_forge/protocols/erc8004.py` -- Agent Identity & Registry
- `src/aether_forge/protocols/erc8126.py` -- Agent Trust & Verification
- `src/aether_forge/protocols/erc8183.py` -- Agentic Commerce
- `src/aether_forge/protocols/x402.py` -- HTTP Micropayments

### 7.2 Security Module

The security module is implemented at `src/aether_forge/security.py` with all components described in Section 4.

### 7.3 OWS Wallet Expansion

The OWS wallet integration is expanded to 21 SDK functions as described in Section 5. New CLI commands are operational.

## 8. Inherited Requirements

All requirements from `v0.8.0` (and transitively from `v0.7.0` through `v0.1.0`) remain in force unless explicitly updated in this document. In particular:

- The memory model, memory safety rules, memory promotion policy, and memory environment separation rules from v0.7.0 are unchanged
- The artifact compatibility, credential-handle, and effect-semantics requirements from v0.6.0 are unchanged
- The autoresearch loop mechanics, iteration ledger, and protected-evaluator requirements from v0.4.0 are unchanged
- The core lifecycle, environment model, and governance requirements from earlier versions are unchanged
- The skills safety rules from v0.8.0 are unchanged and extended by protocol safety rules in Section 3.5

## 9. Functional Requirements Additions

The following requirements are added on top of `v0.8.0`.

### Open Agent Economy Protocols

- The system must support ERC-8004 Agent Card generation from forge artifact bundles.
- The system must support agent identity registration and discovery through on-chain registries.
- The system must support multi-dimensional trust assessment (ERC-8126) with ETV, SCV, WAV, and WV verification types.
- The system must support offline trust assessment from forge artifacts without requiring live network calls.
- The system must support ERC-8183 job lifecycle management (create, fund, submit, evaluate, complete, reject).
- The system must support escrowed payment with evaluator-judged work delivery.
- The system must support x402 HTTP micropayment discovery via 402index.io.
- The system must support automatic 402 payment flow: request, parse requirements, pay, retry.
- The system must enforce budget controls on all x402 payments.

### Security Hardening

- The system must support session key policies with contract/chain allowlists and spending caps.
- The system must support budget controls with circuit breakers that trigger at 3x rolling average.
- The system must support prompt injection detection with at least 12 compiled regex patterns.
- The system must support token-bucket rate limiting for all agent operations.
- The system must support append-only audit logging for all security-sensitive operations.
- The system must support environment-tiered security defaults (sandbox, paper, canary, production).

### OWS Wallet Expansion

- The system must support wallet import from mnemonic and private key.
- The system must support wallet delete, export, and rename operations.
- The system must support EIP-712 typed data signing.
- The system must support sign-and-send as a single atomic operation.
- The system must support wallet policy CRUD operations.
- The system must support API key creation, listing, and revocation.

## 10. Non-Functional Requirements Additions

- Protocol modules must remain stdlib-only with no web3 dependency in core
- Trust assessments must complete within 500ms for offline artifact-based scoring
- Prompt injection detection must add less than 10ms latency per prompt
- Audit log writes must not block the calling operation
- Session key validation must complete within 50ms
- Circuit breaker state changes must be durable across process restarts
- All new modules must maintain the existing public API stability guarantee

## 11. Roadmap Implications

### Open Agent Economy

Protocol modules are operational for v1. Future work includes:

- On-chain registration transaction support (currently generates artifacts only)
- Live trust score aggregation from multiple on-chain sources
- Multi-chain job escrow support
- x402 payment channel optimization for high-frequency micropayments
- Agent reputation dashboard and analytics

### Security

Security module is operational for v1. Future work includes:

- Machine learning-based prompt injection detection
- Anomaly detection for spending patterns beyond simple rolling averages
- Hardware security module (HSM) integration for session key storage
- Formal verification of policy enforcement logic

### Wallet

Full wallet SDK is operational for v1. Future work includes:

- Multi-signature wallet support
- Social recovery mechanisms
- Cross-chain wallet abstraction
- Gas optimization strategies

## 12. Open Questions

Inherited from v0.8.0:

- Which low-risk memory types, if any, should ever be auto-promotable later?
- Should `operator-preference` memory have lighter promotion requirements than strategy or incident memory?
- How much retention enforcement should be built into v1 versus delegated to the storage backend?
- Should memory records eventually become part of promotion evidence bundles automatically?
- Should skills declare their own sensitivity classification, or should that be inferred from their capability mappings?
- Should skill registries support signed skill manifests for trust verification?
- Should the `bankr:` shorthand be generalized to a configurable registry alias system?
- What is the upgrade path when an installed skill's `SKILL.md` changes in a breaking way?

New in v0.9.0:

- Should Agent Cards (ERC-8004) be auto-generated on every artifact build, or only on explicit request?
- What is the minimum trust score threshold for agent-to-agent job creation?
- Should trust assessment results be cached, and if so, what is the appropriate TTL?
- Should x402 payment failures trigger automatic retry with backoff, or fail immediately?
- Should circuit breaker thresholds be configurable per-agent, or global per-environment?
- What is the correct behavior when prompt injection is detected: block, warn, or quarantine?
- Should audit logs support structured export for external SIEM integration in v1?
- Should wallet export require multi-factor confirmation beyond the single confirmation gate?

## 13. Final Recommendation

`Aether Forge` v0.9.0 transforms the framework from a standalone agent builder into a full participant in the open agent economy. Agents built with Aether Forge can now register identity, establish trust, transact work, and make micropayments using open Ethereum standards.

The security hardening ensures that these new economic capabilities are bounded by defense-in-depth protections: session key scoping, budget circuit breakers, prompt injection detection, rate limiting, and comprehensive audit logging.

The correct product posture remains:

- spec-first ownership
- policy enforcement on all capability surfaces, including protocols and payments
- environment separation with tiered security defaults
- evidence-backed promotion with trust assessment gates
- explicit, auditable operations with append-only logging
- self-evolution through bounded, reviewable loops

The open agent economy protocols extend the product surface without weakening governance. Every new economic action is a governed capability subject to the same default-deny, policy-checked, audit-logged discipline as any other forge operation.

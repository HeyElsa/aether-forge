# Aether Forge PRD v0.24.0

**Date**: 2026-05-20
**Status**: Proposed
**Previous**: v0.23.1 (`docs/prd/aether-forge-prd-v0.23.1.md`)

---

## Summary

v0.24.0 is the battle-ready crypto readiness release. It keeps Aether Forge spec-first, developer-first, and general at the core while tightening the crypto-native module layer enough that builders can reason clearly about the path from sandbox to paper to live capital.

This release does not make live capital the default. It makes live-capital readiness explicit: risky tests are gated, external capability boundaries fail closed, placeholder live execution is removed, paper/live parity becomes measurable, production incident docs become first-class, and realistic crypto strategy examples document the guardrails needed before any deployment can move money.

## Release Objectives

1. Make risky crypto test suites visible but gated by explicit operator intent.
2. Harden signer, x402, wallet, MCP, and runtime prompt-context boundaries.
3. Remove placeholder live exchange execution paths that could imply real fills.
4. Add a paper/live parity harness for exchange orders and account snapshots.
5. Document live deployment, incident response, and "do not go live until" gates.
6. Provide realistic crypto strategy examples beyond scaffolds without encouraging unsafe live use.

## Requirements

### 1. Risky Crypto Test Gates

Tests that can touch external services, testnets, or live capital must be marked with explicit pytest markers:

- `integration`
- `network`
- `testnet`
- `live_capital`

The default test path must remain offline and safe for contributors. Network, testnet, and live-capital suites require explicit environment flags and credentials. A missing flag or credential must skip the test, not silently hit a provider.

CI must make these boundaries visible as separate jobs so maintainers can distinguish offline correctness from optional external readiness.

### 2. Fail-Closed External Boundaries

Security-sensitive boundaries must reject ambiguous input before side effects:

- x402 payment gates must structurally validate payment headers before executing paid capabilities.
- Wrong receiver, wrong network, unsupported asset, insufficient amount, replayed nonce, or missing settlement configuration must be rejected.
- x402 budget check, payment execution, and budget state updates must be atomic under a file lock.
- Session-key constrained signing must fail closed when required intent fields are missing.
- Wallet transfer intents must reject invalid or non-positive amounts.
- MCP direct tool execution must honor server-level `tools.include` and `tools.exclude` filters.
- Capability results from MCP, A2A, x402, and other external sources must be recursively scanned for prompt-injection patterns before entering planner prompt context.

### 3. Real Live Execution Boundary

Aether Forge must not fabricate live exchange transaction IDs or imply a real fill when no exchange adapter submitted an order.

Non-dry-run live exchange execution requires an explicit live submitter or project-specific exchange adapter. Generated agents must fail closed when the live adapter is disabled, absent, or misconfigured. Dry-run and validation-only paths remain available for local development, CI, and operational drills.

### 4. Paper/Live Parity Harness

The exchange integration layer must expose canonical order and account snapshot shapes that can be compared across paper and live adapters.

Parity reports should identify:

- order identifier mapping,
- symbol and side normalization,
- quantity and notional differences,
- status mapping,
- fee and fill metadata,
- account balance deltas,
- divergence severity.

Production promotion for an exchange-backed strategy should require paper/live parity evidence before canary or full live rollout.

### 5. Production Docs And Incident Response

The documentation site must include a clear live deployment path for crypto agents:

- a production readiness checklist,
- a dedicated incident response guide,
- live-capital stop conditions,
- rollback and kill-switch procedures,
- post-incident evidence collection,
- operator approval gates.

The docs must include an explicit "Do Not Go Live Until" checklist. The checklist should be framed as a gate, not as advice.

### 6. Realistic Strategy Examples

Crypto examples must go beyond toy scaffolds while staying sandbox-first. Strategy examples should document:

- market thesis,
- data dependencies,
- execution surfaces,
- policy limits,
- wallet and exchange permissions,
- paper/live parity expectations,
- known failure modes,
- safe test path,
- live-readiness checklist.

Examples must not include a one-command path to live-capital deployment. Live promotion remains an operator-governed process.

## Implementation Slices

This release is intentionally split into independently reviewable slices:

1. Test markers, CI gates, and central skip logic.
2. x402/runtime/MCP/wallet fail-closed security hardening.
3. Live exchange adapter contract and removal of placeholder live execution.
4. Paper/live parity harness and divergence reporting.
5. Production incident and go-live documentation.
6. Realistic crypto strategy examples.

## Non-Negotiables Added

- Risky crypto tests must be marked and gated; default contributor tests must not touch networks, testnets, or live capital.
- Live-capital tests require explicit operator opt-in and must skip when credentials or enablement flags are absent.
- Runtime code must not synthesize fake live exchange execution results for non-dry-run live mode.
- Non-dry-run live exchange execution requires an explicit submitter or adapter and must fail closed when absent.
- Paper/live parity evidence is required before promoting exchange-backed strategies beyond sandbox or paper trading.
- Production readiness docs must contain an explicit "Do Not Go Live Until" gate for live-capital agents.
- Incident response docs are part of the live-capital readiness contract, not optional supporting material.
- Realistic crypto strategy examples must remain sandbox-first and must document risks, permissions, policy limits, and live-readiness gates.

## Verification Plan

- Offline contributor suite passes without external credentials.
- Gated network/testnet/live-capital tests skip by default and collect when their markers are selected.
- Security hardening tests cover malformed x402 headers, wrong receiver/network/asset, replayed nonce, budget locking, missing signer intent fields, invalid wallet amounts, MCP tool filtering, and recursive prompt-injection scanning.
- Live exchange tests prove non-dry live execution refuses to run without an explicit submitter or adapter.
- Parity tests compare fake live and paper adapters through the canonical order/account snapshot shapes.
- Docs-site build passes after adding production readiness, incident response, and strategy example pages.

## Open Questions

- Which real exchange adapter should be the first officially supported live adapter?
- Which testnet or sandbox exchange should be the canonical CI-safe integration target?
- What severity thresholds should block promotion when paper/live parity divergence is detected?
- Who owns the published incident contact and escalation path for framework-hosted examples?

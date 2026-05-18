# Aether Forge PRD v0.23.0

**Date**: 2026-05-16
**Status**: Approved
**Previous**: v0.22.0 (`docs/prd/aether-forge-prd-v0.22.0.md`)

---

## Summary

v0.23.0 is the **TypeScript SDK + cross-language conformance** release. It is Sprint 3 (and the closing sprint) of the dev-feedback retrospective. v0.21.0 closed the silent-failure paths, v0.22.0 spec-first'd the missing seams, and v0.23.0 puts the framework's contract behind a second-language SDK and a language-neutral planner-output spec.

The five friction points that motivated the retrospective are now closed end-to-end:

| FP | Closed by |
|---|---|
| FP-1 (LLM planner resilience) | v0.21.0 `_extract_json` + retry envelope + v0.22.0 native tool-use + v0.23.0 normative spec + cross-language fixtures |
| FP-2 (Ollama-first auto-detect) | v0.21.0 cloud-first reorder + v0.22.0 `deploymentProfile` escalation |
| FP-3 (hosted-marketplace trust) | v0.22.0 `DelegatedSigner` Protocol + reference impls + payer allowlist (Python side); v0.1.1 `@aether-forge/sdk/x402` will follow (browser side) |
| FP-4 (schema versioning) | v0.21.0 `MEMORY_RECORD_SCHEMA_VERSION` + v0.22.0 `MigrationRunner` |
| FP-5 (Python-only barrier) | **v0.23.0 `@aether-forge/sdk` TypeScript SDK + 19-schema generated types + cross-language conformance** |

For existing Python users, behavior is unchanged. The new SDK lives in `sdk-ts/` as a sibling package; no Python code imports it. CI gates ensure the two implementations stay in lockstep on the parts they share (JSON schemas, planner-output spec).

---

## What's New

### 1. Language-agnostic planner-output spec (FP-1, cross-language)

The original dev feedback pointed out two equally valid paths for the planner resilience work: embed the logic in the model client, or publish it as a language-agnostic spec. v0.21.0 took the first path; v0.23.0 takes the second.

**Shipped:**

- **`docs/specs/planner-output.md`** — normative behavioral spec at version 1.0.0. Covers: input shapes (clean JSON, fenced, preambled, truncated, garbage), the four-step recovery algorithm (trim → fence-strip → JSON.parse → balanced-brace recovery), the observability contract (`last_planner_parse_failure` event with four discriminator kinds), the retry envelope rules (transient HTTP codes, `Retry-After` honoring, opt-out), the conformance fixture protocol, and the versioning policy.
- **`src/aether_forge/schemas/runtime/planner-output.schema.json`** — structural contract pinning the JSON shape every parser produces. Either `{steps: PlannerStep[]}` or `PlannerStep[]`; each step has `kind` (one of five `StepKind` values), `description`, optional `capabilityId` / `capability_id` / `payload`.
- **`tests/fixtures/planner-outputs/`** — 13 baseline fixtures covering every recovery case mentioned in the spec. Format: `{description, input, expected: {outcome: "parsed" | "parse-failure", value?: <value>}}`. Adding a fixture is a single-step change; both reference implementations pick it up automatically via filesystem discovery.
- **`tests/test_planner_output_spec.py`** — Python conformance test that parametrizes over every fixture, plus two meta-tests (minimum-count tripwire, required-shape assertion).

The TypeScript counterpart (`sdk-ts/test/conformance.test.ts`) runs the same fixtures through the new `parsePlannerOutput` and asserts identical results. CI runs both jobs on any change to the spec, schemas, or fixtures.

### 2. `@aether-forge/sdk` TypeScript SDK v0.1.0 (FP-5)

The Python-only adoption barrier was the dev's single biggest concern ("most of the agent-marketplace ecosystem is JS/TS; a TypeScript SDK exposing the same `Planner` / `DataSource` / `MemoryStore` protocols would dramatically expand adoption"). v0.23.0 ships the thin-SDK scope from the plan: validators + types + the planner-output parser. Runtime tick loop and policy gate are deliberately deferred.

**Shipped:**

- **`sdk-ts/` sibling directory** in the monorepo. Standalone `package.json`, no root workspace, mirrors the v0.20.0 pattern that lets `docs-site/` coexist with Python without monorepo machinery.
- **Generated types for 19 schemas** — bundled into `sdk-ts/src/schemas/generated/index.ts` by `scripts/generate-schemas.ts`. Generator uses `json-schema-to-typescript` with an in-bundle JSON-Pointer rewrite for cross-schema `$ref`s, then post-processes to strip the synthetic root interface. Bundle is committed; CI verifies it matches a fresh regeneration.
- **Ajv-backed validators** — `validateAgentSpec`, `validateCapabilityManifest`, `validatePolicyBundle`, `validateScenarioPack`, `validateResearchRecord`, `validatePromotionRecord`, `validateMemoryRecord`, `validateScaffoldManifest`, `validateMigrationContract`, `validatePlannerOutput`, `validateDelegatedSigner`, `validateAgentConfig`, plus the composite `validateArtifactBundle`. Returns Result objects or throws via `assertValid<T>`. All schemas are pre-registered on the ajv instance so cross-schema `$ref` URLs resolve in-memory without network fetches.
- **`parsePlannerOutput`** — TypeScript reference implementation of the planner-output spec. Pure function, no dependencies, mirrors `_extract_json` exactly: `FENCE_OPEN_RE` / `FENCE_CLOSE_RE`, `JSON.parse` happy path, string-aware balanced-brace scan, `PlannerParseError` on miss.
- **Protocol interfaces** — `Planner`, `ExecutionRouter`, `MemoryStore`, `DataSource`, `PlanningModel`, `DelegatedSigner` mirror the Python Protocols at `runtime.py`, `memory.py`, `data_layer.py`, `planner.py`, `crypto/signers.py`. Plus `StepProposal`, `StepKind`, `ExecutionResult`, `RuntimeSession`, `ArtifactBundle`, `FunctionCallResponse`, `FunctionToolCall`, `MemoryQuery`, `MemoryPromotionRequest`, `MemoryPromotionResult`, `DataResult`, `SigningIntent`. Interface-only — no runtime implementations in v0.1.0.
- **Error hierarchy** — `AetherForgeError` is the base class; `PlannerParseError`, `ValidationError`, `SchemaCompatError` extend it. Preserves prototype chain across the ES2015 class boundary so `instanceof` survives bundler transformations.
- **Build & test stack** — `tsup` (dual esm + cjs + .d.ts output), `vitest`, `tsx`, TypeScript 5.6, ajv 8.x, ajv-formats 3.x. Stdlib-only at runtime beyond ajv.

### 3. CI: schema conformance gate (`.github/workflows/sdk-ts.yml`)

**Shipped:**

- New workflow scoped to changes under `sdk-ts/**`, `src/aether_forge/schemas/**`, `tests/fixtures/planner-outputs/**`, or `docs/specs/planner-output.md`.
- Pipeline: setup Bun → install (frozen lockfile) → **regenerate schemas + `git diff --exit-code`** (fails if the committed bundle drifted from the source JSON schemas) → typecheck → build → test.
- Cross-language conformance runs as part of the standard vitest job; no separate gate needed.

---

## Verification

- **Python suite**: 620 → 635 tests (+15 net: the parametrized fixture suite). All pass.
- **TypeScript suite**: 0 → 37 tests (14 parser unit + 9 validator + 14 conformance, including 13 fixtures + 1 tripwire). All pass.
- **Build**: `bun run build` → dist/index.js (51.65 KB ESM), dist/index.cjs (54.34 KB CJS), dist/index.d.ts (29.21 KB types). Clean.
- **Typecheck**: `bun run typecheck` — zero errors.
- **Cross-language sanity**: same 13 fixtures pass under both Python `_extract_json` and TS `parsePlannerOutput`. Real example agent at `examples/delta-neutral-btc/` validates under both Python `jsonschema` and TS `ajv`.

---

## Files Changed

| File | Change | Net lines |
|---|---|---|
| `docs/specs/planner-output.md` | NEW — normative spec | +180 |
| `src/aether_forge/schemas/runtime/planner-output.schema.json` | NEW | +50 |
| `tests/fixtures/planner-outputs/README.md` + 13 `.json` | NEW — conformance fixtures | +150 |
| `tests/test_planner_output_spec.py` | NEW — Python conformance | +85 |
| `sdk-ts/package.json` | NEW | +44 |
| `sdk-ts/tsconfig.json` | NEW | +25 |
| `sdk-ts/vitest.config.ts` | NEW | +9 |
| `sdk-ts/README.md` | NEW | +130 |
| `sdk-ts/.gitignore` | NEW | +5 |
| `sdk-ts/scripts/generate-schemas.ts` | NEW — schema generator | +150 |
| `sdk-ts/src/index.ts` | NEW — public surface | +60 |
| `sdk-ts/src/types/protocols.ts` | NEW — Protocol interfaces | +145 |
| `sdk-ts/src/types/errors.ts` | NEW — error hierarchy | +40 |
| `sdk-ts/src/validate/index.ts` | NEW — ajv validators | +110 |
| `sdk-ts/src/planner/parse.ts` | NEW — parsePlannerOutput | +105 |
| `sdk-ts/src/schemas/generated/index.ts` | NEW — generated bundle (committed) | +780 |
| `sdk-ts/test/parse.test.ts` | NEW — 14 tests | +90 |
| `sdk-ts/test/validate.test.ts` | NEW — 9 tests | +95 |
| `sdk-ts/test/conformance.test.ts` | NEW — 14 tests (cross-lang) | +60 |
| `.github/workflows/sdk-ts.yml` | NEW — CI gate | +55 |

20 new files, ~+2370 lines. No existing files modified.

---

## Non-Negotiables added (AGENTS.md §3)

- The planner-output spec (`docs/specs/planner-output.md` v1.0.0) is the cross-language contract. Both the Python reference (`aether_forge.planner._extract_json`) and the TypeScript reference (`@aether-forge/sdk` `parsePlannerOutput`) MUST conform to every shared fixture under `tests/fixtures/planner-outputs/`. Adding a fixture is the canonical way to extend the contract.
- The committed `sdk-ts/src/schemas/generated/index.ts` MUST match a fresh regeneration via `bun run generate:schemas`. CI fails the build on any drift.
- The TS SDK MUST register every JSON schema with its ajv instance up front (no network fetches at runtime). Any new schema added under `src/aether_forge/schemas/` MUST also be imported and addSchema'd in `sdk-ts/src/validate/index.ts`.
- `parsePlannerOutput` is a pure function with no dependencies beyond the stdlib. It MUST NOT acquire dependencies as the SDK grows — keeps it embeddable in any TS runtime (Node, browsers, edge, Workers).
- v0.1.0 of `@aether-forge/sdk` ships ZERO runtime behavior beyond validation and the planner-output parser. The runtime tick loop, policy gate, memory store implementations, autoresearch loop are explicitly out of scope until cross-language usage data justifies porting them — they are the highest lockstep surfaces.

---

## What's Next

The five-FP retrospective is closed end-to-end with this release. Follow-ups that fall out of it:

- **v0.1.1 of `@aether-forge/sdk`** — the `@aether-forge/sdk/x402` sub-package: `parse402Response`, `encodePaymentHeader`, `WalletSigner` interface, `eip1193Signer(provider)` (works with `window.ethereum` / Privy / RainbowKit), `fetchWithX402(signer, { confirm })`. Mirrors `src/aether_forge/protocols/x402.py` wire format exactly. Closes FP-3 on the browser side. Per the plan: ~1 sprint.
- **Spec evolution** — when a future Python parser change requires a recovery rule the spec doesn't cover, the change is a two-step PR: update `docs/specs/planner-output.md` (bump version per the rules in §8), add a fixture demonstrating the case, ensure both implementations pass. CI gates the rest.
- **Schema migration packages** — third parties can now ship transforms via the `aether_forge.migrations` entry-point group from v0.22.0. A `@aether-forge/migrations-v0.21-to-v0.22` package mirroring those transforms in TypeScript would let JS-side validators preview / dry-run the same migrations. Optional.

The framework is positioned as "the best framework for agent devs" — with the five reported frictions closed and a cross-language SDK shipped, that positioning is now backed by code, not just intent.

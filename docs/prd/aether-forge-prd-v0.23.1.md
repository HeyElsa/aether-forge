# Aether Forge PRD v0.23.1

**Date**: 2026-05-19
**Status**: Approved
**Previous**: v0.23.0 (`docs/prd/aether-forge-prd-v0.23.0.md`)

---

## Summary

v0.23.1 is a patch release that clarifies and hardens three contracts introduced across v0.21.0-v0.23.0, and brings the documentation set up to date with the new TypeScript SDK.

No product direction changes. The core remains spec-first, developer-first, general at the core, and crypto-native at the module layer.

## Contract Clarifications

### 1. Planner env vars are explicit operator choices

`AETHER_FORGE_PLANNER_MODE` is equivalent to passing `--planner-mode` for generation-time provenance. When `forge generate-fast --deployment-profile production` runs with `AETHER_FORGE_PLANNER_MODE` set, the generated `aether-forge.json` must stamp:

```json
{
  "planner": {
    "mode": "anthropic",
    "source": "explicit"
  },
  "deploymentProfile": "production"
}
```

This is not autodetection. The operator supplied a deterministic planner through the documented precedence chain. `AETHER_FORGE_PLANNER_MODEL`, `AETHER_FORGE_PLANNER_BASE_URL`, and `AETHER_FORGE_PLANNER_API_KEY_ENV` are also carried into the generated config when the corresponding CLI flag is absent.

### 2. Memory migrations target exact `fromVersion`

`MigrationRunner.apply_to_memory_store()` must apply a migration contract only to records whose `MemoryRecord.schema_version == contract.fromVersion`.

Rows older than `fromVersion` are not eligible for the transform. They require their own earlier migration step. This prevents a `1.0.0 -> 1.1.0` transform from accidentally rewriting `0.9.0` rows and stamping them as `1.1.0`.

The `SqliteMemoryStore.iter_records_below()` helper remains available for scanning and reporting old rows, but the runner filters to the exact migration cohort before invoking the transform.

### 3. Session-key chain constraints fail closed on missing chain id

`SessionKeyConstrainedSigner` must delegate to `SessionKeyPolicy.permits()` when available. If a policy declares `allowed_chains`, a `SigningIntent` with `chain_id=None` must be refused.

This matters for payment networks or signer intents that cannot be mapped to a known chain id. Missing chain information is not "unconstrained"; it is insufficient evidence to sign.

## Documentation Updates

The docs-site now has a first-class TypeScript SDK reference page covering:

- generated JSON-schema types,
- Ajv validators,
- `parsePlannerOutput`,
- protocol interfaces,
- CI drift checks,
- the explicit "no TS runtime tick loop in v0.1.x" boundary.

Reference and guide pages now embed relevant existing walkthrough videos where they previously had none:

- configuration,
- stable API,
- production readiness,
- multi-tenant integration,
- TypeScript SDK,
- delta-neutral BTC example.

No new video binary was added in this patch. Existing docs videos are reused so the site never points at a missing asset.

## Verification

- `python3 -m pytest` — `655 passed, 15 skipped, 1 warning`
- `cd sdk-ts && bun run test` — `37 passed`
- `cd docs-site && npm run build` — Next.js build and Pagefind indexing passed
- `git diff --check` — clean

## Non-Negotiables Added

- `AETHER_FORGE_PLANNER_MODE` and related planner env vars are explicit operator planner choices during `forge generate-fast`; they must not be treated as autodetected.
- `MigrationRunner` must only execute a memory migration transform for rows whose `schema_version` exactly matches the contract's `fromVersion`.
- `SessionKeyConstrainedSigner` must fail closed when a policy constrains chains and the signing intent does not declare a chain id.

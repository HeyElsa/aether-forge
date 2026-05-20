# Aether Forge PRD v0.22.0

**Date**: 2026-05-16
**Status**: Approved
**Previous**: v0.21.0 (`docs/prd/aether-forge-prd-v0.21.0.md`)

---

## Summary

v0.22.0 is the **Spec-First the Missing Seams** release. It is Sprint 2 of a multi-sprint dev-feedback retrospective; v0.21.0 (Sprint 1) closed the silent-failure paths, this release ships the four spec-first capabilities the hardening was preparation for:

1. **Deployment profiles** that turn the v0.21.0 planner-source advisory into a hard fail on production hosts.
2. **A runnable migration layer** over the existing `migration-contract.schema.json` — `versioning.py` could already describe migrations but execution was a manual exercise; `MigrationRunner` makes them safe to apply.
3. **Provider-native tool-use** for Anthropic and OpenAI-compatible models — the planner can now opt out of JSON string-parsing entirely and use the structured tool-call protocol the provider already speaks.
4. **The `DelegatedSigner` Protocol** — finally documents and codifies the hosted-marketplace trust model the dev pointed out was missing. Three reference signers ship (OWS, browser-relay, delegated-secrets); the `SessionKeyConstrainedSigner` wrapper composes any of them with a `SessionKeyPolicy` for fail-closed scope enforcement.

Sprint 3 (TypeScript SDK, FP-5) follows.

For existing users behavior is unchanged unless they opt in. The deployment profile defaults to `local`, tool-mode defaults to off, the legacy `sign_typed_data_fn` keeps working (with a deprecation log), and the new `MigrationRunner` only runs when invoked via `forge migrate`. `forge doctor` is the only surface that changes verdict for existing users: an autodetected planner in a production-profile config now FAILS instead of advising — exactly the regression the original dev feedback called for.

---

## What's New

### 1. `deploymentProfile` first-class config (FP-2 deepening)

**Shipped:**

- New `deploymentProfile` top-level field on `aether-forge.json` — enum `local` / `staging` / `production`, default `local`.
- Resolution chain in `src/aether_forge/config.py`: `resolve_deployment_profile(*, profile, config)` honors CLI flag → `AETHER_FORGE_DEPLOYMENT_PROFILE` env var → `aether-forge.json:deploymentProfile` → `DEFAULT_DEPLOYMENT_PROFILE = "local"`.
- `forge generate-fast` gains `--deployment-profile {local,staging,production}` flag. The handler:
  - Refuses **production + autodetected** with a clear error (exit 2).
  - Refuses **production + explicit-heuristic** (exit 2).
  - Refuses **staging + heuristic-fallback** when no LLM is reachable (exit 2).
- `FastGenerateRequest.deployment_profile` field; `_project_config_json` in `src/aether_forge/generator.py` stamps it into the generated `aether-forge.json` at the top level.
- `forge doctor` gains `_check_deployment_profile(config_path)` and upgrades `_check_planner_source`:
  - production + autodetected → FAIL
  - production + heuristic → FAIL
  - staging + autodetected → FAIL
  - local + autodetected → advisory only (dev machines untouched)
  - explicit (any profile) → production-safe

**New schema:** `src/aether_forge/schemas/runtime/agent-config.schema.json`. Declares the full `aether-forge.json` contract for the first time. Permissive on unknown top-level keys (`additionalProperties: true`) so user-managed sections like `mcp_servers` and `adapters` continue to extend the contract without breaking validation; strict on the v0.21.0+ provenance fields the framework writes itself.

**Tests pinned in** `tests/test_deployment_profile.py` (20 cases): resolution chain ordering, invalid-value rejection, profile baked into generated config, three CLI rejection paths, doctor escalation for each (profile, source) combination, legacy unstamped configs default to local.

### 2. `MigrationRunner` execution layer (FP-4)

**Shipped:**

- New `src/aether_forge/migrations.py`:
  - `TransformRegistry` — keyed on `(from_version, to_version, target)`. Duplicate registrations raise. Used to look up the actual transform callable for a given migration contract.
  - `MigrationContract.from_dict(data)` / `.from_path(path)` — schema-validated parsing.
  - `MigrationRunner.apply_to_memory_store(store, contract, *, dry_run, lossy_ok)` — migrates every row whose `schema_version` is `<= contract.from_version` (cohort streamed via the new `SqliteMemoryStore.iter_records_below`). Per-row tolerance: a transform raising on one row skips that row with an audit issue, not the whole batch. Verifies the transform's output `schemaVersion` matches `contract.to_version` before writing back through the store's `write` path so secret-scan + WAL invariants are honored.
  - `MigrationRunner.apply_to_artifact_file(path, contract, *, target, dry_run, lossy_ok)` — single-file migration with the same gates plus a sibling `.pre-migration-<timestamp>.bak`.
  - `MigrationReport` — dataclass with `records_scanned / migrated / skipped`, `backup_path`, `issues`. `ok` property reports overall success.
- `SqliteMemoryStore.iter_records_below(version, *, inclusive=False)` and `count_records_below(...)` for the streamed cohort iteration.
- `forge migrate memory|artifact` CLI subcommand. Default dry-run; `--apply` to mutate; `--lossy-ok` to override the deny-by-default policy on contracts with non-empty `lossyFields`.
- New `aether_forge.migrations` entry-point group: third-party packages register transforms by declaring `[project.entry-points."aether_forge.migrations"] name = "pkg:register_fn"` where `register_fn(registry)` calls `registry.register(...)`. Plugin failures are logged + skipped per the framework-wide non-negotiable.
- Schema extension: `src/aether_forge/schemas/common/migration-contract.schema.json` gains optional `transformRef` (resolved against the registry) and `policy.lossyOk` (deny-by-default bool). The schema stays `additionalProperties: false` — every field is explicit.

**Safety invariants:**

1. **Dry-run by default.** Default `apply_to_*` mode is `dry_run=True`. CLI requires `--apply` to mutate.
2. **Lossy fields refuse silently.** A contract with non-empty `lossyFields` refuses to apply unless `policy.lossyOk` OR caller-passed `lossy_ok=True`. Mirrors the `_weakens_criteria` philosophy from `evolution.py:423`.
3. **Pre-mutation backup.** When the runner touches a SQLite database, it copies the file to `<db>.pre-migration-<timestamp>.bak` before writing the first row. Recovery is a file rename away.
4. **Documentation-only contracts refuse to execute.** A contract without `transformRef` cannot be executed by the runner (the runner returns an issue and never touches data). The field serves dual purpose: runnable vs human-only discriminant.
5. **Per-row exception tolerance.** A transform that raises on one row records the issue and continues with the next — partial migrations are valid and reported.

**Tests pinned in** `tests/test_migration_runner.py` (25 cases): registry register/lookup/dedup; contract parsing happy path + missing-field + bad-policy + file path; dry-run no-mutation; apply mutates + writes backup; lossy refused / overridden by caller / overridden by contract; missing transformRef refused; missing registered transform reported; wrong toVersion rejected per-row; transform raising skipped per-row; only-matching-from-version cohort; iter/count helpers; artifact dry-run / apply / version mismatch; CLI dry-run / apply / no-sub-command.

### 3. Provider-native tool-use (FP-1 deepening)

**Shipped:**

- `src/aether_forge/adapters/function_call.py` adds four new module-level helpers:
  - `build_tool_schema_from_manifest(manifest) -> list[dict]` — projects a capability-manifest into OpenAI-shaped tool definitions.
  - `to_anthropic_tool_schema(openai_tools) -> list[dict]` — rewraps OpenAI shape to Anthropic's `{name, description, input_schema}` shape.
  - `from_anthropic_tool_use(content_blocks) -> FunctionCallResponse` — parses mixed `text` + `tool_use` blocks.
  - `from_openai_tool_calls(message) -> FunctionCallResponse` — parses `tool_calls` with JSON-string arguments; skips malformed entries gracefully.
- New `complete_with_tools(prompt, tools) -> FunctionCallResponse` method on `OpenAICompatiblePlanningModel` and `AnthropicPlanningModel`. Raises `PlanningModelError` if `tools` is empty (a planner opting into tool-mode without a manifest is a configuration error, not a degenerate-but-valid case). Gemini support deliberately deferred — single-provider extension can land without breaking the contract.
- `PromptDrivenPlanner.tool_mode: bool = False`. When True, the new `_propose_plan_tool_mode` branch:
  - Builds tools from the capability-manifest.
  - Calls `model.complete_with_tools(prompt, tools)` and runs the response through the existing `FunctionCallTranslator`.
  - Records `model-error` if the model lacks `complete_with_tools` or raises; records `empty-plan` if no tool calls came back. Same `last_planner_parse_failure` shape as the legacy string path so observability is consistent.
- `PlannerSettings.tool_mode` field; `resolve_planner_settings` reads `AETHER_FORGE_PLANNER_TOOL_MODE` env > config `planner.toolMode` > False. `build_planner_factory` threads `tool_mode` into the OpenAI-compatible and Anthropic factory branches.

**New schema:** `src/aether_forge/schemas/runtime/planner-tool-use.schema.json` pins the (capability-manifest → OpenAI tool definitions) projection. Third-party planners implementing against the same shape get the same contract.

**Tests pinned in** `tests/test_planner_tool_mode.py` (22 cases): schema builder happy path + skip-missing-ids; Anthropic shape adapter; Anthropic mixed-block parser; OpenAI tool_calls parser (string args, malformed args, dict args, empty content); provider `complete_with_tools` payload shape (Anthropic + OpenAI-compatible); empty-tools raises; planner end-to-end tool-mode round-trip; undeclared capability → REPORT_GAP; model lacking `complete_with_tools` records `model-error`; empty response records `empty-plan`; model raise records `model-error`; default-off preserves legacy path; settings resolution (config / env-override / default); factory threading (Anthropic + OpenAI-compatible).

### 4. `DelegatedSigner` Protocol + hosted-marketplace patterns (FP-3)

**Shipped:**

- New `src/aether_forge/crypto/signers.py`:
  - `DelegatedSigner` — single-method Protocol `sign_typed_data(typed_data, *, intent: SigningIntent | None) -> str`.
  - `SigningIntent` — frozen dataclass: `chain_id`, `contract_address`, `spend_usd`, `purpose`. Optional fields — the constrained wrapper enforces what the policy declares.
  - `SignerKind` literal + `SIGNER_KINDS = ("ows", "browser-relay", "delegated-secret", "mock")`.
  - `SigningError` + `SigningRefusedError` exception hierarchy.
  - `OwsSigner` — extracts the v0.21.0 inline OWS path into a first-class signer; preserves the exact API-key-then-passphrase fallback behavior.
  - `BrowserRelaySigner` — POSTs `{typedData, intent}` to a user-configured relay URL; expects `{signature: "0x..."}` back. Surfaces user rejection (HTTP 4xx) as `SigningRefusedError` so audit logs distinguish "user said no" from "relay was down."
  - `DelegatedSecretsSigner` — resolves the signing callable from a `CredentialResolver` lease's `metadata["signFn"]` or `maximum_access_scope["signFn"]`. Lets ops keep keys in a vault / HSM without baking those SDKs into core.
  - `SessionKeyConstrainedSigner` — wraps any inner signer, consults a `SessionKeyPolicy` (chain whitelist / contract allowlist / per-tx spend cap / expiry) before delegating. Fail-closed: `intent=None` is refused outright.
  - `LegacyCallableSigner` — back-compat shim that wraps the existing `sign_typed_data_fn` callable so it can flow through the new protocol surface during the deprecation window.
- New `SessionKeyPolicy.permits(*, chain_id, contract_address, spend_usd) -> tuple[bool, str]` method in `src/aether_forge/security.py`. Pre-existing scope fields finally have an explicit decision path. Used by `SessionKeyConstrainedSigner` to keep the wrapper logic in one place.
- `X402Client.__init__` accepts `signer: DelegatedSigner | None`. Precedence: `signer` > legacy `sign_typed_data_fn` (logged as deprecated when used without `signer`, scheduled for removal in v0.24.0) > `OwsSigner` fallback. `_sign_authorization` builds a `SigningIntent` from the `PaymentRequirement` (chain id from `_chain_id_for_network`, contract address from `requirement.asset`, USD spend from `_micros_to_usd(max_amount_required)`) and dispatches.
- `X402PaymentGate.verify_and_settle_onchain(... allowed_payers: set[str] | None = None)` — case-insensitive payer allowlist gate that runs after structural verification, before any on-chain submit. Closes the "anyone can pay anything" gap.

**New schema:** `src/aether_forge/schemas/runtime/delegated-signer.schema.json` pins the four signer-kind variants plus the optional `SessionKeyConstrainedSigner` wrapper config. Conditional `allOf` blocks enforce kind-specific required fields (e.g., `kind=browser-relay` requires `browserRelayUrl`).

**Tests pinned in** `tests/test_delegated_signer.py` (25 cases): `SigningIntent` frozen; signer-kinds tuple; BrowserRelaySigner POST payload + auth header + empty signature + 4xx-as-refused + 5xx-as-error + intent serialization; DelegatedSecretsSigner lease metadata path + missing-signFn error; SessionKeyConstrainedSigner intent-required, chain/contract/spend/expiry enforcement + permits-matches-wrapper; LegacyCallableSigner forward + empty-signature; X402Client signer-wins-over-legacy / legacy-fallback / signer-error-as-PaymentSigningError / refused-as-PaymentSigningError; verify_and_settle_onchain allowlist rejection + case-insensitive accept + structural-error-before-allowlist.

---

## Verification

- **Test suite**: 528 → 620 tests (+92 net). All pass. `python3.14 -m pytest tests/` → `620 passed, 15 skipped, 1 warning in 16s`.
- **Independent code audit** (Explore agent): no blocking issues; no behavioral regressions; the OwsSigner extraction preserves the legacy try-API-key-then-passphrase fallback exactly; the X402Client signer-dispatch chain falls through OwsSigner correctly when neither `signer` nor `sign_typed_data_fn` are passed; the agent-config schema is permissive enough that pre-v0.22.0 configs validate cleanly.
- **Back-compat manual smoke**: opening a v0.21.0 `memory.db` with the new code adds no migration and reads/writes unchanged; an `X402Client(sign_typed_data_fn=...)` still works and logs the deprecation warning once; `forge doctor` against a v0.20.0 config (no `deploymentProfile` field) treats it as `local` with an "(implicit default)" hint.

---

## Files Changed

| File | Change | Net lines |
|---|---|---|
| `src/aether_forge/config.py` | `DeploymentProfile` literal + `resolve_deployment_profile`; `PlannerSettings.tool_mode`; tool-mode threading in `build_planner_factory` | +54 |
| `src/aether_forge/cli.py` | `--deployment-profile` flag + production / staging refusal; `forge migrate` subcommand + dispatcher | +120 |
| `src/aether_forge/doctor.py` | `_check_deployment_profile`; upgraded `_check_planner_source` | +85 |
| `src/aether_forge/generator.py` | `FastGenerateRequest.deployment_profile`; stamped into generated config | +18 |
| `src/aether_forge/migrations.py` | New module — `TransformRegistry`, `MigrationContract`, `MigrationRunner`, `MigrationReport` | +362 |
| `src/aether_forge/storage.py` | `iter_records_below` + `count_records_below` | +33 |
| `src/aether_forge/plugins.py` | `GROUP_MIGRATIONS` added to `ALL_GROUPS` | +7 |
| `src/aether_forge/adapters/function_call.py` | `build_tool_schema_from_manifest`, `to_anthropic_tool_schema`, `from_anthropic_tool_use`, `from_openai_tool_calls` | +130 |
| `src/aether_forge/models.py` | `complete_with_tools` on Anthropic + OpenAI-compatible | +105 |
| `src/aether_forge/planner.py` | `tool_mode` field + `_propose_plan_tool_mode` dispatcher | +75 |
| `src/aether_forge/crypto/signers.py` | New module — protocol + intent + four reference signers + constrained wrapper + legacy shim | +280 |
| `src/aether_forge/x402_client.py` | `signer` param + dispatcher refactor; `_chain_id_for_network` + `_micros_to_usd` helpers | +50 |
| `src/aether_forge/x402_server.py` | `allowed_payers` param + gate | +28 |
| `src/aether_forge/security.py` | `SessionKeyPolicy.permits` + `_coerce_chain_id` helper | +65 |
| `src/aether_forge/schemas/runtime/agent-config.schema.json` | NEW | +75 |
| `src/aether_forge/schemas/runtime/planner-tool-use.schema.json` | NEW | +45 |
| `src/aether_forge/schemas/runtime/delegated-signer.schema.json` | NEW | +75 |
| `src/aether_forge/schemas/common/migration-contract.schema.json` | `transformRef` + `policy.lossyOk` | +24 |
| `pyproject.toml` | `aether_forge.migrations` entry-point group | +8 |
| `tests/test_deployment_profile.py` | NEW — 20 tests | +260 |
| `tests/test_migration_runner.py` | NEW — 25 tests | +540 |
| `tests/test_planner_tool_mode.py` | NEW — 22 tests | +315 |
| `tests/test_delegated_signer.py` | NEW — 25 tests | +500 |

14 source files modified, 7 new files (4 test, 3 schema, 1 module), `pyproject.toml` updated. Net ~+3160 lines.

---

## Non-Negotiables added (AGENTS.md §3)

- The `deploymentProfile` field on `aether-forge.json` is part of the contract. `forge doctor` MUST escalate `production + autodetected` and `production + heuristic` and `staging + autodetected` to a hard fail; `local` profile keeps autodetected as an advisory.
- Generated `aether-forge.json` MUST stamp the resolved `deploymentProfile` at the top level so the value is the same byte the operator chose at generation time.
- `MigrationRunner` MUST default to dry-run and MUST refuse lossy contracts unless `policy.lossyOk` or caller `lossy_ok=True`. Pre-mutation SQLite backups are mandatory before any row write.
- `forge migrate` MUST default to dry-run; `--apply` is the only path that mutates.
- A migration contract without `transformRef` MUST be treated as documentation-only; `MigrationRunner` MUST refuse to execute it.
- Provider `complete_with_tools` methods MUST raise `PlanningModelError` if `tools` is empty. Opting into tool-mode with no manifest is a configuration error, not a no-op.
- `PromptDrivenPlanner` tool-mode failures MUST record the same `last_planner_parse_failure` event shape as the legacy string path. Observability MUST stay consistent across both planner paths.
- `DelegatedSigner` is the canonical signing surface in v0.22.0+. The legacy `sign_typed_data_fn` keeps working with a deprecation warning; new code MUST pass `signer=` instead. Removal target: v0.24.0.
- `SessionKeyConstrainedSigner` MUST refuse `intent=None` (fail-closed). A caller without an intent has nothing for the policy to check, so no signature is permitted.
- `X402PaymentGate.verify_and_settle_onchain` MUST honor `allowed_payers` when provided. Payer matching MUST be case-insensitive (EIP-55 vs lowercase).

---

## What's Next (Sprint 3 — v0.23.0)

The remaining FP-5 work, scoped in the retrospective plan: the parallel TypeScript SDK track. `@aether-forge/sdk` thin v0.1.0 (validators + types + planner-resilience spec) and v0.1.1 `@aether-forge/sdk/x402` for browser sign-and-relay. The signer-kind enum and the `BrowserRelaySigner` schema that just landed in this release are the contract that the TS-side `eip1193Signer` will satisfy.

After v0.23.0, the five friction points are closed end-to-end:

- FP-1 (planner resilience): v0.21.0 parser + retry + v0.22.0 native tool-use + v0.23.0 cross-language conformance spec
- FP-2 (Ollama-first auto-detect): v0.21.0 reorder + v0.22.0 deployment profiles
- FP-3 (hosted-marketplace trust model): v0.22.0 DelegatedSigner + v0.23.0 browser signer SDK
- FP-4 (schema versioning): v0.21.0 schema-version pin + v0.22.0 MigrationRunner
- FP-5 (Python-only barrier): v0.23.0 TypeScript SDK + cross-language conformance CI

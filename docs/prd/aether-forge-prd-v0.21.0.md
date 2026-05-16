# Aether Forge PRD v0.21.0

**Date**: 2026-05-16
**Status**: Approved
**Previous**: v0.20.0 (`docs/prd/aether-forge-prd-v0.20.0.md`)

---

## Summary

v0.21.0 is the **Resilience & Schema Hardening** release. It is Sprint 1 of a five-point dev-feedback retrospective (the full plan lives at `~/.claude/plans/friction-points-python-only-concurrent-lecun.md`). The product positioning — *"the best framework for agent devs"* — is only credible if a developer's first-touch experience does not include silent failure paths.

A developer evaluating Aether Forge surfaced five frictions: thin LLM planner parsing, Ollama-first auto-detect breaking production, undocumented x402 trust model for hosted marketplaces, missing runtime migration execution for artifact schemas, and the lack of a TypeScript SDK. Sprint 1 closes the silent-failure subset (FP-1 partial, FP-2, FP-4 prep). Sprints 2 and 3 (delegated signers, migration execution, TS SDK) follow.

For existing users with no provider keys set, behavior is unchanged. For existing users with cloud keys AND a host Ollama daemon, the planner choice flips from Ollama to the cloud provider — the exact regression that prompted this work — and the change is now auditable via the new `planner.source` field surfaced by `forge doctor`.

---

## What's New

### 1. Planner JSON parsing resilience (FP-1)

The pre-v0.21.0 parser at `planner.py:73-86` stripped a single ` ``` ` fence and called `json.loads`. Anything more interesting — a reasoning preamble (`Let me think… {…}`), trailing prose, double fences, mid-JSON truncation — silently returned `[]`, which the outer `try/except` turned into a `HeuristicPlanner` fallback with no audit signal. The dev's complaint: *"real-world LLM output is messier than 'parse fenced JSON'."*

**Shipped:**

- New module-level `_extract_json(response: str) -> Any` helper in `src/aether_forge/planner.py`. Order of operations: strip outer ` ```/```json ` fence pair → `json.loads` happy path → balanced-brace scan that returns the largest top-level `{…}` or `[…]` slice that parses (ignores brace-like characters inside strings) → raise `PlannerParseError` (a `ValueError` subclass) on miss.
- `PromptDrivenPlanner._parse_response` now calls `_extract_json` and lets `PlannerParseError` propagate.
- `PromptDrivenPlanner.propose_plan` records a structured `last_planner_parse_failure` event on `session.session_state` whenever the heuristic fallback is triggered. Schema:

  ```json
  {
    "kind": "parse-failure" | "parse-exception" | "model-error" | "empty-plan",
    "detail": "…",
    "responsePreview": "first 500 chars…",
    "recordedAt": "2026-05-16T18:00:00+00:00"
  }
  ```

  Replays and live `forge run` traces gain an audit trail for what previously failed silently. Distinguishes "model returned garbage" from "model returned empty plan" from "provider call raised."

**Behavior tests pinned in** `tests/test_planner_parse_resilience.py` (18 cases): fenced JSON, JSON-fenced (` ```json `), reasoning preamble, trailing prose, double-fenced, braces-in-strings, truncated mid-object, empty string, plain refusal text, bare scalar (`null` / `true` / `42`), top-level array, end-to-end happy path, end-to-end parse-failure observability event, model-error event, empty-plan event distinct from parse-failure, preview truncation at 500 chars.

### 2. Provider retry envelope with jittered exponential backoff (FP-1)

The pre-v0.21.0 models opened a raw `urlopen` per request, no retry, no `Retry-After` honoring. A single 429 or transient network blip propagated as `PlanningModelError` and triggered fallback.

**Shipped:**

- New `_with_retry(call, *, attempts, sleep)` helper in `src/aether_forge/models.py`. Retries on `URLError`, `TimeoutError`, and `HTTPError` whose code is in `{408, 425, 429, 500, 502, 503, 504}`. Honors `Retry-After` (integer-seconds and HTTP-date forms). Jittered exponential backoff (`base=0.5s`, `cap=8s`, ±20% jitter). Non-transient HTTP codes (e.g. 400, 401) raise on the first attempt.
- All three providers (`OpenAICompatiblePlanningModel`, `AnthropicPlanningModel`, `GeminiPlanningModel`) gained a `retry_attempts: int = 3` dataclass field. Setting `retry_attempts=1` opts out.
- The fast path through user-provided `request_fn` is wrapped in the retry envelope too, so test stubs can verify retry behavior without HTTP.
- `sleep` is dependency-injected (`time.sleep` by default), keeping tests deterministic and instant.

**Behavior tests pinned in** `tests/test_models_retry.py` (11 cases): success short-circuit, URLError-then-success, 429 with explicit `Retry-After: N`, 400 non-transient immediate raise, exhaustion at 503, `attempts=1` opt-out, header-parse helper, missing-header fallback, provider integration for OpenAI-compatible + Anthropic.

**No new dependency** — stdlib only. `random.random` for jitter, `time.sleep` for the delay.

### 3. Planner auto-detect order reversed (FP-2)

The pre-v0.21.0 `cli._autodetect_planner` probed Ollama first, then the cloud chain, then heuristic. The dev's complaint: *"every production deploy has to override it."* A host with both cloud keys and a stray Ollama daemon silently got Ollama.

**Shipped (behavior change):**

- New probe order in `cli._autodetect_planner`:
  1. **Override** — if `AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT=1` is set AND Ollama is reachable, use it (escape hatch for local devs whose shell carries a cloud key from another project).
  2. **Cloud chain** — `ANTHROPIC_API_KEY → OPENAI_API_KEY → (GOOGLE_API_KEY | GEMINI_API_KEY) → OPENROUTER_API_KEY`. First match wins.
  3. **Ollama as fallback** — only if no cloud key is set and Ollama is reachable with at least one model. Local-dev convenience preserved when no cloud keys exist.
  4. **Heuristic** — last resort.
- Return dict gains a `source` discriminant: `"cloud" | "ollama" | "heuristic"`.
- A `[planner] WARNING:` line is emitted when heuristic was selected — the silent "your agent has no LLM" case is now loud at the moment of decision.
- A no-op contract is now pinned: when a cloud key is set and the override flag is not, `_autodetect_planner` does NOT open a socket to localhost:11434. Production startup is fully deterministic.

**Behavior tests pinned in** `tests/test_planner_autodetect.py` (11 cases): cloud-wins-with-Ollama-running (the exact regression), chain ordering (Anthropic > OpenAI > Gemini > OpenRouter), no-cloud-key Ollama fallback, Gemma-preferred-when-available, heuristic when nothing is reachable, `AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT` override beats cloud, override falls through when Ollama is down, no-probe contract when cloud key is set, doctor advisory for explicit / autodetected / legacy unstamped configs.

### 4. Planner provenance audit fields (FP-2)

A new agent's `aether-forge.json` now records *why* the planner was chosen, so operators can grep for silent autodetect picks in production.

**Shipped:**

- `FastGenerateRequest` gained `planner_source` (`"explicit"` when `--planner-mode` was passed or `AETHER_FORGE_PLANNER_MODE` was set, `"autodetected"` when `_autodetect_planner` ran) and `planner_detected_at` (ISO timestamp, UTC).
- `_project_config_json` in `src/aether_forge/generator.py` stamps both into the generated `aether-forge.json` as `planner.source` and `planner.detectedAt`. Older configs without these fields remain valid (treated as "unstamped" by doctor).
- `forge doctor` gained `_check_planner_source(config_path)` in `src/aether_forge/doctor.py`. Surfaces three states: `explicit` → "production-safe"; `autodetected` → advisory to pin via `AETHER_FORGE_PLANNER_MODE`; `unstamped` → advisory to regenerate. Sprint 2's `deploymentProfile` work will upgrade `autodetected` + `production` from advisory to fail.

### 5. MemoryRecord schema version pin (FP-4 preparation)

The pre-v0.21.0 `MemoryRecord.schema_version` defaulted to a hardcoded `"1.0.0"` at `memory.py:31`. The dev's complaint: *"had to invent schema versioning when persisting."* The schemas DO have `schemaVersion` infrastructure; the gap was that the in-code constant and the persisted-row stamp were not connected, so the planned Sprint 2 `MigrationRunner` had no way to know which DB rows were old.

**Shipped:**

- New `MEMORY_RECORD_SCHEMA_VERSION = "1.0.0"` module constant in `src/aether_forge/memory.py`. `MemoryRecord.schema_version` field default and `MemoryRecord.from_dict` fallback both reference it. A future bump propagates atomically.
- `SqliteMemoryStore._init_schema` in `src/aether_forge/storage.py` now stamps `('memory_record_schema_version', '1.0.0')` into `schema_meta` via `INSERT OR IGNORE`. Pre-existing v0.20.0 databases backfill the row on next open — no migration required.
- New `SqliteMemoryStore.memory_record_schema_version()` method returns the persisted value.

Sprint 2's `MigrationRunner` will read this to gate transforms; until then, the stamp is observable but advisory.

**Behavior tests pinned in** `tests/test_memory_schema_version_stamp.py` (3 cases): new DB stamps both versions; legacy DB without the row backfills on open; `MemoryRecord` default uses the module constant.

---

## Verification

- **Test suite**: 485 → 526 tests (+41 net). All pass. Run: `python3.14 -m pytest tests/` → `526 passed, 15 skipped, 1 warning in 20.80s`.
- **Independent code audit** (Explore agent + manual review): no behavioral regressions found, no missed callers, no contract violations, no schema collisions. One micro-cleanup applied (in-function `datetime`/`UTC` reimport in `cli.py` removed in favor of the existing module-level import at line 7).
- **Manual smoke**: `forge generate-fast` with `ANTHROPIC_API_KEY` + Ollama running picks Anthropic and stamps `planner.source: autodetected`. `forge doctor` with that config surfaces the autodetected advisory.
- **Back-compat**: a v0.20.0 `memory.db` opened with the new `SqliteMemoryStore` gets the meta row added; reads and writes succeed unchanged.

---

## Files Changed

| File | Change | Net lines |
|---|---|---|
| `src/aether_forge/planner.py` | `_extract_json` helper, `PlannerParseError`, parse-failure recording | +93 |
| `src/aether_forge/models.py` | `_with_retry` helper, `_retry_after_seconds`, `retry_attempts` field on three providers | +99 |
| `src/aether_forge/cli.py` | Reordered `_autodetect_planner`, `_is_truthy_env`, stamp provenance fields | +50 |
| `src/aether_forge/generator.py` | `planner_source` / `planner_detected_at` fields on `FastGenerateRequest`, stamped by `_project_config_json` | +12 |
| `src/aether_forge/doctor.py` | `_check_planner_source` advisory | +62 |
| `src/aether_forge/memory.py` | `MEMORY_RECORD_SCHEMA_VERSION` constant + references | +8 |
| `src/aether_forge/storage.py` | Import constant, stamp `schema_meta`, `memory_record_schema_version()` getter | +18 |
| `tests/test_planner_parse_resilience.py` | 18 new tests | +185 |
| `tests/test_models_retry.py` | 11 new tests | +198 |
| `tests/test_planner_autodetect.py` | 11 new tests | +220 |
| `tests/test_memory_schema_version_stamp.py` | 3 new tests | +75 |

7 source files modified, 4 new test files. No file deletions. No schema additions in this sprint (schema work follows in Sprint 2 with `planner-tool-use.schema.json`, `delegated-signer.schema.json`, and additions to `migration-contract.schema.json` and `credential-handle.schema.json`).

---

## Non-Negotiables added (AGENTS.md §3)

To be appended to `AGENTS.md`:

- The `HeuristicPlanner` fallback **MUST** emit a structured event on `session.session_state` when triggered. Silent fallback is a contract violation.
- `_autodetect_planner` **MUST NOT** probe Ollama when any cloud-provider env var is set, unless `AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT` is explicitly truthy.
- Generated `aether-forge.json` **MUST** include `planner.source` and `planner.detectedAt` so the planner-choice provenance is auditable post-hoc.
- `MemoryRecord.schema_version` **MUST** be sourced from `aether_forge.memory.MEMORY_RECORD_SCHEMA_VERSION`; hardcoded `"1.0.0"` strings in new code are a regression.
- Provider planning models (`OpenAICompatiblePlanningModel`, `AnthropicPlanningModel`, `GeminiPlanningModel`) **MUST** route their HTTP calls through `_with_retry` and accept a `retry_attempts` opt-out.

---

## What's Next (Sprint 2 — v0.22.0, ~2-4 weeks)

The remaining friction-point work, scoped in the retrospective plan:

- **Provider-native tool-use** (FP-1 deepening): `adapters/function_call.py` learns `build_tool_schema_from_manifest`, `from_anthropic_tool_use`, `from_openai_tool_calls`. Two new `complete_with_tools` methods. Opt-in via `aether-forge.json.planner.toolMode = true`.
- **`deploymentProfile` first-class config** (FP-2 deepening): `local` / `staging` / `production` enum in `aether-forge.json`. Production forbids autodetect, upgrades the doctor advisory to a failure.
- **`DelegatedSigner` Protocol + `SessionKeyConstrainedSigner` wrapper** (FP-3): `src/aether_forge/crypto/signers.py` with three reference impls (`OwsSigner`, `BrowserRelaySigner`, `DelegatedSecretsSigner`). New `schemas/runtime/delegated-signer.schema.json`. `x402_client.py` accepts a `signer` param. `x402_server.py` `verify_and_settle_onchain` gains `allowed_payers`. Hosted-marketplace example agent under `examples/hosted-marketplace/`.
- **`MigrationRunner`** (FP-4): `src/aether_forge/migrations.py` (~200 LOC) executes the existing `versioning.build_artifact_migration_plan` contracts. `forge migrate artifacts` / `forge migrate memory` CLI. Default dry-run, `--apply` required, auto-backup. Lossy fields deny-by-default per the `_weakens_criteria` philosophy.

Sprint 3 (v0.23.0, ~4 sprints) is the parallel TypeScript SDK track (FP-5): `@aether-forge/sdk` thin v0.1.0 (validators + types + planner-resilience spec) and v0.1.1 `@aether-forge/sdk/x402` for browser sign-and-relay.

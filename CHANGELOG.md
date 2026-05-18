# Changelog

User-facing changes to Aether Forge. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] — 2026-05-16 — Spec-first the missing seams (v0.22.0 PRD)

Sprint 2 of the dev-feedback retrospective (`docs/prd/aether-forge-prd-v0.22.0.md`). Ships the four spec-first capabilities the Sprint 1 hardening was preparation for: deployment profiles that escalate the planner-source advisory, a runnable migration layer over the existing migration-contract schema, provider-native tool-use for Anthropic and OpenAI-compatible models, and the `DelegatedSigner` Protocol that finally documents the hosted-marketplace trust model.

### Added
- **`deploymentProfile` first-class config (FP-2 deepening)** — new top-level `deploymentProfile` field on `aether-forge.json` (enum: `local` / `staging` / `production`; default `local`). Resolved via CLI flag → `AETHER_FORGE_DEPLOYMENT_PROFILE` env → config file → default. `forge generate-fast --deployment-profile production` refuses autodetected planners and heuristic fallback at generation time. `forge doctor` upgrades the v0.21.0 advisory to a HARD FAIL when `production + autodetected`, `production + heuristic`, or `staging + autodetected` — `local`-profile autodetected stays advisory so dev machines aren't punished.
- **Agent-config schema** — new `src/aether_forge/schemas/runtime/agent-config.schema.json` declares the full `aether-forge.json` contract (`deploymentProfile`, `planner.{mode,model,baseUrl,apiKeyEnv,source,detectedAt,toolMode}`, `runtime.cryptoRouter`). Permissive on unknown top-level keys so user-managed sections (mcp_servers, adapters) keep extending the contract without breaking validation.
- **`MigrationRunner` execution layer (FP-4)** — new `src/aether_forge/migrations.py` with `TransformRegistry`, `MigrationContract`, `MigrationRunner`, `MigrationReport`. Executes existing `migration-contract.schema.json` documents end-to-end against a `SqliteMemoryStore` (`apply_to_memory_store`) or a single artifact JSON file (`apply_to_artifact_file`). Dry-run by default; `--apply` required to mutate; auto-writes a `<db>.pre-migration-<timestamp>.bak` before touching anything; per-row exception tolerance (a single bad row gets skipped with an audit issue, not the whole batch). Lossy fields deny-by-default — refuses to apply unless the contract's `policy.lossyOk` is true OR the caller passes `lossy_ok=True` (mirrors the `_weakens_criteria` philosophy from `evolution.py`).
- **`forge migrate memory|artifact` CLI** — `forge migrate memory ./agent --contract migration.json --apply` and `forge migrate artifact ./spec.json --contract migration.json --target agent-spec --apply`. Reports scanned / migrated / skipped counts and the backup path. Loads transforms from a new `aether_forge.migrations` entry-point group (`pyproject.toml` registers it; downstream packages declare `[project.entry-points."aether_forge.migrations"] name = "pkg:register_fn"` where `register_fn(registry)` calls `registry.register(...)` once per transform).
- **`migration-contract.schema.json` extensions** — new optional `transformRef` (string id resolved against `TransformRegistry`) and `policy.lossyOk` (bool, deny-by-default). Contracts without `transformRef` are documentation-only; `MigrationRunner` refuses to execute them so the field also serves as the runnable / human-only discriminant.
- **`SqliteMemoryStore.iter_records_below(version, *, inclusive=False)`** + `count_records_below(...)` — streamed cohort iteration for the migration runner. Used to walk old-schema rows without loading the whole DB into memory.
- **Provider-native tool-use (FP-1 deepening)** — extended `src/aether_forge/adapters/function_call.py` with `build_tool_schema_from_manifest(manifest)`, `to_anthropic_tool_schema(openai_tools)`, `from_anthropic_tool_use(content_blocks)`, `from_openai_tool_calls(message)`. New `complete_with_tools(prompt, tools) -> FunctionCallResponse` method on `OpenAICompatiblePlanningModel` and `AnthropicPlanningModel` (Gemini deliberately deferred — single-provider extension can land later without breaking the contract).
- **`PromptDrivenPlanner.tool_mode` (default False)** — when True and the wrapped model exposes `complete_with_tools`, the planner skips JSON string-parsing entirely and runs the `FunctionCallTranslator` directly on the provider-native response. Records `model-error` / `empty-plan` failure events on `session.session_state` the same way as the legacy string path so observability stays consistent across both paths. Opt in via `aether-forge.json:planner.toolMode = true` or `AETHER_FORGE_PLANNER_TOOL_MODE=1`.
- **`planner-tool-use.schema.json`** — new schema pinning the (capability-manifest → OpenAI tool definitions) projection so third-party planners can implement against the same contract.
- **`DelegatedSigner` Protocol (FP-3, hosted-marketplace patterns)** — new `src/aether_forge/crypto/signers.py`: `DelegatedSigner` single-method Protocol, `SigningIntent` frozen value object, `SigningError` + `SigningRefusedError` exception hierarchy. Three reference implementations:
  - `OwsSigner` — extracts today's OWS path (the v0.21.0 default) into a first-class signer
  - `BrowserRelaySigner` — POSTs typed-data + intent to a user-configured relay URL; surfaces user rejection (HTTP 4xx) as `SigningRefusedError`, network failure as `SigningError`. Enables hosted-marketplace patterns where the user's browser wallet (window.ethereum / Privy / RainbowKit) signs and the agent runtime just relays.
  - `DelegatedSecretsSigner` — pulls the signing callable from a `CredentialResolver` lease, letting ops keep keys in a vault / HSM
- **`SessionKeyConstrainedSigner`** — wrapper that consults a `SessionKeyPolicy` (chain whitelist / contract allowlist / per-tx spend cap / expiry) before delegating to an inner signer. Refuses `intent=None` outright (fail-closed — without an intent there is nothing to check). Composable with any of the three reference signers.
- **`SessionKeyPolicy.permits(*, chain_id, contract_address, spend_usd) -> tuple[bool, str]`** — explicit decision method used by the constrained wrapper; pre-existing fields (`allowed_chains`, `allowed_contracts`, `max_spend_per_tx_usd`, `expires_at`) finally have a documented evaluation path.
- **`X402Client(signer=...)`** — preferred hook for delegated / browser-relay / HSM-backed signing. When both `signer` and the legacy `sign_typed_data_fn` are passed, `signer` wins; the legacy callable is logged once as deprecated (scheduled for removal in v0.24.0). Wrapping it in `LegacyCallableSigner` lets the existing back-compat callable flow through the new protocol surface during the deprecation window.
- **`X402PaymentGate.verify_and_settle_onchain(allowed_payers=...)`** — case-insensitive payer allowlist gate that runs after structural verification and before any on-chain submit. Closes the "anyone can pay anything" gap (`x402_server.py:223-328`).
- **`delegated-signer.schema.json`** — new schema pinning the four signer-kind variants (`ows`, `browser-relay`, `delegated-secret`, `mock`) and the optional `SessionKeyConstrainedSigner` wrapper config. Conditional `allOf` blocks enforce kind-specific required fields.
- **`agent_payments` entry-point group documented** — `aether_forge.migrations` added to `plugins.ALL_GROUPS` and registered in `pyproject.toml` with an example commented out.
- **92 new tests** — `tests/test_deployment_profile.py` (20), `tests/test_migration_runner.py` (25), `tests/test_planner_tool_mode.py` (22), `tests/test_delegated_signer.py` (25). Suite: 528 → 620 tests. All pass.

### Changed
- `forge doctor` now emits two new check rows when a config file is provided: `Deployment profile` and (upgraded) `Planner source`. Both compose: an autodetected planner with profile=production is reported as a HARD FAIL, not just an advisory.
- `X402Client._sign_authorization` is now a thin dispatcher: builds a `SigningIntent` (chain id, contract address, USD spend) and routes through `signer` → legacy `sign_typed_data_fn` (via shim) → `OwsSigner` fallback. Default-no-args behavior is unchanged — the OWS path simply runs through the new abstraction instead of inline code.

### Notes
- **Back-compat**: Pre-v0.22.0 agents on disk are untouched. The new `deploymentProfile` field defaults to `local` when absent (matches today's behavior). The new `planner.toolMode` field defaults to false. `sign_typed_data_fn` keeps working but logs a deprecation warning once per `X402Client` instance.
- **Memory migration is opt-in, never automatic.** `forge migrate memory` defaults to dry-run; `--apply` is required to mutate; a `.bak` file is always written first. Lossy migrations refuse to apply unless `--lossy-ok` is also passed.
- **Tool-mode is provider-gated.** A model that doesn't expose `complete_with_tools` (e.g., the existing `GeminiPlanningModel`) records a `model-error` event on the session and falls back to `HeuristicPlanner`, so misconfiguration is loud and recoverable.
- **No new hard dependencies.** All four features are stdlib-only. The OWS extra remains optional.

## [0.21.0] — 2026-05-16 — Resilience & schema hardening (v0.21.0 PRD)

Sprint 1 of the dev-feedback retrospective (`docs/prd/aether-forge-prd-v0.21.0.md`). Closes three silent-failure paths a real dev hit; preparation for Sprint 2 delegated-signer + migration-execution work.

### Added
- **Resilient planner JSON extraction (FP-1)** — new `_extract_json(response)` helper in `src/aether_forge/planner.py` recovers JSON from fenced code blocks (` ```json `), reasoning preambles (`Let me think… {…}`), trailing prose, double-fenced responses, and braces-inside-strings. Raises `PlannerParseError` on miss instead of silently returning `[]`.
- **Observable parse-failure events** — `PromptDrivenPlanner.propose_plan()` now records a structured `last_planner_parse_failure` event on `session.session_state` whenever the heuristic fallback is triggered. Discriminator `kind` is one of `parse-failure`, `parse-exception`, `model-error`, or `empty-plan`. Response preview is truncated to 500 chars. Replays gain an audit trail for what previously failed silently.
- **Provider retry envelope with jittered exponential backoff (FP-1)** — new `_with_retry(call, attempts, sleep)` helper in `src/aether_forge/models.py` retries `URLError`, `TimeoutError`, and HTTP `408/425/429/500/502/503/504`. Honors `Retry-After` on 429/503. All three providers (`OpenAICompatiblePlanningModel`, `AnthropicPlanningModel`, `GeminiPlanningModel`) gained a `retry_attempts: int = 3` dataclass field. Pass `retry_attempts=1` to opt out. Stdlib-only — no new dependency.
- **Planner provenance audit fields (FP-2)** — `FastGenerateRequest` gained `planner_source` (`"explicit"` / `"autodetected"`) and `planner_detected_at` (ISO timestamp). `_project_config_json` stamps both into generated `aether-forge.json` as `planner.source` and `planner.detectedAt`. `forge doctor` surfaces them via new `_check_planner_source` advisory.
- **`AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT` escape hatch (FP-2)** — set to `1`/`true`/`yes`/`on` to force Ollama probe ahead of any cloud key. Local devs whose shell carries a cloud key from another project keep their Ollama default. Default off.
- **`MEMORY_RECORD_SCHEMA_VERSION` module constant (FP-4 prep)** — `src/aether_forge/memory.py` exposes `MEMORY_RECORD_SCHEMA_VERSION = "1.0.0"`; `MemoryRecord.schema_version` default and `MemoryRecord.from_dict` fallback both reference it so a future bump propagates atomically. `SqliteMemoryStore` stamps `('memory_record_schema_version', '1.0.0')` into `schema_meta` (idempotent — pre-existing DBs backfill on open) and exposes `memory_record_schema_version()` reader. Foundation for the Sprint 2 `MigrationRunner`.
- **41 new tests** — `tests/test_planner_parse_resilience.py` (18: fenced, preamble, trailing prose, truncation, bare scalars, top-level array, observability events), `tests/test_models_retry.py` (11: helper unit + provider integration + 429 Retry-After + opt-out), `tests/test_planner_autodetect.py` (11: cloud-wins-over-Ollama regression, no-cloud-key fallback, override flag, no-probe contract, doctor advisory), `tests/test_memory_schema_version_stamp.py` (3: new DB stamps, legacy DB backfill, constant reference). Suite: 485 → 526 tests, all green.

### Changed
- **Auto-detect order reversed (FP-2, behavior change)** — `cli._autodetect_planner` now probes the cloud chain (`ANTHROPIC_API_KEY` → `OPENAI_API_KEY` → `GOOGLE_API_KEY` → `GEMINI_API_KEY` → `OPENROUTER_API_KEY`) before falling through to Ollama. Production deploys with both a cloud key and a host Ollama daemon no longer silently pick Ollama. Ollama remains the auto-pick when no cloud key is present (local-dev convenience preserved). Returned dict gains a `source` discriminant (`"cloud"|"ollama"|"heuristic"`).
- `forge generate-fast` now prints a `[planner] WARNING:` line when heuristic fallback is selected because no LLM is reachable. Surfaces the silent "your agent has no LLM" case at the moment of decision.

### Notes
- **Back-compat**: Existing agents on disk are untouched. The new `planner.source` / `planner.detectedAt` fields are written only by new `forge generate-fast` runs; older configs that omit them are tagged "unstamped" by `forge doctor` (advisory, not failure).
- **Local-dev impact**: A developer with cloud keys set in their shell who previously got Ollama at generation time will now get the cloud provider. Set `AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT=1` to invert this. The exact provider used is now visible via `forge doctor` and the new `planner.source` field.
- **Memory DB**: The `schema_meta` upsert is idempotent and additive — no migration required for v0.20.0 databases.
- **No new dependencies**: `_with_retry` and `_extract_json` are stdlib-only. `time.sleep` is injectable in `_with_retry` so tests run instantly without real backoff.

## [Unreleased] — 2026-05-03 — DX & extensibility (v0.20.0 PRD)

### Added
- **Public extension Protocols** — `Planner`, `ExecutionRouter`, `PlanningModel`, `MemoryStore`, `DataSource` (and `Subscription`, `DataResult`, `DataRouter`, `DataSourceCost`, `HTTPDataSource`, `X402DataSource`, `WebSocketDataSource`, `McpDataSource`, `MockDataSource`, `StaticPlanningModel`) are now exported from `aether_forge` with contract docstrings (one-paragraph summary, canonical signature, 5-line minimum impl, pointer to in-tree reference).
- **Plugin discovery via `importlib.metadata`** — new `aether_forge/plugins.py` (cached, lazy). Four entry-point groups in `pyproject.toml`: `aether_forge.{planners,execution_routers,data_sources,skill_registries}`. Wired into `config.build_planner_factory` (mode fallback) and `skills.get_registries()`. Plugin failures are logged + skipped, never raised.
- **Generator batteries** — `forge generate-fast` now also emits `.dockerignore`, `Makefile` (validate / eval-pack / test / run-paper / run-sandbox / run-live with `CONFIRM_LIVE=yes` guard / doctor / halt / resume / docker-build / docker-run / clean), `.env.example`, and `tests/test_agent.py` (offline-`HeuristicPlanner` smoke test that validates artifacts + asserts every scenario meets its expected outcome — green on day one, no LLM key needed).
- **Shared test fixtures** — `tests/conftest.py` with `tmp_agent_dir`, `memory_store`, `in_memory_store`, `static_planner`, `static_planning_model`, `mock_router`, `policy_gate`, `runtime_session`, `reset_plugin_cache`. Demonstrated by `tests/test_conftest_fixtures.py`.
- **`docs-site/.../guides/extending.mdx`** — worked examples for custom Planner (xAI), DataSource, MemoryStore, skill registry, and PyPI plugin distribution. Linked from README + CONTRIBUTING + `_meta.js`.
- **`ARCHITECTURE.md`** at repo root — runtime tick lifecycle, four-layer memory, policy gate sequence, payment channels, "where to change things" table.
- **`docs/README.md`** — index mapping every topic to its authoritative source.
- **CLI reference gap-fill** — added 12 commands to `cli.mdx` (`artifact-{compat,migration-plan}`, `scaffold-{run,policy-sync,live-status}`, `resume-replay`, `x402-call`, `models-list`, `config-validate`, `init`, `wallet-info`, `completions`, `eval`).
- **Configuration reference walkthrough** — `configuration.mdx` adds the precedence chain (CLI > env > config > defaults), all `AETHER_FORGE_*` env vars, and a pointer to plugin-mode resolution.
- **mypy** — `[tool.mypy]` strict on the public-API surface (`__init__`, `runtime`, `planner`, `policy`, `memory`, `data_layer`, `plugins`); CI step is `continue-on-error: true` (informational).
- **pre-commit** — `.pre-commit-config.yaml` with `ruff format`/`ruff check`, file-hygiene hooks, and `pytest --collect-only`. `CONTRIBUTING.md` documents `pre-commit install`.

### Fixed
- Generator-emitted `Makefile`'s `doctor` target previously called `forge doctor ./aether-forge.json`, but `forge doctor` doesn't take a positional config arg. Now just runs `forge doctor`. CLI reference `forge doctor` example similarly corrected.

### Notes
- For existing users with no third-party plugins installed, behavior is unchanged. The new entry-point fallback only triggers when `mode` doesn't match a built-in; same `ValueError("Unsupported planner mode: …")` is raised if no matching plugin is found.
- Pre-existing generated agents on disk are not modified; only newly-generated agents include the new templates.

## [0.19.0] — 2026-04-16

### Added
- **Direct USDC transfers wired end-to-end** — `agent_payments.execute_payment(method="transfer")` now signs via OWS and broadcasts to Base mainnet. Previously returned only the unsigned tx. Verified live: TX `0x8b2c0df7ef58...` moved $0.001 USDC between two agent wallets.
- **`agentPayments` policy gate** — `policy-bundle.json` requires explicit `directTransferEnabled: true` to opt into direct transfers. Supports `maxPerTransferUsd`, `allowedRecipients` whitelist, `allowedChains` whitelist. Default deny.
- **Two-agent marketplace example** — `examples/two-agent-marketplace/`: setup.sh generates buyer + oracle, run.sh launches both, terminal-dashboard.py shows live agent state with on-chain balances and audit feed (no Flask required).
- **RPC User-Agent header** — `_rpc_call` now sends a User-Agent so public Base RPCs (publicnode, llamarpc) don't return 403. Required for direct transfer flow with default RPC.
- **Cloud LLM auto-detection** — `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` automatically picked up from env when planner mode is set. No `apiKeyEnv` config needed. (`config.py`)
- **Deep health checks** — `/ready` endpoint returns 503 when planner has consecutive failures or kill switch is active (`runner.py`). Distinguishes liveness from readiness for K8s.
- **Prometheus metrics** — `/metrics` endpoint exports tick counts, failures, agent state in Prometheus text format. (`runner.py`)
- **Per-tick timeout** — `tick_timeout_seconds` in `RunnerConfig` (default 120s) prevents hung LLM calls from stalling the loop.
- **Circuit breaker** — `circuit_breaker_threshold` (default 5) auto-pauses the agent for `circuit_breaker_cooldown_seconds` (default 60s) after consecutive failures. Stops cost runaway when LLM is down.
- **Token budget enforcement** — prompts auto-truncate to fit each model's context window. (`prompting.py`: `estimate_tokens`, `get_token_budget`, `truncate_to_budget`)
- **DeFi safety helpers** — new `defi_safety.py` module: `simulate_tx()` (eth_call before signing), `check_slippage()`, `ExposureTracker` (concentration limits), `check_position_health()` (liquidation monitoring).
- **Replay debugging CLI** — `forge replays <agent>` lists ticks; `forge replay-show <file>` pretty-prints the step ledger with reasoning.
- **Documentation site** — full Nextra v4 site at `docs-site/` with 25 pages and per-page videos. Vercel-deployable.
- **Issue/PR templates** — `.github/ISSUE_TEMPLATE/` and `PULL_REQUEST_TEMPLATE.md`.
- **GitHub Actions CI** — `.github/workflows/ci.yml` runs pytest + ruff on Python 3.12/3.13.

### Changed
- A2A server and health server now bind to `127.0.0.1` (was `0.0.0.0`) — prevents unintended network exposure.
- A2A server enforces 1MB max body size on POST.
- `.env` files created with `chmod 0600` immediately, not deferred to `forge security-check --harden`.
- Hardcoded Alchemy RPC URL removed from CLI defaults — falls back to public `mainnet.base.org`.

### Security
- Scrubbed Alchemy RPC API key from git history (`git filter-repo`).
- All historical commits re-authored to canonical email.
- Root `.gitignore` covers `.env`, `.ows/`, `wallet-backup-*`, `x402_state.json`, `replays/`, `memory.db`, `knowledge/`, `node_modules/` for defense in depth.

## [0.17.0] — 2026-04-14
- Local agent registry (`~/.aether-forge/agents.db`)
- A2A inter-agent communication (Google A2A protocol)
- On-chain ERC-8004 registry on Base mainnet
- Anti-impersonation attestation (EIP-712 self-attestation + framework attestor)
- Agent-to-agent payments (x402, direct USDC, ERC-8183 escrow)
- x402 payment server (agents can ACCEPT payments)
- Security audit fixes: atomic budget locking, A2A rate limiting, MCP timeout, prompt injection scanning

## [0.15.0] — 2026-04-11
- MCP (Model Context Protocol) client — discover and call tools from any MCP server (stdio + HTTP)
- Function-call planner adapter
- `forge doctor` probes MCP servers

## Earlier versions
See `docs/prd/CHANGELOG.md` for the full PRD-level history.

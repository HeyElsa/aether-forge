# Changelog

User-facing changes to Aether Forge. Format follows [Keep a Changelog](https://keepachangelog.com/).

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

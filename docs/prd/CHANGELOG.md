# PRD Changelog

## v0.18.0 - 2026-04-15

Cloud LLM auto-detection, Nextra docs site, 25 video walkthroughs, HeyElsa branding, install-from-source.

### Cloud LLM provider auto-detection
- `config.py` auto-detects `OPENROUTER_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` from env when using named provider modes. No `apiKeyEnv` config needed.
- Tested: OpenRouter + Claude Sonnet 4 (2 ticks, 30 steps), DeepSeek R1 (working, slow).

### Documentation site (Nextra v4)
- 25 MDX pages across 4 sections: Getting Started, Guides (6), Features (11), Reference (5)
- End-to-end tutorial from install to production (15 steps with real terminal output)
- Strategy writing guide with patterns (momentum, mean reversion, grid, multi-agent coordinator)
- Full configuration reference for `aether-forge.json`
- CLI reference with all 45+ commands
- Built-in copy dropdown (Copy for LLM, Open in ChatGPT, Open in Claude)
- Copy button on every code block
- Vercel-ready: `vercel.json` + `next build` passes clean

### 25 unique video walkthroughs
- One per docs page, no duplicates. Remotion-rendered Apple-style walkthroughs.
- Videos 17-24 created specifically for docs pages that would otherwise share videos.
- All include "by [Elsa logo]" outro (white variant for dark backgrounds).

### HeyElsa branding
- Footer + homepage: "by [Elsa logo]" linking to heyelsa.ai
- Light/dark mode: `<picture>` + `prefers-color-scheme` swaps logo variants
- Elsa dark variant: only wordmark text changed to `#1a1a1a`, icon stays red+white

### Install from source
- GitHub install as primary method until PyPI publish
- Updated: README.md, docs intro, Getting Started, End-to-End Tutorial, Custom Agent guide

### Expanded demo (17 sections)
- Added sections 11-17: agent registry, A2A, on-chain registration, attestation, payments, multi-agent, docs site

## v0.17.0 - 2026-04-14

Agent registry, A2A inter-agent communication, on-chain ERC-8004 identity, and anti-impersonation attestation.

### Local agent registry
- `~/.aether-forge/agents.db` SQLite database tracks every agent created through the framework (auto-registered at generation time)
- `forge agent-list` / `forge agent-info <id>` / `forge agent-remove <id>` CLI commands
- `agent_peers` table for discovered remote agents with `find_peers_by_capability()` search
- `--no-registry` flag on `forge generate-fast` for users who want zero tracking

### A2A inter-agent communication (Google A2A protocol, v1.0.0)
- `src/aether_forge/a2a_server.py` — stdlib HTTP server exposing agent capabilities via A2A protocol. Serves Agent Card at `GET /.well-known/a2a-card`, handles JSON-RPC 2.0 at `POST /` (message/send, tasks/get, tasks/list, tasks/cancel). In-memory task store with full lifecycle (submitted → working → completed/failed/canceled).
- `src/aether_forge/a2a_client.py` — wraps `a2a-sdk` Python package for calling other agents. `A2AForgeClient` provides `get_agent_card()`, `send_task(capability, arguments)`, `is_available()`.
- `build_agent_card()` generates A2A Agent Cards from `capability-manifest.json`, mapping declared capabilities to A2A skills.
- `forge agent-send --capability X --endpoint http://...` CLI command.
- New `[a2a]` extra in pyproject.toml with `a2a-sdk>=0.3.0`.

### On-chain ERC-8004 registry (Base mainnet)
- `src/aether_forge/onchain_registry.py` — pure-stdlib client for the deployed IdentityRegistry at `0x8004A169FB4a3325136EB29fA0ceB6D2e539a432` on Base mainnet (61k+ agents). Proper ABI encoding for `register(string)`, `setAgentURI(uint256,string)`, `balanceOf(address)`, `ownerOf(uint256)`, `tokenURI(uint256)`, `getAgentWallet(uint256)`, `name()`. Multi-RPC fallback across free Base endpoints.
- `forge agent-register <id> [--testnet]` builds unsigned registration transaction with metadata URI.
- Verified live: `contract_name()` returned "AgentIdentity" from Base mainnet.

### Anti-impersonation attestation (two-layer defense)
- **Layer 1 — Self-attestation** (automatic): agent's OWS wallet signs an EIP-712 `AetherForgeAttestation` at generation time linking `artifactSetId + capabilitiesHash + agentAddress + timestamp`. Saved as `attestation.json`. Proves wallet ownership.
- **Layer 2 — Framework attestation** (opt-in): the project team's well-known attestor wallet signs verified agents on-chain. Only this signature proves genuine Aether Forge origin — impersonators can't produce it without the team's private key. Address will be published in `ATTESTOR.md`.
- Three trust tiers: **verified** (attestor signed) > **self-attested** (wallet signed) > **unverified** (metadata only).
- `src/aether_forge/attestation.py` — `Attestation` dataclass, `create_self_attestation()`, `verify_self_attestation()`, `verify_framework_attestation()`, `determine_trust_tier()`, EIP-712 type definitions.
- `ATTESTOR.md` — documents the attestor address, trust tiers, verification process, and impersonation threat model.

### Agent-to-agent payments (bidirectional)
- `src/aether_forge/agent_payments.py` — three payment channels for inter-agent commerce:
  - **x402 pay-per-call** via existing `X402Client` (EIP-3009 on USDC)
  - **Direct USDC transfer** via `build_transfer_tx()` (ERC-20 transfer on Base/Ethereum)
  - **ERC-8183 escrow** via `build_escrow_fund_tx()` (contract deployment pending)
- `PaymentRequest` / `PaymentResult` typed dataclasses for A2A message metadata
- `check_budget()` enforces the same budget caps (`x402_state.json`) for inter-agent payments as for Elsa x402 calls — one budget, multiple channels
- `execute_payment()` dispatcher routes to the right channel based on `method` field. Holds an exclusive file lock (`fcntl.flock`) across budget check + payment execution to prevent race conditions (CRITICAL fix from security audit).
- 19 tests covering all three channels, budget enforcement, edge cases

### x402 payment server — agents can ACCEPT payments
- `src/aether_forge/x402_server.py` — the SERVER complement to the existing `X402Client`. Lets agents gate their capabilities behind x402 payments so other agents must pay before receiving results.
- `X402PaymentGate` — configures prices per capability, returns 402-style `auth-required` responses with payment requirements (`PaymentRequirement` dataclass with scheme, network, maxAmountRequired, payTo, asset), verifies incoming payment headers (x402 version, network, pay-to address, amount, signature), records payments with audit logging.
- `build_paid_task_handler(gate, handlers)` — factory that builds an A2A task handler with payment gating. Free capabilities execute directly; paid capabilities without payment return `auth-required`; paid capabilities with valid payment are verified, recorded, and executed.
- Tested end-to-end: free capability ✓, paid without payment → auth-required ✓, paid with valid payment → completed ✓, wrong address → rejected ✓, insufficient amount → rejected ✓, payment tracking ✓.

### Security audit fixes (5-persona audit: security analyst, white hat, protocol architect, AI safety, performance engineer)
- **Atomic budget enforcement**: `execute_payment()` holds `fcntl.flock()` across check + dispatch (CRITICAL — race condition fix).
- **A2A rate limiting**: `_TaskStore` gains 60 tasks/min per-IP rate limit + 1000 max queue size. Rejects excess with JSON-RPC error -32000.
- **MCP readline timeout**: `McpStdioClient._rpc()` uses `select.select()` before `readline()` to prevent hanging on stuck servers.
- **Prompt injection scanning**: `runtime.py` scans all capability execution results through `InputSanitizer` before they enter `working_set` and the planner's prompt.
- **Bounded tick history**: `_tick_history` converted to `deque(maxlen=200)` to prevent memory growth.
- **MCP subprocess cleanup**: `McpStdioClient.__del__()` kills zombie processes on garbage collection.
- **Attestation warnings**: `verify_framework_attestation()` logs WARNING when attestor address is empty. `verify_self_attestation()` docstring warns that structural validation ≠ cryptographic validation.
- **EIP-712 chainId parameterized**: `build_attestation_typed_data()` accepts `chain_id` param (default 8453 Base, 84532 Sepolia).
- **ABI string length validation**: `_encode_string()` raises ValueError if string exceeds 8 KB.

### Real-money validation
- **Agent-to-Elsa payment**: Agent A paid $0.002 USDC to Elsa's `get_token_price` on Base mainnet (EIP-3009, wallet `0x0000000000000000000000000000000000000001`).
- **Agent-to-agent data forwarding**: Agent A forwarded Elsa's price data to Agent B via A2A. Agent B confirmed receipt and computed a risk score.
- **Multi-agent team test**: 3 agents (price-oracle, risk-analyzer, portfolio-mgr) generated, registered, started A2A servers, exchanged tasks via real HTTP, verified rate limiting, budget enforcement, peer discovery. 40/40 passed.
- **Payment acceptance test**: Agent B gated a capability at $0.005 USDC. Without payment → auth-required. With payment → verified and executed. 16/16 passed.

### Tests
- 442 passed, 1 skipped across 47 test files. E2E multi-agent: 40/40. Payment acceptance: 16/16. Real money: 14/14.

## v0.15.0 - 2026-04-11

MCP client support and a new function-call planner. This release adds Model Context Protocol (MCP) as a first-class capability source so generated agents can discover and call tools from any MCP server — filesystem servers, GitHub API servers, Hermes Agent's messaging gateway, or any custom MCP server. It also introduces a dedicated `FunctionCallPlanner` for models that produce JSON function-call output.

### New: MCP (Model Context Protocol) client

- **New module `src/aether_forge/mcp_client.py`** — pure-stdlib MCP client supporting both stdio (subprocess) and HTTP transports. Implements `initialize`, `tools/list`, `tools/call`, and the `notifications/initialized` handshake. Emits a `DeprecationWarning`-style log when servers return errors and raises a typed `McpProtocolError` / `McpError` / `McpTimeoutError` hierarchy so callers can retry intelligently.
- **New data source `McpDataSource`** in `data_layer.py` alongside `HTTPDataSource`, `X402DataSource`, `WebSocketDataSource`, and `MockDataSource`. Discovers tools at connection time via `tools/list` and routes `fetch()` calls through `tools/call`. Works with the existing `DataRouter` fallback chain so MCP tools can be one option among many in a scaffold router.
- **New factory `build_mcp_source()`** — accepts either an `McpServerConfig` or a plain dict so you can build a data source directly from the `mcp_servers:` block in `aether-forge.json`.
- **Config schema**: generated agents can declare an `mcp_servers:` block at the top level of `aether-forge.json`. Each entry is either stdio (`command` + `args` + optional `env`) or HTTP (`url` + optional `headers`) with optional `tools.include` / `tools.exclude` whitelists.
- **StrategyConfig gained an `mcp_servers` field** — `scaffold_router.py`'s strategy router config now carries the MCP server declarations through to the generated agent's execution router. `forge run` reads them from `aether-forge.json` automatically.
- **Stdio subprocess hardening** — when spawning MCP servers as subprocesses, only a safe baseline environment (`PATH`, `HOME`, `USER`, `SHELL`, `LANG`, `LC_ALL`, `TERM`) plus explicitly-declared `env:` entries are passed through. The full parent environment is never leaked. Matches Hermes Agent's own stdio security model.
- **`forge doctor` probes MCP servers** — when called with a config path, the doctor initializes each declared MCP server and reports the tool count. Failures are marked as optional (they don't flip the overall verdict to UNHEALTHY) since an unreachable MCP server is usually a config issue, not a missing runtime requirement.
- **New `docs/mcp.md`** — user guide covering: local filesystem example, Hermes Agent messaging bridge example, remote HTTP example, tool filtering, stdio hardening, credentials via env vars, programmatic API, troubleshooting table, list of unsupported MCP features (resources, prompts, sampling, streaming, Aether-as-server).
- **New `tests/test_mcp_client.py`** — 20 tests covering config validation, stdio protocol round-trip (initialize, list tools, call tool, error handling, tool filtering), HTTP transport (with injected `request_fn` for mocking), `McpDataSource` integration (fetch routing, unknown tool handling, DataRouter dispatch), and the `build_mcp_source` factory.

### Renamed: Hermes adapter → Function-call adapter

### Added: Function-call planner

- **`FunctionCallPlanner`** in `src/aether_forge/config.py` — a planner that wraps any `PlanningModel`, prompts it for a JSON function-call response, and translates that into native Aether `StepProposal` objects. Use with `--planner-mode function-call` and any OpenAI-compatible endpoint (Ollama, vLLM, LM Studio, or a hosted provider) pointed at a model fine-tuned for structured tool use.
- **Adapter module**: `src/aether_forge/adapters/function_call.py` exposes `FunctionCallTranslator`, `FunctionCallResponse`, and `FunctionToolCall` — the dataclasses + translator that define the expected JSON shape `{reasoning, tool_calls, final_message, requires_approval}` and convert it into native steps.
- **Tests**: `tests/test_function_call_adapter.py` — 7 tests covering the translator layer (declared/undeclared capabilities, approval flow) and the end-to-end `FunctionCallPlanner` with a mock model (valid response parsing, markdown code-fence stripping, malformed-JSON fallback with logged warning).

### Fixed: prompt/parser mismatch in the function-call planner

Before: `HermesPlanner.propose_plan` called the generic `build_planning_prompt_from_session()`, which asked the model for `{"steps": [...]}`, then tried to parse `{reasoning, tool_calls, final_message}` out of the response. It worked by accident on capable models and silently fell through to the heuristic planner on everything else, with no log line pointing at the problem.

After: `FunctionCallPlanner` uses a dedicated `build_function_call_prompt_from_session()` that requests the exact shape the translator expects. The new prompt includes an explicit schema example, capability constraints, and formatting rules. When parsing does fail, the planner now logs a `WARNING` at `aether_forge.config` so operators can see why the fallback kicked in.

### Fixed: markdown code-fence handling

Added `_parse_function_call_payload()` which strips ```` ```json ... ``` ```` wrappers before calling `json.loads()`. Several models (Gemma, some Ollama checkpoints) wrap JSON responses in markdown fences even when asked not to. Previously these would hit the fallback path silently.

### Fixed: empty capability manifest passthrough

`HermesPlanner(model=..., capability_manifest={})` was always constructed with an empty dict and the `capability_manifest` field was never read. Removed the dead parameter from `FunctionCallPlanner.__init__` — the translator gets the real declared capability ids from `session.artifacts.capability_manifest` at runtime, which is what was always actually happening.

## v0.14.0 - 2026-04-11

LLM-driven by default, four-layer memory architecture, doctor as runtime stack verifier, install extras refactor, canonical team demo script.

- **LLM-driven by default.** `forge generate-fast` no longer hardcodes `"planner": {"mode": "heuristic"}` in generated agents. The new `_autodetect_planner()` helper in `cli.py` probes the host machine in order — local Ollama (preferring Gemma if present), then `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`, `OPENROUTER_API_KEY`, falling back to `heuristic` only when nothing is available — and writes the resolved planner block into the generated agent's `aether-forge.json`. Operators don't need CLI flags or hand-edits to wire an LLM into a new agent.
- `FastGenerateRequest` gained `planner_mode`, `planner_model`, `planner_base_url`, `planner_api_key_env` fields. `_project_config_json()` reads them and honors the operator's choice.
- `forge generate-fast` accepts `--planner-mode`, `--planner-model`, `--planner-base-url`, `--planner-api-key-env` for explicit override of auto-detection. The resolved choice is logged loudly: `[planner] auto-detected: mode=ollama model=gemma4:latest baseUrl=http://localhost:11434`.
- **Documented four-layer memory architecture as a first-class framework concept.** Layer 1 = `replays/tick-N.json` audit only; Layer 2 = `session.working_set` per-tick scratch; Layer 3 = `SqliteMemoryStore` durable per-agent (`memory.db`); Layer 4 = `KnowledgeStore` long-term semantic + temporal (MemPalace, optional). The LLM reads Layers 2-4 in the planning prompt every tick (`## Runtime State`, `## Memory Context`, `## Knowledge`).
- **`forge doctor` expanded** to verify the runtime memory and crypto stack with **functional round-trip checks**, not just import-existence:
  - `_check_sqlite_memory_store()` instantiates a real `SqliteMemoryStore` in a temp dir, writes a sentinel `MemoryRecord`, reads it back via `MemoryQuery`. Reports `Layer 3 round-trip ok (write + read)`.
  - `_check_mempalace_knowledge_layer()` imports `mempalace`, instantiates a `KnowledgeStore`, calls `add_fact()` + `remember()` + `query_entity()`. Reports the mempalace version + `KG + semantic round-trip ok`. Degrades gracefully when the optional dep is missing.
  - `_check_cryptography()` reports the `cryptography` version (required for AES-256-GCM encrypted backups and encrypted memory records).
  - **Removed** `_check_ruff()` and `_check_pytest()` — those are framework-contributor tools, not runtime requirements for an agent. Cleaner doctor output for production users.
- `forge doctor` now prints a one-line verdict summary: `Healthy — N/N ok, 0 skipped, 0 failed`, `Healthy (with optional skips) — ...`, or `UNHEALTHY — ...`.
- **New install extras** in `pyproject.toml`:
  - `[security]` → `cryptography>=42.0.0` for encrypted backups + encrypted memory records.
  - `[all]` → `wallet + knowledge + security` in one install for production users (`pip install 'aether-forge[all]'`).
  - Added `ruff>=0.6.0` to `[dev]` for framework contributors.
- **`demo.sh`** — new top-level canonical team walk-through script. 10 sections, ~3 minutes in `DEMO_AUTO=1` mode, ~10 minutes with narration pauses. Built around an autonomous ETH swing trader that interprets a markdown strategy file every tick. Covers: doctor preflight, skill catalogs, model selection (with local Gemma smoke prompt), prose strategy authoring, generation with `--strategy-file --autonomous --wallet`, validation, eval-pack, wallet inspection, security audit, paper run with autoresearch + knowledge, replay reasoning trail, autoresearch proposals, both memory layers (SQLite + MemPalace) inspected via `sqlite3`, live x402 mode, kill switch via direct `forge x402-call --confirm-live`, encrypted backup. Supports `DEMO_AUTO`, `DEMO_SKIP_LIVE`, `DEMO_BACKUP_PASSPHRASE`, `DEMO_PLANNER_MODE`/`DEMO_PLANNER_MODEL` env overrides for rehearsal vs live demo.
- New PRD file: `docs/prd/aether-forge-prd-v0.14.0.md`.
- Test count: 345 passing (no regressions; new doctor checks covered by existing `test_doctor.py`).

## v0.13.0 - 2026-04-08

Production-grade security hardening, encrypted backups, x402 payment client robustness, generic data layer.

- Added `security_hardening.py` module with end-to-end safeguards for systems handling real money:
  - `sanitize_string()` / `sanitize_dict()` strip mnemonics, OWS API keys, hex private keys, EIP-712 signatures, and labelled secrets from any string or dict before logging.
  - `lock_down_file()` / `lock_down_directory()` enforce 0600 file and 0700 directory permissions on secrets and vaults.
  - `harden_agent_directory()` walks an agent project and locks down `.env`, `wallet.json`, `x402_state.json`, `memory.db`, `.ows/`, `knowledge/`, `replays/`, and any `wallet-backup-*.json[.enc]` files.
  - `encrypt_backup()` / `decrypt_backup()` produce passphrase-encrypted wallet backups using AES-256-GCM with scrypt KDF (n=2^16, r=8, p=1) — only public metadata (wallet ID, addresses) is stored in the clear.
  - `scan_for_secrets()` recursively scans an agent directory for accidental secret leakage in source files, skipping known-safe `.env`, vault, and binary files.
  - `preflight_security_check()` runs an 8-point audit (wallet exists, real OWS, .env perms, .gitignore coverage, vault perms, halt file, secret scan, audit log) and returns a structured report.
- Added `forge security-check <agent>` CLI command with `--harden` flag to apply file permission fixes in place.
- Added `forge wallet-backup <agent>` and `forge wallet-restore <backup>` commands. Backups are encrypted by default (passphrase prompt via `getpass`); `--unencrypted` requires an explicit opt-in.
- `provision_wallet()` now calls `harden_agent_directory()` after writing the wallet config so every newly generated agent ships with locked-down secrets out of the box.
- `provision_wallet()` now also writes `wallet-backup-*.json[.enc]` and `x402_state.json` into the generated `.gitignore` alongside `.env`, `.ows/`, and `wallet-mnemonic.txt`.
- Runner JSON log handler now passes every emitted record through `sanitize_string()` and locks the log file to 0600 on creation, so accidental mnemonic/key emission cannot end up in plaintext on disk.
- `X402Client._audit()` now passes the payload through `sanitize_dict()` before persistence and locks the audit log to 0600 on first write. The persistent state file (`x402_state.json`) is locked down on every save.
- Added `x402_client.py` improvements: persistent budget state across restarts (loads/saves to `x402_state.json`), pre-call balance check via Base RPC `eth_call`, `DEFAULT_RPCS` chain map, fallback to passphrase signing when API-key EIP-712 is unsupported.
- Added `data_layer.py`: a generic `DataRouter` with `HTTPDataSource`, `X402DataSource`, `WebSocketDataSource`, and `MockDataSource` plus capability-based dispatch with fallback chains. Pre-built constructors for Binance (HTTP and WebSocket), CoinGecko, and Elsa (x402).
- Validated end-to-end on Base mainnet with a real OWS-funded wallet (`0x0000000000000000000000000000000000000001`): 3 paid Elsa x402 calls succeeded, budget caps and persistent state confirmed.
- New modules: `src/aether_forge/security_hardening.py`, `src/aether_forge/data_layer.py`, `src/aether_forge/x402_client.py`.
- New tests: `tests/test_security_hardening.py` (20 tests), `tests/test_x402_client.py` (13 tests), `tests/test_data_layer.py`. Total suite: 345 passing.
- Wired the new `DataRouter` into the generated scaffold's `src/strategy/router.py`. The router now builds a per-mode source chain in `__init__` (`paper`/`simulated` → free Binance + CoinGecko; `live` → paid Elsa x402 first, then Binance + CoinGecko fallback). `_fetch_price()`, `_handle_data_source()`, and the new `cost_summary()` all flow through the same router so prices, balances, portfolios, swap quotes, and any matching capability slug come from a single dispatched source with uniform cost tracking. Added `chain` field to `StrategyConfig` and `--chain` flag to `forge run`. Generated routers cache the agent's own EVM address from `wallet.json` for live calls.
- Generated routers now ship with a per-chain `_TOKEN_REGISTRY` (Base/Ethereum) and a `_resolve_token_address()` helper. The Elsa `get_token_price` API keys off contract addresses, not symbols, so `_fetch_price` now translates `ETH` → `0x4200000000000000000000000000000000000006` (WETH on Base) before sending the body. Edit/extend the registry per agent.
- `X402Client._audit("payment_rejected", ...)` now captures a truncated response body so HTTP-400 schema errors from paid endpoints are debuggable. The raised `X402Error` includes the snippet too.
- Validated end-to-end live agent run on Base mainnet with real money: `forge run /tmp/eth-prod --mode live --chain base --auto-approve --max-ticks 2` completed both ticks, the planner proposed a data-source step during a tick, the scaffold's `DataRouter` dispatched to Elsa via the x402 client, EIP-3009 authorization was signed, Elsa accepted the payment, and `x402_state.json` updated to `total_payments=2, session_spent_usd=0.004`. Wallet `0x0000000000000000000000000000000000000001` retains ~1.99 USDC.

## v0.12.0 - 2026-04-09

Runtime self-improvement, deployment infrastructure, provider-agnostic architecture, proper OWS wallet, strategy file parsing.

- Added `evolution.py` module with runtime autoresearch: `StrategyArtifact` (structured, mutable, versioned strategy parameters), `SelfEvaluator` (win rate, P&L, drawdown from trade history), `RuntimeAutoresearch` (Karpathy keep/discard loop at runtime), `ImprovementProposal` (structured mutation proposals shown to user). Protected evaluator prevents agent from weakening its own success criteria.
- Added `forge run --autoresearch --eval-interval 6` for runtime self-improvement.
- Added `forge strategy view|accept|reject` commands for managing strategy proposals.
- Added deployment infrastructure to `runner.py`: `--health-port` HTTP endpoint (`/health`, `/status`, `/ticks`), `--json-log` structured JSON logging to file, `--pid-file` for daemon management, crash recovery from replay files.
- Runner now survives individual tick failures instead of stopping.
- Made framework fully provider-agnostic: deleted `elsa_router.py`, replaced with `scaffold_router.py` (generic config + loader). All trading logic lives in generated scaffold `src/strategy/`. Router reads capabilities from manifest and routes by `kind` and `provider`.
- Added `wallet.py` with proper OWS wallet integration: per-agent vault isolation (`.ows/` per agent), chain-restriction policy with CAIP-2 IDs, scoped API key (`ows_key_...`) so agent never gets owner passphrase, `sign_message()` and `sign_and_send()` via API key + vault path, 9 chains (EVM, Solana, Bitcoin, Cosmos, Tron, TON, Sui, Filecoin, XRPL), fallback to simulated when OWS not installed.
- Added `strategy_parser.py` with `--strategy-file` flag: accepts English/markdown/JSON strategy descriptions; regex extracts spread, position size, max orders, stop loss, daily loss, rebalance interval, tokens, entry rules, success metrics; optional LLM enhancement; parsed parameters override defaults in `strategy.json`.
- Added agent summary card printed after generation: wallet addresses (EVM, Solana, Bitcoin), strategy parameters, entry rules, success criteria, capabilities (read vs write), deployment readiness, wallet provider.
- Enhanced generated scaffolds: `AGENT.md` (comprehensive docs), `strategy.json` (tunable params), `strategy-description.md` (original strategy file), `Dockerfile` + `docker-compose.yml` (container deployment), `wallet.json` + `.env` + `.gitignore` (wallet config).
- Added `--wallet` and `--autonomous` flags to `forge generate-fast`.
- Fixed Ollama not requiring API key for local endpoints.
- Fixed autoresearch planner initialization safety.
- Fixed `forge init` parent directory creation.
- Test count: 272 to 288.
- New modules: `src/aether_forge/evolution.py`, `src/aether_forge/wallet.py`, `src/aether_forge/strategy_parser.py`, `src/aether_forge/scaffold_router.py`.
- Added `knowledge.py` with MemPalace integration as long-term knowledge layer: semantic search (ChromaDB vectors), temporal knowledge graph (SQLite facts with validity windows), layered memory retrieval, and agent planning context. Sits alongside SqliteMemoryStore: operational data in SQLite, long-term knowledge in MemPalace.
- Added `--knowledge` flag to `forge run` to enable MemPalace knowledge layer.
- Added `mempalace>=3.1.0` as optional dependency (`pip install aether-forge[knowledge]`).
- Knowledge context injected into planning prompts when available.
- Test count: 288 to 295.
- Deleted module: `src/aether_forge/elsa_router.py` (replaced by `scaffold_router.py`).

## v0.11.0 - 2026-04-09

Continuous agent execution, paper trading, scaffold-owned strategy, planning enhancements.

- Added `forge run` CLI command and `AgentRunner` class for continuous governed agent execution with configurable interval, max ticks, auto-approve, memory persistence, and per-tick replay writing.
- Added `RunnerConfig` and `TickResult` dataclasses for programmatic runner control and tick-by-tick status reporting.
- Trading strategy code (price feeds, momentum, paper trading, routing) is now generated INTO the scaffold project under `src/strategy/`, not in the framework.
- Generated scaffolds include `src/strategy/price_feed.py` (Binance API), `src/strategy/momentum.py` (trend detection), `src/strategy/paper_trading.py` (order simulation + P&L), `src/strategy/router.py` (ExecutionRouter implementation).
- Paper trading with real Binance market data: live ETH prices, 30m candle history, momentum indicators, balance enforcement, holdings tracking, portfolio valuation.
- Added `_AutoApproveGate` policy gate that injects synthetic approval tokens for side-effecting capabilities in sandbox/paper environments. All other policy checks (environment, notional, staleness) still apply.
- Generated scaffolds now include `pyproject.toml` (with aether-forge dependency) and `main.py` (entry point) for standalone agent execution.
- Enhanced planning prompts: working set data (not just keys), recent observations, action-oriented instructions, auto-approve awareness.
- Fixed planner to strip markdown code fences from LLM responses before JSON parsing.
- Fixed planner to accept both camelCase and snake_case capability IDs from LLMs, normalizing to kebab-case.
- Runtime sessions now enter PAUSED status (not FAILED) when max_steps is exhausted, enabling continuous agents to resume on the next tick.
- Expanded crypto domain detection with 30+ DeFi keywords.
- Fixed skills to include `credentialHandleId` and handle declarations for validation.
- Added `forge eval --list` to discover available scenario IDs without executing them.
- Improved error messages across CLI commands.
- Test count: 159 to 266.
- New modules: `src/aether_forge/runner.py`, `src/aether_forge/elsa_router.py`, `tests/test_runner.py`, `tests/test_paper_trading.py`.

## v0.10.0 - 2026-04-09

Multi-provider LLM support, persistent memory, model discovery, CI/CD, E2E tests.

- Added native LLM adapter classes for Anthropic (Claude) and Google Gemini alongside the existing OpenAI-compatible adapter, enabling direct access to frontier models without proxies. All adapters are stdlib-only (urllib, no SDK deps).
- Added named provider shortcuts (`anthropic`, `gemini`, `openai`, `openrouter`, `ollama`) that auto-resolve base URLs and API format, removing the need for users to know provider-specific endpoints.
- Added `SqliteMemoryStore` as a persistent memory backend satisfying the `MemoryStore` protocol. Agents can now retain memory across sessions via `--memory-store sqlite`. 15 tests.
- Added `forge models-list` CLI command for discovering available models from OpenRouter (351+ models), Ollama (local), and OpenAI. Supports `--query` filtering and provider-specific output formatting.
- Added GitHub Actions CI/CD pipeline (`.github/workflows/ci.yml`) running pytest + ruff on Python 3.12/3.13.
- Added ruff linting configuration to `pyproject.toml`.
- Added 5 end-to-end integration tests covering `generate → validate → eval → promote` for crypto, general, CLI, SQLite memory, and skills flows.
- Fixed planner memory store access to use protocol-compatible `read()` instead of internal `_records` attribute, enabling any `MemoryStore` implementation as a drop-in backend.
- Added configuration documentation to README covering config file format, all environment variables, provider setup examples, and memory store usage.
- Test count: 127 → 159.
- New modules: `src/aether_forge/storage.py`, `tests/test_e2e.py`, `tests/test_storage.py`, `.github/workflows/ci.yml`.

## v0.9.0 - 2026-04-07

MAJOR: Open agent economy protocols, security hardening, full OWS wallet.

- Added four open agent economy protocol modules enabling every forge agent to participate in the open agent economy:
  - ERC-8004 (Agent Identity & Registry): on-chain Agent Card generation from forge artifact bundles, identity/reputation/validation registries. Module: `src/aether_forge/protocols/erc8004.py`.
  - ERC-8126 (Agent Trust & Verification): multi-dimensional risk scoring (ETV, SCV, WAV, WV) on a 0-100 scale with five risk tiers, offline trust assessment from forge artifacts. Module: `src/aether_forge/protocols/erc8126.py`.
  - ERC-8183 (Agentic Commerce): agent-to-agent job primitives (create, fund, submit, evaluate, complete, reject) with escrowed payment and evaluator role. Job lifecycle: Open, Funded, Submitted, Completed, Rejected, Expired. Module: `src/aether_forge/protocols/erc8183.py`.
  - x402 (HTTP Micropayments): agent discovery of paid endpoints via 402index.io, automatic 402 payment flow (request, parse, pay, retry), budget controls integration, support for skills.sh, bankr.bot, and any x402-enabled API. Module: `src/aether_forge/protocols/x402.py`.
- Added defense-in-depth security hardening module (`src/aether_forge/security.py`):
  - Session key policies with contract/chain allowlists, per-tx and per-day spending caps, and expiry.
  - Budget controls with circuit breakers that auto-pause when spending exceeds 3x rolling average.
  - Prompt injection detection with 12 compiled regex patterns covering instruction override, role impersonation, jailbreaks, delimiter injection, hidden content, base64 payloads, and zero-width unicode.
  - Token-bucket rate limiting for all agent operations.
  - Append-only audit logging for wallet.sign, x402.payment, job.create, and other security-sensitive operations.
  - Environment-tiered security defaults: sandbox (permissive) through paper, canary, to production (strictest).
- Expanded OWS wallet support from 6 to 21 SDK functions: wallet lifecycle (create, import mnemonic/private key, delete, export, rename), signing (message, transaction, typed data EIP-712, sign-and-send), policy management (create, list, get, delete), API key management (create, list, revoke), utilities (generate mnemonic, derive address). New CLI commands: wallet-import, wallet-delete, wallet-export.
- Updated skills integration with multiple registries (skills.sh, bankr.bot, any SKILL.md repo), `bankr:skill-name` shorthand, and capability-manifest mapping.

## v0.8.0 - 2026-04-07

- Marked the governed persistent memory layer as implemented: memory store wired into RuntimeSession with memory.read, memory.write, memory.promote surfaces, policy enforcement, expiry filtering, camelCase serialization, memory-aware planner, and eval memory_store injection.
- Marked slow-mode autoresearch as implemented: `forge generate-slow` CLI command with Karpathy-style baseline-first keep-or-discard loop, diminishing-returns early stopping, research-record.json artifact, and support for any PlanningModel as research backend.
- Added Hermes adapter integration as an implemented planner backend: `hermes` planner mode, HermesPlanner class wrapping PlanningModel and HermesAdapterTranslator, full factory wiring in build_planner_factory.
- Added skills integration: `forge skills-search`, `forge skills-add`, `--skills` flag on generate commands, support for multiple registries (skills.sh, skills.bankr.bot, GitHub repos), open SKILL.md standard, and capability-manifest mapping with full policy governance.
- Recorded Pure Python consolidation: removed TypeScript packages/ directory, Python SDK is the canonical implementation.
- Recorded full public API exports from __init__.py and adapters/__init__.py.

## v0.7.0 - 2026-04-06

- Added a governed persistent memory layer on top of the v0.6.0 product contract.
- Added a typed `Memory Record` artifact family and explicit `memory.read`, `memory.write`, and `memory.promote` capability surfaces.
- Added environment-scoped memory behavior and manual-only sandbox-to-live-like memory promotion in v1.
- Added provenance, sensitivity, expiry, and retention expectations for memory records.
- Clarified that memory is context, not authority, and cannot override spec or policy.

## v0.6.0 - 2026-04-06

- Ran a stricter exact-style autoresearch pass against the PRD using a fixed scoring rubric, baseline-first comparison, and keep/discard candidate variants.
- Added artifact compatibility status, migration contracts, generator version, and input digest requirements.
- Added credential-handle requirements so specs, runtime state, prompts, and traces do not rely on raw secret material.
- Added credential-handle scope requirements in capability manifests and policy enforcement.
- Added explicit effect-semantics metadata for side-effecting capabilities, including idempotency, retry, duplicate-submit, and compensation classes.
- Strengthened crypto execution and rollback requirements to reference declared effect semantics.
- Added exact-style autoresearch logs and results tracking under `docs/plans/`.

## v0.5.0 - 2026-04-06

- Ran an autoresearch-style improvement loop directly against the product spec and tightened the existing requirements.
- Added explicit artifact ownership, artifact-set IDs, and stronger scaffold regeneration semantics.
- Added validation classes, structured validation outputs, and stronger import/export requirements.
- Added an immutable active comparison contract, stronger keep-or-discard evidence rules, and machine-readable mutation-surface declarations.
- Added runtime step-ledger requirements, fail-closed policy availability behavior, and linked policy decision records.
- Added structured evaluation stage outcomes, machine-readable rollout limits, automatic rollout hold triggers, rollback verification rules, and stronger incident lifecycle requirements.
- Added derived health-signal requirements and stronger evidence-chain linkage across artifacts, runtime, and promotion.

## v0.4.0 - 2026-04-06

- Refined `slow mode` using `karpathy/autoresearch` loop mechanics instead of generic deep-research wording.
- Added a baseline-first protocol for slow-mode and self-evolution comparisons.
- Added fixed-budget and comparable-condition requirements for candidate evaluation.
- Added explicit `keep`, `discard`, `blocked`, and `execution failure` iteration outcomes.
- Added an append-only `Iteration Ledger` inside the `Research Record`.
- Added protected-evaluator requirements so candidates cannot weaken the policy or evaluation surface used to judge them.
- Added accepted mutation surface guidance and complexity-aware variant selection.

## v0.3.0 - 2026-04-06

- Added deep-research-driven refinements across architecture, crypto safety, slow mode, evaluation, and promotion.
- Added typed and versioned artifact expectations for the `Agent Spec` and related product objects.
- Added a `Research Record`, `Capability Manifest`, and `Scenario Pack` to the product model.
- Tightened the architecture into spec, reasoning, execution, effect, policy, and evidence layers.
- Added default-deny policy semantics, structured policy decisions, and runtime approval gates.
- Expanded the crypto model with wallet control topologies, signing isolation, venue capability matrices, idempotency, nonce management, and compliance hooks.
- Expanded the environment model with `shadow` and `canary live` stages.
- Expanded evaluation and rollout with offline vs online evals, progressive promotion, residual-risk review, rollback classes, and deactivation criteria.

## v0.2.0 - 2026-04-06

- Added `fast` and `slow` agent creation modes to the canonical product workflow.
- Defined `slow mode` as a Karpathy-style autoresearch loop that improves the spec, tools, policies, and evaluation plan before presenting a near-complete draft.
- Added product requirements for mode selection, research-backed refinement, completeness thresholds, and consolidated slow-mode presentation behavior.
- Expanded the architecture with an autoresearch engine and updated roadmap milestones to account for dual-mode creation.

## v0.1.0 - 2026-04-06

- Created the first canonical, human-readable PRD for `Aether Forge`.
- Established PRD versioning rules and a changelog process.
- Locked the product direction around a spec-first, developer-first agent builder framework.
- Defined crypto as the initial wedge through first-party wallets, exchanges, onchain actions, and market-data modules.
- Defined the core lifecycle as `Ideate -> Specify -> Generate -> Simulate -> Promote -> Operate -> Evolve`.
- Defined the v1 safety model around governed execution, sandbox-first testing, and human-approved promotion.

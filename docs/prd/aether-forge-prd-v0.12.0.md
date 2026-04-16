# Aether Forge Product Requirements Document

Version: `v0.12.0`
Status: `Draft`
Date: `2026-04-09`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.11.0.md`
Base PRD: `docs/prd/aether-forge-prd-v0.11.0.md`

Supporting design:

- `docs/plans/2026-04-06-aether-forge-schema-design.md`

## 1. Status

This PRD inherits all unchanged requirements from v0.11.0.

v0.12.0 adds runtime self-improvement, proper OWS wallet integration, strategy file parsing, deployment infrastructure, and provider-agnostic architecture. The framework can now generate an agent from a plain-language strategy file, provision a real multi-chain wallet with scoped API keys, run the agent continuously with health monitoring and structured logging, and let the agent propose improvements to its own strategy parameters at runtime — all within the governed pipeline. Key additions:

- Runtime autoresearch / self-improvement via `evolution.py` (new)
- Deployment infrastructure: health endpoint, JSON logging, PID file, crash recovery (new)
- Provider-agnostic architecture: `scaffold_router.py` replaces `elsa_router.py` (updated)
- Proper OWS wallet integration with per-agent vaults, scoped API keys, 9 chains (updated)
- Strategy file parsing from English/markdown/JSON via `strategy_parser.py` (new)
- Agent summary card with wallet addresses, strategy, capabilities, deployment readiness (new)
- Generated scaffold improvements: `AGENT.md`, `strategy.json`, `Dockerfile`, `docker-compose.yml` (updated)
- Bug fixes: Ollama API key, tick failure resilience, planner code fence stripping, autoresearch init safety, `forge init` parent dirs (updated)
- Test count: 272 to 288

## 2. Summary of Changes

Compared with `v0.11.0`, this version:

1. Added `evolution.py` module with `StrategyArtifact`, `SelfEvaluator`, `RuntimeAutoresearch`, and `ImprovementProposal` for runtime self-improvement using the Karpathy keep/discard pattern. The agent evaluates its own performance, proposes strategy mutations, and presents them to the user. A protected evaluator ensures the agent cannot weaken its own success criteria.
2. Added deployment infrastructure to `runner.py`: `--health-port` serves `/health`, `/status`, `/ticks` HTTP endpoints; `--json-log` writes structured JSON logs to file; `--pid-file` enables daemon management; crash recovery restores state from replay files.
3. Made the framework fully provider-agnostic by deleting `elsa_router.py` and replacing it with `scaffold_router.py`, a generic config and loader that reads capabilities from the manifest and routes by `kind` and `provider`. All trading logic now lives in generated scaffold `src/strategy/`.
4. Added proper OWS wallet integration in `wallet.py`: per-agent vault isolation (`.ows/` per agent), chain-restriction policy with CAIP-2 IDs, scoped API keys (`ows_key_...`) so the agent never gets the owner passphrase, `sign_message()` and `sign_and_send()` via API key + vault path, 9 chain families, fallback to simulated when OWS not installed.
5. Added `strategy_parser.py` with `--strategy-file` flag: accepts English, markdown, or JSON strategy descriptions; regex extracts spread, position size, max orders, stop loss, daily loss, rebalance interval, tokens, entry rules, and success metrics; optional LLM enhancement for deeper parsing; parsed parameters override defaults in `strategy.json`.
6. Added agent summary card printed after generation: shows wallet addresses (EVM, Solana, Bitcoin), strategy parameters, entry rules, success criteria, capabilities split (read vs write), deployment readiness, health endpoints, and wallet provider (OWS vs simulated).
7. Enhanced generated scaffolds with `AGENT.md` (comprehensive documentation), `strategy.json` (tunable parameters), `strategy-description.md` (original strategy file), `Dockerfile` + `docker-compose.yml` (container deployment), `wallet.json` + `.env` + `.gitignore` (wallet config), and `--wallet`, `--autonomous`, `--strategy-file` flags.
8. Fixed Ollama not requiring API key for local endpoints; runner survives individual tick failures instead of stopping; planner strips markdown code fences from LLM responses; autoresearch planner initialization made safe; `forge init` creates parent directories.
9. Test count increased from 272 to 288.

## 3. Runtime Autoresearch (New)

The framework now supports runtime self-improvement: a running agent can evaluate its own performance, propose strategy mutations, and improve over time — all within the governed pipeline with user approval.

### 3.1 `StrategyArtifact`

A structured, mutable, versioned container for strategy parameters that the agent can reason about and propose changes to:

| Field | Type | Description |
|---|---|---|
| `spread` | `float` | Bid-ask spread target |
| `position_size` | `float` | Position size as fraction of portfolio |
| `momentum_threshold` | `float` | Momentum signal threshold |
| `entry_rules` | `list[str]` | BUY/SELL conditions |
| `success_metrics` | `dict` | Win rate, max drawdown targets |
| `version` | `int` | Monotonically increasing version number |

The `StrategyArtifact` is loaded from `strategy.json` in the agent project and updated when the user accepts an improvement proposal.

### 3.2 `SelfEvaluator`

Computes agent performance metrics from balance history and trade results:

| Metric | Computation |
|---|---|
| Win rate | Fraction of trades with positive P&L |
| Total P&L | Sum of realized gains/losses |
| Max drawdown | Maximum peak-to-trough decline |
| Sharpe proxy | Return / volatility approximation |

The evaluator is **protected**: the agent cannot modify, weaken, or bypass the evaluation criteria used to judge its own performance. Success metrics are defined at generation time and locked.

### 3.3 `RuntimeAutoresearch`

Implements the Karpathy keep/discard loop at runtime:

1. After every `--eval-interval` ticks (default: 6), the `SelfEvaluator` computes current performance
2. If performance is below success criteria, `RuntimeAutoresearch` uses the LLM to propose a strategy mutation
3. The mutation is wrapped in an `ImprovementProposal` and presented to the user
4. The user can accept (apply the mutation) or reject (keep current strategy)
5. If accepted, the `StrategyArtifact` version increments and the agent continues with new parameters

### 3.4 `ImprovementProposal`

A structured change suggestion presented to the user:

| Field | Type | Description |
|---|---|---|
| `hypothesis` | `str` | Why this change should improve performance |
| `mutations` | `dict` | Parameter changes (old value to new value) |
| `rationale` | `str` | Evidence-based reasoning |
| `evidence` | `dict` | Current metrics that triggered the proposal |
| `risk_assessment` | `str` | What could go wrong |

### 3.5 CLI Integration

```bash
# Enable runtime autoresearch
forge run ./my-agent --autoresearch --eval-interval 6 --auto-approve

# View current strategy
forge strategy view ./my-agent

# Accept a pending proposal
forge strategy accept ./my-agent

# Reject a pending proposal
forge strategy reject ./my-agent
```

| Flag / Command | Default | Description |
|---|---|---|
| `--autoresearch` | `false` | Enable runtime self-improvement |
| `--eval-interval` | `6` | Ticks between evaluations |
| `forge strategy view` | | Show current strategy parameters and pending proposals |
| `forge strategy accept` | | Apply the pending improvement proposal |
| `forge strategy reject` | | Discard the pending improvement proposal |

### 3.6 Protected Evaluator Rules

1. The `SelfEvaluator` criteria (win rate target, max drawdown threshold) are set at agent generation time
2. The agent cannot modify, weaken, or remove evaluation criteria through any proposal
3. Proposals that attempt to change success metrics are rejected automatically
4. The evaluator code path is not accessible to the LLM planner as a mutable surface
5. This preserves the Karpathy principle: the judge must be independent of the candidate

Module: `src/aether_forge/evolution.py`

## 4. OWS Wallet Integration (Updated)

The wallet module has been substantially upgraded from basic OWS SDK function wrappers to a proper per-agent wallet provisioning system with vault isolation and scoped API keys.

### 4.1 Per-Agent Vault Isolation

Each agent gets its own `.ows/` directory containing wallets, policies, and keys. This prevents cross-agent access:

```
my-agent/
  .ows/              # Per-agent vault (auto-gitignored)
    wallets/
    policies/
    keys/
  wallet.json        # Addresses and policy/key IDs (no secrets)
  .env               # API key (auto-gitignored)
  .gitignore         # Covers .ows/, .env
```

The vault path is stored in `wallet.json` and passed to all signing operations.

### 4.2 Chain-Restriction Policy

Each agent wallet is created with a chain-restriction policy using CAIP-2 chain identifiers:

| Chain | CAIP-2 ID |
|---|---|
| Ethereum | `eip155:1` |
| Base | `eip155:8453` |
| Arbitrum | `eip155:42161` |
| Optimism | `eip155:10` |
| Polygon | `eip155:137` |
| Solana | `solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp` |
| Bitcoin | `bip122:000000000019d6689c085ae165831e93` |
| Cosmos | `cosmos:cosmoshub-4` |
| Tron | `tron:mainnet` |

Additional chains (TON, Sui, Filecoin, XRPL) are supported when available in the OWS SDK.

### 4.3 Scoped API Key

- `forge generate-fast --wallet` creates a scoped API key (`ows_key_...`)
- The API key is saved to `.env` (never committed to git)
- The agent uses only the API key for signing — never the owner passphrase
- `sign_message()` and `sign_and_send()` accept the API key and vault path
- If the OWS SDK is not installed, the module falls back to simulated addresses

### 4.4 Wallet Configuration Files

| File | Contents | Committed |
|---|---|---|
| `wallet.json` | Addresses, policy ID, key ID, vault path, provider | Yes |
| `.env` | `OWS_API_KEY=ows_key_...` | No (gitignored) |
| `.ows/` | Encrypted vault data | No (gitignored) |

### 4.5 CLI Flags

```bash
# Generate with real OWS wallet
forge generate-fast --name "My Agent" --idea "..." --output ./agent --wallet

# Generate with wallet + autonomous mode
forge generate-fast --name "My Agent" --idea "..." --output ./agent --wallet --autonomous
```

Module: `src/aether_forge/wallet.py`

## 5. Strategy File Parsing (New)

Users can now provide a strategy description file in plain English, markdown, or JSON, and the framework will extract structured trading parameters from it.

### 5.1 `--strategy-file` Flag

```bash
forge generate-fast --name "My Bot" --idea "spread trader" --output ./bot \
    --strategy-file ./my-strategy.md
```

The strategy file content is:
1. Embedded in `agent-spec.json` as the strategy source
2. Saved as `strategy-description.md` in the agent project
3. Parsed into structured parameters that populate `strategy.json`

### 5.2 Regex Extraction

`strategy_parser.py` uses regex patterns to extract trading parameters from natural language:

| Parameter | Example Match |
|---|---|
| Spread | "maintain a 0.5% spread" |
| Position size | "position size of 10%" |
| Max orders | "maximum 5 orders" |
| Stop loss | "stop loss at 3%" |
| Daily loss limit | "daily loss limit of $500" |
| Rebalance interval | "rebalance every 30 minutes" |
| Tokens | "trade ETH, BTC, and SOL" |
| Entry rules | "BUY when RSI < 30" |
| Success metrics | "target win rate of 60%" |

### 5.3 LLM Enhancement

When an LLM planner is configured, the parser can optionally send the strategy text to the LLM for deeper extraction of parameters that regex cannot capture (complex conditional logic, multi-step entry conditions, etc.). The LLM-extracted parameters are merged with regex results.

### 5.4 Parameter Override

Parsed parameters override the defaults in `strategy.json`. The override precedence is:

1. Explicit CLI flags (highest)
2. LLM-enhanced extraction
3. Regex extraction
4. Default values (lowest)

Module: `src/aether_forge/strategy_parser.py`

## 6. Deployment Infrastructure (New)

The runner now includes production deployment features for running agents as long-lived services.

### 6.1 Health Endpoint

```bash
forge run ./my-agent --health-port 8080
```

Starts an HTTP server on the specified port with three endpoints:

| Endpoint | Method | Response |
|---|---|---|
| `/health` | GET | `{"status": "ok", "uptime_seconds": N}` |
| `/status` | GET | `{"agent": "name", "tick": N, "last_status": "complete", "environment": "sandbox"}` |
| `/ticks` | GET | `{"total": N, "complete": N, "failed": N, "paused": N}` |

The health endpoint enables integration with container orchestrators (Kubernetes liveness/readiness probes), monitoring systems, and load balancers.

### 6.2 Structured JSON Logging

```bash
forge run ./my-agent --json-log ./logs/agent.jsonl
```

Writes one JSON object per line for each significant event:

```json
{"ts": "2026-04-09T12:00:00Z", "level": "info", "event": "tick_complete", "tick": 1, "steps": 5, "status": "complete"}
```

Enables integration with log aggregation systems (ELK, Datadog, Splunk) without custom parsers.

### 6.3 PID File

```bash
forge run ./my-agent --pid-file ./agent.pid
```

Writes the process ID to a file for daemon management. The PID file is removed on clean shutdown. External tools can send SIGTERM to the PID for graceful stop.

### 6.4 Crash Recovery

When a runner crashes (or is killed), it can recover state from replay files:

1. On startup, the runner checks `replays/` for the latest `tick_NNNN.json`
2. It restores the working set and tick counter from the replay
3. Execution resumes from the next tick

This ensures that long-running agents can survive process restarts without losing state.

### 6.5 Tick Failure Resilience

The runner now survives individual tick failures instead of stopping. A failed tick is logged and the runner continues to the next tick. This prevents transient errors (network timeouts, API failures) from killing long-running agents.

### 6.6 Docker Support

Generated scaffolds now include deployment files:

- `Dockerfile` — multi-stage build with Python 3.12, installs aether-forge and the agent project
- `docker-compose.yml` — service definition with health check, volume mounts for memory and replays, environment variable pass-through

```bash
cd my-agent
docker compose up -d
```

Module: `src/aether_forge/runner.py`

## 7. Provider-Agnostic Architecture (Updated)

The framework no longer contains any provider-specific trading logic. All trading code lives in the generated scaffold.

### 7.1 Before (v0.11.0)

- `elsa_router.py` in the framework contained Elsa-specific endpoint handling, Binance price feeds, paper trading simulation
- Framework was coupled to the Elsa API contract

### 7.2 After (v0.12.0)

- `elsa_router.py` deleted from framework
- `scaffold_router.py` added: generic config dataclass + loader that reads the scaffold's router implementation
- All trading logic generated into `src/strategy/` in the scaffold project:
  - `price_feed.py` — Binance API price fetching
  - `momentum.py` — trend detection and signals
  - `paper_trading.py` — order simulation + P&L tracking
  - `router.py` — `ExecutionRouter` implementation that reads capabilities from manifest
- The scaffold router routes by `kind` and `provider` fields from the capability manifest, not hardcoded endpoint names
- Any provider can be supported by generating a different `src/strategy/` implementation

### 7.3 `scaffold_router.py`

The framework module provides:

- `ScaffoldRouterConfig` — configuration dataclass with mode, provider, and paths
- `load_scaffold_router()` — dynamic loader that imports the scaffold's router module
- No provider-specific code, no API URLs, no endpoint definitions

Module: `src/aether_forge/scaffold_router.py`

## 8. Agent Summary Card (New)

After generation, the CLI prints a comprehensive summary card showing everything about the new agent:

```
╔══════════════════════════════════════════════════╗
║               BTC Basis Trader                   ║
╠══════════════════════════════════════════════════╣
║  ID:        btc-basis-trader-a1b2c3              ║
║  Domain:    crypto                               ║
║  Wallet:    OWS (real keys)                      ║
║                                                  ║
║  Addresses:                                      ║
║    EVM:     0x1234...5678                         ║
║    Solana:  7Kp2...9xYz                          ║
║    Bitcoin: bc1q...mn0p                           ║
║                                                  ║
║  Strategy:                                       ║
║    Spread:          0.5%                          ║
║    Position size:   10%                           ║
║    Stop loss:       3%                            ║
║    Entry:           BUY when RSI < 30             ║
║    Success:         Win rate > 60%                ║
║                                                  ║
║  Capabilities:     12 (8 read, 4 write)          ║
║  Skills:           elsa:trading, bankr:bankr      ║
║  Autoresearch:     enabled                        ║
║  Health endpoint:  --health-port 8080             ║
║  Deployment:       Dockerfile ready               ║
╚══════════════════════════════════════════════════╝
```

The card shows:
- Agent name, ID, domain
- Wallet provider (OWS vs simulated) and addresses per chain
- Strategy parameters, entry rules, and success criteria
- Capabilities split by read vs write
- Skills from all registries
- Autonomy settings (autoresearch on/off)
- Deployment readiness (health endpoint, Docker)

## 9. Implementation Status Updates

### 9.1 New Modules

| Module | Purpose | Tests |
|---|---|---|
| `src/aether_forge/evolution.py` | `StrategyArtifact`, `SelfEvaluator`, `RuntimeAutoresearch`, `ImprovementProposal` | Included in total |
| `src/aether_forge/wallet.py` | Per-agent vault, chain policy, scoped API key, signing | Included in total |
| `src/aether_forge/strategy_parser.py` | Regex + LLM strategy extraction from English/markdown/JSON | Included in total |
| `src/aether_forge/scaffold_router.py` | Generic config + loader for scaffold strategy routers | Included in total |

### 9.2 Updated Modules

| Module | Change |
|---|---|
| `src/aether_forge/runner.py` | Health endpoint, JSON logging, PID file, crash recovery, tick failure resilience |
| `src/aether_forge/cli.py` | `forge strategy view\|accept\|reject`, `--autoresearch`, `--eval-interval`, `--health-port`, `--json-log`, `--pid-file`, `--strategy-file`, `--wallet`, `--autonomous` |
| `src/aether_forge/generator.py` | `AGENT.md`, `strategy.json`, `strategy-description.md`, `Dockerfile`, `docker-compose.yml`, `wallet.json`, `.env`, `.gitignore`, agent summary card |
| `src/aether_forge/planner.py` | Autoresearch planner initialization safety |
| `src/aether_forge/config.py` | Ollama API key not required for local endpoints |

### 9.3 Deleted Modules

| Module | Reason |
|---|---|
| `src/aether_forge/elsa_router.py` | Replaced by `scaffold_router.py`; trading logic moved to generated scaffolds |

### 9.4 Test Count

| Version | Tests |
|---|---|
| v0.9.0 | 127 |
| v0.10.0 | 159 |
| v0.11.0 | 266 |
| v0.12.0 | 288 |

New tests since v0.11.0: 22 tests covering evolution/autoresearch, wallet provisioning, strategy parsing, scaffold router, deployment infrastructure, and bug fixes.

## 10. Inherited Requirements

All requirements from `v0.11.0` (and transitively from `v0.10.0` through `v0.1.0`) remain in force unless explicitly updated in this document. In particular:

- Continuous agent execution via `forge run` and `AgentRunner` from v0.11.0 is unchanged (extended with deployment features)
- Paper trading with real Binance market data from v0.11.0 is unchanged (now in scaffold, not framework)
- Auto-approve policy gate from v0.11.0 is unchanged
- Multi-provider LLM support from v0.10.0 is unchanged
- SQLite persistent memory from v0.10.0 is unchanged
- Model discovery from v0.10.0 is unchanged
- CI/CD pipeline from v0.10.0 is unchanged
- The open agent economy protocols (ERC-8004, ERC-8126, ERC-8183, x402) from v0.9.0 are unchanged
- The security hardening module from v0.9.0 is unchanged
- The memory model from v0.7.0 is unchanged
- The autoresearch loop mechanics from v0.4.0 are unchanged (extended with runtime autoresearch)
- The core lifecycle, environment model, and governance requirements from earlier versions are unchanged

## 11. Functional Requirements Additions

### Runtime Autoresearch

- The system must support runtime self-improvement via `StrategyArtifact`, `SelfEvaluator`, `RuntimeAutoresearch`, and `ImprovementProposal`
- The `SelfEvaluator` must compute win rate, P&L, and max drawdown from trade history
- `RuntimeAutoresearch` must use the Karpathy keep/discard pattern: evaluate, propose, present, accept/reject
- `ImprovementProposal` must include hypothesis, mutations, rationale, and evidence
- The protected evaluator must prevent the agent from weakening its own success criteria
- Success metrics must be set at generation time and locked against modification by proposals
- `forge strategy view|accept|reject` must manage strategy proposals via CLI
- `--autoresearch` and `--eval-interval` must control runtime self-improvement in `forge run`

### Deployment Infrastructure

- `--health-port` must serve `/health`, `/status`, and `/ticks` HTTP endpoints
- `/health` must return uptime; `/status` must return agent name, tick count, and last status; `/ticks` must return tick statistics
- `--json-log` must write structured JSON log lines (one per event) to the specified file
- `--pid-file` must write the process ID and remove it on clean shutdown
- Crash recovery must restore state from the latest replay file in the replays directory
- The runner must survive individual tick failures and continue to the next tick
- Generated scaffolds must include `Dockerfile` and `docker-compose.yml`

### Provider-Agnostic Architecture

- The framework must not contain provider-specific trading logic
- `scaffold_router.py` must provide a generic config and loader for scaffold routers
- The scaffold router must route by `kind` and `provider` from the capability manifest
- Generated scaffolds must include `src/strategy/` with price feed, momentum, paper trading, and router modules

### OWS Wallet Integration

- `wallet.py` must provision per-agent vaults with `.ows/` directory isolation
- Each agent wallet must have a chain-restriction policy using CAIP-2 identifiers
- The system must create scoped API keys (`ows_key_...`) — the agent must never receive the owner passphrase
- The `.env` file must be auto-gitignored; `wallet.json` must not contain secrets
- `sign_message()` and `sign_and_send()` must use the API key and vault path
- The module must support 9 chain families: EVM, Solana, Bitcoin, Cosmos, Tron, TON, Sui, Filecoin, XRPL
- The module must fall back to simulated addresses when the OWS SDK is not installed

### Strategy File Parsing

- `--strategy-file` must accept English, markdown, or JSON strategy descriptions
- The parser must extract spread, position size, max orders, stop loss, daily loss, rebalance interval, tokens, entry rules, and success metrics via regex
- Optional LLM enhancement must be available when a planner is configured
- Parsed parameters must override defaults in `strategy.json`
- The original strategy file must be saved as `strategy-description.md` in the agent project

### Agent Summary Card

- The CLI must print a summary card after agent generation
- The card must show wallet addresses per chain, strategy parameters, entry rules, success criteria, capabilities (read vs write), deployment readiness, and wallet provider

### Generated Scaffold Improvements

- Generated projects must include `AGENT.md` with comprehensive documentation
- Generated projects must include `strategy.json` with tunable parameters
- Generated projects must include `strategy-description.md` when `--strategy-file` is used
- Generated projects must include `Dockerfile` and `docker-compose.yml` for container deployment
- Generated projects must include `wallet.json`, `.env`, and `.gitignore` when `--wallet` is used
- `--wallet` must enable real OWS wallet provisioning (or simulated fallback)
- `--autonomous` must enable autoresearch by default

## 12. Non-Functional Requirements Additions

- Health endpoint must respond within 100ms for all three paths
- Health endpoint must not interfere with the tick execution loop (run in a separate thread)
- JSON log writes must be append-only and flushed after each event
- PID file must be removed on SIGINT, SIGTERM, and normal exit
- Strategy parsing regex must complete within 1 second for any reasonable strategy file
- LLM-enhanced parsing must respect the configured planner timeout
- Wallet provisioning must complete within 30 seconds (OWS SDK) or 1 second (simulated fallback)
- Per-agent vault directories must be created with restrictive permissions (owner-only read/write)
- All new modules must maintain the stdlib-only constraint (no new external dependencies)
- Agent summary card must render correctly in terminals with minimum 80 columns

## 13. Open Questions

Inherited from v0.11.0 (all remain open):

- Should Agent Cards (ERC-8004) be auto-generated on every artifact build, or only on explicit request?
- What is the minimum trust score threshold for agent-to-agent job creation?
- Should circuit breaker thresholds be configurable per-agent, or global per-environment?
- Should audit logs support structured export for external SIEM integration in v1?
- Should wallet export require multi-factor confirmation?
- Should `models-list` cache results locally for faster repeated queries?
- Should the SQLite memory store support optional encryption at rest?
- Should provider selection be persisted in the config file after first use (wizard-style setup)?
- What is the upgrade path for SQLite schema changes in future versions?
- Should the framework provide built-in token counting for cost estimation across providers?
- Should Ollama model pulling (`ollama pull`) be integrated into the CLI for convenience?
- What is the right default tick interval for different agent types?
- Should paper trading fills simulate slippage?
- Should the agent remember strategies across restarts (strategy persistence)?
- Should there be a `forge stop` command for graceful remote shutdown?

New in v0.12.0:

- Should runtime autoresearch proposals be auto-accepted after N consecutive improvements?
- Should the health endpoint support authentication (API key, basic auth)?
- Should crash recovery validate replay file integrity before restoring state?
- Should strategy parsing support additional formats (YAML, TOML)?
- Should per-agent vaults support backup/restore for migration between machines?
- Should the agent summary card be exportable as JSON for programmatic consumption?

## 14. Final Recommendation

`Aether Forge` v0.12.0 completes the transition from operational agent platform to self-improving agent system. The key improvements:

1. **Agents now improve themselves** via runtime autoresearch — the Karpathy keep/discard loop runs at runtime, evaluating performance and proposing strategy mutations, with a protected evaluator that prevents the agent from gaming its own metrics
2. **Proper wallet isolation** with per-agent vaults, scoped API keys, and chain-restriction policies means agents can sign real transactions without ever accessing the owner's master keys
3. **Strategy files in plain English** lower the barrier to entry — users describe what they want in natural language, and the framework extracts structured parameters
4. **Deployment-ready infrastructure** with health endpoints, JSON logging, PID files, crash recovery, and Docker support means agents can run as production services
5. **Provider-agnostic architecture** ensures the framework is not coupled to any specific trading API — all provider logic lives in the generated scaffold
6. **288 tests** across 35+ files protect the growing codebase

The correct product posture remains unchanged: spec-first, policy-governed, eval-driven, production-ready. These additions make the system genuinely autonomous within governed bounds: an agent can be generated from a strategy file, provisioned with a real wallet, deployed as a service, and improve its own strategy over time — all without bypassing policy, evaluation, or human approval at critical decision points.

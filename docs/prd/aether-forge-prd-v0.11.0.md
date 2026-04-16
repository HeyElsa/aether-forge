# Aether Forge Product Requirements Document

Version: `v0.11.0`
Status: `Draft`
Date: `2026-04-09`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.10.0.md`
Base PRD: `docs/prd/aether-forge-prd-v0.10.0.md`

Supporting design:

- `docs/plans/2026-04-06-aether-forge-schema-design.md`

## 1. Status

This PRD inherits all unchanged requirements from v0.10.0.

v0.11.0 is a milestone release: the framework can now generate, govern, and continuously run a real LLM-driven trading agent with live market data. Key additions:

- Continuous governed agent loop via `forge run` and `AgentRunner` (new)
- Elsa execution router with three modes: simulated, paper, live (new)
- Paper trading with real Binance market data and simulated P&L tracking (new)
- Generated scaffold improvements: `pyproject.toml` and `main.py` per project (updated)
- Enhanced planning prompts with working set data and action-oriented instructions (updated)
- Planner robustness: code fence stripping and snake_case capability IDs (updated)
- Runtime PAUSED status instead of failure on max_steps exhaustion (updated)
- Auto-approve policy gate for sandbox/paper environments (new)
- Expanded crypto domain detection with 30+ DeFi keywords (updated)
- Walkthrough bug fixes across `forge init`, skills, `forge eval`, and error messages (updated)

## 2. Summary Of Changes

Compared with `v0.10.0`, this version:

1. Added `forge run` command and `AgentRunner` class for continuous governed agent execution with configurable interval, max ticks, memory persistence, and replay writing
2. Added `ElsaExecutionRouter` with three modes: simulated (fake prices + fake orders), paper (real Binance prices + simulated orders with P&L tracking), and live (real x402 API)
3. Generated scaffolds now include `pyproject.toml` and `main.py` for standalone execution
4. Enhanced planning prompts with working set data (not just keys), recent observations, and action-oriented instructions with auto-approve awareness
5. Fixed planner to strip markdown code fences from LLM responses and accept both camelCase and snake_case capability IDs
6. Runtime sessions now PAUSE (not fail) when max_steps exhausted, enabling continuous agents to resume
7. Added `_AutoApproveGate` policy gate that injects approval tokens for sandbox/paper environments
8. Expanded crypto domain detection with 30+ DeFi keywords (defi, staking, aave, compound, lido, yield, swap, etc.)
9. Fixed skills credential handle generation: skills now get `credentialHandleId` and handle declarations for validation
10. Added `forge eval --list` to discover available scenario IDs without running them

## 3. Continuous Agent Execution (New)

The framework now supports continuous, governed agent execution via the `forge run` CLI command and the `AgentRunner` Python class. This enables agents to run indefinitely (or for a bounded number of ticks), maintaining state across iterations.

### 3.1 `forge run` CLI Command

```bash
forge run ./my-agent \
    --interval 30 \
    --max-ticks 100 \
    --environment sandbox \
    --auto-approve \
    --memory-store sqlite \
    --memory-db ./my-agent/memory.db
```

| Flag | Default | Description |
|---|---|---|
| `--interval` | `30` | Seconds between ticks |
| `--max-ticks` | `0` (unlimited) | Maximum number of ticks before stopping |
| `--max-steps` | `20` | Maximum planner steps per tick |
| `--environment` | `sandbox` | Execution environment |
| `--auto-approve` | `false` | Auto-approve side-effecting capabilities (sandbox/paper only) |
| `--memory-store` | `sqlite` | Memory backend (`memory` or `sqlite`) |
| `--memory-db` | `<artifact_dir>/memory.db` | SQLite database path |
| `--replay-dir` | `<artifact_dir>/replays/` | Directory for replay JSON files |

Module: `src/aether_forge/cli.py`

### 3.2 `AgentRunner` Class

The `AgentRunner` class provides programmatic access to the continuous execution loop:

```python
from aether_forge.runner import AgentRunner, RunnerConfig

config = RunnerConfig(
    interval_seconds=30,
    max_ticks=10,
    max_steps_per_tick=20,
    environment="sandbox",
    auto_approve=True,
    persist_memory=True,
    persist_replays=True,
)

runner = AgentRunner(
    artifact_directory="./my-agent",
    config=config,
)

# Blocking: runs until max_ticks or SIGINT/SIGTERM
results = runner.run()

# Or use the tick generator for custom control
for tick_result in runner.tick_generator():
    print(f"Tick {tick_result.tick_number}: {tick_result.session_status}")
    if tick_result.session_status == "failed":
        break
```

Module: `src/aether_forge/runner.py`

### 3.3 `RunnerConfig` Dataclass

| Field | Type | Default | Description |
|---|---|---|---|
| `interval_seconds` | `float` | `30.0` | Pause between ticks |
| `max_ticks` | `int` | `0` | 0 = unlimited |
| `max_steps_per_tick` | `int` | `20` | Planner steps per tick |
| `environment` | `str` | `sandbox` | Execution environment |
| `persist_memory` | `bool` | `True` | Write tick summaries to memory store |
| `persist_replays` | `bool` | `True` | Write replay JSON per tick |
| `replay_directory` | `str | None` | `None` | Override replay output directory |
| `memory_db_path` | `str | None` | `None` | Override SQLite database path |
| `auto_approve` | `bool` | `False` | Auto-approve in sandbox/paper |

### 3.4 `TickResult` Dataclass

Each tick yields a `TickResult` containing:

| Field | Type | Description |
|---|---|---|
| `tick_number` | `int` | Monotonically increasing tick counter |
| `timestamp` | `str` | ISO 8601 UTC timestamp |
| `session_status` | `str` | `complete`, `hold`, `failed`, or `paused` |
| `steps_executed` | `int` | Number of planner steps in this tick |
| `observations` | `list[dict]` | Type and description of observations |
| `pending_approvals` | `list[str]` | Request IDs awaiting human approval |
| `working_set_keys` | `list[str]` | Keys in the persisted working set |

### 3.5 Tick Model

Each tick executes the full governed loop:

```
Load artifacts
  -> Create RuntimeSession with persistent memory + working set
  -> Planner -> Policy Gate -> Execute -> Ledger
  -> Persist working set across ticks
  -> Write tick memory summary
  -> Write replay JSON
```

Working set state (prices, positions, observations) persists across ticks via an in-memory dictionary that survives between sessions. Memory records persist to the configured `MemoryStore` (SQLite by default).

### 3.6 Auto-Approve Behavior

When `auto_approve=True` and the environment is `sandbox` or `paper`:

1. The runner replaces the standard `NativePolicyGate` with `_AutoApproveGate`
2. `_AutoApproveGate` injects a synthetic `approval_token` into action payloads so that side-effecting capabilities (execute-swap, open-perp, etc.) pass the approval check without human intervention
3. All other policy checks (environment tier, notional limits, staleness) still apply
4. If the session enters HOLD with pending approvals, the runner auto-approves and retries (up to 5 times per tick)
5. Auto-approve is never available in `canary` or `production` environments

### 3.7 Replay Writing

When `persist_replays=True`, each tick writes a `tick_NNNN.json` replay file to the replay directory. Replays use the existing `write_session_replay_json` format and can be resumed with `forge resume-replay`.

### 3.8 Signal Handling

`AgentRunner.run()` installs handlers for SIGINT and SIGTERM that set `_running = False`, allowing the current tick to complete before stopping. The interruptible sleep between ticks checks `_running` every 500ms.

### 3.9 Continuous Execution Rules

1. Each tick must run through the full governed pipeline (planner -> policy -> execute -> ledger)
2. Working set state must persist across ticks within a single `AgentRunner` lifetime
3. Memory records must persist across ticks and across restarts (when using SQLite)
4. Auto-approve must only be available in sandbox and paper environments
5. The runner must handle SIGINT/SIGTERM gracefully, completing the current tick
6. Replay files must be written atomically per tick
7. A failed tick must stop the runner (fail-fast); a PAUSED tick is treated as complete

## 4. Elsa Execution Router (New)

The `ElsaExecutionRouter` provides three execution modes for Elsa DeFi capabilities, enabling agents to progress from simulation through paper trading to live execution.

### 4.1 Router Modes

| Mode | Price Source | Order Execution | Payment | Use Case |
|---|---|---|---|---|
| `simulated` | Random walk from seed prices | Instant fill, fake tx hashes | None | Development, unit tests |
| `paper` | Real-time Binance API | Simulated fill with balance tracking | None | Strategy validation with real market data |
| `live` | Elsa x402 API | Real on-chain execution | x402 USDC micropayments | Production trading |

### 4.2 `ElsaRouterConfig` Dataclass

| Field | Type | Default | Description |
|---|---|---|---|
| `mode` | `str` | `simulated` | `simulated`, `paper`, or `live` |
| `wallet_address` | `str | None` | `None` | Wallet address for live x402 payments |
| `price_data` | `dict[str, float]` | `{}` | Seed prices for simulation |
| `order_book` | `list[dict]` | `[]` | Tracked orders |
| `trade_log` | `list[dict]` | `[]` | Trade history |
| `paper_balance_usd` | `float` | `10,000.0` | Starting paper balance |
| `paper_holdings` | `dict[str, float]` | `{}` | Paper token holdings |
| `request_fn` | `Callable | None` | `None` | Injectable HTTP function for testing |
| `binance_request_fn` | `Callable | None` | `None` | Injectable Binance fetcher for testing |

### 4.3 Paper Trading

Paper mode combines real market data with simulated execution:

1. **Price feeds**: Fetches real-time prices from the Binance public API (`/api/v3/ticker/24hr`). Falls back to simulated prices if Binance is unreachable.
2. **Order execution**: Limit orders fill immediately at the limit price. Buy orders deduct from `paper_balance_usd` and add to `paper_holdings`. Sell orders reverse this.
3. **Balance enforcement**: Buy orders are rejected if notional value exceeds available cash. Sell orders are rejected if holdings are insufficient.
4. **P&L tracking**: Portfolio value is computed as cash + sum(holdings * latest price). The trade log records every order creation.
5. **Swap quotes**: Use live Binance prices for accurate quote calculation.

Paper mode is designed for strategy validation: agents make decisions based on real market conditions, but no real money moves.

### 4.4 Simulated Mode

Simulated mode uses random-walk price generation from seed values:

- Prices change by +/- 2% per fetch (uniform random)
- 24h change, volume, and market cap are randomized
- All orders fill instantly with `sim_order_N` IDs
- Swap quotes use simulated prices with 5bps slippage

### 4.5 Live Mode

Live mode calls the real Elsa x402 API at `https://api.heyelsa.ai/v1`:

- Requires a wallet address for x402 USDC micropayments
- Handles HTTP 402 (payment required) responses
- Uses `urllib` (stdlib-only, no SDK dependency)
- Timeout: 15 seconds per request

### 4.6 Supported Endpoints

Both simulated and paper modes handle the following Elsa endpoints:

| Endpoint | Simulated | Paper | Notes |
|---|---|---|---|
| `get-token-price` | Random walk | Binance live | Falls back to simulated on error |
| `search-token` | Mock result | Mock result | |
| `get-swap-quote` | Simulated price | Live price | |
| `execute-swap` | Instant fill | N/A (use limit orders) | |
| `create-limit-order` | Instant fill | Instant fill + P&L | Balance enforcement in paper |
| `get-limit-orders` | Order book list | Order book list | |
| `cancel-limit-order` | Status update | Status update | |
| `get-balances` | N/A | Cash + holdings | Paper-only |
| `get-portfolio` | N/A | Full portfolio value | Paper-only |
| `get-gas-prices` | Mock gas prices | Mock gas prices | |

Module: `src/aether_forge/elsa_router.py`

### 4.7 Execution Router Rules

1. The router must accept both kebab-case (`get-token-price`) and snake_case (`get_token_price`) endpoint names
2. Paper mode must use real Binance prices and fall back to simulated prices on network failure
3. Paper mode must enforce balance constraints (no negative cash, no selling more than held)
4. Live mode must handle HTTP 402 responses and report them as payment-required failures
5. The router must remain stdlib-only (urllib, no external HTTP libraries)
6. Price history and order book must be accessible as properties for inspection

## 5. Generated Scaffold Improvements (Updated)

Generated agent projects now include two additional files for standalone execution.

### 5.1 `pyproject.toml`

Every generated project now includes a `pyproject.toml` with:

- Project name derived from the agent name
- `aether-forge` as a dependency
- Python 3.12+ requirement
- Entry point for direct execution

### 5.2 `main.py`

Every generated project now includes a `main.py` with:

- Imports from `aether_forge`
- Agent loading and runtime session setup
- Configurable planner and execution router
- Command-line argument parsing for quick iteration

### 5.3 Quick Start Flow

With these additions, generated agents can be run immediately:

```bash
forge generate-fast --name "My Agent" --idea "your idea" --output ./my-agent
cd my-agent
pip install -e .
python main.py
```

Or via the new `forge run` command:

```bash
forge run ./my-agent --interval 30 --auto-approve
```

## 6. Planning & Prompting Enhancements (Updated)

### 6.1 Code Fence Stripping

The planner now strips markdown code fences (`` ```json ... ``` ``) from LLM responses before parsing. Many LLMs wrap JSON responses in code blocks even when instructed not to. The planner detects and removes these fences to extract the raw JSON.

### 6.2 Snake_case Capability ID Acceptance

The planner now accepts both camelCase (`getTokenPrice`) and snake_case (`get_token_price`) capability IDs from LLMs. Previously, only the canonical kebab-case IDs were accepted. The planner normalizes all IDs to kebab-case before execution.

### 6.3 Working Set Data in Prompts

Planning prompts now include the full working set data (not just keys) so the LLM can reason about current state:

- Current prices, positions, balances
- Recent observations with type and description
- Action-oriented instructions that tell the LLM what actions are available and how to format responses

### 6.4 Auto-Approve Awareness

When `auto_approve` is active, planning prompts inform the LLM that side-effecting actions will be auto-approved. This allows the LLM to propose actions without hedging about approval requirements.

### 6.5 Recent Observations in Prompts

The planner now injects recent observations (last N from the session) into the planning prompt, giving the LLM context about what happened in previous steps.

Module: `src/aether_forge/prompting.py`, `src/aether_forge/planner.py`

## 7. Runtime PAUSED Status (Updated)

When a `RuntimeSession` exhausts its `max_steps` budget, the session now enters `PAUSED` status instead of `FAILED`. This is critical for continuous agents:

- The `AgentRunner` treats `PAUSED` as `COMPLETE` and proceeds to the next tick
- State is preserved and the working set carries forward
- Memory records from the paused tick are persisted normally
- Replays are written for paused ticks

This change ensures that step-budget exhaustion is a normal operating condition for long-running agents, not an error.

## 8. Crypto Domain Detection (Updated)

The crypto domain detection heuristic now recognizes 30+ DeFi keywords in addition to the original set:

New keywords: `defi`, `staking`, `aave`, `compound`, `lido`, `yield`, `swap`, `uniswap`, `sushiswap`, `pancakeswap`, `curve`, `balancer`, `1inch`, `paraswap`, `dex`, `amm`, `liquidity`, `pool`, `farm`, `harvest`, `vault`, `lending`, `borrowing`, `collateral`, `leverage`, `margin`, `perpetual`, `futures`, `options`, `derivatives`.

This improves auto-detection accuracy so that agents described with DeFi terminology correctly receive crypto capabilities and skills.

## 9. Implementation Status Updates

### 9.1 New Modules

| Module | Purpose | Tests |
|---|---|---|
| `src/aether_forge/runner.py` | `AgentRunner`, `RunnerConfig`, `TickResult`, `_AutoApproveGate` | 8 tests |
| `src/aether_forge/elsa_router.py` | `ElsaExecutionRouter`, paper trading, Binance price feeds | 1 test |
| `tests/test_runner.py` | Runner unit tests | 8 tests |
| `tests/test_paper_trading.py` | Paper trading tests | 1 test |

### 9.2 Updated Modules

| Module | Change |
|---|---|
| `src/aether_forge/cli.py` | Added `forge run`, `forge eval --list`, `forge init` parent dir fix, better error messages |
| `src/aether_forge/planner.py` | Code fence stripping, snake_case capability ID normalization |
| `src/aether_forge/prompting.py` | Working set data, recent observations, action-oriented instructions, auto-approve awareness |
| `src/aether_forge/runtime.py` | `PAUSED` status on max_steps exhaustion instead of `FAILED` |
| `src/aether_forge/generator.py` | `pyproject.toml` and `main.py` generation, expanded crypto keywords, credential handle fixes |
| `src/aether_forge/skills.py` | `credentialHandleId` and handle declarations for skill capabilities |
| `src/aether_forge/config.py` | Crypto domain keyword expansion |

### 9.3 Test Count

| Version | Tests |
|---|---|
| v0.9.0 | 127 |
| v0.10.0 | 159 |
| v0.11.0 | 266 |

New tests since v0.10.0: 107 tests across 15 new and updated test files. Major additions include runner tests (8), paper trading tests (1), real agent tests (3), doctor tests (8), security adversarial tests (26), protocol enhancement tests (8), usage tests (10), and expanded coverage across existing modules.

## 10. Inherited Requirements

All requirements from `v0.10.0` (and transitively from `v0.9.0` through `v0.1.0`) remain in force unless explicitly updated in this document. In particular:

- Multi-provider LLM support from v0.10.0 is unchanged
- SQLite persistent memory from v0.10.0 is unchanged; the runner uses it by default
- Model discovery from v0.10.0 is unchanged
- CI/CD pipeline from v0.10.0 is unchanged
- The open agent economy protocols (ERC-8004, ERC-8126, ERC-8183, x402) from v0.9.0 are unchanged
- The security hardening module from v0.9.0 is unchanged
- The OWS wallet support from v0.9.0 is unchanged
- The memory model from v0.7.0 is unchanged
- The autoresearch loop mechanics from v0.4.0 are unchanged
- The core lifecycle, environment model, and governance requirements from earlier versions are unchanged

## 11. Functional Requirements Additions

### Continuous Agent Execution

- The system must support continuous governed agent execution via `forge run` and the `AgentRunner` class
- Each tick must execute the full planner -> policy -> execute -> ledger loop
- Working set state must persist across ticks within a runner lifetime
- Memory records must persist across ticks and across restarts when using SQLite
- The runner must handle SIGINT/SIGTERM gracefully, completing the current tick before stopping
- Replay files must be written per tick when configured
- A failed tick must stop the runner; a paused tick must be treated as complete

### Auto-Approve Policy Gate

- The system must provide an auto-approve policy gate for sandbox and paper environments
- Auto-approve must inject approval tokens so side-effecting capabilities pass without human intervention
- Auto-approve must not bypass other policy checks (environment tier, notional limits, staleness)
- Auto-approve must never be available in canary or production environments

### Paper Trading

- The system must support paper trading with real Binance market data and simulated order execution
- Paper trading must enforce balance constraints (no spending more than available cash, no selling more than held)
- Paper trading must track P&L across orders
- Paper trading must fall back to simulated prices when Binance is unreachable
- Paper trading must use the same policy governance as all other execution modes

### Generated Scaffold Improvements

- Generated projects must include a `pyproject.toml` with correct metadata and dependency on `aether-forge`
- Generated projects must include a `main.py` entry point for standalone execution
- Generated projects must be immediately runnable after `pip install -e .`

### Planning Robustness

- The planner must strip markdown code fences from LLM responses before parsing
- The planner must accept snake_case, camelCase, and kebab-case capability IDs and normalize to kebab-case
- Planning prompts must include working set data, recent observations, and available actions
- Planning prompts must indicate when auto-approve is active

### Runtime Resilience

- Runtime sessions must enter PAUSED (not FAILED) status when max_steps is exhausted
- PAUSED sessions must preserve state for continuation

### Crypto Domain Detection

- The crypto domain detection heuristic must recognize 30+ DeFi keywords including staking, yield, swap, and protocol names
- Detection must be case-insensitive

### Skills Validation

- Skill capabilities must include `credentialHandleId` and handle declarations
- Skills must pass validation with the credential handle requirements

### Eval Discovery

- `forge eval --list` must list available scenario IDs without executing them

## 12. Non-Functional Requirements Additions

- Agent ticks must complete within a configurable timeout (default: no timeout, bounded by max_steps)
- Paper trading Binance price fetches must timeout after 10 seconds
- Live Elsa API calls must timeout after 15 seconds
- Interruptible sleep must check the running flag every 500ms
- Replay files must be written synchronously to avoid data loss on crash
- All new modules must maintain the stdlib-only constraint (no new external dependencies)

## 13. Open Questions

Inherited from v0.10.0 (all remain open):

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

New in v0.11.0:

- What is the right default tick interval for different agent types?
- Should paper trading fills simulate slippage?
- Should the agent remember strategies across restarts (strategy persistence)?
- Should there be a `forge stop` command for graceful remote shutdown?

## 14. Final Recommendation

`Aether Forge` v0.11.0 marks the transition from development tool to operational agent platform. The key improvements:

1. **Agents now run continuously** via `forge run`, with governed ticks, memory persistence, and replay writing — the framework can keep an agent alive indefinitely
2. **Paper trading with real market data** lets agents validate strategies against live Binance prices without risking real capital
3. **Three execution modes** (simulated -> paper -> live) provide a clear progression from development through validation to production
4. **Enhanced planning** with working set data, observations, and code fence handling makes LLM-driven agents more reliable
5. **Auto-approve** removes the human bottleneck in sandbox/paper, enabling fully autonomous agent loops for testing
6. **266 tests** across 34 files protect the growing codebase

The correct product posture remains unchanged: spec-first, policy-governed, eval-driven, production-ready. These additions make that posture operational: an agent can now be generated, validated, evaluated, and run continuously with real market data — all within the governed framework.

# Aether Forge

[![CI](https://github.com/HeyElsa/aether-forge/actions/workflows/ci.yml/badge.svg)](https://github.com/HeyElsa/aether-forge/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![ERC-8004](https://img.shields.io/badge/ERC--8004-Base%20mainnet-green)](https://basescan.org/address/0x8004A169FB4a3325136EB29fA0ceB6D2e539a432)

Spec-first agent builder framework. **Idea to governed, testable, production-capable agent in one CLI.**

```
$ forge generate-fast --name "BTC Basis Trader" \
    --idea "delta-neutral BTC basis capture on Binance" \
    --output ./my-agent --skills elsa:trading
```

---

## Table of Contents

- [Why](#why)
- [Install](#install)
- [Quick Start](#quick-start)
- [What Every Agent Includes](#what-every-agent-includes)
- [Architecture](#architecture)
- [Memory Architecture](#memory-architecture)
- [Tools & MCP](#tools--mcp-model-context-protocol)
- [Artifact System](#artifact-system)
- [Skills](#skills)
- [Wallet](#wallet)
- [Security](#security)
- [Agent Registry & Discovery](#agent-registry--discovery)
- [Open Agent Economy](#open-agent-economy)
- [Documentation](#documentation)
- [Contributing](CONTRIBUTING.md)
- [Security Policy](SECURITY.md)
- [Changelog](CHANGELOG.md)

---

## ⚠️ Disclaimer

Aether Forge is **early-stage software** (`v0.1.0`, pre-1.0). It moves real
money on Base mainnet through autonomous LLM-driven agents. Use at your own
risk:

- **Software is provided AS-IS without warranty** of any kind. See [LICENSE](LICENSE) (MIT).
- **You are solely responsible** for any funds loaded into agent wallets,
  any transactions those agents sign, and any losses incurred from bugs,
  LLM hallucinations, market events, exploits, or your own configuration.
- **Always test in `--mode paper` first** with simulated orders. Set
  conservative `x402_budget` caps. Use the kill switch (`forge halt .`).
- **This is NOT financial advice**, NOT a regulated service, NOT an audited
  smart contract framework. We make no guarantees about correctness,
  security, profitability, or fitness for any purpose.
- **Agent decisions are non-deterministic** — the same strategy.md against
  the same market data can produce different actions across LLM providers
  and even between runs.
- **For production use**: drain wallets between sessions, run a
  `forge security-check --harden` audit, monitor `/ready` and
  `/metrics`, and have a rollback plan.

If you spot a security vulnerability, email **ask@heyelsa.ai** — do NOT
open a public issue. See [SECURITY.md](SECURITY.md).

---

## Why

Building autonomous agents today means scattered configs, no policy enforcement, untested deployments, and zero auditability. Moving to production is a leap of faith.

Aether Forge gives every agent a governed lifecycle: typed specs, policy-checked execution, scenario-driven evaluation, and evidence-backed promotion from sandbox to production.

---

## Install

```bash
# Install from GitHub (not yet published to PyPI)
pip install 'aether-forge[all] @ git+https://github.com/HeyElsa/aether-forge.git'

# Or clone and install locally
git clone https://github.com/HeyElsa/aether-forge.git
cd aether-forge
pip install -e '.[all]'
```

Once published to PyPI, you'll also be able to:

```bash
# Production agents — wallet + long-term memory + encrypted backups
pip install 'aether-forge[all]'

# Or pick extras individually
pip install 'aether-forge[wallet]'      # Real OWS wallets across 9 chains
pip install 'aether-forge[knowledge]'   # MemPalace long-term memory layer
pip install 'aether-forge[security]'    # cryptography for encrypted backups
pip install aether-forge                # Core only — heuristic planner, no extras
```

Requires Python 3.12+. Single core dependency (`jsonschema`). Verify the install with:

```bash
forge doctor
# [  ok] Python version: Python 3.12.13 (ok)
# [  ok] jsonschema: jsonschema 4.26.0
# [  ok] OWS SDK: open-wallet-standard installed
# [  ok] cryptography: cryptography 46.0.7 (encrypted backups available)
# [  ok] Ollama: Connected (3 models)
# [  ok] OpenRouter: Connected (350 models)
# [  ok] Memory store (SQLite): Layer 3 round-trip ok (write + read)
# [  ok] Knowledge layer (MemPalace): mempalace 3.1.0 — KG + semantic round-trip ok
#
#   Healthy — 8/8 ok, 0 skipped, 0 failed
```

Every check is a functional round-trip, not just an import test. The doctor verifies the runtime stack the agent needs — Python, validators, wallets, LLM providers, both memory layers, encrypted backups — and prints a one-line verdict at the bottom.

---

## Quick Start

### 1. Generate an agent

```bash
# Fast mode — instant scaffold. Auto-detects the best LLM planner on your
# machine (Ollama → Anthropic → OpenAI → Gemini → OpenRouter → heuristic)
# and bakes it into the generated agent's aether-forge.json. No flags needed.
forge generate-fast --name "My Agent" --idea "your idea" --output ./my-agent
# [planner] auto-detected: mode=ollama model=gemma4:latest baseUrl=http://localhost:11434

# Slow mode — autoresearch refinement
forge generate-slow --name "My Agent" --idea "your idea" --output ./my-agent --max-iterations 5

# With skills from registries
forge generate-fast --name "DeFi Bot" --idea "yield monitor" --output ./bot \
    --skills elsa:portfolio elsa:trading bankr:bankr

# With real OWS wallet and autonomous mode
forge generate-fast --name "DeFi Bot" --idea "yield monitor" --output ./bot \
    --wallet --autonomous

# With a strategy file (English, markdown, or JSON)
forge generate-fast --name "Spread Trader" --idea "basis capture" --output ./bot \
    --strategy-file ./my-strategy.md

# Force a specific LLM instead of auto-detect
forge generate-fast --name "My Agent" --idea "your idea" --output ./my-agent \
    --planner-mode anthropic --planner-model claude-opus-4-6 \
    --planner-api-key-env ANTHROPIC_API_KEY
```

The auto-detected planner block lands in `./my-agent/aether-forge.json`, so anyone running the agent later — Docker, CI, a teammate — gets the same model with no flags and no JSON edits.

### 2. Validate

```bash
forge validate ./my-agent
# Validated 5 artifacts in ./my-agent
```

### 3. Evaluate

```bash
forge eval-pack ./my-agent
# Scenario pack: total=2 matched=2 pass=1 hold=1 fail=0
```

### 4. Run continuously

```bash
forge run ./my-agent --interval 30 --auto-approve --environment sandbox
# BTC Basis Trader
# Environment: sandbox | Interval: 30s | Ctrl+C to stop
# [  ok] Tick 1: complete (5 steps)
# [  ok] Tick 2: complete (3 steps)

# With runtime self-improvement
forge run ./my-agent --autoresearch --eval-interval 6 --auto-approve

# With deployment infrastructure
forge run ./my-agent --health-port 8080 --json-log ./logs/agent.jsonl --pid-file ./agent.pid
```

### 4b. Manage strategy

```bash
forge strategy view ./my-agent         # Show current parameters + pending proposals
forge strategy accept ./my-agent       # Apply pending improvement proposal
forge strategy reject ./my-agent       # Discard pending improvement proposal
```

### 5. Promote

```bash
forge promote-draft ./my-agent --target paper --approver "ops-team"
# Promotion decision: approved
# Wrote promotion-record.json
```

---

## What Every Agent Includes

```
┌────────────┬────────────────────┬─────────────────────────────────────────────────────────┐
│   Layer    │     Standard       │                      What It Does                       │
├────────────┼────────────────────┼─────────────────────────────────────────────────────────┤
│ Identity   │ ERC-8004           │ Agent Card, on-chain registry, reputation tracking      │
│ Trust      │ ERC-8126           │ 5-tier risk scoring, 4 verification types, ZK proofs    │
│ Commerce   │ ERC-8183           │ Escrowed jobs, evaluator role, settlement lifecycle     │
│ Payments   │ x402               │ HTTP 402 micropayments, 402index.io, budget controls    │
│ Wallet     │ OWS (21 functions) │ Full lifecycle, EIP-712 signing, policies, API keys     │
│ Skills     │ SKILL.md           │ skills.sh + bankr.bot + Elsa x402 + any repo            │
│ DeFi       │ Elsa x402          │ Swaps, perps, staking, airdrops — pay-per-call on Base  │
│ Security   │ Hardened           │ Session keys, circuit breakers, injection detection      │
│ DeFi Safety│ defi_safety        │ tx simulation, slippage, exposure, liquidation health   │
│ Observability│ /metrics + /ready│ Prometheus metrics, deep health, replay debugger        │
│ Runtime    │ Forge Engine       │ Planner → Policy → Execute → Ledger + memory + replay   │
│ Spec       │ JSON Schema        │ 8 artifact types, cross-validation, migration contracts │
│ Eval       │ Scenario Packs     │ Baseline + edge cases, promotion evidence, replays      │
│ Research   │ Autoresearch       │ Baseline-first loop, keep/discard, research record      │
│ Promotion  │ Staged Pipeline    │ Sandbox → Paper → Canary → Production, governed         │
└────────────┴────────────────────┴─────────────────────────────────────────────────────────┘
```

---

## Architecture

### Runtime Loop

Every agent action flows through the same governed pipeline:

```
Planner ──▶ Policy Gate ──▶ Execute ──▶ Step Ledger
   ^                                        │
   └──────── loop (max 20 steps) ───────────┘
```

- **Planner** proposes next steps (heuristic, LLM-driven, or JSON function-call adapter)
- **Policy Gate** evaluates rules: environment, notional limits, wallet chains, approvals, memory sensitivity
- **Execute** runs the capability via the appropriate router (mock, paper, live, OWS wallet)
- **Ledger** records every step for audit, replay, and resumption

Side-effecting capabilities default to **deny** until policy explicitly allows.

### Promotion Pipeline

```
Sandbox ──▶ Paper ──▶ Canary Live ──▶ Production
  eval       eval       eval            eval
  pass       pass       pass            pass
            +policy   +approver       +approver
              ok      +rollout        +rollout
                       limits          limits
```

Each promotion is evidence-backed: scenario results, policy compliance, approver sign-off, rollout limits.

---

## Memory Architecture

Aether Forge agents have **four typed memory layers** with distinct lifetimes and purposes. The LLM reads three of them in the planning prompt on every tick.

```
┌────────────────────────────────────────────────────────────────────┐
│  Layer 4: KnowledgeStore (MemPalace)         long-term, optional   │
│  knowledge/             (Chroma vector store)                       │
│  knowledge/knowledge_graph.db   (SQLite temporal triple store)      │
│  Read by:  prompt's ## Knowledge section if --knowledge             │
│  Written by: runner.record_tick_knowledge() per tick                │
├────────────────────────────────────────────────────────────────────┤
│  Layer 3: SqliteMemoryStore                  durable, per-agent    │
│  memory.db    (typed MemoryRecord rows)                              │
│  Read by:  prompt's ## Memory Context section every tick            │
│  Written by: runner._persist_tick_memory() + memory.write capability │
├────────────────────────────────────────────────────────────────────┤
│  Layer 2: working_set / session_state        in-process, one tick  │
│  session.working_set    { eth_price, momentum, balance, ... }       │
│  Read by:  prompt's ## Runtime State section                        │
│  Written by: capability handlers during the tick                    │
├────────────────────────────────────────────────────────────────────┤
│  Layer 1: replays/                           audit only, forever   │
│  One JSON file per tick: full step ledger, state_before/after       │
│  Read by:  humans (and crash recovery)                              │
└────────────────────────────────────────────────────────────────────┘
```

| Layer | Backend | Lifetime | LLM reads it? | Purpose |
|---|---|---|---|---|
| **1 — Replays** | JSON files | Forever | No | Audit trail, replay, crash recovery |
| **2 — Working set** | In-process dict | One tick | Yes (`## Runtime State`) | "What's true right now?" |
| **3 — SQLite memory** | `memory.db` | Forever (or `expires_at`) | Yes (`## Memory Context`) | "What did I do and remember?" |
| **4 — KnowledgeStore** | Chroma + SQLite KG | Forever (bitemporal) | Yes (`## Knowledge`) if `--knowledge` | "What have I learned across sessions?" |

**Why all four are needed.** A swing trader's prose strategy file might contain clauses like *"did not stop out in the last hour"*, *"after 10 ticks, evaluate win rate"*, *"if I've seen this regime before, weight my decision toward what worked"*. None of these can be evaluated without memory. Layer 2 alone gets you a stateless reflex agent. Layer 3 adds within-session and cross-restart memory. Layer 4 adds cross-session learning via semantic recall and temporal facts.

**Layer 4 is optional** — if `mempalace` isn't installed (`pip install aether-forge[knowledge]`), the agent runs on Layers 1-3 only and the prompt's `## Knowledge` section is empty.

---

## Tools & MCP (Model Context Protocol)

Aether Forge is an **MCP client**. Generated agents can discover and call tools from any [Model Context Protocol](https://modelcontextprotocol.io) server — local subprocess or remote HTTPS — just by declaring them in `aether-forge.json`. No code changes, no per-server integrations to maintain.

### Supported transports

| Transport | Example |
|---|---|
| **Stdio** | Spawn an MCP server as a subprocess (`npx @mcp/server-filesystem`, `hermes mcp serve`) and talk over stdin/stdout |
| **HTTP** | POST JSON-RPC to a remote MCP endpoint with custom auth headers |

### Declaration

Agents declare their MCP servers in `aether-forge.json`:

```json
{
  "planner": {"mode": "ollama", "model": "gemma4:latest"},
  "mcp_servers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    },
    "hermes": {
      "command": "hermes",
      "args": ["mcp", "serve"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GH_TOKEN}"},
      "tools": {"include": ["list_issues", "create_issue"]}
    },
    "internal": {
      "url": "https://mcp.example.com/mcp",
      "headers": {"Authorization": "Bearer ${API_KEY}"}
    }
  }
}
```

### Tool filtering

Per-server `include`/`exclude` whitelists scope an agent to exactly the tools it needs. Filtered tools are invisible to the planner — the LLM never learns they exist.

### Runtime flow

1. `forge run` reads the `mcp_servers:` block and threads it into `StrategyConfig`
2. The generated scaffold's execution router builds one `McpDataSource` per declared server
3. On first tool lookup, the source lazily connects: spawns the server (or opens the HTTP connection), runs `initialize` + `tools/list`, caches the tool descriptors
4. The planner proposes a capability → DataRouter dispatches to the right `McpDataSource` → the client emits a `tools/call` JSON-RPC request → result flows back into the agent's working set
5. Tool results land in the four-layer memory system naturally (replay audit, working set, SQLite memory, optional knowledge layer)

### Pre-flight verification

```bash
forge doctor
# [  ok] Config file: Valid: ./aether-forge.json
# [  ok] MCP server [filesystem]: 14 tools available (stdio)
# [  ok] MCP server [hermes]: 10 tools available (stdio)
#
#   Healthy — 10/10 ok, 0 skipped, 0 failed
```

The doctor spawns each declared MCP server, runs the handshake + tool discovery, reports tool counts, and cleans up. Failures are marked optional (don't flip verdict to UNHEALTHY).

### Security

- **Stdio subprocess hardening**: when Aether Forge spawns an MCP server, it passes only a safe baseline env (`PATH`, `HOME`, `USER`, `SHELL`, `LANG`, `LC_ALL`, `TERM`) plus whatever is explicitly declared in the server's `env:` block. The parent shell's secrets never leak to subprocess code.
- **Policy gate still applies**: MCP tool calls flow through the same policy gate as every other side-effecting capability. The agent's `policy-bundle.json` decides which tools require approval, which environments can invoke them, etc.
- **Halt-file kill switch applies**: `forge halt .` blocks MCP tool calls alongside x402 payments and every other outbound side effect.

### What's not yet supported

- **Aether Forge as an MCP server** (`forge mcp serve`) — planned but not shipped. Today agents can *consume* MCP servers but not expose their own capabilities as MCP tools to external clients.
- **MCP resources, prompts, sampling** — only `tools/list` + `tools/call` are implemented.
- **Streaming HTTP (SSE)** — HTTP transport does plain request/response only.

See [`docs/mcp.md`](./docs/mcp.md) for the full user guide including the Hermes Agent messaging bridge example, programmatic API, and troubleshooting.

---

## Artifact System

Every agent is defined by typed, versioned, machine-validatable JSON artifacts:

| Artifact | Required | Purpose |
|----------|:--------:|---------|
| `agent-spec.json` | Yes | Agent contract — objective, capabilities, eval criteria |
| `capability-manifest.json` | Yes | Declared capabilities, credential handles, effect semantics |
| `policy-bundle.json` | Yes | Safety rules — notional limits, wallet chains, approvals |
| `scenario-pack.json` | Yes | Test scenarios with expected outcomes |
| `scaffold.manifest.json` | Yes | Project structure, ownership zones |
| `research-record.json` | | Slow-mode iteration ledger and findings |
| `promotion-record.json` | | Evidence-backed promotion decision |
| `memory-record.json` | | Typed persistent memory records |

---

## Skills

Three registries built in. All use the open [SKILL.md](https://agentskills.io) standard.

| Registry | Source Format | Focus |
|----------|-------------|-------|
| [skills.sh](https://skills.sh) | `owner/repo` | General-purpose (91K+ skills) |
| [bankr.bot](https://skills.bankr.bot) | `bankr:skill-name` | Crypto/DeFi (~31 skills) |
| [Elsa x402](https://x402.heyelsa.ai) | `elsa:name` / `elsa:category` / `elsa:all` | 21 pay-per-call DeFi endpoints |

```bash
# Search skills
forge skills-search "trading"

# Add to existing project
forge skills-add elsa:trading --project ./my-agent
forge skills-add bankr:bankr --project ./my-agent

# List Elsa endpoints
forge elsa-list
forge elsa-list --category perpetuals
```

Skills auto-map to forge capabilities with correct `kind`, `riskLevel`, `effectSemantics`, and `requiredApproval`. Side-effecting skills (execute-swap, open-perp) require policy approval.

---

## Wallet

Full [Open Wallet Standard](https://docs.openwallet.sh) support — 21 SDK functions across 10 chain families.

```bash
forge wallet-create --name agent-wallet
forge wallet-list
forge wallet-account --name agent-wallet --chain evm
forge wallet-sign-message --name agent-wallet --chain evm --message "hello"
forge wallet-sign-tx --name agent-wallet --chain evm --tx-hex 0x...
forge wallet-send-tx --name agent-wallet --chain evm --tx-hex 0x... --rpc-url https://...
forge wallet-import --name imported --mnemonic "word1 word2 ..."
forge wallet-export --name agent-wallet
forge wallet-delete --name old-wallet
```

Supported chains: EVM, Solana, Bitcoin, Cosmos, Tron, TON, Sui, XRPL, Filecoin, Spark.

### Per-Agent Wallet Provisioning

When using `--wallet` with `forge generate-fast`, each agent gets:

- **Per-agent vault** (`.ows/` directory) — wallets, policies, and keys isolated per agent
- **Chain-restriction policy** — CAIP-2 chain IDs restrict which chains the agent can sign on
- **Scoped API key** (`ows_key_...`) — agent never gets the owner passphrase
- **9 chain families** — EVM, Solana, Bitcoin, Cosmos, Tron, TON, Sui, Filecoin, XRPL
- **Simulated fallback** — when OWS SDK is not installed, generates simulated addresses

Generated wallet files:

| File | Contains | Git-committed |
|------|----------|:-------------:|
| `wallet.json` | Addresses, policy ID, key ID, vault path | Yes |
| `.env` | `OWS_API_KEY=ows_key_...` | No |
| `.ows/` | Encrypted vault data | No |

---

## Security

Defense-in-depth for autonomous agents:

- **Session Key Policies** — scoped keys with contract/chain allowlists, per-tx and per-day spending caps, auto-expiry
- **Budget Circuit Breakers** — track spending velocity, auto-pause if it exceeds 3x rolling average
- **Prompt Injection Detection** — 12 compiled patterns covering role impersonation, jailbreaks, delimiter injection, hidden content, base64 payloads, zero-width unicode
- **Rate Limiting** — token-bucket per operation type
- **Audit Log** — append-only log for every wallet sign, x402 payment, and job creation
- **Environment Tiers** — sandbox (permissive) to production (strictest) with tiered defaults
- **Anti-impersonation** — two-layer attestation (self-attestation via EIP-712 + framework attestor wallet) prevents copycats from claiming to be Aether Forge agents on the public ERC-8004 registry. See [`ATTESTOR.md`](./ATTESTOR.md) for the full threat model.

---

## Agent Registry & Discovery

Every agent created through Aether Forge is tracked in a local SQLite registry at `~/.aether-forge/agents.db`. Registration is automatic at generation time (opt-out via `--no-registry`).

```bash
forge agent-list                    # List all my agents
forge agent-info <id>               # Show full details
forge agent-remove <id>             # Archive (soft-delete)
```

### On-chain registration (ERC-8004 on Base mainnet)

Agents can be published to the [ERC-8004](https://eips.ethereum.org/EIPS/eip-8004) IdentityRegistry on Base mainnet (`0x8004A169FB4a3325136EB29fA0ceB6D2e539a432`, 61k+ agents) so other agents and users can discover them:

```bash
forge agent-register <id>           # Build unsigned registration tx
forge agent-register <id> --testnet # Use Base Sepolia instead
```

Each registered agent is an NFT with a metadata URI pointing to its capability manifest on IPFS.

### Inter-agent communication (A2A protocol)

Agents communicate via [Google's A2A protocol](https://github.com/google/A2A) (JSON-RPC 2.0 over HTTP). Each running agent exposes an Agent Card at `/.well-known/a2a-card` and accepts tasks from other agents.

```bash
forge agent-send http://peer:8090 --capability get-token-price --payload '{"token":"ETH"}'
```

### Trust tiers

Discovered agents are classified by their attestation level:

| Tier | Meaning |
|---|---|
| **Verified** | Framework attestor signed it — genuine Aether Forge agent |
| **Self-attested** | Agent's wallet signed it — owner is authentic |
| **Unverified** | Just metadata tags — no cryptographic proof |

---

## Open Agent Economy

Every forge agent participates in the on-chain agent economy:

**ERC-8004** — Register your agent with an Agent Card. Discover other agents. Build reputation through feedback and validation. Deployed on Base mainnet + 20 other chains.

**ERC-8126** — Assess trustworthiness before transacting. Four verification types (smart contract, staking, web app, wallet). Five risk tiers from low to critical.

**ERC-8183** — Create jobs with escrowed payment. Three roles: client, provider, evaluator. Full lifecycle from open to completed/rejected with on-chain settlement.

**x402** — Pay for API calls with USDC on Base. No API keys, no accounts. Budget-controlled with automatic 402 payment flow. **Bidirectional**: agents can both send and receive payments.

**A2A** — Agent-to-agent collaboration via Google's open protocol. Complements MCP (tool use) with agent delegation, task lifecycle, and streaming.

### Agent-to-Agent Payments

Agents can pay each other for capabilities using three channels, all on Base mainnet:

| Channel | Use case | Status |
|---|---|---|
| **x402 pay-per-call** | Agent B gates capabilities behind a price. Agent A pays per request via EIP-3009. | ✅ Shipped (client + server) |
| **Direct USDC transfer** | One-shot transfer for tips, bounties, flat fees | ✅ Wired end-to-end (signs + broadcasts) |
| **ERC-8183 escrow** | Complex jobs with evaluator sign-off | ⚠️ Tx builder ready, contract not yet deployed |

Agent B configures paid capabilities:

```python
from aether_forge.x402_server import X402PaymentGate, build_paid_task_handler

gate = X402PaymentGate(
    wallet_address="0xAgentB...",
    prices={"premium-analysis": 0.005, "basic-info": 0.0},
)
task_handler = build_paid_task_handler(gate, capability_handlers)
```

When Agent A calls a paid capability without payment, Agent B returns `auth-required` with the price and payment address. Agent A pays, retries, and gets the result.

#### Direct USDC transfers (policy-gated)

Agents can directly transfer USDC to other addresses, but only when the agent's `policy-bundle.json` explicitly opts in (default: deny):

```json
{
  "agentPayments": {
    "directTransferEnabled": true,
    "maxPerTransferUsd": 0.10,
    "allowedRecipients": ["0xPeerAgent..."],
    "allowedChains": ["base"]
  }
}
```

```python
from aether_forge.agent_payments import PaymentRequest, execute_payment

result = execute_payment(agent_dir, PaymentRequest(
    method="transfer", budget_usd=0.001,
    pay_to="0xPeerAgent...", chain="base",
))
print(result.tx_hash)  # → real Base mainnet tx hash
```

See `examples/two-agent-marketplace/` for a working end-to-end demo (buyer agent pays oracle agent for ETH price data, with a live terminal dashboard).

---

## CLI Reference

| Category | Commands |
|----------|----------|
| **Create** | `generate-fast`, `generate-slow` |
| **Verify** | `validate`, `eval`, `eval-pack`, `artifact-compat`, `artifact-migration-plan` |
| **Run** | `run`, `scaffold-run`, `resume-replay`, `scaffold-policy-sync`, `scaffold-live-status` |
| **Strategy** | `strategy view`, `strategy accept`, `strategy reject` |
| **Agents** | `agent-list`, `agent-info`, `agent-remove`, `agent-send`, `agent-register`, `agent-discover` |
| **Debug** | `replays`, `replay-show` |
| **Ship** | `promote-draft` |
| **Skills** | `skills-search`, `skills-add`, `elsa-list` |
| **Models** | `models-list` |
| **Wallet** | `wallet-create`, `wallet-list`, `wallet-info`, `wallet-account`, `wallet-sign-message`, `wallet-sign-tx`, `wallet-send-tx`, `wallet-import`, `wallet-delete`, `wallet-export`, `wallet-backup`, `wallet-restore` |
| **Payments** | `x402-call`, `halt`, `resume` |
| **Security** | `security-check` |
| **Diagnostics** | `doctor`, `config-validate`, `init`, `completions` |

---

## Project Structure

```
src/aether_forge/
  cli.py                 40+ CLI commands · planner auto-detect · doctor verdict
  generator.py           Fast-mode artifact generation · planner config baked into agent
  slow_generate.py       Slow-mode autoresearch loop
  runtime.py             Session orchestration · memory layer 2/3 read-into-prompt
  runner.py              AgentRunner continuous loop · health/JSON-log/PID/replays · knowledge layer hookup
  scaffold_router.py     Generic scaffold strategy loader · StrategyConfig (mode + chain)
  evolution.py           Runtime autoresearch: self-eval, proposals, keep/discard
  wallet.py              Per-agent OWS vault, scoped API keys, 9 chains
  strategy_parser.py     Regex + LLM strategy extraction from English/markdown/JSON
  data_layer.py          Generic DataRouter: HTTP / x402 / WebSocket / MCP sources, fallback chain
  mcp_client.py          Model Context Protocol client · stdio + HTTP transports
  a2a_server.py          A2A (Agent-to-Agent) server · Agent Card + JSON-RPC task handling
  a2a_client.py          A2A client wrapping a2a-sdk for calling other agents
  agent_registry.py      Local SQLite registry at ~/.aether-forge/agents.db
  onchain_registry.py    On-chain ERC-8004 registry client for Base mainnet
  attestation.py         EIP-712 self-attestation + framework verification
  agent_payments.py      Three-channel payment dispatcher (x402, transfer, escrow)
  x402_client.py         EIP-3009 signed pay-per-call · persistent budget · halt-file kill switch (CLIENT)
  x402_server.py         Payment gate for agent capabilities · verify + accept payments (SERVER)
  security_hardening.py  Sanitization · file/dir lockdown · AES-256-GCM backups · 8-point preflight
  knowledge.py           Layer 4 wrapper over MemPalace (Chroma + temporal KG)
  storage.py             Layer 3 SqliteMemoryStore
  memory.py              Typed MemoryRecord + MemoryQuery + promotion
  doctor.py              Functional round-trip diagnostics + verdict summary
  planner.py             Heuristic + prompt-driven planners
  policy.py              Native policy gate
  evals.py               Scenario evaluation + promotion
  artifacts.py           8 artifact types, validation
  versioning.py          Compatibility + migration
  crypto.py              5 routers, OWS wallet (21 functions)
  skills.py              3 registries (skills.sh, bankr, Elsa)
  security.py            Session keys, circuit breakers, injection detection
  config.py              Config discovery + planner factory + resolution chain
  prompting.py           Planning prompt assembly · 6 sections (objective, env, caps, runtime, memory, knowledge)
  models.py              Anthropic + Gemini + OpenAI-compatible models + discovery
  scaffold.py            Live adapter loading
  adapters/function_call.py  JSON function-call translator (for structured-output LLMs)
  protocols/
    erc8004.py           Agent identity + registry
    erc8126.py           Trust assessment + verification
    erc8183.py           Agentic commerce + jobs
    x402.py              HTTP 402 micropayments

demo.sh                  Canonical 10-section team walk-through (LLM-driven swing trader)
schemas/                 23 JSON schemas
tests/                   442 tests across 47 files
examples/                Delta-neutral BTC trading agent
docs/prd/                versioned PRDs (v0.1.0 — v0.15.0)
```

---

## Configuration

Aether Forge can be configured via CLI flags, environment variables, or a JSON config file.

### Config file

Place an `aether-forge.json` in your artifact directory or working directory:

```json
{
  "planner": {
    "mode": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "apiKeyEnv": "ANTHROPIC_API_KEY"
  },
  "runtime": {
    "cryptoRouter": "mock"
  },
  "mcp_servers": {
    "hermes": {
      "command": "hermes",
      "args": ["mcp", "serve"]
    }
  }
}
```

The `mcp_servers:` block is optional — declare one entry per [Model Context Protocol](https://modelcontextprotocol.io) server you want the agent to discover tools from. See [Tools & MCP](#tools--mcp-model-context-protocol) for the full feature surface and [`docs/mcp.md`](./docs/mcp.md) for examples.

### LLM Provider Setup

**Aether Forge agents are LLM-driven by default.** `forge generate-fast` auto-detects the best planner on the host machine and bakes the choice into the generated agent's `aether-forge.json`. The probe order is:

1. **Local Ollama** at `http://localhost:11434` — preferred when present (free, fast, no key, no network). Auto-picks a Gemma model if one is pulled.
2. **`ANTHROPIC_API_KEY`** → Claude Sonnet 4.5
3. **`OPENAI_API_KEY`** → GPT-4o
4. **`GOOGLE_API_KEY` / `GEMINI_API_KEY`** → Gemini 2.5 Flash
5. **`OPENROUTER_API_KEY`** → Claude Sonnet 4.5 via OpenRouter
6. **`heuristic`** fallback — labeled, not silent. Only used when nothing above is available.

The auto-detected choice is logged at generation time:

```
[planner] auto-detected: mode=ollama model=gemma4:latest baseUrl=http://localhost:11434
```

The full provider table:

| Mode | Provider | Base URL (auto-configured) |
|------|----------|---------------------------|
| `anthropic` | Claude (native API) | `https://api.anthropic.com` |
| `gemini` | Google Gemini (native API) | `https://generativelanguage.googleapis.com` |
| `openai` | OpenAI | `https://api.openai.com/v1` |
| `openrouter` | OpenRouter (any model) | `https://openrouter.ai/api/v1` |
| `ollama` | Ollama (local) | `http://localhost:11434/v1` |
| `openai-compatible` | Any OpenAI-compatible endpoint | User-configured |
| `function-call` | JSON function-call format (for models fine-tuned for structured tool use) via any OpenAI-compatible endpoint | User-configured |
| `heuristic` | Built-in rule-based (no LLM) | N/A |

```bash
# Claude
forge generate-slow --name "My Agent" --idea "your idea" --output ./agent \
    --planner-mode anthropic --planner-model claude-sonnet-4-20250514 \
    --planner-api-key-env ANTHROPIC_API_KEY

# Gemini
forge generate-slow --name "My Agent" --idea "your idea" --output ./agent \
    --planner-mode gemini --planner-model gemini-2.5-pro \
    --planner-api-key-env GEMINI_API_KEY

# OpenAI
forge generate-slow --name "My Agent" --idea "your idea" --output ./agent \
    --planner-mode openai --planner-model gpt-4o \
    --planner-api-key-env OPENAI_API_KEY

# OpenRouter (access any model)
forge generate-slow --name "My Agent" --idea "your idea" --output ./agent \
    --planner-mode openrouter --planner-model anthropic/claude-sonnet-4 \
    --planner-api-key-env OPENROUTER_API_KEY

# Local Ollama
forge generate-slow --name "My Agent" --idea "your idea" --output ./agent \
    --planner-mode ollama --planner-model llama3
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `AETHER_FORGE_PLANNER_MODE` | Default planner mode |
| `AETHER_FORGE_PLANNER_MODEL` | Default model name |
| `AETHER_FORGE_PLANNER_BASE_URL` | Default base URL |
| `AETHER_FORGE_PLANNER_API_KEY` | API key (direct) |
| `AETHER_FORGE_PLANNER_API_KEY_ENV` | Name of env var holding the API key (indirect) |
| `AETHER_FORGE_CRYPTO_ROUTER` | Default crypto router backend |

### Memory Store

`forge run` writes to a per-agent `memory.db` (Layer 3) by default. Override the path with `--memory-db`:

```bash
forge run ./my-agent --memory-db ./my-agent/memory.db --auto-approve
```

Enable the long-term knowledge layer (Layer 4 — Chroma vectors + temporal KG via MemPalace) with `--knowledge`:

```bash
pip install 'aether-forge[knowledge]'   # installs mempalace
forge run ./my-agent --knowledge --auto-approve
```

The knowledge layer creates `<agent>/knowledge/` with two stores: `chroma.sqlite3` (semantic vectors) and `knowledge_graph.db` (temporal triples). The LLM reads both in the prompt's `## Knowledge` section every tick.

Programmatic use of the SQLite memory store:

```python
from aether_forge import SqliteMemoryStore, evaluate_scenario_pack

store = SqliteMemoryStore("./memory.db")
summary, sessions = evaluate_scenario_pack("./my-agent", memory_store=store)
store.close()
```

See [Memory Architecture](#memory-architecture) above for the full four-layer model.

### Planner config precedence

CLI flags > environment variables > config file > defaults.

---

## Development

```bash
# Clone and setup
git clone <repo-url> && cd aether-forge
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all,dev]"   # all runtime extras + dev tools (pytest, ruff, build, twine)

# Verify the stack
forge doctor

# Run tests
pytest tests/ -v              # 442 tests

# Validate the example
forge validate examples/delta-neutral-btc
forge eval-pack examples/delta-neutral-btc
```

### Team demo

The canonical end-to-end walk-through is `demo.sh` at the repo root. It generates an LLM-driven ETH swing trader from a markdown strategy file, runs 8 paper ticks with autoresearch and the knowledge layer enabled, inspects both memory layers, optionally fires real x402 payments on Base mainnet, and ends with an encrypted wallet backup.

```bash
./demo.sh                                           # Live demo with narration pauses
DEMO_AUTO=1 DEMO_SKIP_LIVE=1 ./demo.sh              # Rehearsal — no money, no prompts
DEMO_PLANNER_MODE=anthropic ./demo.sh               # Override the LLM
```

See `demo.sh` for the full env-var matrix.

---

## Documentation

Full documentation site lives at `docs-site/` (Nextra v4, deployable to Vercel):

```bash
cd docs-site
npm install
npm run dev   # → http://localhost:3000
```

Or browse the markdown directly:
- [End-to-End Tutorial](docs-site/src/content/guides/end-to-end.mdx)
- [Build a Custom Agent](docs-site/src/content/guides/custom-agent.mdx)
- [Writing Strategies](docs-site/src/content/guides/strategy-writing.mdx)
- [CLI Reference](docs-site/src/content/reference/cli.mdx)
- [Configuration Reference](docs-site/src/content/reference/configuration.mdx)

---

## License

MIT. See [LICENSE](LICENSE) for details. Built by [HeyElsa](https://heyelsa.ai).

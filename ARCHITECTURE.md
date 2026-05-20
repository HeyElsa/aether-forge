# Architecture

This document describes how Aether Forge works **inside** — the runtime
contract, the data flow through a single tick, the memory layers, the
extension points, and the safety envelope. The [`README.md`](./README.md)
covers what to use it for; this is for people changing how it works.

## TL;DR

Every Aether Forge agent is a JSON-defined spec running through one
governed loop: **Planner → Policy Gate → Execute → Step Ledger**. The
loop is bounded (max 20 steps per tick), planner-agnostic, and mediated
by typed protocols you can substitute. Memory is layered — replays for
audit, working set for the current tick, SQLite for durable per-agent
state, and an optional `KnowledgeStore` (MemPalace) for cross-session
learning. Side-effecting capabilities default to **deny** until the
`policy-bundle.json` allows them.

```
forge run ./agent
   │
   └─► AgentRunner.run()                                   runner.py:228
         per tick:
           RuntimeSession.run(max_steps=20)                runtime.py:157
             ├─ hydrate memory_context (Layer 3 + 4)
             ├─ planner.propose_plan(session) ──────────►  Planner protocol
             │                                             runtime.py:110
             ├─ for each StepProposal:
             │    ├─ halt-file kill switch?               runtime.py:272
             │    ├─ policy_gate.evaluate_action() ─────► policy.py:72
             │    ├─ execution_router.execute() ────────► ExecutionRouter
             │    │                                         runtime.py:114
             │    ├─ sanitize external output             runtime.py:344
             │    └─ append StepLedgerEntry
             └─ persist working_set, memory writes, replay tick_NNNN.json
```

## Module map

```
src/aether_forge/
├─ Entry / orchestration
│   ├─ cli.py              40+ subcommands · planner auto-detect · doctor verdict
│   ├─ __main__.py         python -m aether_forge → cli.main_cli
│   ├─ runtime.py          RuntimeSession · Planner / ExecutionRouter Protocols
│   ├─ runner.py           AgentRunner: continuous loop, /metrics, /ready, replays
│   ├─ scaffold_router.py  load src/strategy/router.py::build_router(config)
│   └─ config.py           planner factory · plugin entry-point fallback
│
├─ Generation & spec
│   ├─ generator.py        Fast-mode: artifact templates · planner config baked in
│   ├─ slow_generate.py    Slow-mode: autoresearch loop · keep/discard
│   ├─ strategy_parser.py  English/markdown/JSON → typed strategy
│   ├─ artifacts.py        8 artifact types · jsonschema validation
│   ├─ versioning.py       Compatibility + migration contracts
│   ├─ evals.py            Scenario eval · promotion-record builder
│   └─ evolution.py        Runtime self-improvement · weakening guard
│
├─ Memory (4 layers)
│   ├─ memory.py           MemoryRecord · MemoryStore Protocol · sensitivity filter
│   ├─ storage.py          SqliteMemoryStore (Layer 3) · optional Fernet encryption
│   └─ knowledge.py        KnowledgeStore wrapper for MemPalace (Layer 4)
│
├─ LLM
│   ├─ models.py           Anthropic / Gemini / OpenAI-compatible / Static
│   ├─ planner.py          PlanningModel Protocol · PromptDrivenPlanner · HeuristicPlanner
│   ├─ prompting.py        6-section planning prompt · token-budget truncation
│   └─ adapters/
│       └─ function_call.py    JSON function-call → typed StepProposal translation
│
├─ Tools / Data
│   ├─ data_layer.py       DataSource ABC · HTTP / X402 / WebSocket / MCP / Mock · DataRouter
│   ├─ mcp_client.py       MCP stdio + HTTP transports · safe-baseline env · per-RPC timeout
│   ├─ skills.py           skills.sh / bankr / Elsa registries · plugin merge
│   ├─ market_data.py      Binance / CoinGecko venues · MarketDataRouter
│   └─ http.py             Shared HTTP retry primitives
│
├─ A2A
│   ├─ a2a_server.py       /.well-known/a2a-card · JSON-RPC dispatch · rate limit
│   └─ a2a_client.py       a2a-sdk wrapper · sync→async bridge
│
├─ Wallet & payments
│   ├─ wallet.py           Per-agent OWS vault · 9 chains · simulated fallback
│   ├─ crypto/             5 ExecutionRouters (Mock / Public / Paper / Sim / OWS)
│   ├─ x402_client.py      EIP-3009 sign · persistent budget · halt-file
│   ├─ x402_server.py      X402PaymentGate · build_paid_task_handler
│   ├─ agent_payments.py   Three-channel dispatcher · fcntl.flock atomicity
│   └─ live_execution.py   Testnet-safe wrapping · audit log
│
├─ Identity
│   ├─ agent_registry.py   ~/.aether-forge/agents.db (local SQLite)
│   ├─ onchain_registry.py ERC-8004 IdentityRegistry on Base mainnet
│   └─ attestation.py      EIP-712 self-attestation + framework-verified tier
│
├─ Protocols (stdlib-only — no web3 in core)
│   └─ protocols/
│       ├─ erc8004.py      Agent identity + registry
│       ├─ erc8126.py      Trust assessment
│       ├─ erc8183.py      Agentic commerce + jobs (escrow contract pending)
│       └─ x402.py         HTTP 402 micropayments
│
├─ Security
│   ├─ security.py             12 prompt-injection patterns · circuit breaker · rate limit
│   ├─ security_hardening.py   Secret scan · 8-point preflight · AES-256-GCM backups
│   ├─ defi_safety.py          tx simulation · slippage · exposure · liquidation health
│   └─ secrets.py              SecretsProvider Protocol · env / file / chain backends
│
├─ Diagnostics
│   ├─ doctor.py           Functional round-trip checks
│   ├─ usage.py            Token usage tracking + cost estimates
│   └─ exceptions.py       ForgeError hierarchy
│
└─ Plugins
    └─ plugins.py          importlib.metadata entry-point discovery (cached, lazy)
```

## The tick lifecycle (the most important flow)

A tick is one bounded execution cycle inside one session. Inside a tick,
the runtime may execute up to `max_steps` (default 20) steps before
stopping. The runner re-enters with a fresh session each interval.

### 1. Runner schedules a tick — `runner.py:228`

`AgentRunner.run()` loops indefinitely (or until `--max-ticks`):

- Signal handlers for SIGINT/SIGTERM (graceful drain)
- Optional health server on `--health-port` (`/metrics` + `/ready`)
- Per-tick: increments counter, builds a fresh `RuntimeSession`, **carries
  the previous tick's `working_set` forward**, calls `session.run()`, then
  persists working set, memory, and the replay JSON
- Auto-approval retry (sandbox/paper) up to 5 times if any step held
- Circuit breaker: 5 consecutive failed ticks → cooldown
- Bounded history: max 200 ticks held in memory; older ones live on disk
- `interval_seconds` sleep, then the next tick

### 2. Session loop — `runtime.py:157`

`RuntimeSession.run(max_steps=20)`:

```
while status == RUNNING and step_counter < max_steps:
    1. Hydrate memory_context from MemoryStore + KnowledgeStore
    2. proposals = planner.propose_plan(self)        # may be []
       │  On parse failure / model error / empty plan (v0.21.0+):
       │  session.session_state["last_planner_parse_failure"] = {
       │      "kind": "parse-failure"|"parse-exception"|"model-error"|"empty-plan",
       │      "detail": "…", "responsePreview": "≤500 chars…",
       │      "recordedAt": "<iso8601>",
       │  }
       │  then fall through to HeuristicPlanner (labeled, never silent)
    3. for proposal in proposals (FIFO):
         if halt_file_exists: ABORT                  # kill switch
         decision = policy_gate.evaluate_action(...) # 8 checks
         if decision.disposition == "hold":
             create PendingApproval, status = HOLD, break
         result = execution_router.execute(self, proposal, capability)
         sanitized = scan_for_injection(result)      # MCP/A2A/x402 outputs
         working_set[capability_id] = sanitized
         step_ledger.append(StepLedgerEntry(...))
         if proposal.mark_complete: status = COMPLETE
```

The planner is consulted **once per tick** — the proposals are queued and
executed in order. A planner that wants iterative replanning emits a
`REPLAN` step. Provider HTTP calls (Anthropic / OpenAI-compatible / Gemini)
flow through `models._with_retry` since v0.21.0: jittered exponential
backoff on `URLError`, `TimeoutError`, and HTTP `{408, 425, 429, 500, 502,
503, 504}`, honoring `Retry-After` on 429/503; non-transient codes raise
immediately. Opt out per-model with `retry_attempts=1`.

### 3. Planning prompt — `prompting.py`

For LLM-driven planners (`PromptDrivenPlanner`), the prompt is assembled
from six sections in this order:

1. **Objective** — primary goal, summary, non-goals (from `agent-spec.json`)
2. **Environment** — sandbox / paper / canary / production
3. **Capabilities** — filtered by declared capability IDs (one line each)
4. **Runtime State** — working set + last 5 observations + blockers + pending approvals
5. **Memory Context** — live `MemoryQuery` against Layer 3 with sensitivity ceiling
6. **Knowledge** — top-3 semantic recall + current KG facts (Layer 4 if installed)

Token budget is enforced per provider (Claude 200K, GPT-4o 128K, Gemini 1M,
unknown 8K). When over budget, the prompt is truncated **in the middle**
(40% head + 50% tail) — instructions and the most recent state are
preserved.

External tool results (MCP, A2A, x402) are scanned against
12 prompt-injection patterns (`security.py:287`) **before** they enter
the planner's prompt context (`runtime.py:344`).

### 4. Policy gate — `policy.py:72`

`NativePolicyGate.evaluate_action(capability, credentials, env, payload)`
runs eight checks in order:

1. Environment allowance (capability allowed in this env?)
2. Credential handle scope
3. Notional limit (`requested_notional_usd > max_notional_usd` → HOLD)
4. Market data staleness (`market_data_age_ms > stalenessBudgetMs`)
5. Explicit `capability.requiredApproval` flag
6. Env-level approval (side-effecting capability in production?)
7. Wallet chain whitelist
8. Memory sensitivity rule per environment

Returns `PolicyDecision{disposition: allow|hold|deny, rule_matches, severity}`.

## Extension points (Protocols you can substitute)

All extension points are exported from the top-level `aether_forge` module
with full Protocol docstrings. The cookbook example for each lives in
[`docs-site/src/content/guides/extending.mdx`](./docs-site/src/content/guides/extending.mdx).

| Protocol | Defined at | Built-in implementations |
|---|---|---|
| `Planner` | `runtime.py:110` | `HeuristicPlanner`, `PromptDrivenPlanner` |
| `ExecutionRouter` | `runtime.py:114` | `MockCryptoExecutionRouter` and 4 paper/live variants in `crypto/` |
| `PlanningModel` | `planner.py:17` | `AnthropicPlanningModel`, `OpenAICompatiblePlanningModel`, `GeminiPlanningModel`, `StaticPlanningModel` |
| `MemoryStore` | `memory.py:139` | `InMemoryMemoryStore`, `SqliteMemoryStore` |
| `DataSource` (ABC) | `data_layer.py:92` | `HTTPDataSource`, `X402DataSource`, `WebSocketDataSource`, `McpDataSource`, `MockDataSource` |
| `MarketDataVenue` | `market_data.py:23` | `BinanceVenue`, `CoinGeckoVenue`, `MockVenue` |
| `SecretsProvider` | `secrets.py:20` | `EnvSecretsProvider`, `FileSecretsProvider`, `ChainSecretsProvider` |

### Plugin discovery

Third parties extend the framework by declaring entry points in their own
`pyproject.toml`. The framework discovers them lazily via
[`plugins.py`](./src/aether_forge/plugins.py) (cached `importlib.metadata`
lookup). A failing plugin is logged and skipped — it cannot crash the
framework.

```toml
[project.entry-points."aether_forge.planners"]
grok = "my_pkg:build_grok_planner"

[project.entry-points."aether_forge.execution_routers"]
my-router = "my_pkg:build_router"

[project.entry-points."aether_forge.data_sources"]
private-prices = "my_pkg:PrivatePricesSource"

[project.entry-points."aether_forge.skill_registries"]
my-registry = "my_pkg.registries:MY_REGISTRY"
```

## Memory architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  Layer 4: KnowledgeStore (MemPalace)         long-term, optional   │
│  knowledge/  (Chroma vectors)                                       │
│  knowledge/knowledge_graph.db  (SQLite temporal triple store)       │
│  Read by:  prompt's ## Knowledge section if --knowledge             │
│  Written by: runner.record_tick_knowledge() per tick                │
├────────────────────────────────────────────────────────────────────┤
│  Layer 3: SqliteMemoryStore                  durable, per-agent    │
│  memory.db    (typed MemoryRecord rows · 18 columns · WAL mode)     │
│  Read by:  prompt's ## Memory Context section every tick            │
│  Written by: runner._persist_tick_memory + memory.write capability  │
├────────────────────────────────────────────────────────────────────┤
│  Layer 2: working_set / session_state        in-process, one tick  │
│  session.working_set    { eth_price, momentum, balance, … }         │
│  Read by:  prompt's ## Runtime State section                        │
│  Written by: capability handlers during the tick                    │
├────────────────────────────────────────────────────────────────────┤
│  Layer 1: replays/                           audit only, forever   │
│  One JSON file per tick: full step ledger, state_before/after       │
│  Read by:  humans (and crash recovery via resume-replay)            │
└────────────────────────────────────────────────────────────────────┘
```

| Layer | Backend | Lifetime | LLM reads it? | Purpose |
|---|---|---|---|---|
| 1 — Replays | JSON files | Forever | No | Audit trail, replay, crash recovery |
| 2 — Working set | In-process dict | One tick | Yes (`## Runtime State`) | "What's true right now?" |
| 3 — SQLite memory | `memory.db` | Forever or `expires_at` | Yes (`## Memory Context`) | "What did I do and remember?" |
| 4 — KnowledgeStore | Chroma + SQLite KG | Forever (bitemporal) | Yes (`## Knowledge`) if `--knowledge` | "What have I learned across sessions?" |

Sensitivity filtering is enforced **inside** the store
(`memory.py:read_for_environment`) — the runtime trusts the store, not the
caller. Promotion across environments creates a **new** memory_id with
`provenance_refs` pointing back at the source — never an in-place mutation.

## Generation: fast vs slow

**Fast** (`generator.py:204 generate_fast_artifact_set`) — heuristic
crypto-keyword detection (`_looks_like_crypto`) → template synthesis →
optional skill installation → planner config baked into the agent's
`aether-forge.json`. No LLM round-trip.

**Slow** (`slow_generate.py:292 generate_slow_artifact_set`) — Karpathy
autoresearch:

1. Baseline = fast-mode output, scored on `evaluate_scenario_pack`
2. LLM proposes one mutation (set / add / remove via dot-paths) on one of
   four surfaces (spec, policy, scenarios, manifest)
3. Re-evaluate; **keep only if** `matched ≥ baseline AND passes ≥ baseline
   AND strictly better on ≥1 axis` (`_is_improvement`)
4. Diminishing returns: 2 consecutive discards → stop
5. Every iteration appended to `research-record.json` (full audit trail)

Strategy parsing (`strategy_parser.py`) is regex-first; LLM fills gaps.
**Regex wins on conflict** — keeps deterministic core parameters even
when the LLM is unavailable or off-topic.

## Self-improvement at runtime

`evolution.py RuntimeAutoresearch` runs every `eval_interval` ticks
(default 6). If performance falls below thresholds (`min_win_rate`,
`max_drawdown_pct`, `min_profit_per_tick`), the LLM proposes mutations →
`ImprovementProposal` queued → user reviews via
`forge strategy view / accept / reject`.

Hard guard: `_weakens_criteria` (line 423) **refuses** to lower
`success_metrics` thresholds or remove policy rules. Self-improvement
cannot turn into goal-hijacking.

## The 8 typed artifacts

Validated against JSON Schema (Draft 2020-12) via `artifacts.py:119`.
Schemas live in `src/aether_forge/schemas/` (packaged) and `schemas/` (top
level — kept in sync).

| Artifact | Required | Purpose |
|---|:---:|---|
| `agent-spec.json` | ✅ | Objective, success metrics, capabilityRefs, environmentContract, non-goals |
| `capability-manifest.json` | ✅ | kind, riskLevel, allowedEnvironments, requiredApproval, credentialHandles, effectSemantics |
| `policy-bundle.json` | ✅ | Notional caps, wallet chains, approval gates, `agentPayments.*` opt-ins |
| `scenario-pack.json` | ✅ | Test scenarios with `expectedOutcome.stageOutcome` (pass / hold / fail) |
| `scaffold.manifest.json` | ✅ | Project layout, ownership zones, regeneration rules |
| `research-record.json` | | Slow-mode autoresearch ledger |
| `promotion-record.json` | | Evidence-backed promotion decision |
| `memory-record.json` | | Typed persistent memory rows |

## Promotion pipeline

```
sandbox  ─►  paper  ─►  canary-live  ─►  production
  eval        eval         eval             eval
  pass        +policy      +approver        +approver
              ok           +rollout         +rollout
                           limits           limits
```

`evals.py:215 create_promotion_record_artifact` runs the scenario pack,
computes `meets_expectations`, and writes a signed JSON artifact with
default rollout limits (paper $5K/10/hr, canary-live $1K/2/hr, production
zero-default — explicit override required). Decision is deterministic:
`approved` iff every scenario matches its expected stage outcome.

## Three payment channels (one budget)

```
                       agent_payments.execute_payment(req)
                                    │
                  fcntl.flock(x402_state.lock) ─ atomic check + execute
                                    │
       ┌────────────────────────────┼────────────────────────────┐
       ▼                            ▼                            ▼
  x402_client                 USDC transfer            ERC-8183 escrow
  (EIP-3009)                  (build + sign + bcast)   (placeholder —
   ✅ shipped                 ✅ wired                  contract pending)
```

All three channels share one budget (`x402_state.json`, atomic via
`fcntl.flock`). The halt file (`<agent>/halt`) is checked **before** the
budget — `forge halt .` is a true kill switch.

`X402PaymentGate` (server side) verifies inbound payment headers
**structurally** by default; `verify_and_settle_onchain` adds full
EIP-3009 calldata + broadcast for production paths.

## On-chain identity

| Component | What |
|---|---|
| Local registry | `~/.aether-forge/agents.db` — auto-registration on generate (opt-out via `--no-registry`) |
| ERC-8004 | Public IdentityRegistry on Base mainnet (`0x8004A169…`) — opt-in via `forge agent-register` |
| Attestation | EIP-712 typed data signed by the agent's OWS wallet → `tier="self-attested"`. Framework attestor wallet (`FRAMEWORK_ATTESTOR_ADDRESS` in `attestation.py:65`) issues `tier="verified"` — empty by default; see [`ATTESTOR.md`](./ATTESTOR.md) |

## Security envelope

- 12 prompt-injection patterns (`security.py:287`) — role impersonation,
  jailbreaks, delimiters, hidden unicode, base64 (decoded + re-scanned)
- Velocity circuit breaker — tail-3-avg vs overall-avg (3× sandbox / 2× prod)
- Token-bucket rate limits per operation type
- Append-only audit log for every wallet sign / x402 payment / job creation
- 8-point preflight (`security_hardening.py:299`) — wallet exists, real OWS,
  `.env` perms 0600, `.gitignore`, vault perms 0700, secret scan, audit log
- AES-256-GCM encrypted backups with scrypt KDF (n=2¹⁶)
- Halt-file kill switch checked before every outbound side effect
- MCP stdio subprocess hardening: only `PATH/HOME/USER/SHELL/LANG/LC_ALL/TERM`
  plus declared `env:` entries pass through; secret vars stripped

## Invariants worth knowing

1. **Working set persistence across ticks** — capabilities can depend on
   prior outputs; this is intentional.
2. **Memory.* operations bypass the capability manifest** —
   `memory.write` / `memory.read` are synthetic and always available.
3. **Halt file is checked before the budget** — never accidentally spends
   while halted.
4. **Promotion never overwrites** — new `memory_id`, provenance chain.
5. **Regex strategy parsing wins over LLM** — deterministic floor when
   the LLM hallucinates.
6. **Slow-mode keep-or-discard** never regresses the baseline — proposals
   must be ≥ baseline on every axis and strictly better on at least one.
7. **Runtime self-improvement cannot weaken success metrics or remove
   policy rules** — `_weakens_criteria` (`evolution.py:423`).
8. **Plugin failures are logged and skipped, never raised** — third-party
   extensions cannot break the framework on import.

## Where to change things

| If you're changing… | Read first |
|---|---|
| Runtime tick behavior | `runtime.py:157` `RuntimeSession.run`, `runner.py:304` `AgentRunner.tick` |
| What policy enforces | `policy.py:72` `evaluate_action` |
| Generation surface | `generator.py:204`, `slow_generate.py:292`, `_apply_mutations` |
| Self-improvement bounds | `evolution.py:299` `accept_proposal`, `_weakens_criteria:423` |
| Promotion gates | `evals.py:215`, `_default_rollout_limits` |
| Memory schema | `storage.py:27` (migrations dict), `memory.py:18` (`MemoryRecord`) |
| Prompt structure | `prompting.py` (6-section assembler + token budget) |
| Adding an LLM provider | `models.py` (each provider implements `complete()`); see also `extending.mdx` for the plugin path |
| Wallet / payments | `wallet.py:68`, `agent_payments.py:309`, `x402_client.py:204` |
| Protocol calldata | `onchain_registry.py:197`, `x402_server.py:475` |
| Security envelope | `security.py:287`, `security_hardening.py:33`, `:299` |

## Documentation

For the user-facing site, see [`docs-site/`](./docs-site/) (Nextra v4).
The high-level orientation map lives in [`docs/README.md`](./docs/README.md).
Product direction is governed by versioned PRDs under
[`docs/prd/`](./docs/prd/). Non-negotiable rules for AI / human
contributors live in [`AGENTS.md`](./AGENTS.md).

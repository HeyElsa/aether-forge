# Aether Forge Product Requirements Document

Version: `v0.14.0`
Status: `Draft`
Date: `2026-04-11`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.13.0.md` (rolled into changelog only)
Base PRD: `docs/prd/aether-forge-prd-v0.12.0.md`

## 1. Status

This PRD inherits all unchanged requirements from v0.12.0 and the v0.13.0 changelog entries (security hardening, x402 client, data layer, generated-router data layer wiring, token registry, real-money live-mode validation).

v0.14.0 makes the framework's mission explicit at the framework level: **Aether Forge agents are LLM-driven by default**, with four typed memory layers that the LLM reads on every tick. Operators no longer have to remember CLI flags or hand-edit JSON to wire an LLM into a generated agent — the framework auto-detects the best planner on the host machine and bakes it into the agent's own config so anyone running the directory later inherits the same model. `forge doctor` now verifies the runtime memory and crypto stack with real round-trip checks instead of just import-existence. A new long-form team demo (`demo.sh`) walks through the entire LLM + memory + autoresearch loop end to end against a swing-trading prose strategy file.

Key additions:

- **LLM-driven by default** — `_autodetect_planner()` in `cli.py` probes Ollama → Anthropic → OpenAI → Gemini → OpenRouter → heuristic, picks the best available, and bakes it into the generated agent's `aether-forge.json`.
- **Four typed memory layers** documented as a first-class architectural concept (replays, working set, SQLite memory store, MemPalace knowledge layer).
- **`forge doctor` expanded** to functional round-trip checks for both memory layers + the cryptography package, with a one-line verdict summary. Removed `ruff` and `pytest` checks (framework-contributor tools, not runtime requirements for an agent).
- **New `[security]` and `[all]` install extras**, with `cryptography` carved out as its own optional dep and a single `pip install aether-forge[all]` for end users.
- **`demo.sh`** — the canonical 10-section team walk-through that exercises every framework feature from a prose strategy file through real x402 spend.

Test count: 288 → 345 across all suites. No regressions.

## 2. Summary of Changes

Compared with v0.12.0 (and the v0.13.0 changelog entries), this version:

1. Made the framework LLM-driven at the default level. `forge generate-fast` now auto-detects a planner and writes a complete planner block into the generated agent's `aether-forge.json`. No more `"mode": "heuristic"` hardcoded default. The auto-detect probe runs at generation time, tries Ollama on `localhost:11434` first (free, fast, no key, no network), then `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`/`GEMINI_API_KEY`, `OPENROUTER_API_KEY`, and only falls back to `heuristic` when nothing is available. Auto-detection prefers a Gemma model when Ollama is reachable. The resolved choice is logged loudly so the operator knows what got baked in.
2. Documented the four-layer memory architecture as a first-class framework concept. Layer 1 is per-tick replay JSON (audit only, never read back into the LLM). Layer 2 is in-process working set + session state (one tick lifetime). Layer 3 is the durable per-agent SQLite memory store (`memory.db`, survives restarts, the LLM reads it under `## Memory Context` every tick). Layer 4 is the optional MemPalace knowledge layer (Chroma vectors + temporal knowledge graph, semantic recall + bitemporal facts, the LLM reads it under `## Knowledge` when `--knowledge` is on). Each layer has its own read/write velocity and its own purpose.
3. Expanded `forge doctor` to verify the runtime memory and crypto stack with **functional round-trip checks**, not just import-existence:
   - `_check_sqlite_memory_store()` instantiates a real `SqliteMemoryStore` in a temp dir, writes a sentinel `MemoryRecord`, reads it back via `MemoryQuery`, and reports `Layer 3 round-trip ok`.
   - `_check_mempalace_knowledge_layer()` imports `mempalace`, instantiates a `KnowledgeStore`, writes a fact via `add_fact()` and a semantic memory via `remember()`, queries the entity, and reports the mempalace version + `KG + semantic round-trip ok`. Degrades gracefully when the optional dep is missing.
   - `_check_cryptography()` reports the `cryptography` version (required for AES-256-GCM encrypted backups and encrypted memory records, lazy-imported by `security_hardening` and `storage`).
   - Removed `_check_ruff` and `_check_pytest` — those are framework-contributor tools, not runtime requirements for an agent.
4. Added a one-line verdict summary to `forge doctor`. Three states: `Healthy — N/N ok, 0 skipped, 0 failed`, `Healthy (with optional skips) — ...`, or `UNHEALTHY — ...`. Operators read the verdict at a glance instead of scanning every line.
5. New install extras in `pyproject.toml`:
   - `[security]` → `cryptography>=42.0.0` for encrypted wallet backups and encrypted memory records.
   - `[all]` → `wallet + knowledge + security` in one install for end users running production agents.
   - Added `ruff>=0.6.0` to `[dev]` so framework contributors get the linter via `pip install -e .[dev]`.
6. Added `demo.sh` — the canonical team walk-through script. 10 sections covering: doctor preflight, skill catalogs, model selection (with local Gemma smoke prompt), prose strategy file authoring, agent generation, validation, eval-pack, wallet inspection, security audit, paper run with autoresearch + knowledge layer, replay reasoning trail, autoresearch proposals, both memory layers (SQLite + MemPalace), live x402 mode, kill switch (via direct `x402-call` so the halt-file preflight actually fires), encrypted wallet backup. Supports `DEMO_AUTO=1`, `DEMO_SKIP_LIVE=1`, `DEMO_BACKUP_PASSPHRASE=...`, `DEMO_PLANNER_MODE=...` env overrides for rehearsal vs live demo.
7. Verified end-to-end that the swing trader generates with auto-detected `ollama / gemma4:latest`, runs 8 paper ticks with autoresearch + knowledge, populates both memory layers, fires real x402 payments during live ticks, and produces an encrypted backup — all with no manual JSON edits and no API keys configured.

## 3. LLM-Driven by Default

### 3.1 Mission Restatement

Aether Forge agents exist to **interpret a user's strategy and execute it within typed runtime guardrails**. Strategies are written in plain English (markdown), not as Python state machines. The LLM is the load-bearing component that turns prose into typed `StepProposal` objects on every tick. Without an LLM, an agent is a deterministic state machine that executes literal pattern matches against the strategy file — a fundamentally different product.

`heuristic` mode still exists for two narrow use cases:

- CI tests — deterministic, reproducible, no API key
- Cold-start fallback — when neither a local model nor a cloud key is available

In both cases, the operator gets a clearly-labeled fallback with a path forward (set a key or pull a model), not a silent degradation.

### 3.2 Auto-Detect Algorithm (`cli._autodetect_planner`)

`forge generate-fast` (no `--planner-mode` flag) probes the host machine in this order:

| Priority | Source | Resolved Mode | Default Model | API Key Env |
|---|---|---|---|---|
| 1 | Local Ollama daemon (`http://localhost:11434/api/tags`) | `ollama` | First Gemma model present, else first model | none |
| 2 | `ANTHROPIC_API_KEY` set | `anthropic` | `claude-sonnet-4-5` | `ANTHROPIC_API_KEY` |
| 3 | `OPENAI_API_KEY` set | `openai` | `gpt-4o` | `OPENAI_API_KEY` |
| 4 | `GOOGLE_API_KEY` set | `gemini` | `gemini-2.5-flash` | `GOOGLE_API_KEY` |
| 5 | `GEMINI_API_KEY` set | `gemini` | `gemini-2.5-flash` | `GEMINI_API_KEY` |
| 6 | `OPENROUTER_API_KEY` set | `openrouter` | `anthropic/claude-sonnet-4.5` | `OPENROUTER_API_KEY` |
| 7 | nothing available | `heuristic` | n/a | n/a |

The result is logged at generation time:

```
[planner] auto-detected: mode=ollama model=gemma4:latest baseUrl=http://localhost:11434
```

### 3.3 Persisted into the Agent

`FastGenerateRequest` gained four planner fields (`planner_mode`, `planner_model`, `planner_base_url`, `planner_api_key_env`). `_project_config_json()` reads them and writes a complete planner block into the generated `aether-forge.json`:

```json
{
  "planner": {
    "mode": "ollama",
    "model": "gemma4:latest",
    "baseUrl": "http://localhost:11434"
  },
  "runtime": { "cryptoRouter": "mock" },
  "adapters": { ... }
}
```

The chain is now:

```
forge generate-fast            (auto-detect, write to aether-forge.json)
  ↓
forge run <agent>              (no flags — config file resolves planner)
  ↓
resolve_planner_settings()     (CLI flag > env > config file > default)
  ↓
build_planner_factory()        (instantiates the right planner)
```

Anyone who runs the agent later — Docker, CI, a teammate — inherits the exact same model the operator picked at generation time, with no flags and no key plumbing required (assuming the same env vars are present in the new context).

### 3.4 Override Path

Operators who want to override auto-detection at generation time can pass any of:

```bash
forge generate-fast ... \
  --planner-mode anthropic \
  --planner-model claude-opus-4-6 \
  --planner-api-key-env ANTHROPIC_API_KEY
```

Operators who want to override at run time (without modifying the agent's config file) keep the existing `forge run --planner-mode/--planner-model` flags.

## 4. Four-Layer Memory Architecture

### 4.1 Architectural Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│  Layer 4: KnowledgeStore (MemPalace)         long-term, optional   │
│  knowledge/             (Chroma vector store)                       │
│  knowledge/knowledge_graph.db   (SQLite temporal triple store)      │
│  Wing: per-agent. Rooms: trades, market-events, performance         │
│  Read by:  prompting._build_knowledge_context() if --knowledge      │
│  Written by: runner.record_tick_knowledge() per tick                │
├────────────────────────────────────────────────────────────────────┤
│  Layer 3: SqliteMemoryStore                  durable, per-agent    │
│  memory.db                                                           │
│  Schema: typed MemoryRecord rows                                     │
│  Read by:  runtime.run() at top of every tick into session_state    │
│  Written by: runner._persist_tick_memory() + memory.write capability │
├────────────────────────────────────────────────────────────────────┤
│  Layer 2: working_set / session_state        in-process, one tick  │
│  session.working_set    { eth_price, momentum, balance, ... }       │
│  session.session_state  { goal_satisfied, blocking_reason, ... }    │
│  Read by:  prompting._summarize_runtime_state()                     │
│  Written by: capability handlers during the tick                    │
├────────────────────────────────────────────────────────────────────┤
│  Layer 1: replays/                           audit only, forever   │
│  One JSON file per tick: full step ledger, state_before/after       │
│  Read by:  humans (and crash recovery)                              │
│  Written by: runner after each tick                                 │
└────────────────────────────────────────────────────────────────────┘
```

### 4.2 Layer-by-Layer Spec

**Layer 1 — Replay files (`replays/tick-N.json`)**

- One file per completed tick.
- Contains the full `stepLedger`: every `StepProposal`, lifecycle, state-before, state-after, message.
- Never read back into the LLM under normal operation.
- Used by humans for audit, debugging, and post-mortem; used by the runner for crash recovery (resume from latest replay).
- Lifetime: forever. Pruning is operator-managed.

**Layer 2 — Working set + session state (in-process)**

- Lives on `RuntimeSession` for the duration of a single tick.
- `session.working_set` is a plain dict capabilities populate during the tick (price, momentum, balance, recent orders).
- `session.session_state` carries goal flags, blocking reasons, current environment, observation count.
- The LLM sees this in the prompt's `## Runtime State` section via `_summarize_runtime_state()`.
- Lifetime: one tick. Cleared at tick end.

**Layer 3 — SqliteMemoryStore (`memory.db`)**

- Lives at `<agent>/memory.db` by default. Override with `--memory-db`.
- Schema in `storage.py`. Typed `MemoryRecord` rows: `memory_id`, `memory_type`, `scope`, `environment`, `content`, `summary`, `source`, `confidence`, `sensitivity`, timestamps, `expires_at`, `retention_policy`, `tags`, `metadata`.
- Default writers: `runner._persist_tick_memory()` writes one `decision-history` row per completed tick. The agent itself can also emit `memory.write` capability calls to remember anything it chose.
- Read into the prompt: every tick, `runtime.run()` (line ~161) executes `memory_store.read(MemoryQuery(scope="session", environment=current_env))` and stuffs the result into `session_state["memory_context"]`. `prompting._summarize_memory_context()` formats it into the `## Memory Context` section.
- The LLM can also explicitly query memory mid-tick via `memory.read` (handled in `runtime._execute_memory_operation`).
- Promotion: `memory.promote` moves a record from a less-trusted environment to a more-trusted one, requiring an approval reference.
- Lifetime: forever, or until `expires_at`. Survives process restarts.

**Layer 4 — KnowledgeStore (MemPalace, `knowledge/`)**

- Optional dep: `pip install aether-forge[knowledge]` (or `[all]`).
- External package: `mempalace>=3.1.0`.
- Two stores under one directory:
  - `knowledge/` → ChromaDB collection — semantic vector search over arbitrary text. Used for *"have I seen something like this before?"* queries.
  - `knowledge/knowledge_graph.db` → SQLite temporal triple store. Bitemporal: every `(subject, predicate, object)` triple has `valid_from` and optional `valid_to`. Used for *"what did I believe about ETH between Apr 8 and Apr 10?"* queries.
- Per-agent isolation via wings: each agent's `KnowledgeStore` is keyed by `wing=agent_name`.
- Write hook: `runner` calls `KnowledgeStore.record_tick_knowledge(prices, orders, momentum, performance)` after each tick. Prices and trends become KG facts, filled orders become semantic drawers in the `trades` room, failing metrics become drawers in the `performance` room.
- Read into the prompt: `prompting._build_knowledge_context()` calls `KnowledgeStore.get_context_for_planning()` which runs a semantic recall on `"current market conditions and strategy performance"` (top 3 hits) plus `query_entity()` for the default token universe. The result lands in the prompt's `## Knowledge` section.
- Graceful degradation: if `mempalace` isn't installed, `KnowledgeStore._init()` catches the `ImportError`, sets `_available = False`, and every method becomes a no-op. The agent runs without long-term memory but doesn't crash.
- Lifetime: forever, with bitemporal validity windows.

### 4.3 Layer Comparison

| Aspect | Layer 1 — Replays | Layer 2 — Working set | Layer 3 — SQLite memory | Layer 4 — MemPalace |
|---|---|---|---|---|
| Backend | JSON files | In-process dict | SQLite (in-tree) | Chroma + SQLite KG (external dep) |
| Lifetime | Forever | One tick | Forever or `expires_at` | Forever (bitemporal) |
| Reads/tick | 0 (1 on recovery) | Constant during tick | 1 (always) + ad-hoc via `memory.read` | 1 if `--knowledge` |
| Writes/tick | 1 (always) | Constant during tick | 1 (tick summary) + agent-emitted | 1 if `--knowledge` |
| Read by LLM? | No | Yes (`## Runtime State`) | Yes (`## Memory Context`) | Yes (`## Knowledge`) |
| Purpose | Audit / replay | "What's true right now?" | "What did I do and remember?" | "What have I learned?" |

### 4.4 Why All Four Are Needed

A swing trader's strategy file contains clauses like *"did not stop out in the last hour"*, *"after 10 ticks, evaluate win rate"*, *"if win rate < 35% and we have at least 5 closed trades, propose tightening entries"*. None of these can be evaluated without memory:

- *"In the last hour"* needs Layer 3 — survives restart, queryable by recency.
- *"After 10 ticks, evaluate"* needs Layer 3 — counts persist across the autoresearch interval.
- *"Have I seen this regime before?"* needs Layer 4 — semantic recall across sessions.
- *"What was the strategy state when this trade was placed?"* needs Layer 4 — bitemporal KG.

Layer 2 alone gets you a stateless reflex agent. Layer 3 alone gets you a single-session learner. Layer 4 alone gets you a knowledge base with no operational state. **All four together** get you a swing trader that remembers what it just did, persists across restarts, learns across sessions, and leaves an auditable trail.

## 5. `forge doctor` as Runtime Stack Verifier

### 5.1 Mission

`forge doctor` verifies the runtime stack an Aether Forge agent depends on — Python, dependency packages, LLM providers, memory layers, and the cryptographic primitives needed for encrypted backups. It does **not** check framework-contributor tooling (linters, test runners, build helpers). Anyone running an agent in production should be able to run `forge doctor` and get a one-line verdict that says whether the agent is going to be able to start and operate.

### 5.2 Checks (in order)

| # | Check | Required | What it verifies |
|---|---|---|---|
| 1 | Python version | yes | Python 3.12+ for typing/dataclass features used by spec models |
| 2 | jsonschema | yes | Validates spec / manifest / policy / scenario artifacts |
| 3 | OWS SDK | optional | Real wallets across 9 chains; falls back to simulated provider when missing |
| 4 | cryptography | optional | AES-256-GCM encrypted backups + encrypted memory records (lazy-imported) |
| 5 | Ollama | optional | Local LLM provider (probes `http://localhost:11434/api/tags`) |
| 6 | OpenRouter | optional | Cloud LLM provider (probes `https://openrouter.ai/api/v1/models`) |
| 7 | Memory store (SQLite) | yes | Layer 3 functional round-trip: write a sentinel `MemoryRecord`, read it back via `MemoryQuery` |
| 8 | Knowledge layer (MemPalace) | optional | Layer 4 functional round-trip: `add_fact()` + `remember()` + `query_entity()` |

### 5.3 Round-Trip Discipline

Every check that involves an actual data store performs a real write + read against a temp dir, not just an `import` test. Rationale: import checks miss real-world failures like *"the schema migration ran but the new column conflicts with the old one"* or *"chroma is installed but its sqlite backend can't write to disk"*. A round-trip catches both. It's also what lets the demo confidently say *"the memory layer is healthy"* — the doctor literally just wrote and read a record.

### 5.4 Verdict Summary

After every check, doctor prints a one-line verdict:

```
Healthy — 8/8 ok, 0 skipped, 0 failed
```

Three states:

- `Healthy — N/N ok, 0 skipped, 0 failed` — every check passed and no optional dep is missing.
- `Healthy (with optional skips) — N/M ok, X skipped, 0 failed` — required checks pass; some optional deps are absent but the agent is operational.
- `UNHEALTHY — N/M ok, X skipped, Y failed` — at least one required check failed. Exit code 1. Operator must fix the failing check before running an agent.

### 5.5 What Got Removed

`_check_ruff()` and `_check_pytest()` were removed. Both are framework-contributor tools (`ruff` lints the framework's Python; `pytest` runs the framework's test suite). End users running an Aether Forge agent in production never need either. Their presence in the doctor output was misleading noise. Anyone hacking on the framework gets both back via `pip install -e .[dev]`.

## 6. Install Extras

`pyproject.toml` now defines five extras:

| Extra | Pulls In | Use Case |
|---|---|---|
| `[dev]` | `pytest`, `ruff`, `build`, `twine` | Framework contributors |
| `[wallet]` | `open-wallet-standard>=1.2.4` | Real OWS wallets across 9 chains |
| `[knowledge]` | `mempalace>=3.1.0` | Layer 4 long-term memory |
| `[security]` | `cryptography>=42.0.0` | Encrypted backups + encrypted memory records |
| `[all]` | `wallet + knowledge + security` | One-command install for production agents |

Two recommended install paths:

```bash
# End user running production agents
pip install 'aether-forge[all]'

# Framework contributor
git clone <repo> && cd aether-forge
python -m venv .venv && source .venv/bin/activate
pip install -e '.[all,dev]'
```

## 7. `demo.sh` — Canonical Team Walk-Through

A new top-level `demo.sh` is the framework's canonical team walk-through. Ten sections, ~3 minutes in `DEMO_AUTO=1` mode, ~10 minutes with narration pauses. Built around an autonomous ETH swing trader that interprets a markdown strategy file every tick.

### 7.1 Sections

| § | Title | Memory layer touched |
|---|---|---|
| 0/0a | Setup + `forge doctor` + tool preflight (`jq`, `sqlite3`, `curl`) | — |
| 1 | `forge elsa-list` + `skills-search` | — |
| 1b | Pick the LLM (default: local Gemma via Ollama) + smoke prompt | — |
| 1c | Write the swing-trade strategy file (markdown, 80+ lines) | This is the file the LLM re-reads on every tick |
| 2 | `forge generate-fast --strategy-file --autonomous --wallet` | All four layers initialized |
| 2a | Inspect the generated artifact set | — |
| 2b | Confirm the planner block is in `aether-forge.json` | — |
| 3 | `forge validate .` | — |
| 4 | `forge eval-pack .` | — |
| 5 | Inspect the OWS wallet | — |
| 6 | `forge security-check . --harden` | — |
| 7 | Paper run: 8 ticks, autoresearch every 3, knowledge layer on | All four layers written |
| 7a | Read LLM reasoning trail from `replays/tick-N.json` | Layer 1 |
| 7b | `forge strategy view .` (autoresearch proposals) | strategy.json |
| 7c | SQLite memory store schema + most recent decision-history rows | **Layer 3** |
| 7d | MemPalace wing layout, current facts, ETH timeline, semantic drawer count | **Layer 4** |
| 8 | `forge run --mode live --chain base` (real x402 spend) | All four layers, real money |
| 8a | Proof of payment from `x402_state.json` + `x402_audit.jsonl` | — |
| 8b | LLM reasoning trail from the LIVE ticks | Layer 1 |
| 9 | Kill switch via direct `forge x402-call --confirm-live` | — |
| 10 | Encrypted wallet backup (AES-256-GCM, scrypt) | — |

### 7.2 Modes

| Env vars | Behavior |
|---|---|
| (none) | Live demo with narration pauses, prompts for backup passphrase, spends real money in §8/§9 |
| `DEMO_AUTO=1` | No pauses — runs the whole script in one shot |
| `DEMO_SKIP_LIVE=1` | Skip §8 and §9 (no real money) |
| `DEMO_BACKUP_PASSPHRASE=...` | Skip the §10 TTY passphrase prompt |
| `DEMO_PLANNER_MODE=...`, `DEMO_PLANNER_MODEL=...` | Override the LLM choice |

The recommended rehearsal incantation is:

```bash
DEMO_AUTO=1 DEMO_SKIP_LIVE=1 DEMO_BACKUP_PASSPHRASE=demo-pass-12345 ./demo.sh
```

This exercises every step except the two live-money sections, finishes in ~3 minutes, and leaves a fully populated agent directory at `~/aether-demo/demo-eth-swing` for inspection.

## 8. Updated Non-Negotiables

The following are added to `AGENTS.md`'s product non-negotiables list as of v0.14.0:

- Aether Forge agents are LLM-driven by default. `heuristic` mode is a labeled fallback, not a silent default.
- The framework MUST persist the operator's planner choice into the generated agent's config so the agent is self-contained.
- The framework MUST treat memory as four typed layers with distinct read/write semantics. Layer 1 is audit-only. Layer 2 is per-tick scratch. Layer 3 is per-agent durable. Layer 4 is long-term semantic + temporal (optional).
- `forge doctor` MUST verify runtime dependencies with functional round-trip checks for stateful components (memory layers), not just import existence.
- Doctor checks MUST be scoped to runtime requirements, not framework-contributor tooling.
- Generated agents MUST NOT bake in framework-developer dependencies (ruff, pytest, build, twine).

## 9. Module Inventory (Updated)

New since v0.12.0 (carried over from v0.13.0 + this PRD):

| Module | Purpose |
|---|---|
| `src/aether_forge/data_layer.py` | Generic `DataRouter` over HTTP / x402 / WebSocket sources, capability-based dispatch with fallback |
| `src/aether_forge/x402_client.py` | EIP-3009 signed pay-per-call client with persistent budget state, balance preflight, halt-file kill switch, audit log |
| `src/aether_forge/security_hardening.py` | Sanitization, file/dir lockdown, AES-256-GCM encrypted backups, secret scanner, 8-point preflight audit |
| `src/aether_forge/runner.py` | `AgentRunner` continuous execution loop with health endpoint, JSON logging, PID file, crash recovery, knowledge layer integration |
| `src/aether_forge/scaffold_router.py` | Generic per-agent strategy router loader; receives `StrategyConfig` with `mode` and `chain` |
| `src/aether_forge/evolution.py` | Runtime autoresearch (`StrategyArtifact`, `SelfEvaluator`, `RuntimeAutoresearch`, `ImprovementProposal`) |
| `src/aether_forge/wallet.py` | Per-agent OWS vault provisioning, scoped API keys, 9 chains, simulated fallback |
| `src/aether_forge/strategy_parser.py` | Parses English / markdown / JSON strategy files into `strategy.json` parameters |
| `src/aether_forge/knowledge.py` | Layer 4 wrapper over MemPalace (Chroma + KG) |
| `src/aether_forge/storage.py` | Layer 3 `SqliteMemoryStore` |

Modified in v0.14.0:

| Module | Change |
|---|---|
| `src/aether_forge/cli.py` | `_autodetect_planner()`, generate-fast planner flags, doctor verdict line |
| `src/aether_forge/doctor.py` | Memory + crypto round-trip checks; removed ruff/pytest checks |
| `src/aether_forge/generator.py` | `FastGenerateRequest` planner fields, `_project_config_json(request)` honors operator's choice |
| `pyproject.toml` | New `[security]`, `[all]`, `ruff` in `[dev]` |

## 10. Test Coverage

| Suite | Count |
|---|---|
| Total | 345 |
| `test_doctor.py` | 8 |
| `test_security_hardening.py` | 20 |
| `test_x402_client.py` | 13 |
| `test_data_layer.py` | (new) |
| `test_cli.py` | (covers generate-fast flags, doctor verdict, planner auto-detect) |
| All others | as in v0.12.0 |

No regressions across the existing suites after v0.14.0 changes.

# Aether Forge Product Requirements Document

Version: `v0.15.0`
Status: `Draft`
Date: `2026-04-11`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.14.0.md`
Base PRD: `docs/prd/aether-forge-prd-v0.12.0.md`

## 1. Status

This PRD inherits all unchanged requirements from v0.14.0 (LLM-driven default, four-layer memory architecture, doctor as runtime stack verifier, install extras, demo.sh canonical walkthrough).

v0.15.0 adds two concrete capabilities:

1. **MCP (Model Context Protocol) client support.** Generated agents can discover and call tools from any MCP server — local subprocess or remote HTTP — as part of their capability manifest at runtime. Unlocks interoperability with [Hermes Agent](https://hermes-agent.nousresearch.com/)'s messaging gateway, official MCP servers (filesystem, GitHub, Brave search, etc.), and any custom MCP server in the ecosystem.
2. **Function-call planner.** A new `FunctionCallPlanner` wraps any `PlanningModel` and translates JSON function-call output into native Aether step proposals. Use with `--planner-mode function-call` pointed at any OpenAI-compatible endpoint running a model fine-tuned for structured tool use.

Test count: 345 → 371 across all suites. No regressions.

## 2. Summary of Changes

Compared with v0.14.0:

1. Added a full MCP client (stdio + HTTP transports) in `src/aether_forge/mcp_client.py`. Pure stdlib — no external dependencies. Implements `initialize`, `tools/list`, `tools/call`, and the `notifications/initialized` handshake per the MCP spec.
2. Added `McpDataSource` in `src/aether_forge/data_layer.py` alongside the existing `HTTPDataSource`, `X402DataSource`, `WebSocketDataSource`, and `MockDataSource`. Discovers tools via `tools/list` at connection time and routes `fetch()` calls through `tools/call`. Plugs into the existing `DataRouter` fallback chain.
3. Added an `mcp_servers:` block to the `aether-forge.json` config schema. Each entry is stdio (`command` + `args` + optional `env`) or HTTP (`url` + optional `headers`), with optional `tools.include`/`tools.exclude` whitelisting.
4. Extended `StrategyConfig` (in `scaffold_router.py`) with an `mcp_servers` field so generated agents' strategy routers pick up the MCP declarations automatically. `forge run` reads the block from `aether-forge.json` and threads it through.
5. Added stdio subprocess hardening: when spawning MCP servers, only a safe baseline env (`PATH`, `HOME`, `USER`, `SHELL`, `LANG`, `LC_ALL`, `TERM`) plus explicit `env:` entries are passed through. The parent environment is never leaked.
6. `forge doctor` now probes MCP servers declared in a config file and reports tool counts. Failures are optional (do not flip verdict to UNHEALTHY).
7. Added `FunctionCallPlanner` in `src/aether_forge/config.py`. Wraps any `PlanningModel`, uses a dedicated prompt builder to request a JSON function-call response, parses it through `FunctionCallTranslator`, and falls back to `HeuristicPlanner` on any parse error with a logged `WARNING` (no more silent fallbacks).
8. Added `src/aether_forge/adapters/function_call.py` with `FunctionCallTranslator`, `FunctionCallResponse`, and `FunctionToolCall` — the dataclasses + translator that define the expected JSON shape and convert it into native `StepProposal` objects.
9. Added `build_function_call_prompt_from_session()` in `prompting.py` that asks the model for the exact JSON shape the translator expects: `{reasoning, tool_calls, final_message, requires_approval}`.
10. Added markdown code-fence stripping in `_parse_function_call_payload()`. Several models wrap JSON in ```` ```json ... ``` ```` even when asked not to.
11. CLI: `--planner-mode function-call` selects the new planner. Uses an `OpenAICompatiblePlanningModel` as the backing model, so any OpenAI-compatible endpoint works (local Ollama, vLLM, LM Studio, or a hosted provider).
12. New tests:
    - `tests/test_function_call_adapter.py` — 7 tests covering the translator layer (declared/undeclared/approval) and end-to-end `FunctionCallPlanner` with a mock model (valid response, markdown fences, malformed JSON fallback with logged warning).
    - `tests/test_mcp_client.py` — 20 tests covering config validation, stdio protocol round-trip, HTTP transport, `McpDataSource` integration, and the `build_mcp_source` factory.
13. New user guide: `docs/mcp.md` covering local filesystem example, Hermes Agent messaging bridge, remote HTTP example, tool filtering, security, programmatic API, and troubleshooting.

## 3. Model Context Protocol (MCP) Client

### 3.1 Why

Aether Forge's existing data layer (`HTTPDataSource`, `X402DataSource`, `WebSocketDataSource`) covers a lot of ground but requires every new integration to go through the framework's own adapters. MCP is an open protocol (spec at https://modelcontextprotocol.io/) for exposing tools to AI agents over a JSON-RPC transport. Adding MCP client support means Aether Forge gains instant compatibility with:

- The official MCP server registry (filesystem, GitHub, Brave search, SQLite, fetch, git, etc.)
- Hermes Agent's `hermes mcp serve` — 10 messaging tools bridging to Telegram, Discord, Slack, WhatsApp, Signal, Matrix, and more
- Any custom MCP server a team builds internally
- Claude Code's own tool-server ecosystem

Without maintaining any of those integrations ourselves.

### 3.2 Scope — what's implemented

| Capability | Stdio | HTTP |
|---|---|---|
| `initialize` handshake with protocol version 2024-11-05 | ✓ | ✓ |
| `notifications/initialized` follow-up | ✓ | ✓ |
| `tools/list` discovery | ✓ | ✓ |
| `tools/call` invocation with structured arguments | ✓ | ✓ |
| Tool filtering (`include` / `exclude` whitelisting per server) | ✓ | ✓ |
| Config-driven subprocess spawning | ✓ | n/a |
| Config-driven HTTP headers + timeout | n/a | ✓ |
| Safe baseline environment (no parent env leakage) | ✓ | n/a |
| Context-manager cleanup of subprocess on exit | ✓ | n/a |
| Typed error hierarchy (`McpError`, `McpProtocolError`, `McpTimeoutError`) | ✓ | ✓ |

### 3.3 Scope — what's explicitly NOT implemented (yet)

- **Resources** (`resources/list`, `resources/read`) — MCP has a concept of static resources separate from tools. Not needed for tools-based agents.
- **Prompts** (`prompts/list`, `prompts/get`) — Reusable prompt templates exposed by MCP servers. Could be wired into the planner later.
- **Sampling** — MCP servers can ask the client to run an LLM completion on their behalf. Would couple the MCP client to the planner layer; not worth it yet.
- **Streaming / SSE transport** — The HTTP client implements plain request/response only. Good enough for most server-exposed REST-style MCP endpoints.
- **Aether Forge as an MCP server** — `forge mcp serve` to expose Aether-generated agents as MCP tools is planned but not shipped. Follow-up work.

### 3.4 Config schema

Generated `aether-forge.json` now accepts an optional top-level `mcp_servers:` block:

```json
{
  "planner": { "mode": "ollama", "model": "gemma4:latest" },
  "runtime": { "cryptoRouter": "mock" },
  "mcp_servers": {
    "hermes": {
      "command": "hermes",
      "args": ["mcp", "serve"]
    },
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": { "GITHUB_PERSONAL_ACCESS_TOKEN": "${GH_TOKEN}" },
      "tools": {
        "include": ["list_issues", "create_issue"],
        "exclude": ["delete_repository"]
      }
    },
    "remote_api": {
      "url": "https://mcp.example.com/mcp",
      "headers": { "Authorization": "Bearer ${API_KEY}" }
    }
  }
}
```

### 3.5 Runtime wiring

`StrategyConfig` in `scaffold_router.py` now carries an `mcp_servers: dict[str, dict[str, Any]]` field. `forge run` reads the block from the agent's `aether-forge.json` and passes it into `StrategyConfig` automatically. The generated scaffold's strategy router can then spawn `McpDataSource` instances via `build_mcp_source(spec, name=name)` and attach them to its `DataRouter`.

## 4. Function-Call Planner

### 4.1 Purpose

A dedicated planner for LLMs that produce JSON function-call output. Use this mode with any OpenAI-compatible endpoint running a model fine-tuned for structured tool use — Nous Hermes-3, Qwen function-calling variants, Llama 3 tool-calling models, etc. The planner asks the model for the exact JSON shape the `FunctionCallTranslator` expects and converts the response into native Aether `StepProposal` objects.

### 4.2 Shape

`FunctionCallPlanner` prompts the model for:

```json
{
  "reasoning": "brief rationale",
  "tool_calls": [
    {"name": "<declared capability id>", "arguments": {...}}
  ],
  "final_message": "optional wrap-up",
  "requires_approval": false
}
```

The translator (`FunctionCallTranslator` in `src/aether_forge/adapters/function_call.py`) converts each field into a typed step:

- `reasoning` → `REASON` step
- Each `tool_calls[i]` with a declared capability → `USE_CAPABILITY` step (or `REQUEST_APPROVAL` if `requires_approval=true`)
- Each `tool_calls[i]` with an undeclared capability → `REPORT_GAP` step listing the requested capability
- `final_message` → trailing `REASON` step with `mark_complete=true`

### 4.3 Robustness

- **Markdown code-fence stripping**: several models wrap JSON in ` ```json ... ``` ` even when asked not to. `_parse_function_call_payload()` strips those wrappers before `json.loads()`.
- **Logged fallback**: on any parse error the planner falls back to `HeuristicPlanner` and logs a `WARNING` at `aether_forge.config` so operators can see why — no more silent fallbacks.
- **Dedicated prompt**: `build_function_call_prompt_from_session()` in `prompting.py` asks for the exact shape the translator expects, rather than reusing the generic `build_planning_prompt_from_session()` that asks for a `{steps: [...]}` shape.

### 4.4 Usage

```bash
# Generate an agent with the function-call planner baked in
forge generate-fast \
  --name my-agent --idea "..." --output ./my-agent \
  --planner-mode function-call \
  --planner-model hermes-3 \
  --planner-base-url http://localhost:11434

# Or at run time
forge run ./my-agent --planner-mode function-call --planner-model hermes-3 --planner-base-url http://localhost:11434
```

## 5. Updated Non-Negotiables

Added to the AGENTS.md product non-negotiables list:

- Aether Forge MUST support MCP as a first-class capability source. Generated agents that declare `mcp_servers:` in their config MUST discover and call those tools at runtime via `McpDataSource`.
- Spawning MCP stdio subprocesses MUST NOT leak the full parent environment — only a safe baseline plus explicitly-declared `env:` entries.
- Tool filtering (`tools.include` / `tools.exclude`) MUST be honored per MCP server.
- The framework MUST NOT be named after a specific external framework or language model in a way that creates confusion. (Drives the Hermes rename.)

## 6. Module Inventory

New in v0.15.0:

| Module | Purpose |
|---|---|
| `src/aether_forge/mcp_client.py` | MCP client: `McpServerConfig`, `McpStdioClient`, `McpHttpClient`, `build_mcp_client`, error hierarchy |
| `src/aether_forge/adapters/function_call.py` | `FunctionCallTranslator`, `FunctionCallResponse`, `FunctionToolCall` — JSON function-call translator |
| `src/aether_forge/config.py` (`FunctionCallPlanner` class) | New planner that wraps any `PlanningModel` and translates JSON function-call output into native step proposals |

Modified in v0.15.0:

| Module | Change |
|---|---|
| `src/aether_forge/config.py` | Added `FunctionCallPlanner` class, `_parse_function_call_payload()` with markdown fence stripping, `function-call` mode in `build_planner_factory` with logged fallback |
| `src/aether_forge/prompting.py` | New `build_function_call_prompt_from_session()` |
| `src/aether_forge/data_layer.py` | New `McpDataSource`, new `build_mcp_source()` factory |
| `src/aether_forge/scaffold_router.py` | `StrategyConfig` gains `mcp_servers` field |
| `src/aether_forge/cli.py` | CLI choices include `function-call`; reads `mcp_servers` from config into `StrategyConfig` |
| `src/aether_forge/doctor.py` | New `_check_mcp_servers()` helper; `mcp_servers` added to valid top-level config keys |
| `src/aether_forge/completions.py` | `function-call` added to planner mode list |

New docs:

| File | Purpose |
|---|---|
| `docs/mcp.md` | User guide for MCP integration with examples and troubleshooting |

## 7. Test Coverage

| Suite | Count |
|---|---|
| Total | 368 |
| `test_function_call_adapter.py` | 7 |
| `test_mcp_client.py` | 20 (new) |
| All others | as in v0.14.0 |

No regressions across the existing 345 tests after v0.15.0 changes.

## 8. Verification

- `pytest tests/ -q --ignore=tests/test_real_agent.py --ignore=tests/test_live_execution.py --ignore=tests/test_e2e.py` passes (368 passed, 1 skipped, 0 failed)
- `forge run --planner-mode function-call --planner-model X ...` works against any JSON-function-call-format model
- `forge doctor ./my-agent/aether-forge.json` probes declared MCP servers and reports their tool counts
- Agent with `mcp_servers:` block can be generated and run end-to-end against a local stdio MCP server
- `forge doctor` still reports 8/8 healthy on the core runtime stack

## 9. Future Work

- **Aether Forge as an MCP server** (`forge mcp serve`) — expose generated agents as MCP tools so Hermes Agent, Claude Code, Cursor, and other MCP clients can invoke them. Two-way bridge via protocol.
- **MCP resources and prompts** — support the `resources/*` and `prompts/*` MCP operations for non-tool-based servers.
- **Streaming HTTP transport** — implement SSE-based streaming for long-running tool calls.
- **Auto-discovery of MCP servers from the registry** — `forge mcp search <query>` that hits the official MCP server registry and suggests installs.

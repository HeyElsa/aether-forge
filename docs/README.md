# Aether Forge — Docs Map

This directory holds product PRDs, planning notes, and a few standalone
guides. The **user-facing documentation site lives in `../docs-site/`**
(Nextra v4) and is the canonical source. This index points you at the right
page for every topic.

## Run the docs site locally

```bash
cd ../docs-site
npm install
npm run dev   # → http://localhost:3000
```

## Where to find things

### Concepts & architecture

| Topic | Authoritative source |
|---|---|
| What Aether Forge is, why it exists | [`../README.md`](../README.md) |
| Runtime tick lifecycle, planner/policy/router pluggability, payment channels | [`../ARCHITECTURE.md`](../ARCHITECTURE.md) |
| Non-negotiables for AI / human contributors | [`../AGENTS.md`](../AGENTS.md) |

### Guides

| Topic | Source |
|---|---|
| End-to-end tutorial | `../docs-site/src/content/guides/end-to-end.mdx` |
| Build a custom agent | `../docs-site/src/content/guides/custom-agent.mdx` |
| Writing strategies | `../docs-site/src/content/guides/strategy-writing.mdx` |
| Production readiness | `../docs-site/src/content/guides/production-readiness.mdx` |
| Incident response for live agents | `../docs-site/src/content/guides/incident-response.mdx` |
| Multi-agent / A2A | `../docs-site/src/content/guides/multi-agent.mdx` |
| Going on-chain (ERC-8004) | `../docs-site/src/content/guides/go-onchain.mdx` |
| Accepting payments (x402 server) | `../docs-site/src/content/guides/accept-payments.mdx` |
| **Extending the framework** (custom planner / router / data source / memory store / skill registry — including PyPI plugin distribution) | `../docs-site/src/content/guides/extending.mdx` |

### Features

| Topic | Source |
|---|---|
| LLM planner (Anthropic, Gemini, OpenAI, Ollama, OpenRouter, function-call) | `../docs-site/src/content/features/llm-planner.mdx` |
| Four-layer memory architecture | `../docs-site/src/content/features/memory.mdx` |
| Data layer (HTTP, x402, WebSocket, MCP sources + DataRouter) | `../docs-site/src/content/features/data-layer.mdx` |
| Wallets (OWS across 9 chains) | `../docs-site/src/content/features/wallets.mdx` |
| x402 payments (client + server) | `../docs-site/src/content/features/x402-payments.mdx` |
| MCP integration | `../docs-site/src/content/features/mcp-integration.mdx` |
| A2A communication | `../docs-site/src/content/features/a2a-communication.mdx` |
| On-chain registry (ERC-8004) | `../docs-site/src/content/features/onchain-registry.mdx` |
| Attestation (self / verified) | `../docs-site/src/content/features/attestation.mdx` |
| Autoresearch (slow-mode + runtime) | `../docs-site/src/content/features/autoresearch.mdx` |
| DeFi safety (tx simulation, slippage, exposure, liquidation) | `../docs-site/src/content/features/defi-safety.mdx` |
| Security (session keys, circuit breakers, injection scanning) | `../docs-site/src/content/features/security.mdx` |
| Observability (`/metrics`, `/ready`, replays) | `../docs-site/src/content/features/observability.mdx` |

### Reference

| Topic | Source |
|---|---|
| Full CLI reference (every `forge` subcommand) | `../docs-site/src/content/reference/cli.mdx` |
| `aether-forge.json` schema (planner / runtime / mcp_servers blocks) | `../docs-site/src/content/reference/configuration.mdx` |
| Public Python API (Protocols + classes you can import from `aether_forge`) | `../docs-site/src/content/reference/python-sdk.mdx` |
| 8 typed artifacts and their JSON schemas | `../docs-site/src/content/reference/artifacts.mdx` |
| Skills (skills.sh, bankr, Elsa) | `../docs-site/src/content/reference/skills.mdx` |
| Glossary | `../docs-site/src/content/reference/glossary.mdx` |
| Open Agent Economy (ERC-8004 / 8126 / 8183 / x402) | `../docs-site/src/content/reference/open-agent-economy.mdx` |
| Plain-text MCP integration walkthrough (kept here for offline reading) | [`./mcp.md`](./mcp.md) |

### Cookbook (recipes)

`../docs-site/src/content/cookbook/` — `custom-data-source.mdx`,
`deployment.mdx`, `discord-bot.mdx`, `test-strategy.mdx`,
`webhook-trigger.mdx`.

### Help

| Topic | Source |
|---|---|
| FAQ | `../docs-site/src/content/help/faq.mdx` |
| Troubleshooting | `../docs-site/src/content/help/troubleshooting.mdx` |

## What lives in `docs/`

| Path | What |
|---|---|
| [`./mcp.md`](./mcp.md) | Standalone MCP user guide (linked from the README; kept as plain markdown for offline reading) |
| [`./prd/`](./prd/) | Product Requirements Documents — versioned (`v0.1.0` … `v0.23.0`). The latest version in `prd/README.md` is canonical when in conflict with anything else. |
| [`./plans/`](./plans/) | Design exploration, planning notes, schema design drafts. Reference material; the corresponding PRD wins on conflicts. |

## Editing rules

- Product direction changes — bump a new PRD under `docs/prd/`, update
  `docs/prd/README.md`, append `docs/prd/CHANGELOG.md`. Never delete or
  overwrite older PRDs (see `../AGENTS.md` §4).
- User-facing features — author the doc in `../docs-site/` (Nextra) and link
  back from this index if it adds a major topic.
- Architecture or runtime invariants — update `../ARCHITECTURE.md` and the
  relevant non-negotiable bullet in `../AGENTS.md`.

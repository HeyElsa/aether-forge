# Aether Forge PRD v0.18.0

**Date**: 2026-04-15
**Status**: Approved
**Previous**: v0.17.0 (CHANGELOG.md)

---

## Summary

v0.18.0 adds cloud LLM provider auto-detection, a full Nextra documentation site with 25 video walkthroughs, HeyElsa branding, install-from-source workflow, and an expanded demo script covering all features. This is the "developer experience" release — making Aether Forge accessible and deployable.

---

## What's New

### 1. Cloud LLM provider auto-detection

**Problem**: When `aether-forge.json` had `"mode": "openrouter"` without an explicit `apiKeyEnv` field, the runtime failed with "missing required settings: api_key" even though `OPENROUTER_API_KEY` was set in the environment.

**Fix**: `config.py` now auto-detects well-known API key environment variables per provider:

| Provider | Auto-detected env var |
|---|---|
| `openrouter` | `OPENROUTER_API_KEY` |
| `anthropic` | `ANTHROPIC_API_KEY` |
| `openai` | `OPENAI_API_KEY` |
| `gemini` | `GEMINI_API_KEY` |
| `google` | `GOOGLE_API_KEY` |

Users set the env var and the framework picks it up automatically. No `apiKeyEnv` config needed.

**Tested**: OpenRouter + Claude Sonnet 4 — 2 ticks, 30 steps, $10K → $14,684 simulated P&L. DeepSeek R1 also confirmed working (slower — reasoning model).

### 2. Documentation site (Nextra v4)

Full documentation site at `docs-site/` built with Nextra v4 (Next.js App Router). Deployable to Vercel.

**25 pages across 4 sections:**

| Section | Pages |
|---|---|
| **Getting Started** | Introduction, Getting Started |
| **Guides** (6) | End-to-End Tutorial, Build a Custom Agent, Writing Strategies, Multi-Agent Teams, Accept Payments, Go On-Chain |
| **Features** (11) | LLM Planner, Data Layer, Memory Architecture, Autoresearch, A2A Communication, x402 Payments, MCP Integration, Wallets, On-Chain Registry, Attestation & Trust, Security |
| **Reference** (5) | CLI Reference, Configuration Reference, Artifact System, Skills & Registries, Open Agent Economy |

**Key capabilities:**
- Built-in Nextra "Copy page" dropdown on every page (Copy as Markdown, Open in ChatGPT, Open in Claude)
- Copy button on all code blocks (`defaultShowCopyCode: true`)
- `sourceCode` prop passed through catch-all MDX page for full copy support
- Pagefind search indexing (postbuild)
- Dark/light mode with adaptive logos

### 3. Video walkthroughs (25 unique videos)

Every docs page has a unique video embedded below the title. Videos are Remotion-rendered Apple-style feature walkthroughs.

| Video | Content |
|---|---|
| 00-hero | Brand reel |
| 01-walkthrough | Step-by-step agent creation |
| 02-user-flow | Install to production journey (11 steps) |
| 03-agent-generation | Generation flags, auto-detect, validation |
| 04-llm-planner | Prompt assembly, typed output, model swap, runtime loop |
| 05-data-layer | Fallback chain, token registry, cost tracking |
| 06-memory | SQLite diary, MemPalace knowledge graph |
| 07-autoresearch | Self-evaluation, mutation proposals |
| 08-a2a-communication | Agent Cards, task delegation, multi-agent chains |
| 09-x402-payments | Pay-per-call, accept payments, budget caps |
| 10-mcp-integration | Config-driven tool servers |
| 11-wallets | 9-chain OWS, encrypted backup, fund & sign |
| 12-onchain-registry | ERC-8004 mint, discovery |
| 13-attestation | Self-attestation, 3 trust tiers |
| 14-security | 8-point audit, kill switch |
| 15-multi-agent | 3-agent team coordination |
| 16-custom-agent-flow | Full 14-step customization walkthrough |
| 17-intro-overview | Architecture: loop, prompt, artifacts, promotion |
| 18-strategy-writing | Strategy patterns, memory instructions, live edit |
| 19-accept-payments | Payment gate setup, 402 flow, revenue tracking |
| 20-go-onchain | Fund wallet, register, discover |
| 21-cli | Generate, run, agents, security commands |
| 22-artifacts | Spec, capabilities, policy artifacts |
| 23-skills | 3 registries, Elsa endpoints, auto-map |
| 24-open-agent-economy | ERC-8004/8126/8183, x402, A2A stack |

All videos include "by [Elsa logo]" in the outro (white variant for dark backgrounds, using Remotion's `<Img>` + `staticFile()`).

### 4. HeyElsa branding

- **Docs site footer**: "2026 Aether Forge | by [Elsa logo]" linking to heyelsa.ai
- **Docs site homepage**: "by [Elsa logo]" under the title
- **Video outros**: "by [Elsa logo]" at 50% opacity in all 25 videos
- **Light/dark mode**: `<picture>` with `prefers-color-scheme` swaps between white-text SVG (dark mode) and dark-text SVG (light mode). Elsa logo dark variant only changes the wordmark fill — icon/mascot stays red+white.
- **Logo files**: `elsa-logo.svg` (white text), `elsa-logo-dark.svg` (dark text, icon unchanged), `logo.svg` (Aether Forge white), `logo-dark.svg` (Aether Forge dark)

### 5. Install from source workflow

Package is not yet on PyPI. All install instructions updated to use GitHub:

```bash
# Primary install method
pip install 'aether-forge[all] @ git+https://github.com/HeyElsa/aether-forge.git'

# Or clone locally
git clone https://github.com/HeyElsa/aether-forge.git
cd aether-forge
pip install -e '.[all]'
```

PyPI instructions kept as "coming soon" below the GitHub instructions.

**Updated in**: README.md, docs-site intro, Getting Started, End-to-End Tutorial, Build a Custom Agent.

### 6. Expanded demo script (17 sections)

`demo.sh` expanded from 10 to 17 sections:

| # | Section | Status |
|---|---|---|
| 0 | Setup + doctor | existing |
| 1 | Browse skills + pick LLM + write strategy | existing |
| 2 | Generate + inspect + confirm LLM + wire MCP | existing |
| 3-6 | Validate, eval, wallet, security | existing |
| 7 | Paper run (LLM ticks, autoresearch, memory L3+L4) | existing |
| 8 | Live run (real x402 on Base) | existing |
| 9 | Kill switch | existing |
| 10 | Encrypted backup | existing |
| **11** | **Agent registry** (agent-list, agent-info) | **new** |
| **12** | **A2A communication** (Agent Cards, EIP-712, tasks) | **new** |
| **13** | **On-chain ERC-8004 registration** (mint NFT on Base) | **new** |
| **14** | **Attestation & trust tiers** | **new** |
| **15** | **Agent-to-agent payments** (x402, transfer, escrow) | **new** |
| **16** | **Multi-agent teams** (3 agents coordinating) | **new** |
| **17** | **Docs site** (Nextra, Vercel, videos) | **new** |

---

## Files Changed

### New files
- `docs-site/` — complete Nextra v4 documentation site (67 files)
- `docs/prd/aether-forge-prd-v0.18.0.md` — this PRD
- `video/src/features/docs-videos.ts` — 8 new video definitions for docs pages
- `video/src/features/custom-agent-flow.ts` — custom agent flow video

### Modified files
- `src/aether_forge/config.py` — auto-detect provider API keys from env vars
- `demo.sh` — 7 new sections (11-17)
- `README.md` — install-from-GitHub as primary method
- `video/src/FeatureVideo.tsx` — HeyElsa branding in outro
- `video/src/scenes/Outro.tsx` — HeyElsa branding in hero outro
- `video/src/scenes/walkthrough/Steps.tsx` — HeyElsa branding in walkthrough outro
- `video/src/Root.tsx` — 8 new compositions (17-24)

---

## Verification

- [x] OpenRouter + Claude Sonnet 4: generate → validate → paper trade (2 ticks, 30 steps)
- [x] Docs site: `next build` → 28 static pages, 0 errors
- [x] All 25 routes return HTTP 200
- [x] Each docs page has a unique video (0 duplicates)
- [x] Copy page dropdown works (Copy, Open in ChatGPT, Open in Claude)
- [x] Light/dark logo switching via `<picture>` + `prefers-color-scheme`
- [x] demo.sh runs end-to-end with `DEMO_AUTO=1 DEMO_SKIP_LIVE=1`

---

## What's Next (v0.19.0 candidates)

1. **Publish to PyPI** — `pip install aether-forge` from the public registry
2. **Beginner-friendly docs** — rewrite for zero-to-pro audience (explain EIP-712, A2A, MCP before using them)
3. **Vercel deployment** — deploy docs-site to production URL
4. **Video hosting** — move 89MB of videos to CDN (currently in git)
5. **XMTP encrypted transport** — optional Layer 2 for E2E encrypted agent messaging

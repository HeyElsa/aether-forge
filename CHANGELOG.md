# Changelog

User-facing changes to Aether Forge. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased] — 2026-04-16

### Added
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

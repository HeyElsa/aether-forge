---
name: forge-agent-builder
description: Build, run, and promote a governed trading/automation agent with Aether Forge (HeyElsa). Use when the user wants to turn a strategy or idea into a deployed agent, scaffold a Forge project, debug a Forge agent run (planner fallbacks, policy holds), or walk the validate → eval → run → promote lifecycle.
---

# Build agents with Aether Forge

Aether Forge (github.com/HeyElsa/aether-forge) turns a plain-language strategy into a governed agent: typed JSON artifacts + policy gate + scenario evals + a tick-based runtime with replays. Binary: `forge`. Note: Foundry's Ethereum tool is also named `forge` -- inside an activated venv Aether's binary wins; outside it, call the venv's `bin/forge` path directly if Foundry shadows it.

## Install & verify

```bash
pip install 'aether-forge[all] @ git+https://github.com/HeyElsa/aether-forge.git'  # needs Python 3.12+
forge doctor   # 8/8 healthy expected; first run may download an embedding model (~80MB)
```

CAUTION: `forge doctor` does NOT verify the cloud API key the planner will use. A "Healthy" doctor does not mean the LLM planner works — verify with a 1-tick run (below).

## The lifecycle (always this order)

```bash
# 1. Generate from the user's strategy (markdown file preferred over --idea alone)
forge generate-fast --name "<Agent Name>" --idea "<one-line summary>" \
    --strategy-file ./strategy.md --output ./my-agent

# 2. Validate artifacts (5 required: agent-spec, capability-manifest, policy-bundle, scenario-pack, scaffold.manifest)
forge validate ./my-agent

# 3. Run the scenario pack
forge eval-pack ./my-agent

# 4. One governed tick in the sandbox (offline-safe, mock data)
forge run ./my-agent --max-ticks 1 --interval 0 --environment sandbox --mode paper --auto-approve

# 5. Continuous paper run with observability
forge run ./my-agent --interval 30 --environment sandbox --mode paper --auto-approve \
    --health-port 8080 --json-log ./logs/agent.jsonl

# 6. Promote on evidence (writes promotion-record.json; needs planner env var set)
forge promote-draft ./my-agent --target paper --approver "<name>"
```

`--environment` (sandbox/paper/canary-live/production) controls POLICY strictness; `--mode` (paper/live/simulated) controls the TRADING backend. They are independent axes.

## After generation: verify the strategy actually transferred

Read `<agent>/strategy.json`. If `entry_rules_provenance` is `"template_default"` or the entry rules look like generic momentum rules the user never wrote, the regex parser failed to extract the user's strategy — the typed layer is running a TEMPLATE. The prose in `strategy-description.md` still drives the LLM planner, but heuristic fallback and autoresearch use the typed rules. Tell the user, and tighten `strategy.md` toward explicit `BUY/SELL when <condition>` clauses, or hand-edit `strategy.json`.

Also review `policy-bundle.json`: generated caps (e.g. `maxNotionalUsd`) are TEMPLATE DEFAULTS, not derived from the strategy's own risk language. Set them to the user's actual limits before any non-sandbox run.

## Planner configuration (the #1 new-user failure)

The generator auto-detects a planner from env keys (ANTHROPIC_API_KEY → OPENAI_API_KEY → GOOGLE/GEMINI → OPENROUTER → local Ollama → heuristic) and bakes it into `<agent>/aether-forge.json`. A present-but-unfunded key autodetects fine and then fails at runtime.

Diagnose: run 1 tick, then check the JSONL/replays for `planner.fallback` events:
- `kind: model-error` + `HTTPError 400/401/429` → key invalid, unfunded, or out of quota. Check the event's `responsePreview` for the provider's message; if it is null (builds without the error-body capture), curl the provider directly with the same key to read the real error.
- `kind: parse-failure` → model returned non-JSON; try a stronger model or `planner.toolMode: true` (Anthropic/OpenAI only).
- IMPORTANT: fallback ticks still print `[ ok ] Tick N: complete` — the run continuing does NOT mean the LLM planned it. Zero `planner.fallback` events = healthy.

Any OpenAI-compatible endpoint works (verified with Fireworks):

```json
{"planner": {"mode": "openai-compatible", "model": "<provider-model-id>",
  "baseUrl": "https://api.fireworks.ai/inference/v1", "apiKeyEnv": "FIREWORKS_API_KEY",
  "source": "explicit"}}
```

## Operating a running agent

```bash
forge replays ./my-agent                 # list tick replays
forge replay-show ./my-agent/replays/tick_0003.json   # full step ledger with reasoning
forge strategy view ./my-agent           # current params + pending self-improvement proposals
forge strategy accept|reject ./my-agent  # review autoresearch proposals
forge halt ./my-agent                    # kill switch (blocks all outbound side effects)
forge resume ./my-agent                  # clear kill switch after review
curl localhost:8080/ready                # deep health (503 = planner failing or halted)
```

## Gotchas (verified)

- `make test` inside a generated agent needs pytest in the SAME interpreter that has aether-forge: `make test PYTHON=.venv/bin/python` (older templates run bare `pytest` and fail with ModuleNotFoundError).
- `promote-draft` constructs the planner, so the planner's API-key env var must be set even though promotion itself is offline.
- Tick counters and memory persist across runs in `memory.db` — delete it (or `make clean`) for a fresh start; it survives process restarts by design.
- Side-effecting capabilities default to DENY. In sandbox/paper, `--auto-approve` retries held steps; in production, holds wait for a real approver.
- Wallets/x402/on-chain (`--wallet`, `agent-register`, `x402-call`) move real value on Base mainnet — never enable outside sandbox/paper without the user's explicit confirmation, conservative `x402_budget`, and a tested `forge halt`.

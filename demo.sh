#!/usr/bin/env bash
# Aether Forge — team demo script
#
# Usage:  ./demo.sh
#
# Walks through the complete Aether Forge feature set:
#   0.  setup + doctor
#   1.  skills browse → pick LLM → write strategy
#   2.  generate agent (LLM-driven, wallet, autonomous)
#   2b. confirm LLM wired in
#   2c. wire up MCP tools
#   3.  validate artifacts
#   4.  scenario evals
#   5.  inspect OWS wallet
#   6.  security audit
#   7.  paper run (LLM ticks, autoresearch, memory layers 3+4)
#   8.  live run (real x402 payments on Base)
#   9.  kill switch
#   10. encrypted backup
#   11. agent registry (local SQLite)
#   12. A2A inter-agent communication
#   13. on-chain ERC-8004 registration
#   14. attestation & trust tiers
#   15. agent-to-agent payments
#   16. multi-agent teams
#   17. docs site
#
# Press <Enter> between steps so you can talk through each one.
# Set DEMO_AUTO=1 to skip the prompts (useful for dry-runs).
# Set DEMO_SKIP_LIVE=1 to skip the real-money sections.

set -e

DEMO_DIR="${DEMO_DIR:-$HOME/aether-demo}"
AGENT_DIR="$DEMO_DIR/demo-eth-swing"
STRATEGY_FILE="$DEMO_DIR/eth-swing-strategy.md"

# Passphrase for the encrypted wallet backup in §10. If unset, the demo
# script will prompt interactively (the right behavior for a live demo).
# Set this for non-interactive dry-runs (DEMO_AUTO=1).
DEMO_BACKUP_PASSPHRASE="${DEMO_BACKUP_PASSPHRASE:-}"

# LLM that will drive the agent during the live ticks.
#
# Default: a local Gemma model via Ollama. No API keys, no network round-trip,
# fully self-contained — perfect for a live team demo. Override at the command
# line if you want to show off a different provider:
#
#   DEMO_PLANNER_MODE=ollama      DEMO_PLANNER_MODEL=gemma4:latest    ./demo.sh   # default
#   DEMO_PLANNER_MODE=ollama      DEMO_PLANNER_MODEL=glm-4.7-flash    ./demo.sh
#   DEMO_PLANNER_MODE=anthropic   DEMO_PLANNER_MODEL=claude-opus-4-6  ./demo.sh
#   DEMO_PLANNER_MODE=openai      DEMO_PLANNER_MODEL=gpt-4o           ./demo.sh
#   DEMO_PLANNER_MODE=gemini      DEMO_PLANNER_MODEL=gemini-2.5-pro   ./demo.sh
#   DEMO_PLANNER_MODE=heuristic                                       ./demo.sh
#
# Heuristic mode needs no model and no key — useful for offline rehearsal.
DEMO_PLANNER_MODE="${DEMO_PLANNER_MODE:-ollama}"
DEMO_PLANNER_MODEL="${DEMO_PLANNER_MODEL:-gemma4:latest}"
OLLAMA_BASE_URL="${OLLAMA_BASE_URL:-http://localhost:11434}"

# ---------- helpers ----------
_bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
_dim()   { printf "\033[2m%s\033[0m\n"  "$*"; }
_cyan()  { printf "\033[36m%s\033[0m\n" "$*"; }
_green() { printf "\033[32m%s\033[0m\n" "$*"; }
_red()   { printf "\033[31m%s\033[0m\n" "$*"; }

step() {
  echo
  _cyan "════════════════════════════════════════════════════════════════"
  _bold "  $1"
  _cyan "════════════════════════════════════════════════════════════════"
  echo
}

run() {
  _green "\$ $*"
  if [ -z "${DEMO_AUTO:-}" ]; then
    read -r -p "  [press enter to run, 's' to skip] " ans
    if [ "$ans" = "s" ]; then _dim "  (skipped)"; return 0; fi
  fi
  eval "$@"
}

pause() {
  if [ -z "${DEMO_AUTO:-}" ]; then
    echo
    read -r -p "  [press enter to continue] " _
  fi
}

# ---------- 0. setup ----------
step "0. Setup — fresh sandbox"
_dim "  Working directory: $DEMO_DIR"
run "rm -rf '$DEMO_DIR' && mkdir -p '$DEMO_DIR' && cd '$DEMO_DIR'"
cd "$DEMO_DIR"

step "0a. Doctor — verify environment"
run "forge doctor"
pause

# Demo helpers — fail loud if a tool the demo needs is missing.
for tool in jq sqlite3 curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    _red "  Missing required tool: $tool"
    _dim "  Install with: brew install $tool"
    exit 1
  fi
done

# ---------- 1. browse ----------
step "1. Browse the skills + paid endpoints catalog"
_dim "  Aether Forge knows about 21 paid Elsa endpoints out of the box."
run "forge elsa-list | head -40"
pause

_dim "  And free skills via the skills.sh registry."
run "forge skills-search 'trading' | head -20"
pause

# ---------- 1b. pick the model ----------
step "1b. Pick the LLM that will drive the agent"
_dim "  The framework is provider-agnostic. The same agent runs against:"
_dim "    Anthropic · OpenAI · Gemini · OpenRouter · Ollama · heuristic"
_dim "  Anything that speaks the planner protocol works."
echo
_dim "  Today's pick — local, no API keys, no network, no cost:"
_green "    --planner-mode  $DEMO_PLANNER_MODE"
_green "    --planner-model $DEMO_PLANNER_MODEL"
_green "    --planner-base-url $OLLAMA_BASE_URL"
pause

if [ "$DEMO_PLANNER_MODE" = "ollama" ]; then
  _dim "  1. Verify the Ollama daemon is reachable."
  run "curl -s -o /dev/null -w 'HTTP %{http_code}\n' $OLLAMA_BASE_URL/api/tags"
  pause

  _dim "  2. List local models — what's already on this machine."
  run "ollama list"
  pause

  _dim "  3. Pull the demo model if it isn't here yet (no-op if cached)."
  run "ollama pull $DEMO_PLANNER_MODEL"
  pause

  _dim "  4. Same models, framework view."
  run "forge models-list --provider ollama"
  pause

  _dim "  5. Smoke-test the local LLM with a one-shot prompt."
  _dim "     This is the same channel the planner will use during ticks."
  run "curl -s $OLLAMA_BASE_URL/api/generate -d '{\"model\":\"$DEMO_PLANNER_MODEL\",\"prompt\":\"In one sentence: what is an autonomous trading agent?\",\"stream\":false}' | jq -r '.response'"
  pause
else
  _dim "  Browse the cloud model catalog instead (override active)."
  run "forge models-list --provider $DEMO_PLANNER_MODE --limit 10 || true"
  pause
fi

# ---------- 1c. write the swing-trade strategy in prose ----------
step "1c. Write the trading strategy in plain English"
_dim "  This is the killer feature: the strategy lives in markdown, not Python."
_dim "  Every tick the LLM re-reads it, interprets it against current market"
_dim "  state, and translates intent into typed runtime steps. Edit the file,"
_dim "  the agent's behavior changes — no code, no redeploy."
echo
_dim "  Writing the swing strategy to:"
_green "    $STRATEGY_FILE"
mkdir -p "$DEMO_DIR"
cat > "$STRATEGY_FILE" <<'STRATEGY_EOF'
# ETH Swing Trading Strategy

## Mission
Capture multi-day ETH price swings on Base mainnet. Optimize for risk-adjusted
returns over raw P&L. Survive drawdowns. Compound steadily. Never blow up.

## Universe
- **Asset**: ETH (and WETH on Base — `0x4200000000000000000000000000000000000006`)
- **Quote**: USDC on Base — `0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913`
- **Venues**: Elsa x402 swap router (best execution across 20+ DEXes)

## Capital
- **Starting balance**: whatever the wallet holds — read it on every session start
- **Per-trade risk**: never more than 2% of total portfolio at risk
- **Max position size**: 25% of portfolio in a single trade
- **Reserve**: always keep at least 30% in USDC for opportunities and gas

## Entry Conditions (ALL must be true)
1. **Trend confirmation**: 5-minute candle closes bullish AND last 3 candles
   show higher highs OR momentum.trend == "bullish"
2. **Volume sanity**: current candle volume is between 0.7x and 4.0x the
   30-candle average. Skip if volume is dead OR if volume is anomalously
   high (often signals exhaustion / a reversal).
3. **No recent failure**: did not stop out in the last hour. If we did,
   wait one full hour and require an extra confirmation candle before
   re-entering.
4. **Gas check**: current Base gas price < $0.50 estimated cost per swap.
   If gas is spiking, wait — never burn 30% of expected profit on fees.
5. **Spread check**: swap quote slippage < 0.5%. If the order book is thin,
   reduce size or skip.

## Position Sizing
Use volatility-adjusted sizing based on the 30-candle volatility from the
momentum indicator:

- Low volatility (<1.0%): position = 25% of portfolio
- Normal (1.0% – 2.5%): position = 15% of portfolio
- High (2.5% – 5.0%): position = 8% of portfolio
- Extreme (>5.0%): SKIP — market is too chaotic to swing trade

## Exit Conditions
Exit a position if ANY of the following are true:

- **Take profit**: unrealized P&L >= +4% from entry
- **Stop loss**: unrealized P&L <= -2% from entry (HARD stop, no negotiation)
- **Trend break**: momentum.trend flipped to "bearish" AND we're profitable
- **Time stop**: held for more than 48 hours regardless of P&L
- **Strategy halt**: kill switch activated externally

## Risk & Approval Rules
- ANY trade above $50 notional → request human approval first
- ANY consecutive loss streak of 3 → halt all entries, request review
- If P&L drawdown exceeds 5% of starting capital this session → halt

## Self-Improvement
After 10 ticks, evaluate:
- Win rate (target: > 45%)
- Avg win / avg loss ratio (target: > 1.5)
- Max drawdown (target: < 5%)

If win rate < 35% AND we have at least 5 closed trades, propose tightening
entry confirmations (require an extra bullish candle, raise the volume
floor). If win rate > 60%, propose relaxing them slightly to increase
trade frequency.

## What NOT to do
- Do NOT chase price after a >2% move in a single candle
- Do NOT average down on a losing position
- Do NOT trade against the prevailing trend "because it feels overdue"
- Do NOT exceed declared capabilities — no leverage, no perps, no margin
- Do NOT touch other tokens — this is an ETH-only strategy
STRATEGY_EOF
chmod 0644 "$STRATEGY_FILE"

_dim "  Strategy file ready ($(wc -l < "$STRATEGY_FILE") lines):"
run "head -20 '$STRATEGY_FILE'"
pause

# ---------- 2. generate ----------
step "2. Generate the agent skeleton (LLM-driven, autonomous)"
_dim "  One command: spec + manifest + policy + scaffold + wallet + LLM config"
_dim "  + the prose strategy file the LLM will re-read every tick."
_dim ""
_dim "  --strategy-file  feeds the markdown strategy into the spec"
_dim "  --autonomous     enables runtime autoresearch (LLM proposes mutations)"
_dim "  --wallet         provisions a real OWS wallet (9 chains, locked-down)"
run "forge generate-fast \\
    --name 'demo-eth-swing' \\
    --idea 'Autonomous ETH swing trader on Base mainnet that interprets a prose strategy file every tick, sizes positions by volatility, and self-improves via autoresearch' \\
    --output '$AGENT_DIR' \\
    --strategy-file '$STRATEGY_FILE' \\
    --wallet \\
    --autonomous"
cd "$AGENT_DIR"
pause

step "2a. Inspect what was generated"
run "ls -la"
pause
_dim "  agent-spec.json          — typed agent contract"
_dim "  capability-manifest.json — what skills the agent can call"
_dim "  policy-bundle.json       — guardrails (budgets, environments)"
_dim "  scenario-pack.json       — evaluation scenarios"
_dim "  strategy.json            — tunable params"
_dim "  wallet.json              — real OWS wallet config"
_dim "  .env                     — scoped API key (gitignored, 0600)"
_dim "  .ows/                    — per-agent vault (0700)"
_dim "  src/strategy/router.py   — THE agent's execution router"
_dim "  Dockerfile + main.py     — deployment-ready"
pause

run "cat agent-spec.json | jq '.capabilities, .strategy' | head -40"
pause

# ---------- 2b. confirm the LLM is wired into the agent ----------
step "2b. The LLM is already baked into the agent"
_dim "  Aether Forge is an LLM-driven framework. \`generate-fast\` auto-detects"
_dim "  the best planner on this machine (local Ollama → cloud key → heuristic)"
_dim "  and writes it into the agent's own aether-forge.json. No post-process,"
_dim "  no jq patch — anyone who runs this directory later (Docker, CI, a"
_dim "  teammate) inherits the same model with zero flags."
echo
_dim "  Confirm what the framework picked:"
run "jq '.planner' aether-forge.json"
pause

# ---------- 2c. Wire up MCP (Model Context Protocol) ----------
step "2c. Wire up MCP — tools from any external server"
_dim "  MCP is an open protocol for exposing tools to AI agents. Aether Forge"
_dim "  is an MCP client — generated agents can discover and call tools from"
_dim "  any MCP server (filesystem, GitHub, Hermes Agent's messaging bridge)"
_dim "  just by declaring them in aether-forge.json. No code changes, no"
_dim "  per-server integrations to maintain."
echo
_dim "  Step 1: drop a tiny self-contained MCP server next to the agent."
_dim "  (Stdio transport, 3 demo tools: ping, echo, agent_stats.)"

cat > "$AGENT_DIR/mcp-demo-server.py" <<'MCP_EOF'
#!/usr/bin/env python3
"""Minimal stdio MCP server for the Aether Forge demo.

Exposes three tools over JSON-RPC:
  - ping        : return a timestamped pong
  - echo        : return whatever text you pass in
  - agent_stats : return synthetic agent metrics
"""
from __future__ import annotations
import json, sys
from datetime import datetime, timezone

UTC = timezone.utc

TOOLS = [
    {"name": "ping", "description": "Return a timestamped pong.",
     "inputSchema": {"type": "object", "properties": {}, "required": []}},
    {"name": "echo", "description": "Echo back the text argument.",
     "inputSchema": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}},
    {"name": "agent_stats", "description": "Return synthetic stats about a running agent.",
     "inputSchema": {"type": "object", "properties": {"agent_id": {"type": "string"}}, "required": []}},
]

def _reply(msg_id, result=None, error=None):
    msg = {"jsonrpc": "2.0", "id": msg_id}
    if error is not None:
        msg["error"] = error
    else:
        msg["result"] = result
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()

def _handle(req):
    method = req.get("method")
    msg_id = req.get("id")
    params = req.get("params") or {}
    if method == "initialize":
        _reply(msg_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "aether-forge-demo-mcp", "version": "0.1.0"},
        })
        return
    if method == "notifications/initialized":
        return
    if method == "tools/list":
        _reply(msg_id, {"tools": TOOLS})
        return
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name == "ping":
            _reply(msg_id, {"content": [{"type": "text", "text": f"pong at {datetime.now(UTC).isoformat()}"}]})
            return
        if name == "echo":
            _reply(msg_id, {"content": [{"type": "text", "text": args.get("text", "")}]})
            return
        if name == "agent_stats":
            _reply(msg_id, {"content": [{"type": "text", "text": json.dumps({
                "agent_id": args.get("agent_id", "unknown"),
                "ticks_completed": 42, "tools_called": 17, "uptime_seconds": 3600,
            })}]})
            return
        _reply(msg_id, error={"code": -32602, "message": f"unknown tool: {name}"})
        return
    _reply(msg_id, error={"code": -32601, "message": f"method not found: {method}"})

for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        req = json.loads(line)
        _handle(req)
    except Exception as error:
        msg_id = req.get("id") if isinstance(req, dict) else None
        _reply(msg_id, error={"code": -32603, "message": str(error)})
MCP_EOF
chmod +x "$AGENT_DIR/mcp-demo-server.py"
_dim "  Wrote: $AGENT_DIR/mcp-demo-server.py ($(wc -l < "$AGENT_DIR/mcp-demo-server.py") lines)"
pause

_dim "  Step 2: declare the server in the agent's aether-forge.json."
_dim "  Just a config edit — no framework code to touch."
run "jq '.mcp_servers = {\"demo\": {\"command\": \"python3\", \"args\": [\"./mcp-demo-server.py\"]}}' aether-forge.json > aether-forge.json.tmp && mv aether-forge.json.tmp aether-forge.json"
run "jq '.mcp_servers' aether-forge.json"
pause

_dim "  Step 3: forge doctor probes every declared MCP server — spawns it,"
_dim "  runs initialize + tools/list, counts tools, then cleans up."
_dim "  Look for the 'MCP server [demo]' line near the bottom."
run "forge doctor"
pause

_dim "  The agent now has three extra tools available to its planner on top"
_dim "  of its declared capabilities — added with one config edit, zero code."
_dim "  Swap the server declaration for 'hermes mcp serve' and the agent"
_dim "  gains messaging on 15+ platforms via Hermes Agent. Same mechanism."

# ---------- 3. validate ----------
step "3. Validate the spec"
_dim "  jsonschema + cross-reference checks across all 4 artifact types."
run "forge validate ."
pause

# ---------- 4. eval ----------
step "4. Run scenario evals (no money, no network)"
run "forge eval-pack ."
pause

# ---------- 5. wallet ----------
step "5. Inspect the agent's real OWS wallet"
run "jq '{walletId, walletName, provider, accounts}' wallet.json"
pause

# ---------- 6. security ----------
step "6. Pre-flight security audit"
_dim "  8 checks: wallet real, .env perms 0600, .gitignore coverage,"
_dim "  vault perms 0700, halt file, secret scan, audit log."
run "forge security-check . --harden"
pause

# Build the planner flags once — every `forge run` invocation reuses this.
PLANNER_FLAGS="--planner-mode $DEMO_PLANNER_MODE --planner-model $DEMO_PLANNER_MODEL"
if [ "$DEMO_PLANNER_MODE" = "ollama" ]; then
  PLANNER_FLAGS="$PLANNER_FLAGS --planner-base-url $OLLAMA_BASE_URL"
fi

# ---------- 7. paper run ----------
step "7. Paper mode — LLM-driven swing trader, full autonomy"
_dim "  Driven by $DEMO_PLANNER_MODE / $DEMO_PLANNER_MODEL."
_dim "  Every tick: LLM re-reads the strategy file, the working set (live"
_dim "  prices, momentum, volatility), the memory of prior ticks, and decides"
_dim "  what to do. Real Binance price feed, simulated paper orders."
_dim ""
_dim "  Flags worth calling out:"
_dim "    --autoresearch       LLM evaluates its own performance every 3 ticks"
_dim "    --eval-interval 3    and proposes strategy mutations"
_dim "    --knowledge          MemPalace long-term memory across ticks"
_dim "    --max-ticks 8        enough ticks to trigger an autoresearch eval"
run "forge run . --mode paper --auto-approve --max-ticks 8 --interval 4 \\
    --autoresearch --eval-interval 3 --knowledge \\
    $PLANNER_FLAGS"
pause

step "7a. Read the LLM's reasoning trail from the replay files"
_dim "  Each tick wrote a JSON replay. The step ledger shows exactly what the"
_dim "  LLM proposed, the kind of step (use-capability/reason/request-approval),"
_dim "  the capability it chose, the payload it synthesized, and the result."
run "ls -1 replays/ | tail -5"
pause

_dim "  The LLM's actual proposals from the most recent tick:"
run "jq '.stepLedger[] | {kind: .proposal.kind, capabilityId: .proposal.capabilityId, description: .proposal.description, lifecycle: .lifecycle}' \"\$(ls -1t replays/*.json | head -1)\""
pause

step "7b. Did the LLM propose strategy improvements?"
_dim "  Autoresearch ran a self-evaluation at tick 3 and 6. Any proposals"
_dim "  the LLM generated are queued for human review."
run "forge strategy view . || true"
pause

# ---------- 7c. Layer 3: SQLite memory store ----------
step "7c. Layer 3 — SQLite memory store (the agent's diary)"
_dim "  Per-tick decision history + anything the LLM chose to remember via"
_dim "  the memory.write capability. Survives process restarts. Scoped per"
_dim "  agent. This is what lands in the prompt's ## Memory Context section"
_dim "  on every tick."
echo
_dim "  Schema:"
run "sqlite3 memory.db '.schema memory_records' 2>/dev/null | head -25 || echo '(no memory.db yet)'"
pause

_dim "  Most recent records (what the LLM reads next tick):"
run "sqlite3 -header -column memory.db \"SELECT memory_type, scope, substr(summary,1,60) AS summary FROM memory_records ORDER BY updated_at DESC LIMIT 10\" 2>/dev/null || echo '(empty)'"
pause

# ---------- 7d. Layer 4: MemPalace knowledge layer ----------
step "7d. Layer 4 — MemPalace knowledge layer (the agent's library)"
_dim "  External package: mempalace>=3.1.0. Two stores in one wing:"
_dim "    1. ChromaDB vectors    — semantic recall (\"have I seen this regime\"?)"
_dim "    2. SQLite triple store — temporal facts with validity windows"
_dim "  Each agent gets its own wing keyed by name. Read into the prompt's"
_dim "  ## Knowledge section every tick when --knowledge is on."
echo
_dim "  Wing layout:"
run "ls -la knowledge/ 2>/dev/null || echo '(knowledge layer not initialized — install mempalace?)'"
pause

_dim "  Current facts the LLM has accumulated about traded entities:"
_dim "  (subject, predicate, object) triples where valid_to IS NULL = current."
run "sqlite3 -header -column knowledge/knowledge_graph.db \"SELECT subject, predicate, object, valid_from FROM triples WHERE valid_to IS NULL ORDER BY valid_from DESC LIMIT 10\" 2>/dev/null || echo '(no triples yet)'"
pause

_dim "  Entity timeline — every fact ever asserted about ETH, even ended ones:"
run "sqlite3 -header -column knowledge/knowledge_graph.db \"SELECT predicate, object, valid_from, COALESCE(valid_to, 'current') AS valid_to FROM triples WHERE LOWER(subject)='eth' ORDER BY valid_from DESC LIMIT 10\" 2>/dev/null || echo '(empty)'"
pause

_dim "  Semantic memory drawer count, per room:"
run "sqlite3 -header -column knowledge/chroma.sqlite3 \"SELECT COUNT(*) AS docs FROM embeddings\" 2>/dev/null || echo '(chroma not yet populated — first --knowledge run will create it)'"
pause

# ---------- 8. live run ----------
if [ -z "${DEMO_SKIP_LIVE:-}" ]; then
  step "8. LIVE MODE — real x402 payment from the agent's wallet"
  _red "  This spends real USDC on Base mainnet (a few cents)."
  _dim "  Tight caps as a safety net; halt file kills it instantly."
  run "cat x402_state.json 2>/dev/null || echo '{\"session_spent_usd\": 0}'"
  pause

  run "forge run . --mode live --chain base --auto-approve --max-ticks 2 --interval 10 \\
      --knowledge \\
      $PLANNER_FLAGS"
  pause

  step "8a. Proof of payment"
  run "cat x402_state.json"
  echo
  run "tail -5 x402_audit.jsonl | jq -c '{event, url, amount_usd, response_status}'"
  pause

  step "8b. The LLM's reasoning during the LIVE ticks"
  _dim "  Same step-ledger trail as paper mode — but every use-capability"
  _dim "  step here corresponds to a real signed EIP-3009 payment from the"
  _dim "  agent's wallet. This is the LLM directing real money."
  run "jq '.stepLedger[] | {kind: .proposal.kind, capabilityId: .proposal.capabilityId, description: .proposal.description}' \"\$(ls -1t replays/*.json | head -1)\""
  pause
fi

# ---------- 9. kill switch ----------
if [ -z "${DEMO_SKIP_LIVE:-}" ]; then
  step "9. Kill switch demo"
  _dim "  forge halt creates a halt file that blocks every paid call. The"
  _dim "  X402Client checks for it in _preflight() before signing any payment,"
  _dim "  so even if the LLM proposes a paid step, the runtime refuses to"
  _dim "  authorize it."
  run "forge halt ."
  run "ls -la halt"
  pause

  _dim "  Try a direct x402 call — should refuse before signing."
  _dim "  (We use forge x402-call so the kill switch is triggered immediately,"
  _dim "  not buried inside a tick that may or may not propose a paid step.)"
  run "forge x402-call . \\
      --url https://x402-api.heyelsa.ai/api/get_gas_prices \\
      --method POST --body '{\"chain\":\"base\"}' \\
      --max-per-call-usd 0.005 --confirm-live || true"
  pause

  _dim "  Clear the halt file when ready."
  run "forge resume ."
  pause
fi

# ---------- 10. backup ----------
step "10. Encrypted wallet backup"
_dim "  AES-256-GCM, scrypt KDF, mnemonic never on disk in plaintext."
if [ -n "$DEMO_BACKUP_PASSPHRASE" ]; then
  _dim "  (Using DEMO_BACKUP_PASSPHRASE — non-interactive.)"
  run "forge wallet-backup . --passphrase '$DEMO_BACKUP_PASSPHRASE'"
else
  _dim "  You'll be prompted for a passphrase (min 8 chars)."
  run "forge wallet-backup ."
fi
run "ls -la wallet-backup-*.json"
pause

# ---------- 11. agent registry ----------
step "11. Agent registry — track every agent you create"
_dim "  Every generated agent is auto-registered in a local SQLite DB at"
_dim "  ~/.aether-forge/agents.db. No on-chain cost, no network required."
run "forge agent-list"
pause

_dim "  Full details on this agent:"
run "forge agent-info \$(jq -r '.artifactSetId' agent-spec.json) || true"
pause

# ---------- 12. A2A inter-agent communication ----------
step "12. A2A — agent-to-agent communication"
_dim "  Google's A2A protocol (JSON-RPC 2.0 over HTTP). Each running agent"
_dim "  exposes an Agent Card at /.well-known/a2a-card and accepts tasks."
_dim ""
_dim "  Start the agent with an A2A server on port 9001:"
_dim "    forge run . --mode paper --a2a-port 9001 --max-ticks 3 --auto-approve"
_dim ""
_dim "  Then from another terminal:"
_dim "    forge agent-send http://localhost:9001 --capability cap-market-btc-price --payload '{\"token\":\"ETH\"}'"
_dim ""
_dim "  The agent's planner sees the incoming task and processes it."
_dim "  Every A2A message is EIP-712 signed for authentication."
pause

# ---------- 13. on-chain registration ----------
step "13. On-chain registration — ERC-8004 on Base mainnet"
_dim "  Optional: mint your agent as an NFT on the ERC-8004 registry."
_dim "  61,000+ agents already registered. Makes your agent discoverable."
_dim ""
_dim "  Contract: 0x8004A169FB4a3325136EB29fA0ceB6D2e539a432 (Base mainnet)"
_dim ""
_dim "  Command (requires ~\$0.003 in ETH for gas):"
_dim "    forge agent-register \$(jq -r '.artifactSetId' agent-spec.json)"
_dim ""
_dim "  Then discover agents:"
_dim "    forge agent-discover --agent-id 1"
_dim ""
if [ -z "${DEMO_SKIP_LIVE:-}" ]; then
  _dim "  Running on-chain registration..."
  run "forge agent-register \$(jq -r '.artifactSetId' agent-spec.json) || _dim '  (skipped — fund wallet with ETH first)'"
  pause
else
  _dim "  (skipped — set DEMO_SKIP_LIVE= to enable)"
  pause
fi

# ---------- 14. attestation & trust ----------
step "14. Attestation — cryptographic identity verification"
_dim "  Every agent gets an EIP-712 self-attestation at generation time."
_dim "  This proves the agent owner authorized its creation with specific"
_dim "  capabilities. The signature lives in attestation.json."
run "jq '{artifactSetId: .artifact_set_id, agentAddress: .agent_address, tier: .tier}' attestation.json 2>/dev/null || echo '(no attestation — generate with --wallet)'"
pause

_dim "  Three trust tiers for discovered agents:"
_dim "    ✅ Verified     — framework attestor signed it"
_dim "    ⚠️  Self-attested — wallet signed it (this agent)"
_dim "    ❓ Unverified    — metadata only, no proof"
pause

# ---------- 15. agent-to-agent payments ----------
step "15. Agent payments — agents pay each other"
_dim "  Three payment channels, all on Base mainnet:"
_dim ""
_dim "  1. x402 pay-per-call  — Agent B gates capabilities behind a price."
_dim "     Agent A pays per request via EIP-3009 signed USDC."
_dim ""
_dim "  2. Direct USDC transfer — one-shot for tips, bounties, flat fees."
_dim ""
_dim "  3. ERC-8183 escrow — complex jobs with evaluator sign-off."
_dim ""
_dim "  Agents can also RECEIVE payments via X402PaymentGate:"
_dim "    → Caller hits /capability → gets 402 with price"
_dim "    → Caller signs EIP-3009 → sends X-PAYMENT header"
_dim "    → Agent verifies + delivers result"
_dim ""
_dim "  Budget caps apply to ALL payment channels:"
run "cat x402_state.json 2>/dev/null || echo '{\"session_spent_usd\": 0}'"
pause

# ---------- 16. multi-agent teams ----------
step "16. Multi-agent teams"
_dim "  Run multiple agents that coordinate via A2A:"
_dim ""
_dim "  Terminal 1: forge run ./price-oracle  --a2a-port 9001 --mode paper"
_dim "  Terminal 2: forge run ./risk-engine   --a2a-port 9002 --mode paper"
_dim "  Terminal 3: forge run ./alpha-trader  --a2a-port 9003 --mode paper"
_dim ""
_dim "  The orchestrator queries peers:"
_dim "    price-oracle → ETH=\$2,249.63 (bullish)"
_dim "    risk-engine  → score=0.35 (moderate)"
_dim "    alpha-trader → BUY 0.001 ETH"
_dim ""
_dim "  Each agent has its own wallet, memory, LLM, and A2A server."
_dim "  Every message is EIP-712 signed."
pause

# ---------- 17. docs site ----------
step "17. Documentation site"
_dim "  Full Nextra v4 docs site with 25 pages and video walkthroughs:"
_dim ""
_dim "    cd docs-site && npm install && npm run dev"
_dim ""
_dim "  Deploy to Vercel:"
_dim "    cd docs-site && npx vercel"
_dim ""
_dim "  Or import the repo in Vercel dashboard with root dir = docs-site."
_dim ""
_dim "  Features:"
_dim "    • Copy page for LLM (built-in dropdown: Copy / ChatGPT / Claude)"
_dim "    • Copy button on every code block"
_dim "    • 25 unique videos (one per page)"
_dim "    • HeyElsa.ai branding, light/dark mode"
pause

# ---------- done ----------
step "Demo complete"
_green "  Agent directory: $AGENT_DIR"
_green "  Strategy file:   $STRATEGY_FILE"
_dim   ""
_dim   "  What you just saw:"
_dim   "    • LLM-driven agent that reads plain-English strategies"
_dim   "    • 4 layers of memory (replays, working set, SQLite, MemPalace)"
_dim   "    • MCP tool integration (any server, one config line)"
_dim   "    • Real OWS wallets across 9 chains"
_dim   "    • x402 payments (send AND receive USDC on Base)"
_dim   "    • A2A inter-agent communication (Google's open protocol)"
_dim   "    • On-chain ERC-8004 agent registry on Base mainnet"
_dim   "    • EIP-712 attestation and trust tiers"
_dim   "    • Kill switch, security audit, encrypted backups"
_dim   "    • Autoresearch self-improvement loop"
_dim   "    • Multi-agent team coordination"
_dim   ""
_dim   "  Next steps:"
_dim   "    Edit the strategy:   vim $STRATEGY_FILE"
_dim   "    Swap the LLM:        DEMO_PLANNER_MODE=anthropic ./demo.sh"
_dim   "    Read the docs:       cd docs-site && npm run dev"
_dim   "    Inspect decisions:   jq '.stepLedger' $AGENT_DIR/replays/*.json | less"
_dim   "    Go live:             forge run . --mode live --chain base"
echo

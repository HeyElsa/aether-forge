
                              ╔═══════════════════════════════════════╗
                              ║          A E T H E R   F O R G E     ║
                              ║    Spec-First Agent Builder Framework ║
                              ╚═══════════════════════════════════════╝

    Idea ──▶ Spec ──▶ Eval ──▶ Production         Pure Python  │  442 Tests  │  45+ CLI Commands


━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  THE PROBLEM                              THE SOLUTION

  Building autonomous agents today         Aether Forge gives every agent a governed,
  means scattered configs, no policy       testable, promotable lifecycle — from a
  enforcement, untested deployments,       plain-language strategy file to production —
  and zero auditability. Moving to         in one CLI. Every tick, an LLM re-reads the
  production is a leap of faith.           strategy, picks from declared capabilities,
                                           and emits typed steps the runtime executes
                                           against four layers of typed memory.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  TWO CREATION MODES

  $ forge generate-fast \                  $ forge generate-slow \
      --name "BTC Basis Trader" \              --name "BTC Basis Trader" \
      --idea "delta-neutral basis" \           --idea "delta-neutral basis" \
      --output ./agent                         --output ./agent --max-iterations 5
      --skills elsa:trading

  ▸ Instant scaffold + 8 artifacts         ▸ Karpathy-style autoresearch loop
  ▸ Auto-detects crypto vs general         ▸ Baseline-first, keep-or-discard
  ▸ Skills from 3 registries               ▸ Research record with iteration ledger

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  WHAT EVERY AGENT INCLUDES

  ┌────────────┬────────────────────┬─────────────────────────────────────────────────────────┐
  │   Layer    │     Standard       │                      What It Does                       │
  ├────────────┼────────────────────┼─────────────────────────────────────────────────────────┤
  │ Planner    │ LLM-driven default │ Auto-detect Ollama/Claude/GPT/Gemini, baked into agent   │
  │ Strategy   │ Markdown / English │ LLM re-reads on every tick, no code change to retune    │
  │ Memory     │ 4 typed layers     │ Replays · working set · SQLite · MemPalace knowledge     │
  │ Tools      │ MCP client         │ Any Model Context Protocol server — stdio or HTTP       │
  │ Agent Comms│ A2A (Google)       │ Agent-to-agent tasks, Agent Cards, JSON-RPC over HTTP   │
  │ Registry   │ ERC-8004 + SQLite  │ On-chain identity on Base + local tracking              │
  │ Trust      │ Attestation        │ Self-attested / verified tiers, anti-impersonation      │
  │ Identity   │ ERC-8004           │ Agent Card, on-chain registry, reputation tracking      │
  │ Trust      │ ERC-8126           │ 5-tier risk scoring, 4 verification types, ZK proofs    │
  │ Commerce   │ ERC-8183           │ Escrowed jobs, evaluator role, settlement lifecycle     │
  │ Payments   │ x402 (send+receive) │ Bidirectional: agents pay AND accept money via EIP-3009 │
  │ Wallet     │ OWS (21 functions) │ Per-agent vaults, scoped API keys, 9 chains, 0600 perms │
  │ Skills     │ SKILL.md           │ skills.sh + bankr.bot + Elsa x402 + any repo            │
  │ DeFi       │ Elsa x402          │ Swaps, perps, staking, airdrops — pay-per-call on Base  │
  │ Data       │ DataRouter         │ HTTP / x402 / WebSocket dispatch with fallback chain     │
  │ Security   │ Hardened           │ AES-256-GCM backups, sanitization, 8-point preflight    │
  │ Runtime    │ Forge Engine       │ Planner → Policy → Execute → Ledger + 4 memory layers   │
  │ Spec       │ JSON Schema        │ 8 artifact types, cross-validation, migration contracts │
  │ Eval       │ Scenario Packs     │ Baseline + edge cases, promotion evidence, replays      │
  │ Research   │ Autoresearch       │ Runtime self-eval, keep/discard, LLM-proposed mutations │
  │ Promotion  │ Staged Pipeline    │ Sandbox → Paper → Canary → Production, governed         │
  └────────────┴────────────────────┴─────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  RUNTIME LOOP                             PROMOTION PIPELINE

  ┌──────────┐    ┌─────────────┐          ┌─────────┐   ┌───────┐   ┌────────┐   ┌──────────┐
  │ Planner  │───▶│ Policy Gate │          │ Sandbox │──▶│ Paper │──▶│ Canary │──▶│Production│
  └──────────┘    └──────┬──────┘          └─────────┘   └───────┘   └────────┘   └──────────┘
                         │                    eval          eval        eval          eval
                  ┌──────▼──────┐             pass          pass        pass          pass
                  │   Execute   │           + policy      + policy    + approver    + approver
                  └──────┬──────┘             ok            ok        + rollout     + rollout
                         │                                              limits       limits
                  ┌──────▼──────┐
                  │   Ledger    │──▶ audit trail, replay, resume
                  └─────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  SECURITY — DEFENSE IN DEPTH

  ▸ Session keys with contract/chain allowlists and per-tx/per-day spending caps
  ▸ Budget circuit breakers — auto-pause if spending velocity exceeds 3x rolling average
  ▸ Prompt injection detection — 12 patterns: role impersonation, jailbreaks, hidden content
  ▸ Rate limiting per operation type, environment-tiered defaults (sandbox → production)
  ▸ Append-only audit log for every wallet sign, x402 payment, and job creation
  ▸ Side-effecting capabilities default to DENY until policy explicitly allows

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  SKILLS — 3 REGISTRIES, ONE COMMAND

  ┌─────────────────┬─────────────────────────────────┬──────────────────────────────────────┐
  │    Registry     │          Source Format           │               Focus                  │
  ├─────────────────┼─────────────────────────────────┼──────────────────────────────────────┤
  │ skills.sh       │ owner/repo                      │ General-purpose (91K+ skills)        │
  │ bankr.bot       │ bankr:skill-name                │ Crypto/DeFi (~31 skills)             │
  │ Elsa x402       │ elsa:name / elsa:category / all │ 21 pay-per-call DeFi endpoints       │
  └─────────────────┴─────────────────────────────────┴──────────────────────────────────────┘

  Elsa endpoints: search-token ($0.001) · get-portfolio ($0.01) · execute-swap ($0.02)
  get-swap-quote ($0.01) · open-perp ($0.05) · get-yield-suggestions ($0.02) · + 15 more

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  WALLET — FULL OPEN WALLET STANDARD (21 SDK FUNCTIONS)

  Lifecycle        create · import (mnemonic/key) · delete · export · rename · list · get
  Signing          message · transaction · typed data (EIP-712) · sign-and-send
  Policy           create · list · get · delete policies
  API Keys         create · list · revoke
  Chains           EVM · Solana · Bitcoin · Cosmos · Tron · TON · Sui · XRPL · Filecoin

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  GET STARTED

  $ pip install 'aether-forge[all]'                          Python 3.12+
  $ forge doctor                                             8/8 ok
  $ forge generate-fast --name "my-agent" \                  Auto-detects LLM
        --idea "your idea here" \                            (Ollama/Claude/GPT/Gemini)
        --strategy-file ./strategy.md \                      and bakes it into the agent
        --output ./my-agent --wallet --autonomous
  $ forge validate ./my-agent
  $ forge eval-pack ./my-agent
  $ forge run ./my-agent --auto-approve --autoresearch --knowledge
  $ forge promote-draft ./my-agent --target paper

  Or run the canonical team walk-through:
  $ ./demo.sh                                                10 sections, ~10 minutes

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Spec-first · Policy-governed · Eval-driven · Production-ready · Open Agent Economy Native


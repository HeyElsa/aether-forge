# Aether Forge Agent Reputation Spec (RFC)

**Status**: Draft / RFC — requesting comments
**Version**: 0.1.0
**Schema**: `src/aether_forge/schemas/artifacts/reputation-record.schema.json`
**Related surfaces**:
- Runtime snapshot: `reputation-record.json` written per run (v0 scorer)
- Identity: `aether_forge.attestation` (EIP-712 self/framework attestation, `ATTESTOR.md`)
- Publication seams: `protocols/erc8004.py` (`build_feedback_payload`, `setMetadata`), `protocols/erc8126.py` (`TrustAssessment`)

---

## 1. Purpose

Every Aether Forge agent should ship with an **auto-produced, evidence-backed, verifiable reputation score** — the way every Forge agent already ships with typed artifacts, policy, and replays. The goal is for "Forge-built" to *mean* "comes with a reputation you can check", and for the record format to become usable beyond Forge.

This RFC specifies:

1. the **record format** (schema'd artifact, like every other Forge artifact),
2. the **scoring requirements** any conforming scorer MUST satisfy,
3. the **publication path** (local → registry → on-chain) and its trust model,
4. the **anti-gaming envelope**, and
5. how the format stays **ZK-ready** so future strategy-privacy proofs (prove PnL without revealing the strategy) drop in without a format change.

The runtime half exists today: each `forge run` ends by writing `reputation-record.json` next to the other artifacts (reliability + follow-through over observed ticks, formula embedded in the record). This RFC layers the standard on top: identity binding, accumulation, confidence, claims verification, and publication. The two halves compose; nothing here changes the runtime scorer's contract.

## 2. Design principles

1. **Evidence-chained.** Every scored component MUST trace to runtime artifacts the framework already records (step ledger / replays, observability events, eval and promotion records, x402 audit log). Self-reported numbers are never scored — they enter only as *claims* (§6).
2. **Observed-only, renormalized.** A component with no underlying observations is listed `unobserved` and removed from the weighting. An agent that never traded MUST NOT look like a break-even trader. (This is the v0 scorer's rule; it is normative here.)
3. **Confidence is first-class.** A score without sample size is noise. Every snapshot MUST carry `confidence ∈ [0,1]` derived from evidence volume and window coverage (reference curve: `min(log10(1 + ticks)/3, 1)` — 2 ticks ≈ 0.16, 1000 ticks ≈ 1.0). Tier labels MUST be confidence-gated: an agent cannot present tier `strong` at confidence < 0.5 regardless of raw score. Consumers MUST display score and confidence together.
4. **Environment-scoped.** Sandbox evidence MUST NOT contribute to published performance reputation (mock data rewards noise). Reliability-family components may aggregate across environments but MUST be labeled per environment. Published records carry the environment ladder explicitly (sandbox / paper / canary-live / production).
5. **Claims vs. verification.** Performance enters the record as `{claimed, verified, method}` triples. `claim_accuracy` (verified/claimed agreement) is itself a scored component — overclaiming damages reputation more than underperforming (methodology shared with the Elsa agent-reputation lab: claim-mismatch penalties + slashing recommendation signals).
6. **Identity-bound, signed.** A published snapshot MUST bind `artifactSetId` + `capabilitiesHash` + the agent's wallet address, and MUST be EIP-712-signed by the agent wallet (self-attested tier). The framework attestor MAY co-sign (verified tier) — same two-layer model as `ATTESTOR.md`. Unsigned records are local diagnostics only.
7. **Cumulative, windowed, decaying.** The published score is an aggregate over a declared contiguous window (default 30 days) of per-run snapshots, not the last run. Gaps in the run ledger are reported, not hidden.

## 3. Record format (v0.1.0)

`reputation-record.json` — artifact family, validated by `reputation-record.schema.json`:

```jsonc
{
  "kind": "aether-forge/reputation-record",
  "version": "0.1.0",
  "artifactSetId": "aset_basis-trader_4c694942",
  "agentName": "Basis Trader",
  "environment": "sandbox",
  "snapshot": {
    "score": 87.5,                  // 0-100, weighted over observed components
    "tier": "developing",           // confidence-gated label
    "components": {
      "reliability":     {"score": 100.0, "weight": 0.5},
      "follow_through":  {"score": 75.0,  "weight": 0.5}
    },
    "unobserved": ["trading"],      // removed from weighting, listed honestly
    "inputs": { /* raw counts — ticksTotal, stepsExecutedTotal, ... */ },
    "computedAt": "2026-06-11T21:47:11Z"
  },
  "scorer": "DefaultReputationScorer",

  // ---- v1 extension blocks (optional, this RFC) ----
  "confidence": {"value": 0.16, "basis": "log-depth over 2 ticks"},
  "window": {"from": "...", "to": "...", "runs": 1, "contiguous": true},
  "identity": {
    "capabilitiesHash": "sha256:...",
    "agentAddress": "0x...",
    "attestationRef": "attestation.json",
    "signature": "0x..."            // EIP-712 over (artifactSetId, capabilitiesHash, window, score)
  },
  "claims": [
    {
      "metric": "realized_pnl_usd_30d",
      "claimed": 1250.0,
      "verified": 1187.5,
      "method": "replay-ledger",     // replay-ledger | onchain | attestor-audit | zk-proof
      "proofRef": "replays/ or tx hash or proof blob ref"
    }
  ],
  "publication": {"target": "local"} // local | erc8004 | hosted-index
}
```

Compatibility: the v0 runtime record (everything above the extension blocks) is valid against the schema as-is. Extension blocks are optional and additive.

## 4. Scoring requirements (conforming scorers)

A conforming scorer MUST:

- score only observed components and renormalize weights (§2.2);
- embed component scores, weights, and raw input counts in the record (recomputability);
- emit `confidence` per §2.3 and gate tier labels on it;
- treat heuristic-fallback ticks as *reduced planner integrity*: a run where the LLM planner failed and the labeled heuristic fallback drove execution MUST NOT score equal to an LLM-planned run. (Reference component: `planner_integrity = llm_planned_ticks / ticks_total`, fed by the `last_planner_parse_failure` / `planner.fallback` events the runtime already records.)
- never fold mock/sandbox PnL into a published performance component (§2.4).

RECOMMENDED v1 component set (weights illustrative, must ship in-record):

| Component | Evidence source | Note |
|---|---|---|
| reliability | tick outcomes (runner history) | v0, keep |
| follow_through | step ledger executed vs pending | v0, keep |
| planner_integrity | planner.fallback events | new — fixes "broken brain, perfect score" |
| policy_compliance | policy decisions (deny/hold rate vs allow) | new |
| claim_accuracy | claims[] verified vs claimed | new, §6 |
| performance | verified claims only, live/paper envs | reported in v0, scored only when verified |

## 5. Publication path

- **Local (default, always on):** `reputation-record.json` per run + append-only `reputation-ledger.jsonl` accumulating snapshots across runs. Free, offline, no opt-in needed.
- **`forge reputation show .`** — render score, confidence, components, window, and divergences (e.g. unobserved components, ledger gaps).
- **`forge reputation publish .` (opt-in):**
  - **ERC-8004:** write the windowed aggregate via `setMetadata(agentId, "aether_forge_reputation", <signed snapshot digest>)` and/or `submitFeedback` (`build_feedback_payload` seam exists in `protocols/erc8004.py`). Requires prior `forge agent-register`.
  - **Hosted index:** POST the signed record to a marketplace/registry index (Elsa). Same signed payload, different transport.
  - Default payload is score + confidence + window + identity binding — **not** raw replays, preserving strategy privacy.
- **Discovery:** `forge agent-discover` SHOULD display reputation (score @ confidence, window, tier) alongside the existing trust tier (verified / self-attested / unverified).

Trust model: the *score* is only as trustworthy as its evidence chain. Tiering mirrors attestation: self-attested reputation = signed by the agent's wallet over its own local evidence; verified reputation = framework attestor re-ran the verification (validated ledger hashes, recomputed the aggregate) and co-signed. The attestor wallet is the same one specified in `ATTESTOR.md` (not yet published — this RFC adds a second reason to stand it up).

## 6. Claims & ZK-readiness

The `claims[]` block is the bridge to verifiable performance:

- Today: `method: "replay-ledger"` — the claim is recomputed from the agent's own hash-chained replays (honest-operator assumption, tamper-evident).
- On-chain agents: `method: "onchain"` — claim verified against chain data (x402 audit log ↔ Base txs).
- Future: `method: "zk-proof"` — the agent proves `realized_pnl_usd_30d ≥ X` (or Sharpe ≥ Y) without revealing strategy or trade-level data; `proofRef` carries the proof blob/verifier id. **The record format does not change** — only the verification method strengthens. This is deliberately aligned with the incoming strategy-proof framework so it lands as a new `method` value, not a new format.

## 7. Anti-gaming envelope

| Attack | Mitigation |
|---|---|
| Sandbox farming (1000 green mock ticks) | environment scoping (§2.4): sandbox never feeds published performance; published tier requires paper+ evidence |
| Tick padding (no-op REASON loops) | confidence uses wall-clock window + step diversity, log-scaled; caps per labrepo methodology |
| Cherry-picked windows | published aggregate MUST be contiguous-window over the ledger; gaps surfaced in-record (`window.contiguous: false`) |
| Replay tampering | hash-chain replays (each tick records prior tick's digest); attestor re-validation for verified tier; TEE/ZK later |
| Sybil re-rolls (burn bad history, regenerate) | identity binding to ERC-8004 registration (costs gas, accrues history); fresh `artifactSetId` = fresh confidence ≈ 0 — a *new* agent has no reputation, which is exactly correct |
| Overclaiming | claim_accuracy penalties + slashing-recommendation signal in the record |

## 8. Out of scope (v0.1.0)

- On-chain reputation aggregation contracts (we publish to existing ERC-8004 surfaces only)
- Cross-framework reputation portability (format is open; adoption is a later conversation)
- Reputation-weighted x402 pricing / job routing (natural follow-on once records are published)

## 9. Open questions for maintainers

1. Should `reputation-record.json` join the **artifact family** (validated by `forge validate`, 9th artifact) or stay a runtime output like replays? This RFC ships the schema either way; wiring into `validate` is a one-line decision.
2. Tier vocabulary: runtime v0 uses strong/developing/weak; ERC-8126 uses a 5-level *risk* tier. Unify or keep reputation-vs-risk as distinct axes? (RFC position: distinct axes, cross-referenced.)
3. Default publication window (30d proposed) and decay function — flat window vs exponential decay.
4. Does the attestor verification flow (ATTESTOR.md §Layer 2) subsume reputation re-validation, or is that a separate attestor capability?

## 10. References

- `ATTESTOR.md` — two-layer attestation trust model
- `ARCHITECTURE.md` — replays, step ledger, observability events (the evidence base)
- `docs/specs/planner-output.md` — spec-format precedent
- Elsa agent-reputation lab — claim-verification, slashing signals, confidence/log-depth scaling, registry statuses (methodology source)
- ERC-8004 / ERC-8126 — identity & trust surfaces already in `protocols/`

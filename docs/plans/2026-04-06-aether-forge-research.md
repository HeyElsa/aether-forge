# Aether Forge Research Review

Date: 2026-04-06
Status: Supporting research for PRD v0.7.0
Related PRD: `docs/prd/aether-forge-prd-v0.7.0.md`

## 1. Purpose

This document captures the deep research pass used to refine the `Aether Forge` PRD.

The goal was to pressure-test the product thesis across four areas:

- agent-builder architecture and product landscape
- crypto wallet, exchange, and policy requirements
- fast/slow creation mode and autoresearch-loop design
- evaluation, promotion, and high-stakes operational rollout

## 2. High-Level Conclusion

The core thesis remains strong:

`Aether Forge` should be a spec-first, developer-first framework for turning ideas into governed, testable, production-capable agents.

The research showed that the strongest differentiation is not generic orchestration. It is the combination of:

- typed, versioned specs
- policy-bound side effects
- realistic sandbox and evaluation loops
- evidence-backed promotion
- crypto-native execution safety
- a meaningful slow mode that improves the draft before presenting it

The biggest missing gaps in earlier PRDs were:

- policy semantics were too abstract
- crypto execution safety was too generic
- slow mode lacked explicit stop conditions and evidence rules
- promotion was too coarse and not progressive enough
- observability, rollback, and deactivation requirements were underdefined

## 3. Research Streams

### 3.1 Agent Builder And Runtime Landscape

Key findings:

- Most agent frameworks optimize for runtime composition first, not for a durable spec artifact.
- Durable orchestration and agent reasoning should be separate layers.
- Tool-level guardrails and resumable approvals are already emerging patterns in serious runtimes.
- Typed outputs and schema-driven artifacts are becoming table stakes for developer-first agent tools.

Implications for Aether Forge:

- The `Agent Spec` must be typed, versioned, and machine-validatable.
- The architecture should clearly separate spec, reasoning, execution, effect, policy, and evidence layers.
- The product should avoid sounding like a generic orchestration framework.
- Promotion and evidence should stay central to positioning.

### 3.2 Crypto Infrastructure And Safety

Key findings:

- Wallet support needs an explicit custody and signer-control model.
- Default-deny policy semantics are critical for side-effecting systems.
- Signing isolation should assume enclave, HSM, co-signer, or comparable protected execution boundaries.
- Exchange abstraction is useful, but venue-specific capability differences remain unavoidable.
- Idempotency, nonce management, replay resistance, and partial-fill handling are core safety requirements.
- Compliance controls such as AML, KYT, and Travel Rule hooks may matter for some crypto workflows.

Implications for Aether Forge:

- A crypto agent cannot just have "wallet support". It needs scoped control topology.
- The framework should require capability manifests and venue capability matrices.
- Promotion to production should include canary live rollouts with capped capital.
- Policy must cover contract methods, calldata, recipients, time windows, and cumulative budgets.

### 3.3 Fast And Slow Creation Modes

Key findings:

- Strong deep-research systems use a `plan -> research -> critique -> synthesize` loop.
- Good slow-mode systems do not stream half-finished results by default.
- Completion should be tied to coverage, evidence, risk closure, and diminishing returns.
- A research-backed mode needs durable research artifacts, not just a better final answer.

Implications for Aether Forge:

- Slow mode should create a `Research Record`.
- Slow mode should only ask the user questions when they are truly blocker-level.
- Slow mode must have explicit budgets and stop conditions.
- The product should benchmark fast vs slow quality, not just latency.

### 3.4 Evaluation, Promotion, And Operations

Key findings:

- High-stakes systems separate offline and online evaluation.
- Historical replay is not enough; teams also need regression packs, incident-derived scenarios, and production monitoring.
- Progressive rollout, shadow execution, canaries, pauses, and deactivation are standard safety patterns.
- Runtime approvals matter in addition to promotion approvals.

Implications for Aether Forge:

- The environment model should include `shadow` and `canary live`.
- Promotion should be staged, not a single jump.
- Residual risk, independent review, and rollback classes should be first-class release artifacts.
- Observability should include policy decisions, approval events, redaction controls, and provenance.

### 3.5 Karpathy Autoresearch Implications

Key findings:

- Autoresearch is not just a longer research conversation. It is a bounded experiment loop.
- A baseline-first run is required before improvement claims mean anything.
- Fixed budgets are what make candidate comparisons fair.
- The loop should advance only when a candidate measurably improves the last accepted state.
- Simplicity matters alongside performance.
- The evaluator should stay fixed while the system is optimizing against it.
- Results need an append-only experiment ledger, not only a narrative summary.

Implications for Aether Forge:

- Slow mode should include a baseline-first protocol.
- Each slow-mode iteration should end in `keep`, `discard`, `blocked`, or `execution failure`.
- The `Research Record` should include an iteration ledger with hypothesis, changed surfaces, budget, metrics, and rationale.
- Slow mode should minimize the editable surface of each experiment.
- Evaluation criteria and policy thresholds should be protected during an active comparison cycle.
- Slow mode should continue autonomously while productive budget remains instead of presenting prematurely.

## 4. Consolidated Product Changes

The research drove these major additions into PRD v0.4.0:

1. Typed and versioned `Agent Spec`
2. New `Research Record` artifact for slow mode
3. New `Capability Manifest` and `Scenario Pack` artifacts
4. Clear architecture layers and deterministic boundaries
5. Default-deny policy model with structured decisions
6. Wallet control topology and signer-isolation requirements
7. Venue capability matrix and exchange-specific safety wrappers
8. Offline vs online evaluation split
9. Shadow and canary environments
10. Progressive promotion, runtime approvals, rollback, and deactivation
11. Baseline-first autoresearch protocol
12. Keep or discard loop semantics for slow mode and self-evolution
13. Protected evaluation surfaces during optimization
14. Iteration ledger and complexity-aware variant selection

## 5. Scenario Families That Must Be Supported

### 5.1 Spec And Scaffold

- spec-to-scaffold drift after user edits
- spec migration across versions
- regeneration with merge conflicts in user-owned code

### 5.2 Slow Mode Research

- baseline-first slow-mode run before variants are tested
- ambiguous prompt with missing risk constraints
- conflicting sources across exchanges or protocols
- low-confidence research output that should trigger a blocker question
- diminishing returns reached before full certainty
- keep versus discard decision on comparable-budget variants

### 5.3 Crypto Execution Safety

- duplicate order submission after retry
- stale market data at execution time
- non-allowlisted venue or contract call
- unsafe recipient or contract approval change
- delegated signer compromise or revocation
- nonce race or transaction replacement scenario

### 5.4 Evaluation And Promotion

- historical replay regression
- paper mode passes but shadow mode reveals unsafe live behavior
- canary rollout fails due to policy incidents
- promoted version accumulates drift relative to sandbox expectations
- halted agent requires explicit re-enable checklist

### 5.5 Operations And Incident Response

- signer outage or exchange outage
- policy breach before side effect
- policy breach after partial side effect
- emergency stop and unwind
- residual-risk signoff with limited promotion

## 6. Recommended Benchmarks

### Fast vs slow mode

- acceptance without major rewrite
- baseline-to-improvement delta under fixed budgets
- spec completeness delta
- safety-gap detection rate
- blocker precision
- wrong-assumption rate
- evidence quality
- simulation readiness
- complexity-adjusted improvement rate

### Runtime and promotion

- policy breach catch rate before side effects
- replay consistency for approval-critical outcomes
- time to explain a production incident from traces
- time to safely deactivate and recover

## 7. Strongest Sources

### Agent and workflow systems

- LangGraph: https://docs.langchain.com/oss/python/langgraph/overview
- Temporal Workflows: https://docs.temporal.io/workflows
- Temporal AI Cookbook: https://docs.temporal.io/ai-cookbook
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- OpenAI Agents SDK Guardrails: https://openai.github.io/openai-agents-python/guardrails/
- OpenAI Agents SDK HITL: https://openai.github.io/openai-agents-python/human_in_the_loop/
- AutoGen: https://microsoft.github.io/autogen/stable/user-guide/core-user-guide/index.html
- CrewAI: https://docs.crewai.com/
- PydanticAI: https://ai.pydantic.dev/
- MCP: https://modelcontextprotocol.io/introduction

### Crypto execution and custody

- Fireblocks policy engine: https://developers.fireblocks.com/docs/set-transaction-authorization-policy
- Fireblocks co-signers: https://developers.fireblocks.com/docs/use-cosigners-for-signing-automation
- Coinbase CDP security best practices: https://docs.cdp.coinbase.com/get-started/authentication/security-best-practices
- Coinbase CDP idempotency: https://docs.cdp.coinbase.com/api-reference/v2/idempotency
- Privy policy controls: https://docs.privy.io/controls/policies/overview
- Privy security overview: https://docs.privy.io/security/overview
- Turnkey policies: https://docs.turnkey.com/concepts/policies/overview
- Turnkey transaction management: https://docs.turnkey.com/concepts/transaction-management
- Hummingbot connectors: https://hummingbot.org/connectors/
- CCXT manual: https://raw.githubusercontent.com/wiki/ccxt/ccxt/Manual.md

### Deep research and slow mode patterns

- Gemini Deep Research: https://blog.google/products-and-platforms/products/gemini/google-gemini-deep-research/
- Gemini help: https://support.google.com/gemini/answer/15719111
- Anthropic building effective agents: https://www.anthropic.com/engineering/building-effective-agents
- Karpathy autoresearch: https://github.com/karpathy/autoresearch
- Karpathy autoresearch program loop: https://github.com/karpathy/autoresearch/raw/refs/heads/master/program.md
- GPT Researcher: https://github.com/assafelovic/gpt-researcher
- Hugging Face open deep research: https://huggingface.co/blog/open-deep-research
- STORM paper: https://arxiv.org/abs/2402.14207
- Plan-and-Solve: https://arxiv.org/abs/2305.04091

### Evaluation, policy, and rollout

- NIST AI RMF: https://www.nist.gov/itl/ai-risk-management-framework
- NIST AI RMF Playbook Measure: https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook/Measure/
- NIST AI RMF Playbook Manage: https://airc.nist.gov/AI_RMF_Knowledge_Base/Playbook/Manage/
- Google SRE reliable launches: https://sre.google/sre-book/reliable-product-launches/
- Azure safe deployments: https://learn.microsoft.com/en-us/azure/well-architected/operational-excellence/safe-deployments
- Argo Rollouts canary: https://argo-rollouts.readthedocs.io/en/stable/features/canary/
- OPA: https://www.openpolicyagent.org/docs/latest/
- LangSmith evaluation: https://docs.smith.langchain.com/evaluation
- OpenTelemetry observability primer: https://opentelemetry.io/docs/concepts/observability-primer/
- OpenTelemetry GenAI semconv: https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/

## 8. Final Takeaway

`Aether Forge` should not try to win as a generic agent builder.

It should win as a framework for forging governed agents in high-stakes environments, starting with crypto.

The most important upgrade from the earlier PRDs is that the product contract is now much sharper:

- typed specs
- evidence-backed slow mode
- baseline-first, keep-or-discard autoresearch loops
- default-deny policy semantics
- crypto-native execution safety
- staged promotion and runtime approvals
- explicit operational safety and incident response

That sharper contract is what makes the product believable.

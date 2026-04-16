# Aether Forge Product Requirements Document

Version: `v0.4.0`
Status: `Draft`
Date: `2026-04-06`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.3.0.md`
Supporting research: `docs/plans/2026-04-06-aether-forge-research.md`

## 1. Executive Summary

`Aether Forge` is a spec-first, developer-first framework for turning an agent idea into a governed, testable, production-capable agent system.

The product starts from a plain-language idea and turns it into a structured specification, an editable scaffold, a bounded execution model, a realistic evaluation loop, and a controlled promotion path into production.

The initial wedge is crypto. V1 ships with first-class wallet, exchange, onchain, and market-data capabilities, but the core must remain general enough to support other high-stakes agent categories later.

The product promise is not "spin up an autonomous bot instantly." The promise is:

> Take my idea, turn it into a reliable agent system, improve it with bounded research when needed, test it realistically, and only let it touch production under explicit controls.

V1 should support two creation modes:

- `Fast mode` for rapid draft generation.
- `Slow mode` for a bounded autoresearch loop that improves the agent before presenting it.

The major refinement in this version is that `slow mode` is no longer defined as a vague deep-research pass. It is defined as a baseline-first, fixed-budget, keep-or-discard experiment loop inspired by `karpathy/autoresearch`.

## 2. Product Thesis

The most valuable agent systems in high-stakes environments will not be the freest ones. They will be the most governable ones.

Users do not only want an LLM that can call tools. They want a system that can:

- define what the agent is trying to do
- constrain what it is allowed to touch
- explain how and why it behaved
- improve itself without escaping review
- move from draft to production under evidence-backed controls

That is especially true in crypto, where agents may control wallets, sign transactions, call exchanges, manage positions, or affect treasury and compliance workflows.

`Aether Forge` should therefore be built around these core ideas:

1. `Specification before execution`
2. `Scaffolding before autonomy`
3. `Default-deny side effects`
4. `Sandbox, shadow, and canary before broad production`
5. `Self-improvement without self-governance`
6. `Fast and slow creation as distinct product paths`
7. `Baseline-first, measurable improvement loops`

## 3. Problem Statement

Technical builders can already prototype ideas with prompts, scripts, cron jobs, or wrappers around agent SDKs. The problem is turning those prototypes into reliable systems.

Common failure modes today:

1. The system is too fragmented.
Data ingestion, tool access, strategy logic, wallet access, risk checks, and deployment logic live in different places with weak contracts.

2. The system is too opaque.
It is hard to explain decisions, replay behavior, review proposed changes, or justify production promotion.

3. The system is too unsafe.
Live side effects are mixed into application logic without strong policy semantics, approvals, or environment separation.

4. The system is hard to improve.
Builders can add logic, but they cannot confidently let the system research, propose improvements, evaluate variants, and return with evidence.

5. The system is hard to operationalize.
Even a promising strategy lacks realistic simulation, incident handling, drift monitoring, and controlled rollout mechanics.

6. The system is hard to compare fairly.
Without a baseline, a fixed budget, and a fixed evaluator, teams cannot tell whether a new variant is actually better or just more expensive, more complex, or judged by a weaker standard.

In crypto, those weaknesses are amplified by capital risk, venue fragmentation, irreversible transactions, and compliance requirements.

## 4. Positioning

Short positioning statement:

> `Aether Forge` helps developers forge reliable, policy-bound agents from ideas into production-ready systems, with realistic testing and governed promotion built in.

How it should feel in the market:

- more serious than a generic agent playground
- more developer-friendly than a no-code agent builder
- more spec-driven than a runtime-only orchestration tool
- more governable than a free-form autonomous agent runtime
- more operationally complete than a one-shot scaffold generator
- more rigorous than a deep-research mode that cannot prove improvement

## 5. Primary User

The primary v1 user is the `crypto strategy developer`.

This user is typically:

- technical and comfortable editing code
- familiar with market structure, venues, and risk concepts
- able to describe a strategy in plain language
- looking for speed without surrendering control

Representative examples:

- a builder creating a delta-neutral spot/perp strategy
- a protocol operator creating a treasury rebalancer
- a research engineer creating a signal-synthesis agent
- an execution engineer creating a hedge assistant

## 6. Secondary Users

Secondary users include:

- protocol or exchange teams building internal operators
- crypto product teams building supervised action agents
- general AI product engineers using the core outside crypto

These users matter, but the primary user should anchor product decisions in v1.

## 7. Product Principles

### 7.1 Spec-first

The first durable artifact should be a typed `Agent Spec`, not a running bot.

### 7.2 Developer-first

Generated output must be inspectable, editable, and understandable by strong builders.

### 7.3 General core, crypto-native modules

The runtime model should stay domain-agnostic. The first-party starter pack should be strongly crypto-native.

### 7.4 Default-deny side effects

No side-effecting capability should be usable in a live environment unless explicitly allowed by policy.

### 7.5 Progressive production trust

Production access should grow through sandbox, shadow, paper, canary, and staged rollout patterns where relevant.

### 7.6 Slow mode must be evidence-backed

Slow mode should not just spend more time. It should produce a meaningfully stronger decision package with evidence, confidence, and explicit stop reasons.

### 7.7 Baseline before improvement claims

Slow mode and self-evolution should establish a baseline before claiming that a candidate is better.

### 7.8 Protected evaluators

The evaluation harness, policy thresholds, and promotion gates used to judge a candidate must remain fixed while that candidate is being compared.

### 7.9 Simplicity still matters

When two variants are materially similar on declared success criteria, the simpler and more editable variant should win.

### 7.10 Self-evolution remains governed

The system may propose improvements and variants, but it may not expand permissions or self-promote into production.

## 8. V1 Scope

### In scope

- plain-language idea intake
- `fast` and `slow` creation modes
- typed and versioned `Agent Spec` generation
- editable spec review
- `Research Record` generation for slow mode
- code and configuration scaffold generation
- capability manifests for tools, wallets, venues, and environments
- supervised runtime for agent sessions
- policy engine with runtime enforcement
- sandbox, paper, shadow, and canary evaluation patterns
- trace capture and inspection
- manual and staged promotion workflows
- runtime approval gates for designated actions
- crypto-native modules for wallets, exchanges, onchain actions, and data
- baseline-first slow-mode experimentation
- iteration ledgers with keep-or-discard decisions

### Out of scope for v1

- fully autonomous self-promotion into production
- consumer no-code UX as the primary product
- a retail strategy marketplace
- unconstrained autonomous research loops with no budget or stop conditions
- pretending all exchanges and chains are perfectly abstractable
- allowing a candidate to modify the evaluator used to judge it

## 9. Core Use Case

Reference use case:

"Build an agent that captures delta-neutral value by buying spot BTC, shorting BTC perps when basis exceeds a threshold, capping exposure per venue, monitoring volatility, and unwinding if risk rises above a policy-defined level."

In `Aether Forge`, the expected workflow should be:

1. The user describes the idea.
2. The user chooses fast or slow mode.
3. The system creates and refines a spec.
4. The system produces a scaffold, policy defaults, and evaluation scenarios.
5. The user simulates the agent.
6. The user progressively promotes the agent through environments.
7. The system later proposes new variants under the same governance loop.

## 10. Agent Creation Modes

### 10.1 Fast Mode

`Fast mode` is optimized for speed to first credible draft.

It should:

- generate a usable `Agent Spec` quickly
- generate a scaffold with strong defaults
- surface obvious risks and unknowns
- avoid excessive up-front ceremony

Fast mode is for exploration and quick iteration.

### 10.2 Slow Mode

`Slow mode` is optimized for draft quality, completeness, and safety coverage.

Slow mode should run a bounded autoresearch loop before presenting the result.

That loop should:

- interpret the user objective and missing assumptions
- build a research plan
- gather evidence on tools, venues, protocols, risks, and policies
- critique the draft for contradictions and unsafe gaps
- refine the `Agent Spec`, evaluation plan, and scaffold recommendations
- decide whether to keep researching, ask a blocker question, or present

`Slow mode` should be treated as a disciplined experiment loop, not a free-form conversation.

### 10.3 Baseline And Variant Protocol

Slow mode must establish a baseline artifact package before proposing or evaluating variants.

The baseline should be the first complete draft produced from the user idea under the current constraints. The baseline package should include:

- baseline `Agent Spec`
- baseline `Capability Manifest`
- baseline scaffold plan or scaffold
- baseline `Scenario Pack`
- baseline measurable improvement criteria

All subsequent variants in the same slow-mode session must be evaluated under comparable conditions, including:

- materially similar inputs
- fixed or explicitly normalized budgets
- fixed evaluation conditions
- fixed policy thresholds for the active comparison cycle

### 10.4 Keep-Or-Discard Decision Loop

Each slow-mode iteration must end in one of four outcomes:

- `keep`
- `discard`
- `blocked`
- `execution failure`

`Keep` advances the candidate artifact set.
`Discard` reverts to the last accepted candidate.
`Blocked` records a blocker question or safety stop.
`Execution failure` records a broken or unusable attempt that does not advance the candidate.

The loop should prefer the smallest meaningful change per iteration unless prior evidence justifies bundling multiple changes together.

### 10.5 Measurable Improvement Criteria

Before iterative refinement begins, slow mode must declare the measurable criteria by which candidate improvements will be judged.

These may include:

- spec completeness
- contradiction reduction
- policy-gap reduction
- scenario coverage
- simulation readiness
- domain-specific strategy or safety metrics

A candidate should not be considered better merely because it is longer, more complex, or consumed more budget.

### 10.6 Slow Mode Stop Rules

Slow mode should present once the draft is `materially complete`.

That means all of the following should be true, or explicit gaps should be called out:

- objective clarity is strong enough
- tools and data dependencies are covered
- policy boundaries are drafted
- evaluation scenarios are proposed
- major risks are identified
- evidence supports major recommendations
- recent iterations are showing diminishing returns

Slow mode should continue autonomously while productive budget remains.

Slow mode should interrupt early only when:

- the system hits a safety-critical blocker
- an identity-defining ambiguity cannot be inferred credibly
- confidence falls below a usable threshold
- the user explicitly asks for intermediate output
- the allocated budget has been exhausted

### 10.7 Slow Mode Artifacts

Slow mode should return a `decision package` and an `implementation package`.

The decision package should include:

- refined spec
- research summary
- evidence links or sources
- confidence notes
- unresolved questions
- stop reason

The implementation package should include:

- scaffold or scaffold plan
- module recommendations
- policy defaults
- scenario pack proposal

The `Research Record` must include an append-only iteration ledger describing each attempted variant.

## 11. Core Lifecycle

The v1 product lifecycle should be:

1. `Ideate`
2. `Choose Mode`
3. `Specify`
4. `Research and Refine` when slow mode is chosen
5. `Generate`
6. `Evaluate`
7. `Promote`
8. `Operate`
9. `Evolve`

This lifecycle should remain visible in the product language and architecture.

## 12. Product Artifacts

### 12.1 Agent Spec

The canonical typed description of what the agent is and what it is allowed to do.

The spec must be:

- versioned
- machine-validatable
- human-readable
- portable across environments
- separated from secrets

It should describe:

- objective
- user intent
- target environments
- tools and side effects
- permissions and capabilities
- wallets and signers
- data dependencies
- policy limits
- evaluation requirements
- promotion criteria
- failure modes
- success metrics

### 12.2 Research Record

The durable record for slow mode.

It should include:

- research plan
- evidence log
- claims and supporting sources
- contradictions and unknowns
- blocker questions
- completeness and confidence notes
- final stop rationale

It must also include an append-only `iteration ledger` with, at minimum:

- candidate ID
- parent candidate ID
- hypothesis
- changed surfaces
- budget consumed
- evaluation conditions
- measured outcomes
- decision status
- keep or discard rationale

### 12.3 Capability Manifest

The formal list of tools, wallet actions, exchange actions, protocol actions, and environment capabilities available to the agent.

It should capture:

- capability type
- risk level
- environment availability
- required approvals
- rate or budget limits
- provider-specific constraints

### 12.4 Agent Scaffold

The generated, developer-owned project implementing the spec.

It should include:

- runtime config
- agent modules
- tool bindings
- adapter setup
- policy config
- scenario pack config
- environment templates
- deployment templates

The scaffold should clearly distinguish:

- user-owned zones
- generated zones
- protected zones that are not part of autonomous mutation during an active comparison cycle

### 12.5 Scenario Pack

The reusable evaluation suite for an agent version.

It should include:

- baseline scenarios
- edge cases
- policy-violation scenarios
- incident-derived regressions
- stress scenarios
- expected metrics and thresholds

### 12.6 Runtime Session

The live or non-live execution context.

It should track:

- state
- tool calls
- model calls
- policy decisions
- approvals
- events and traces
- budgets and limits
- environment metadata

### 12.7 Promotion Record

The evidence package behind environment promotion.

It should include:

- artifact versions
- scenario results
- policy outcomes
- offline and online evaluation results
- residual risk statement
- approver metadata
- rollout stage and status

## 13. Architecture Layers

The architecture should be explicit about boundaries.

### 13.1 Spec Layer

Owns typed intent, environments, tools, permissions, and evaluation criteria.

### 13.2 Reasoning Layer

Owns prompt logic, planning, model decisions, and agentic loops.

### 13.3 Execution Layer

Owns state progression, durable orchestration, resumability, and event history.

### 13.4 Effect Layer

Owns tool adapters, exchange connectors, chain interactions, and side-effecting calls.

### 13.5 Policy Layer

Owns executable checks, approvals, pauses, budgets, and invariants.

### 13.6 Evidence Layer

Owns traces, metrics, approvals, provenance, research evidence, and promotion artifacts.

### 13.7 Inspector And Ops Surface

Owns human visibility and control over specs, runs, policies, and promotion.

## 14. Determinism And Replay Model

`Aether Forge` should distinguish deterministic from non-deterministic surfaces.

The system must define:

- what is replayable exactly
- what is replayable approximately
- what is only auditable, not reproducible

For production trust, the goal is not perfect bitwise replay of every model output. The goal is reliable reconstruction of decisions, policy outcomes, side effects, and evidence relevant to promotion and incident review.

## 15. Crypto-Native Starter Pack

Crypto is the v1 wedge and needs stronger contracts than generic tool calling.

### 15.1 Wallet Control Topology

The product must support explicit wallet control models per agent, such as:

- user-owned
- app-owned
- delegated signer
- quorum or m-of-n controlled
- break-glass or recovery path

### 15.2 Signing Isolation

The product should support pluggable signing backends with declared guarantees such as enclave, HSM, TEE, or co-signer models.

The runtime should never require raw private keys to be available inside ordinary agent logic.

### 15.3 Exchange Capability Model

The framework should expose a venue capability matrix rather than pretending all venues are identical.

The model should capture:

- spot and perp support
- order types
- rate limits
- sandbox availability
- idempotency support
- margin or funding semantics
- venue-specific constraints

### 15.4 Onchain Execution Controls

The framework should support:

- chain allowlists
- contract allowlists
- function-selector or calldata constraints
- recipient allowlists
- simulation or preflight before broadcast
- nonce and replay handling

### 15.5 Data Model

The framework should support:

- market prices
- funding rates
- order book data
- chain state
- account and portfolio state
- custom connectors

### 15.6 Compliance Hooks

The product should be able to integrate AML, KYT, Travel Rule, freeze, or review-state hooks where the user domain requires them.

## 16. Policy Model

Policies must be executable contracts, not just configuration.

### 16.1 Core semantics

The policy system should support:

- default deny
- deny-overrides-allow precedence
- structured decision outputs
- versioned policy bundles
- replayable policy evaluation
- dry-run policy mode

### 16.2 Decision shape

A policy decision should be able to return:

- allow or deny
- violated rule IDs
- severity
- reason
- required approval path
- recommended remediation

### 16.3 Enforcement points

Policy checks should exist at:

- spec validation time
- promotion time
- tool invocation time
- post-action invariant checks
- environment transition time

### 16.4 Runtime approvals

Certain actions should pause for approval, such as:

- designated transfers
- designated trades above thresholds
- risky wallet operations
- changes in permissions or recipients

## 17. Environment Model

The product should support distinct environments with clear semantics.

### 17.1 Local

Local development and dry runs.

### 17.2 Sandbox

Historical replay and synthetic scenario execution.

### 17.3 Shadow

Live inputs and live decisioning with side effects suppressed or mirrored.

### 17.4 Paper

Realistic but non-capital-bearing execution.

### 17.5 Testnet Or Venue Sandbox

Exchange or chain-native non-production environments where available.

### 17.6 Canary Live

Limited-value production execution with capped exposure.

### 17.7 Production

Full live operation under approved controls.

Promotion between these environments should be explicit and evidence-backed.

## 18. Evaluation Model

The product should split evaluation into offline and online stages.

### 18.1 Offline evaluation

Should include:

- replay
- regression packs
- edge and stress scenarios
- policy-violation scenarios
- incident-derived scenarios

### 18.2 Online evaluation

Should include:

- shadow behavior review
- paper evaluation
- canary behavior review
- drift and anomaly monitoring

### 18.3 Scenario requirements

Every promoted agent version should have scenario coverage across:

- baseline behavior
- known failure modes
- dependency outages
- unsafe inputs
- policy boundary attempts
- domain-specific edge cases

### 18.4 Protected Evaluation Surface

The evaluation harness, policy criteria, and promotion thresholds used to judge a candidate must remain fixed during that candidate's comparison cycle.

Slow mode and self-evolution must not weaken the evaluator or relax policy gates in order to claim improvement.

If the team decides the evaluator itself must change, that change should start a new comparison cycle with a new baseline.

## 19. Promotion And Operations

Promotion should be progressive, not a single jump.

### 19.1 Promotion stages

The framework should support staged rollout such as:

- sandbox pass
- shadow review
- paper approval
- canary live
- broader production rollout

### 19.2 Promotion evidence

Promotion should require:

- explicit pass thresholds
- policy summary
- residual risk statement
- required approvals
- environment-specific rollout limits

### 19.3 Runtime safety operations

The framework should support:

- kill switch
- pause and resume
- emergency stop
- partial bypass to manual control
- safe degradation when dependencies fail

### 19.4 Rollback model

The framework should distinguish:

- config rollback
- prompt rollback
- model rollback
- runtime version rollback
- irreversible side-effect handling requiring compensation rather than rollback

### 19.5 Independent review

High-risk promotions should support reviewer separation from the author when required.

## 20. Controlled Self-Evolution

`Aether Forge` should support self-improvement inside the same governance model.

### 20.1 Accepted Mutation Surface

Self-improvement loops should only mutate explicitly allowed surfaces inside an active comparison cycle.

Examples of allowed mutation surfaces may include:

- prompt or planning logic
- tool-selection logic
- bounded scaffold modules
- strategy parameters
- scenario parameters for candidate stress testing

Examples of protected surfaces should include:

- live policy thresholds used to judge the active cycle
- promotion criteria used for the active cycle
- credential boundaries
- environment permissions
- fixed evaluation harness logic for the active cycle

### 20.2 Allowed in v1

- prompt changes
- tool-selection changes
- strategy-safe variant generation
- policy-safe scaffold variants
- scenario-based comparison

### 20.3 Not allowed in v1

- self-promotion to production
- permission expansion without approval
- bypassing policy checks
- bypassing the evaluation loop
- weakening the evaluator used to judge the current cycle

The product model remains:

`learn in bounded loops, prove in evaluation, promote with approval`

## 21. Detailed Functional Requirements

### 21.1 Idea intake and mode selection

- The system must accept plain-language ideas.
- The system must preserve original user intent.
- The system must let the user choose `fast` or `slow` mode.
- The system must expose inferred assumptions.

### 21.2 Spec and artifact generation

- The system must generate a typed, versioned `Agent Spec`.
- The system must validate the spec.
- The system must separate secrets from specs.
- The system must generate a `Capability Manifest` and `Scenario Pack`.

### 21.3 Slow mode research

- Slow mode must build a research plan.
- Slow mode must collect evidence for major recommendations.
- Slow mode must keep a `Research Record`.
- Slow mode must establish and record a baseline before evaluating variants.
- Slow mode must compare variants under fixed or explicitly normalized budgets.
- Slow mode must define measurable improvement criteria before iteration begins.
- Slow mode must assign each iteration a status of `keep`, `discard`, `blocked`, or `execution failure`.
- Slow mode must continue autonomously until stop conditions are met.
- Slow mode must log an iteration ledger with measurable outcomes and rationale.
- Slow mode must use explicit stop conditions.
- Slow mode must only ask blocker questions when necessary.
- Slow mode must not modify the evaluation harness or policy criteria used for the active comparison cycle.

### 21.4 Scaffold generation

- The system must generate an editable scaffold.
- The scaffold must clearly separate generated zones and user-owned zones.
- The scaffold must identify protected mutation zones for active comparison cycles.
- The system must detect drift between spec and scaffold.
- The system must support regeneration with explicit merge behavior.

### 21.5 Runtime execution

- The system must run supervised agent sessions.
- The runtime must support durable pauses and resumptions.
- The runtime must record policy decisions and approval events.
- The runtime must preserve enough history for incident review.

### 21.6 Policy enforcement

- Policies must be executable and versioned.
- The system must support default-deny behavior.
- The system must return structured policy decisions.
- The system must support runtime approval gates.

### 21.7 Crypto execution safety

- The system must support explicit wallet control topologies.
- The system must support protected signing backends.
- The system must support venue capability matrices.
- The system must support idempotency and duplicate-submit protection where available.
- The system must support nonce or replay management for chain interactions.
- The system must support recipient, contract, and chain restrictions.

### 21.8 Evaluation

- The system must support offline and online evaluation stages.
- The system must support historical replay, shadow, paper, and canary patterns.
- The system must support regression comparison between versions.
- The system must support new baselines when the evaluator itself changes.

### 21.9 Promotion and operations

- The system must support staged promotion.
- The system must store promotion evidence.
- The system must support residual-risk documentation.
- The system must support deactivation and incident workflows.

### 21.10 Extensibility and interoperability

- The system must support user-defined tools and adapters.
- The system should support common tool description standards such as MCP where useful.
- The system should support importing or mapping external API descriptions such as OpenAPI when useful.

## 22. Non-Functional Requirements

- reproducible evaluation where possible
- auditable event history
- strong environment separation
- secure credential handling
- explicit secret isolation
- modular architecture
- strong local developer usability
- clear human-readable artifacts
- strong observability and redaction controls
- mode-aware latency expectations
- bounded slow-mode budgets
- explicit completeness and confidence signaling
- iteration comparability across candidate runs
- complexity-aware variant selection

## 23. Observability And Auditability

The system should capture more than raw traces.

It should capture:

- correlation IDs
- tool-call lineage
- policy decisions
- approval events
- environment metadata
- artifact versions
- redaction-aware content logging
- promotion and deactivation events
- per-iteration candidate decisions for slow mode and self-evolution

The logging model must distinguish between audit-required metadata and content that may contain secrets, sensitive prompts, or regulated data.

## 24. Scenario Matrix

The product should explicitly support and test scenarios such as:

- spec-to-scaffold drift after user edits
- baseline-first slow-mode run before variants are tested
- slow-mode blocker question on identity-defining ambiguity
- keep versus discard decision on comparable-budget variants
- policy breach before side effect
- policy breach after partial side effect
- duplicate order submission after retry
- stale-data execution attempt
- unsupported venue capability
- signer compromise or signer revocation
- replay mismatch in evaluation
- shadow pass followed by canary failure
- emergency stop and unwind
- halted agent re-enable review

## 25. Success Metrics

### Builder experience

- time from idea to first fast-mode spec
- time from idea to first slow-mode decision package
- user satisfaction with scaffold quality
- acceptance rate of slow-mode outputs without major rewrite
- baseline-to-improvement delta under fixed budgets
- complexity-adjusted keep rate for slow-mode variants

### Safety and trust

- policy issues found before production
- runtime policy violation rate
- canary failure catch rate before broad rollout
- incident-free live runs
- time to explain an incident from stored evidence

### Product pull

- agents created per active user or team
- percentage reaching evaluation
- percentage reaching canary live
- percentage reaching production
- repeat builds by the same team

## 26. Roadmap And Milestones

### Milestone 1: Typed Spec And Fast Mode

Goal:
Prove that ideas can become typed specs and credible scaffolds quickly.

### Milestone 2: Slow Mode Research Loop

Goal:
Prove that slow mode materially improves outputs, records a baseline, and produces useful research records with keep-or-discard decisions.

### Milestone 3: Policy And Evaluation Core

Goal:
Ship executable policy semantics plus realistic evaluation and scenario infrastructure.

### Milestone 4: Crypto Starter Pack

Goal:
Ship wallet, exchange, onchain, data, and compliance-aware crypto primitives.

### Milestone 5: Promotion And Ops

Goal:
Ship staged promotion, shadow/canary support, approvals, and incident controls.

### Milestone 6: Controlled Evolution

Goal:
Ship governed variant generation and comparison.

## 27. Suggested 12-Month Sequence

### Q1

- typed spec model
- fast mode
- scaffold generator
- initial runtime

### Q2

- slow mode autoresearch engine
- research record and iteration ledger
- baseline and keep-or-discard protocol
- policy core
- scenario packs
- sandbox and shadow primitives

### Q3

- crypto wallet and signing layer
- exchange and onchain modules
- venue capability model
- paper and canary infrastructure

### Q4

- staged promotion
- approvals and residual-risk workflow
- incident operations and deactivation
- controlled evolution loop

## 28. Key Risks

1. The product becomes too broad too early.

2. Slow mode adds cost without meaningful quality lift.

3. The spec and scaffold contract is weak or hard to maintain.

4. Crypto execution safety is underbuilt relative to user expectations.

5. Promotion and rollback semantics are too vague for serious use.

6. The autoresearch loop lacks fair comparison and therefore generates misleading improvements.

7. The product sounds like a generic agent builder instead of a governed agent engineering system.

## 29. Open Questions

- Which chains and exchanges should be first-party in the first crypto pack?
- Which language and runtime should the first scaffold target?
- How much of v1 should be local-first versus hosted?
- Which slow-mode evidence thresholds should be global versus domain-specific?
- Which approval and reviewer models should be mandatory in v1?
- Which compliance hooks are required in the first crypto release versus optional integrations?
- Which measurable criteria should govern keep-or-discard decisions across different agent categories?

## 30. Glossary

### Agent Spec

The typed contract describing the agent, its permissions, dependencies, and evaluation requirements.

### Research Record

The durable evidence log created by slow mode.

### Capability Manifest

The formal inventory of what the agent can access and under what constraints.

### Scenario Pack

The reusable suite of evaluation scenarios and thresholds for an agent version.

### Promotion Record

The evidence package supporting movement between environments.

### Shadow

Live-input execution where the candidate does not own the real side effect path.

### Canary Live

Limited-value or limited-scope live execution used before broader rollout.

### Iteration Ledger

The append-only record of each slow-mode or self-evolution candidate, its budget, measured outcomes, and keep-or-discard decision.

## 31. Final Recommendation

Build `Aether Forge` as a spec-first, developer-first framework with a general core and a crypto-native v1 starter pack.

The product should differentiate on:

- typed specs
- evidence-backed slow mode
- baseline-first, keep-or-discard autoresearch loops
- default-deny policies
- realistic evaluation loops
- staged production promotion
- crypto-native execution safety

That combination is stronger and more defensible than trying to compete as a generic agent runtime.

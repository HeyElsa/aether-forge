# Aether Forge Product Requirements Document

Version: `v0.2.0`
Status: `Draft`
Date: `2026-04-06`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.1.0.md`

## 1. Executive Summary

`Aether Forge` is a developer-first framework for turning an agent idea into a production-capable agent system.

The product begins with a plain-language idea and transforms it into a governed, testable, inspectable agent stack. Instead of producing a one-shot autonomous bot, `Aether Forge` produces a structured specification, an editable scaffold, runtime policies, sandbox environments, and a promotion workflow.

The initial wedge is crypto, because crypto is one of the clearest places where agents are useful and dangerous at the same time. Builders want software that can reason about strategies, interact with wallets and exchanges, adapt over time, and still remain inside rigid boundaries. Scripts are too brittle. Generic agent runtimes are too ungoverned. `Aether Forge` exists between those two extremes.

The product should feel like an `agent engineering system`, not just an agent runtime.

V1 should support two creation modes:

- `Fast mode` for rapid idea-to-spec and idea-to-scaffold generation.
- `Slow mode` for deeper research-backed agent creation using an autoresearch loop that improves the result before presenting it.

The v1 promise is:

> Give me an idea, help me turn it into a structured agent system, let me test it in realistic environments, and only let it reach production with evidence and explicit control.

## 2. Product Thesis

The most valuable agent systems in high-stakes environments will not be the freest ones. They will be the most governable ones.

Users do not only want an LLM that can call tools. They want a way to:

- define what an agent is trying to do
- constrain what it is allowed to touch
- observe how it behaves under stress
- improve it over time without losing control
- move it from draft to production in a disciplined way

That is especially true in crypto, where agents may control wallets, open positions, call exchanges, execute onchain transactions, or affect treasury and risk operations.

`Aether Forge` should therefore be built around six core ideas:

1. `Specification before execution`
2. `Scaffolding before autonomy`
3. `Policy-bound side effects`
4. `Sandbox before production`
5. `Self-improvement without self-governance`
6. `Dual-mode creation depth`

The last principle matters because not every build should take the same path. Some users want a quick first draft. Others want the system to think harder, research the environment, tighten assumptions, and only come back when the draft is materially stronger.

## 3. Problem Statement

Technical builders already know how to prototype ideas. They can write scripts, cron jobs, market data fetchers, execution logic, and prompt wrappers. The problem is that these prototypes rarely become reliable agent systems.

Common failure modes today:

1. The system is too fragmented.
Data ingestion, strategy logic, wallet access, risk controls, and deployment are all built separately with weak guarantees between them.

2. The system is too opaque.
Autonomous agents may act in ways that are difficult to explain, replay, or approve.

3. The system is too unsafe.
Live side effects are often mixed directly into strategy logic, making it hard to enforce permissions or fail safely.

4. The system is hard to evolve.
Builders can add logic, but they cannot confidently let the agent propose improvements, compare variants, and move forward under a review loop.

5. The system is hard to harden.
Even when the raw idea is sound, the early draft often misses critical tool choices, venue constraints, risk policies, or evaluation scenarios.

In crypto, those weaknesses are amplified by capital risk, venue fragmentation, and real operational consequences.

## 4. Product Vision

The long-term vision for `Aether Forge` is a framework where any serious builder can say:

"I have an agent idea. Forge it into a reliable system I can inspect, test, operate, and improve."

The product starts with crypto because that is where the demand for governable agents is strongest, but the core should stay general enough to support:

- research agents
- treasury and finance agents
- operations agents
- execution agents
- knowledge and planning agents
- other domain-specific builders that need the same safety and lifecycle controls

The product should be general at the core and opinionated at the edges.

## 5. Positioning

Short positioning statement:

> `Aether Forge` helps developers turn ideas into reliable, policy-bound agents that can be simulated, improved, and promoted safely into production.

How it should feel in the market:

- more serious than a generic agent playground
- more developer-friendly than a no-code agent builder
- more agent-native than a workflow orchestration tool
- more governable than a free-form autonomous agent runtime
- more thoughtful than a one-shot scaffolding generator

## 6. Primary User

The primary v1 user is the `crypto strategy developer`.

This user is usually:

- technical and comfortable with code
- fluent in market structure, venue behavior, and basic risk concepts
- able to explain a strategy idea in plain language or code terms
- looking for speed without giving up control

Typical examples:

- a builder creating a delta-neutral perp and spot strategy
- a protocol team member building a treasury rebalancer
- a research engineer building a signal synthesis agent
- an operator building a hedge execution assistant

This user does not want an opaque black box and does not want a fully no-code product. They want a scaffold that is close to production shape, with strong defaults and room to edit.

## 7. Secondary Users

Secondary v1 users include:

- protocol or exchange teams building internal operational agents
- crypto product teams building supervised operator agents
- general AI product engineers using the core framework outside crypto

These users matter, but the product should not broaden the UX so much that the primary user experience becomes vague.

## 8. Example Use Case

Reference example for the first product narrative:

"Build an agent that captures delta-neutral value by buying spot BTC, shorting BTC perps when basis exceeds a threshold, capping exposure per venue, monitoring volatility, and unwinding if risk rises above a policy-defined level."

In a script-based world, the user would need to build:

- exchange connectivity
- market data normalization
- decision logic
- wallet and account management
- risk checks
- environment separation
- simulation tools
- deployment and monitoring

In `Aether Forge`, the user should instead be able to:

1. Describe the idea.
2. Choose `fast` or `slow` creation mode.
3. Review the generated spec.
4. Adjust parameters and policies.
5. Generate a working scaffold.
6. Simulate behavior against scenarios.
7. Promote the agent through environments.
8. Review proposed improvements later.

That is the core user promise in concrete form.

## 9. Jobs To Be Done

When I have an agent idea, help me:

- turn it into a clear system instead of a vague prompt
- identify the tools, wallets, and data sources required
- enforce what the agent can and cannot do
- simulate the agent under realistic conditions
- understand why it behaved the way it did
- improve it over time without letting it run wild
- move it into production only when it earns that right
- choose whether I want a quick draft or a deeper researched draft

## 10. Product Principles

### 10.1 Spec-first

The first output should be a structured `Agent Spec`, not a live autonomous agent.

### 10.2 Developer-first

The product should generate inspectable artifacts that strong builders can own and edit.

### 10.3 General core, crypto-native modules

The runtime and core abstractions should stay general. The first-party modules should be highly useful for crypto.

### 10.4 Reliability over novelty

The product should optimize for safe, auditable operation over flashy autonomy.

### 10.5 Governance before production

Anything that can move capital or trigger sensitive actions must live inside a policy and promotion model.

### 10.6 Sandbox-first learning

Agents can improve themselves, but they must prove proposed changes in a sandbox before promotion.

### 10.7 Dual-mode creation

The product should support both rapid generation and deeper research-backed creation.

### 10.8 Slow mode should be patient, not noisy

When the user selects `slow mode`, the system should research, refine, and consolidate before presenting a result. It should not interrupt constantly with half-finished drafts unless blocked by missing critical information or explicitly asked to show progress.

## 11. V1 Product Scope

### In scope

- plain-language idea intake
- `fast` and `slow` creation mode selection
- structured `Agent Spec` generation
- editable spec review
- code and configuration scaffold generation
- autoresearch-driven spec refinement in `slow mode`
- supervised runtime for agent sessions
- policy engine and guardrail definitions
- sandbox environments for replay, paper, and synthetic scenarios
- trace capture and inspection
- manual promotion workflow
- candidate variant generation and comparison
- crypto-native modules for wallets, exchanges, onchain actions, and market data

### Out of scope

- autonomous self-promotion into production
- a consumer-facing no-code product
- a strategy marketplace
- a social distribution layer
- broad enterprise workflow management before the core builder works
- open-ended autonomous research loops with no completion criteria

## 12. Agent Creation Modes

`Aether Forge` should support two distinct creation paths.

### 12.1 Fast Mode

`Fast mode` is optimized for speed to first draft.

It should:

- generate a usable `Agent Spec` quickly
- make lightweight assumptions when possible
- produce a scaffold with strong defaults
- highlight obvious risks and missing details
- favor rapid iteration over exhaustive research

Fast mode is the right choice when the user wants to explore an idea, pressure-test a concept, or get to an editable scaffold quickly.

### 12.2 Slow Mode

`Slow mode` is optimized for draft quality and completeness.

It should run a Karpathy-style autoresearch loop before presenting the result. In practice, that means the system should:

- research the strategy domain and operating context
- inspect likely tools, data sources, venue constraints, and protocol considerations
- identify missing policies, edge cases, and failure modes
- refine the `Agent Spec`
- improve module and adapter choices
- improve policy defaults
- improve the evaluation and simulation plan
- improve the scaffold before the user sees it

Slow mode should feel like the system spent time thinking, not just spent time waiting.

### 12.3 Slow Mode Presentation Behavior

In `slow mode`, the system should present once it believes the draft is `quite complete`.

That means it should wait until it has reached a practical completeness threshold across:

- objective clarity
- tool and data selection
- permissions and policy boundaries
- evaluation scenarios
- major known risks
- recommended module structure

It should present earlier only if:

- it encounters a real blocker that requires user input
- confidence drops below a usable threshold
- the user explicitly asks to see intermediate output

### 12.4 Slow Mode Outputs

Slow mode should return more than just a scaffold. It should return a package of improved artifacts, including:

- a refined `Agent Spec`
- a research summary
- recommended tool and module choices
- policy and guardrail recommendations
- evaluation and scenario recommendations
- open questions and confidence notes
- an improved scaffold or scaffold plan

## 13. Core Product Workflow

The product lifecycle should be:

1. `Ideate`
The user shares a free-form goal, strategy, or workflow idea.

2. `Choose Mode`
The user selects `fast` or `slow` creation mode.

3. `Specify`
The system turns the idea into a structured `Agent Spec`, filling missing assumptions and surfacing risk-sensitive choices.

4. `Refine`
If the user selected `slow mode`, the system runs an autoresearch loop that improves the spec and its supporting decisions before moving on.

5. `Generate`
The system generates an editable `Agent Scaffold` with code, config, adapters, policies, and scenario packs.

6. `Simulate`
The user runs the agent in historical replay, paper, and synthetic environments with full traces and policy checks.

7. `Promote`
The user reviews outcomes, evidence, and policy compliance, then explicitly approves movement into a higher environment.

8. `Operate`
The agent runs live under supervision, within its environment and permission boundaries.

9. `Evolve`
The system proposes candidate changes that must return to the same spec, sandbox, and promotion loop.

This sequence is central to the identity of the product. It should appear consistently in product language, documentation, demos, and architecture.

## 14. Human-Readable Artifact Model

The framework should revolve around four durable objects.

### 14.1 Agent Spec

The `Agent Spec` is the contract for what the agent is and how it is allowed to behave.

It should describe:

- objective
- user intent
- target environment
- available tools
- available side effects
- wallets and credentials
- data dependencies
- policy limits
- evaluation scenarios
- promotion criteria
- failure modes
- success metrics

### 14.2 Agent Scaffold

The `Agent Scaffold` is the generated project a developer owns.

It should include:

- runtime configuration
- agent modules
- tool bindings
- adapter setup
- policy definitions
- scenario packs
- evaluation config
- environment templates
- deployment templates

### 14.3 Runtime Session

The `Runtime Session` is the live or sandbox execution context.

It should track:

- objective state
- execution history
- budgets
- tool calls
- model calls
- policy events
- pauses and approvals
- traces and outputs

### 14.4 Promotion Record

The `Promotion Record` is the evidence package behind any environment transition.

It should contain:

- the version under review
- the scenarios that ran
- performance metrics
- policy outcomes
- comparisons against baseline
- approval metadata

## 15. System Architecture

The v1 architecture should be organized into seven major components.

### 15.1 Spec Engine

Transforms raw user intent into structured, editable product artifacts.

Responsibilities:

- intake raw ideas
- ask for or infer missing details
- normalize goals and constraints
- surface ambiguous assumptions
- identify tools, data, and policies
- emit machine-usable spec documents

### 15.2 Autoresearch Engine

Improves slow-mode outputs before presentation.

Responsibilities:

- perform research loops against relevant domain context
- compare candidate approaches and tool choices
- identify missing constraints and risks
- improve policy suggestions and environment assumptions
- enrich scenario design for simulation
- score draft completeness and confidence
- decide whether to present, keep refining, or ask a targeted blocker question

This engine should be designed as an autoresearch loop inspired by Karpathy-style research agents, but grounded in `Aether Forge`'s product needs: better specs, safer agents, and more credible scaffolds.

### 15.3 Scaffold Generator

Produces a runnable project from the spec.

Responsibilities:

- generate code and configuration layout
- bind selected adapters and modules
- create policy and scenario files
- create deployment and environment templates
- produce a runnable local developer surface

### 15.4 Runtime

Executes agent sessions under supervision.

Responsibilities:

- manage session state
- coordinate tool and model access
- enforce budgets and timeouts
- emit traces and execution events
- integrate policy decisions into runtime flow

### 15.5 Policy Engine

Separates permission logic from strategy logic.

Responsibilities:

- wallet authorization
- venue restrictions
- exposure caps
- action restrictions
- leverage and drawdown limits
- cooldown and emergency-stop behavior

### 15.6 Sandbox Runner

Tests agent behavior before production use.

Responsibilities:

- historical replay
- paper execution
- synthetic stress scenarios
- deterministic run capture where possible
- metrics and evaluation output

### 15.7 Inspector and Ops Surface

Gives developers and operators visibility into the system.

Responsibilities:

- spec review
- run inspection
- trace playback
- policy event review
- scenario comparison
- promotion approvals
- slow-mode research summary review

## 16. Crypto-Native Starter Pack

Crypto should be a first-class starter pack in v1 rather than an afterthought.

### 16.1 Wallet Modules

The base framework should support:

- scoped wallet permissions
- environment-aware signing behavior
- dry-run and simulation modes
- multi-wallet and multi-account support
- policy-gated action approval

### 16.2 Exchange Modules

The base framework should support:

- spot adapters
- perpetual futures adapters
- position and balance reads
- order placement and cancellation
- venue-specific safety wrappers
- fee and funding awareness

### 16.3 Onchain Modules

The base framework should support:

- chain data reads
- transaction construction
- policy-aware transaction execution
- protocol adapter surfaces for common actions

### 16.4 Data Source Modules

The base framework should support:

- market prices
- funding rates
- order book snapshots
- chain state
- account and portfolio state
- user-defined custom connectors

## 17. Safety Model

Safety is not a feature layer. It is one of the reasons the product exists.

Any action with side effects should pass through a governed execution path. A strategy module may decide what it wants to do, but the runtime and policy engine decide whether it is allowed to happen.

### Required policy categories in v1

- wallet allowlists
- venue allowlists
- maximum notional exposure
- maximum order size
- leverage limits
- drawdown limits
- cooldown windows
- rate limits
- action-type restrictions
- emergency stop conditions

### Safety design rules

1. Policies must be versioned and inspectable.
2. Policies must apply in sandbox and production.
3. Side-effecting tools must declare risk metadata.
4. Environment boundaries must be explicit.
5. Failure should default to safe halt or explicit pause.

## 18. Sandbox And Evaluation

The sandbox must be treated as a real environment tier.

It should answer four questions clearly:

1. What would the agent have done?
2. Did it remain inside policy?
3. How did it perform?
4. Why did it make each decision?

### Sandbox modes

- historical replay
- paper execution
- synthetic stress scenarios

### Default evaluation pack for each generated agent

- baseline scenarios
- edge-case scenarios
- policy violation checks
- success metrics from the spec
- regression comparison against previous versions

The product should make simulation feel as normal as running tests in a software project.

## 19. Controlled Self-Evolution

`Aether Forge` should support self-improvement, but only inside a governed loop.

### Allowed in v1

- proposing prompt changes
- proposing tool-selection changes
- proposing policy-safe strategy changes
- generating scaffold variants
- comparing variants in sandbox

### Not allowed in v1

- autonomous promotion to production
- autonomous expansion of wallet or environment permissions
- skipping the simulation loop
- bypassing approval controls

The operating model is:

`learn in sandbox, promote with evidence, deploy with approval`

## 20. Environment Model

The framework should recognize distinct environments rather than a single runtime.

### Local

Used for scaffold generation, manual development, and local dry runs.

### Sandbox

Used for replay, simulation, and synthetic scenario evaluation.

### Paper

Used for realistic but non-capital-bearing execution.

### Production

Used for real side effects with live policies, credentials, and observability.

Promotion between these environments should always be explicit and evidence-backed.

## 21. Detailed Functional Requirements

### Idea intake and specification

- The system must accept a plain-language idea.
- The system must preserve the user intent and show what assumptions it inferred.
- The system must allow the user to select `fast` or `slow` creation mode.
- The system must produce an editable `Agent Spec`.
- The system must distinguish between objective, tools, permissions, policies, and environments.

### Fast mode requirements

- Fast mode must optimize for speed to first credible draft.
- Fast mode must produce a usable spec and scaffold without requiring exhaustive research.
- Fast mode must still surface important unknowns and obvious risk gaps.

### Slow mode requirements

- Slow mode must run an autoresearch loop before presentation.
- Slow mode must refine the spec, tool choices, policy suggestions, and evaluation plan.
- Slow mode must accumulate research findings into a human-readable summary.
- Slow mode must decide whether the draft is complete enough to present.
- Slow mode must only interrupt early when blocked by a missing critical input or when explicitly asked for progress.
- Slow mode must expose open questions and confidence notes with the returned result.

### Scaffold generation

- The system must generate an editable project scaffold.
- The scaffold must be understandable by a developer without hidden product-only logic.
- The scaffold must include config for environments, policies, adapters, and evaluation.

### Runtime execution

- The system must run supervised agent sessions.
- The runtime must capture state and event history.
- The runtime must integrate policy decisions into execution.
- The runtime must support pauses, failures, and resumable state where possible.

### Tooling and adapters

- The system must support modular tools and adapters.
- Side-effecting tools must declare risk metadata.
- The system must support wallet, exchange, onchain, and market-data modules in v1.

### Policy and safety

- The system must enforce runtime policies independently of strategy code.
- The system must support versioned guardrail definitions.
- The system must fail safely when a policy boundary is crossed.

### Simulation and evaluation

- The system must run replay, paper, and synthetic scenarios.
- The system must emit results suitable for comparison.
- The system must allow new variants to be evaluated against prior versions.

### Promotion and operations

- The system must support explicit approval before promotion.
- The system must store evidence supporting a promotion.
- The system must expose traces and policy events to users.

### Extensibility

- The system must allow user-defined tools and data connectors.
- The system must allow new domain packs without changing the core runtime model.

## 22. Non-Functional Requirements

- reproducible sandbox runs where possible
- auditable history for significant actions
- strong separation between environments
- secure credential handling
- safe default failure behavior
- modular architecture
- local developer usability
- clear human-readable artifacts
- strong observability for debugging and review
- mode-aware latency and progress expectations
- explicit completeness and confidence signaling for slow mode

## 23. UX Expectations

The product should not feel like a toy prompt box.

Expected UX qualities:

- generated output should read like a thoughtful engineering artifact
- the user should see assumptions, not just conclusions
- dangerous permissions should be obvious and reviewable
- simulation output should be understandable by a technical user
- promotion should feel like shipping software, not clicking "go live"
- fast mode should feel quick, reversible, and easy to iterate on
- slow mode should feel like a careful research assistant that comes back with materially better work
- slow mode should not spam the user with small intermediate deltas unless blocked or asked

## 24. Success Metrics

### Builder experience

- time from idea to first valid fast-mode spec
- time from approved spec to runnable scaffold
- time from scaffold to first sandbox pass
- percentage of generated scaffolds needing only bounded edits
- user satisfaction with scaffold quality
- acceptance rate of slow-mode drafts without major rework

### Safety and trust

- policy issues found before production
- production policy violation rate
- incident-free live runs
- time to explain agent behavior from traces
- percentage of promoted versions with complete evidence packages

### Product pull

- number of agents created per active user or team
- percentage of created agents reaching sandbox
- percentage of sandboxed agents reaching production
- repeat builds by the same user or team
- usage split between fast and slow mode

## 25. Roadmap And Milestones

### Milestone 1: Fast Mode Spec-to-Scaffold

Goal:
Prove that free-form ideas can become high-quality specs and useful editable scaffolds quickly.

Exit criteria:

- coherent fast-mode spec generation
- credible scaffold quality
- runnable local output
- clear surfacing of missing assumptions

### Milestone 2: Slow Mode Research-Refined Creation

Goal:
Prove that the autoresearch loop materially improves agent drafts before presentation.

Exit criteria:

- slow mode produces better specs than fast mode on benchmark ideas
- research findings are human-readable and useful
- completeness thresholds behave predictably
- the system asks blocker questions only when genuinely needed

### Milestone 3: Safe Simulation

Goal:
Prove that generated agents can be tested in deterministic or controlled environments.

Exit criteria:

- replay works end to end
- scenario packs run correctly
- traces and policy events are visible

### Milestone 4: Crypto Pack

Goal:
Ship the wedge that makes the product compelling to crypto strategy developers.

Exit criteria:

- wallet support ships
- exchange modules ship
- onchain modules ship
- market-data modules ship
- financial guardrail templates ship

### Milestone 5: Promotion And Operations

Goal:
Create a trustworthy path from sandbox to live operation.

Exit criteria:

- promotion records exist
- explicit approval path exists
- paper and production environments are clearly separate
- live traces can be inspected

### Milestone 6: Controlled Evolution

Goal:
Support supervised self-improvement without self-deployment.

Exit criteria:

- variants can be generated
- variants can be compared in sandbox
- recommended changes can be manually promoted

## 26. Suggested 12-Month Sequence

### Q1

- spec engine
- fast mode spec-to-scaffold flow
- initial local runtime
- project artifact model

### Q2

- autoresearch engine
- slow mode completeness logic
- inspector
- sandbox runner
- policy engine

### Q3

- wallet modules
- exchange modules
- onchain modules
- market-data library
- crypto starter templates

### Q4

- promotion records
- team approvals
- variant testing
- controlled self-evolution loop

## 27. Key Risks

1. The product becomes too broad too early.
If the core user and wedge blur, the product becomes generic.

2. The generated spec or scaffold is weak.
If the first artifact is not credible, the product loses trust immediately.

3. The slow mode research loop adds time without quality.
If slow mode does not materially improve the result, it becomes an expensive delay.

4. The safety model is incomplete.
If live actions are not bounded tightly enough, serious users will not trust the platform.

5. The system over-invests in platform UX before the core builder works.
If the control plane grows faster than the spec and scaffold engine, the product becomes bloated.

6. Self-evolution is framed irresponsibly.
If the product sounds like uncontrolled self-modifying automation, it will create justified resistance.

## 28. Dependencies And Assumptions

- a stable spec representation will be needed early
- module boundaries must stay clean enough to support future domain packs
- wallet and exchange integrations will need strong environment handling
- simulation quality will strongly shape user trust
- the first supported language and runtime should be chosen deliberately, not implicitly
- slow mode will need a credible research source strategy and a clear completion heuristic

## 29. Open Questions

- Which chains and exchanges should be first-party in the first crypto pack?
- How local-first should the initial experience be?
- Which language and runtime should the first scaffold target?
- Which performance metrics should be standardized for strategy agents?
- How much team approval workflow is needed before full org-level controls exist?
- What exact completeness threshold should slow mode use across different agent categories?

## 30. Glossary

### Agent Spec

The structured contract describing an agent's objective, permissions, policies, data, and evaluation model.

### Agent Scaffold

The generated developer-owned project implementing the spec.

### Runtime Session

A supervised live or sandbox execution context for the agent.

### Promotion Record

The evidence package supporting movement between environments.

### Sandbox

A non-production environment tier used for replay, simulation, evaluation, and policy validation.

### Fast Mode

The rapid creation path optimized for speed to first credible draft.

### Slow Mode

The research-refined creation path that uses an autoresearch loop to improve the draft before presenting it.

## 31. Final Recommendation

Build `Aether Forge` as a spec-first, developer-first framework with a general core and a crypto-native v1 starter pack.

Do not lead with maximal autonomy.
Lead with structured generation, governed execution, realistic simulation, evidence-backed promotion, and dual-mode agent creation.

`Fast mode` should get builders to a strong first draft quickly.
`Slow mode` should think harder, research more deeply, improve the draft, and present when it is materially more complete.

That positioning gives the project a clear identity, a strong initial wedge, and a believable path to becoming the default framework for serious agents in high-stakes environments.

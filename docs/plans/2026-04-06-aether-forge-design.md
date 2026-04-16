# Aether Forge PRD

Date: 2026-04-06
Status: Superseded by PRD v0.7.0
Owner: OpenCode + user

Canonical PRD: `docs/prd/aether-forge-prd-v0.7.0.md`

Note: This file is the original design and brainstorming draft. The human-readable, versioned PRD now lives under `docs/prd/`.

## 1. Summary

`Aether Forge` is a developer-first framework that turns an agent idea into a production-capable agent system.

The product starts with a free-form idea such as a crypto strategy, treasury workflow, or research task, and converts it into:

- a structured `Agent Spec`
- an editable `Agent Scaffold`
- a governed runtime with policies and guardrails
- a sandbox for simulation and evaluation
- a promotion path from sandbox to production

The initial wedge is crypto. V1 ships with first-class wallet, exchange, onchain, and market-data capabilities, but the core framework remains domain-agnostic so other agent categories can use the same system.

The central product promise is:

> Turn an idea into a reliable, inspectable, self-improving agent without handing users an opaque autonomous black box.

## 2. Problem

Today, technical builders can prototype agent behavior with scripts, prompts, cron jobs, and APIs, but they struggle to turn those experiments into reliable systems.

This is especially painful in crypto and other high-stakes domains where agents may:

- hold credentials
- access wallets
- call exchanges or onchain protocols
- manage capital
- need to operate under explicit risk constraints

Existing approaches usually fail in one of two ways:

1. They are too manual.
Builders wire together scripts, API calls, risk checks, data ingestion, and deployment logic by hand. These systems are fragile and hard to evolve safely.

2. They are too opaque.
Some agent platforms make it easy to spin up autonomous behavior, but they do not make it easy to inspect assumptions, enforce policies, run realistic simulations, or control promotion to production.

The user does not just need an agent runtime. They need an `agent engineering system` that helps generate, harden, test, and ship serious agents.

## 3. Vision

`Aether Forge` should be the framework where a builder can say:

"I have an agent idea. Turn it into a safe, inspectable, testable agent system that I can evolve over time."

In v1, the experience should feel like a disciplined forge pipeline:

1. Capture the idea.
2. Convert it into a precise `Agent Spec`.
3. Generate an editable scaffold.
4. Attach tools, wallets, data, and policies.
5. Simulate behavior in a sandbox.
6. Promote the agent into higher environments with evidence.
7. Let the system propose improvements that must re-enter the same review loop.

The product should feel more like software delivery for agents than chatbot assembly.

## 4. Product Principles

1. Spec before execution
The first artifact is a structured specification, not a running bot.

2. Developer-first
Generated output must be inspectable, editable, and useful to serious technical builders.

3. General core, crypto-native modules
The platform core stays domain-agnostic while v1 ships with a strong crypto starter pack.

4. Reliability over novelty
The system must favor safe execution, traceability, and policy enforcement over flashy autonomy.

5. Controlled self-evolution
Agents may propose changes and generate variants, but production promotion remains governed.

6. Sandbox is a real environment tier
Simulation, paper execution, and stress testing are first-class product surfaces.

## 5. Target Users

### Primary user

`Crypto strategy developers`

These users are technically strong builders who have ideas for agents such as:

- delta-neutral perp and spot strategies
- funding-rate capture
- treasury allocation and rebalancing
- market surveillance
- research and signal synthesis
- execution and hedging workflows

They do not want a no-code toy. They want a generated starting point that is close to production shape and easy to extend.

### Secondary users

- protocol or exchange teams building internal agents
- crypto product teams building managed operator agents
- general AI product engineers using the non-crypto core

## 6. Jobs To Be Done

When I have an agent idea, help me:

- turn it into a clear architecture instead of a vague prompt
- define the tools, wallets, and data needed to run it
- enforce guardrails so the agent cannot exceed its mandate
- simulate it under realistic conditions before it touches production
- understand why it behaved the way it did
- improve it over time without losing control

## 7. V1 Scope

### In scope

- plain-language idea intake
- `Agent Spec` generation and editing
- scaffold generation for a developer-owned agent project
- policy and guardrail framework
- runtime for supervised agent sessions
- sandbox environments for simulation and paper execution
- trace capture and inspection
- manual promotion workflow from sandbox to production
- controlled variant generation and evaluation
- crypto-native starter modules:
  - wallet connectors
  - exchange adapters
  - onchain action adapters
  - market-data providers
  - financial policy templates

### Out of scope for v1

- fully autonomous self-promotion to production
- retail strategy marketplace
- consumer-facing no-code product
- broad social or collaborative distribution network
- fully managed hosted control plane for every workflow

## 8. Core User Flow

The core product flow is:

1. `Ideate`
The user provides a free-form idea, for example:
"Build an agent that captures delta-neutral value by buying spot, shorting perps when basis is high, limiting venue exposure, and unwinding on volatility spikes."

2. `Specify`
`Aether Forge` converts the idea into an `Agent Spec` containing objective, environment, allowed actions, wallet permissions, data needs, constraints, risks, evaluation scenarios, and promotion criteria.

3. `Generate`
The framework generates an editable `Agent Scaffold` that includes code, config, tool bindings, policies, scenario packs, and deployment templates.

4. `Simulate`
The user runs the agent in historical replay, synthetic stress, and paper environments with full trace capture.

5. `Promote`
The user reviews outcomes, policy compliance, and promotion criteria, then manually approves movement to the next environment.

6. `Operate`
The live agent runs under runtime supervision with continuous observability.

7. `Evolve`
The system proposes candidate improvements that must return through `Specify`, `Simulate`, and `Promote` before deployment.

## 9. Core Objects

### 9.1 Agent Spec

The canonical description of the agent.

Contains:

- objective and success metrics
- domain context
- tools and action space
- wallet and account permissions
- data sources
- policy constraints
- failure conditions
- simulation scenarios
- promotion gates

### 9.2 Agent Scaffold

The generated project that a developer owns and edits.

Contains:

- strategy modules
- runtime config
- adapter bindings
- policy definitions
- scenario and evaluation config
- deployment and environment templates

### 9.3 Runtime Session

The execution context for a live or sandbox agent run.

Contains:

- current objective
- state
- action history
- budget usage
- tool invocations
- policy events
- traces and decisions

### 9.4 Promotion Record

The evidence package for moving an agent version to a higher environment.

Contains:

- version under review
- scenario results
- policy status
- comparison against baseline
- human approval metadata

## 10. Product Components

### 10.1 Spec Engine

Turns raw user intent into a structured, editable `Agent Spec`.

Responsibilities:

- interrogate missing requirements
- normalize ambiguous ideas
- surface safety-sensitive assumptions
- propose tools, data, and policies
- produce machine-usable spec artifacts

### 10.2 Scaffold Generator

Builds a developer-friendly project from the spec.

Responsibilities:

- generate code and config structure
- attach selected adapters and modules
- create simulation and policy files
- produce a runnable local environment

### 10.3 Runtime

Executes agent sessions under supervision.

Responsibilities:

- manage state and step progression
- enforce budgets, timeouts, and policies
- isolate tools and credentials
- capture traces and execution history

### 10.4 Policy Engine

Applies hard runtime constraints independent of strategy logic.

Responsibilities:

- wallet permission checks
- risk rule enforcement
- venue allowlists and denylists
- exposure and leverage limits
- emergency stop handling

### 10.5 Sandbox Runner

Runs agents safely before production.

Responsibilities:

- historical replay
- paper trading
- synthetic stress tests
- deterministic scenario execution
- metrics and result packaging

### 10.6 Inspector / Ops Console

Developer and operator control surface for inspection and promotion.

Responsibilities:

- spec review
- trace viewing
- policy event inspection
- scenario comparison
- promotion approvals

## 11. Crypto-Native Base Modules

V1 should ship with strong first-party crypto modules because they are part of the wedge, not an optional ecosystem detail.

### Wallet capabilities

- hot wallet integration
- policy-bound signing
- scoped permissions per agent
- dry-run and simulation modes
- support for multiple accounts and venue identities

### Exchange capabilities

- spot and perp venue adapters
- order placement and cancellation
- position and balance reads
- funding and fee awareness
- venue-specific safety wrappers

### Onchain capabilities

- chain data reads
- transaction construction
- policy-aware execution
- protocol adapter surface for common actions

### Data sources

- price feeds
- funding rates
- order book snapshots
- chain state
- portfolio state
- custom user-provided data connectors

## 12. Safety Model

Safety is a product pillar.

All high-risk agent capabilities must be bounded by runtime-enforced policies rather than strategy code alone.

### Required policy categories in v1

- wallet allowlists
- venue allowlists
- max notional exposure
- max per-trade sizing
- leverage caps
- max drawdown
- cooldown windows
- rate limits
- action type restrictions
- circuit breakers and emergency stop

### Safety design rules

1. Policies must be inspectable and versioned.
2. Policies must be enforced in sandbox and production.
3. Side-effecting tools must declare risk metadata.
4. Secret isolation must be environment-specific.
5. Failure should default to safe halt, not blind retry.

## 13. Sandboxing And Evaluation

The sandbox is a first-class environment tier.

It exists to answer:

- What would this agent have done?
- Would it have stayed within policy?
- How did it perform across conditions?
- Why did it make each decision?

### V1 sandbox modes

- historical replay
- paper execution
- synthetic stress scenarios

### Default evaluation pack per generated agent

- baseline scenario set
- edge-case scenario set
- policy violation checks
- success metrics from the spec
- regression comparison against prior versions

## 14. Self-Evolution Model

`Aether Forge` supports self-improvement, but not uncontrolled self-governance.

### Allowed in v1

- propose prompt changes
- propose tool-selection changes
- propose decision-policy changes
- generate alternative scaffold variants
- compare variants in sandbox

### Not allowed in v1

- auto-promote to production
- expand permissions without approval
- bypass simulation and policy checks
- modify live environment boundaries autonomously

The model is:

`learn in sandbox, promote with evidence, deploy with approval`

## 15. Functional Requirements

### FR-1 Idea intake

The product must accept a plain-language agent idea and preserve the original user intent.

### FR-2 Spec generation

The product must produce a structured `Agent Spec` with editable fields and clear assumptions.

### FR-3 Scaffold generation

The product must generate an editable project scaffold from the spec.

### FR-4 Module attachment

The product must support attaching tool, wallet, exchange, onchain, and data modules to the scaffold.

### FR-5 Runtime supervision

The product must run agents under a supervised runtime with policy enforcement and trace capture.

### FR-6 Sandbox execution

The product must execute agents in replay, paper, and synthetic environments.

### FR-7 Promotion workflow

The product must support promotion decisions backed by evidence and explicit approval.

### FR-8 Variant evaluation

The product must allow generation and comparison of candidate agent improvements.

### FR-9 Extensibility

The product must let developers add custom tools, policies, and adapters without forking the system.

## 16. Non-Functional Requirements

- reproducible sandbox runs
- auditable action history
- environment isolation
- safe failure defaults
- typed or strongly structured interfaces where possible
- local developer usability
- secure credential handling
- modular extension points

## 17. Success Metrics

### Builder experience

- time from idea to first valid `Agent Spec`
- time from spec approval to runnable scaffold
- time from scaffold to first sandbox pass
- percentage of generated scaffolds that need only bounded edits
- developer satisfaction with output quality

### Safety and trust

- sandbox-detected issues before promotion
- runtime policy violation rate
- incident-free production runs
- mean time to understand agent behavior from traces
- percentage of promotions backed by complete evidence packages

### Product pull

- number of agents created per active team
- number of agents reaching sandbox
- number of agents reaching production
- repeat usage for second and third agent builds

## 18. Roadmap And Milestones

### Milestone 1: Spec-to-Scaffold

Goal:
Prove that free-form ideas can reliably become useful `Agent Specs` and high-quality editable scaffolds.

Exit criteria:

- spec engine produces coherent outputs
- scaffold output feels credible to developers
- generated projects run locally

### Milestone 2: Safe Simulation

Goal:
Prove that generated agents can be evaluated in deterministic sandbox environments.

Exit criteria:

- historical replay works end to end
- scenario packs are attachable per agent
- traces and policy events are inspectable

### Milestone 3: Crypto Pack

Goal:
Make the framework meaningfully differentiated for crypto strategy developers.

Exit criteria:

- wallet support ships
- exchange adapters ship
- onchain actions ship
- market-data connectors ship
- financial guardrail templates ship

### Milestone 4: Promotion And Operations

Goal:
Create a trustworthy path from sandbox to live operation.

Exit criteria:

- promotion records exist
- approval workflow exists
- paper and production environments are separable
- live trace inspection works

### Milestone 5: Controlled Evolution

Goal:
Support supervised self-improvement without self-deployment.

Exit criteria:

- agent variants can be generated
- comparative sandbox evaluation works
- recommended changes can be reviewed and promoted manually

## 19. Suggested 12-Month Sequence

### Q1

- spec engine
- scaffold generator
- local runtime
- local project model

### Q2

- sandbox runner
- inspector
- policy engine
- deterministic scenario execution

### Q3

- crypto pack
- wallets
- exchange and onchain modules
- data-source library

### Q4

- team approvals
- promotion records
- variant testing
- controlled self-evolution loop

## 20. Positioning

`Aether Forge` is not just an agent runtime.

It is a framework for `forging agents from ideas into governed production systems`.

Short positioning statement:

> Aether Forge helps developers turn ideas into reliable, policy-bound agents that can be simulated, improved, and promoted safely into production.

## 21. Key Risks

1. Over-generalization
If the product tries to serve every agent use case equally from day one, it may lose its wedge and feel vague.

2. Low-quality generation
If the spec or scaffold quality is weak, the core value proposition collapses.

3. Safety gaps
If wallet or exchange actions are not tightly governed, the system will not be trusted.

4. Too much platform, too early
If the product over-invests in a control plane before the core generation and runtime loop works, it will become bloated.

5. False autonomy promise
If "self-evolving" is framed as unchecked self-modification, the product will sound irresponsible in high-risk domains.

## 22. Open Questions

- Which chains and exchanges should be first-party in the first crypto pack?
- How much of the v1 experience should be local-first versus hosted?
- Should generated scaffolds target one primary language and runtime first?
- Which evaluation metrics should be standardized for strategy agents versus custom per user?
- What level of human approval workflow is enough for early teams before full RBAC and org controls?

## 23. Recommendation

Build `Aether Forge` as a spec-first, developer-first agent framework with a general core and a crypto-native v1 module pack.

Do not lead with full autonomy.
Lead with `structured generation, governed execution, realistic sandboxing, and evidence-backed promotion`.

That gives the product a clear identity, a strong wedge, and a practical path to becoming the default framework for serious agents in high-stakes environments.

# Aether Forge v0.6.0 Implementation Plan

Date: 2026-04-06
Status: Draft
Related PRD: `docs/prd/aether-forge-prd-v0.7.0.md`
Related design: `docs/plans/2026-04-06-aether-forge-schema-design.md`

## 1. Goal

This plan turns PRD `v0.6.0` into a concrete implementation sequence.

The objective is not to build the whole vision at once. It is to establish the smallest implementation path that proves the core product contract:

- typed artifacts
- spec-first generation
- governed runtime execution
- governed persistent memory
- realistic evaluation
- staged promotion
- crypto-native capability boundaries
- bounded slow-mode improvement loops

## 2. Recommended Implementation Target

Recommendation for the first implementation target:

- language/runtime: `Python 3.12+`
- canonical schemas: `JSON Schema 2020-12`
- runtime validator: `jsonschema`
- repository shape: `single Python package + schemas/ + examples/`

Rationale:

- Python is strong for agent systems, research loops, runtime control logic, and domain integrations.
- JSON Schema plus `jsonschema` gives immediate machine validation and portability.
- A single-package Python layout is the smallest clean implementation surface for the current repo phase.

## 3. Implementation Principles

1. Build the artifact kernel first.
2. Keep local-first workflows as the default.
3. Treat runtime policy enforcement as non-optional.
4. Simulate before integrating real side effects.
5. Keep generated output readable and diffable.
6. Add crypto connectors only after capability contracts exist.
7. Do not build a hosted control plane before the local system is coherent.

## 4. Proposed Repository Layout

```text
schemas/
  common/
  artifacts/
  runtime/

src/
  aether_forge/
    artifacts.py
    cli.py
    generator.py
    runtime.py
    policy.py
    evals.py
    crypto.py
    memory.py

tests/

examples/
  delta-neutral-btc/

docs/
  prd/
  plans/
```

### Module responsibilities

`src/aether_forge/artifacts.py`

- load and normalize artifacts
- schema validation
- compatibility and migration checks
- export and import helpers

`src/aether_forge/generator.py`

- idea-to-spec generation
- artifact-set construction
- scaffold manifest generation

`src/aether_forge/runtime.py`

- runtime sessions
- step ledger
- credential-handle resolution boundary

`src/aether_forge/policy.py`

- policy bundle loading
- policy decision envelope
- approval gates
- fail-closed enforcement hooks

`src/aether_forge/evals.py`

- scenario pack runner
- stage outcomes
- promotion evidence assembly

`src/aether_forge/crypto.py`

- wallet capability descriptors
- exchange capability descriptors
- onchain capability descriptors
- crypto-specific guardrail helpers

`src/aether_forge/memory.py`

- typed memory record interfaces
- environment-scoped memory read/write/promote flows
- secure default memory promotion policy

`src/aether_forge/cli.py`

- local developer entry point
- commands for init, validate, generate, eval, promote

## 5. Implementation Phases

## Phase 0: Foundation

Goal:

- create the base repo structure and developer workflow

Deliverables:

- `pyproject.toml`
- local virtualenv workflow
- test setup
- `schemas/` directory and schema build tooling
- initial CLI shell

Acceptance criteria:

- repository installs and tests cleanly
- CLI command skeleton runs
- schema files load in validation tests

## Phase 1: Artifact Kernel

Goal:

- make the artifact system real before runtime or crypto work expands

Deliverables:

- shared artifact envelope schema
- `Agent Spec` schema
- `Capability Manifest` schema
- `Scenario Pack` schema
- `Research Record` schema
- `Promotion Record` schema
- `Memory Record` schema
- `Scaffold Manifest` schema
- compatibility and migration validators
- stable JSON export path
- memory schema integration

Acceptance criteria:

- example artifact set validates end to end
- compatibility statuses are enforced
- migration contract requirements are enforced
- secret-bearing fields are rejected in `Agent Spec`
- memory records reject secret-like fields and require sensitivity metadata

Tests:

- schema fixtures
- invalid fixture coverage
- compatibility mismatch tests
- secret-field rejection tests

## Phase 2: Fast Mode Generator

Goal:

- turn an idea into a valid first-pass artifact set and scaffold

Deliverables:

- idea intake interface in CLI
- normalized draft `Agent Spec` generation
- baseline `Capability Manifest` generation
- baseline `Scenario Pack` generation
- scaffold manifest generation
- readable project scaffold template

Acceptance criteria:

- a local command can produce a valid artifact set from a seed prompt
- output scaffold contains machine-readable ownership metadata
- scaffold regeneration modes are represented correctly

Tests:

- snapshot tests for scaffold output
- artifact normalization tests
- drift-detection tests against edited fixtures

## Phase 3: Policy And Runtime Core

Goal:

- implement governed execution before live crypto integrations

Deliverables:

- runtime session model
- runtime step ledger
- policy decision envelope
- approval gate interface
- credential-handle resolver boundary
- memory read/write/promote interfaces
- fail-closed behavior for missing policy/approval dependencies

Acceptance criteria:

- a simulated side-effect attempt cannot execute without a valid policy decision
- runtime never exposes raw credential values to ordinary agent logic or persisted step state
- sandbox memory cannot promote into live-like environments without approval
- policy decisions link to effect records

Tests:

- fail-closed tests
- policy-to-effect linkage tests
- step ledger integrity tests
- credential redaction tests
- memory promotion policy tests

## Phase 4: Evaluation And Promotion Core

Goal:

- make sandbox and promotion workflows concrete

Deliverables:

- scenario pack runner
- stage outcome model
- offline evaluation runner
- shadow/paper/canary stubs and local simulation modes
- promotion record assembly
- rollout limit enforcement hooks
- rollback target and verification model

Acceptance criteria:

- every evaluation stage produces typed outcomes
- promotion records include artifact refs, rollout limits, and decisions
- automatic hold triggers can stop a canary simulation

Tests:

- stage outcome tests
- rollout hold tests
- rollback verification tests
- incident-to-regression tests

## Phase 5: Crypto Capability Pack

Goal:

- add the v1 wedge after the capability contract is stable

Deliverables:

- wallet capability descriptors
- exchange capability descriptors
- onchain capability descriptors
- credential-handle requirements for crypto actions
- effect semantics metadata for crypto actions
- mock adapters for spot, perp, and onchain flows

Acceptance criteria:

- crypto capabilities declare idempotency and compensation semantics
- recipient, contract, and chain restrictions are representable
- duplicate-submit and nonce-handling tests exist for mocked providers

Tests:

- capability schema fixtures
- mock wallet action tests
- duplicate-submit handling tests
- compensation-class tests

## Phase 6: Slow Mode And Autoresearch Loop

Goal:

- implement the bounded improvement loop after artifacts, runtime, and eval exist

Deliverables:

- active comparison contract
- iteration ledger
- baseline-first loop controller
- keep/discard decision engine
- fixed-budget comparison hooks
- research record assembly

Acceptance criteria:

- slow mode creates a baseline before variants
- a candidate cannot be marked `keep` without the required evidence
- changing evaluator or policy thresholds forces a new comparison cycle

Tests:

- keep/discard rule tests
- comparison contract immutability tests
- budget-normalization tests
- blocked/execution-failure path tests

## 7. CLI Plan

Recommended early CLI surface:

- `forge init`
- `forge validate`
- `forge generate`
- `forge eval`
- `forge promote`
- `forge slow-run`

The CLI should remain the primary v1 surface.

A richer inspector UI can come later after the local CLI and artifact flows are solid.

## 8. Example First End-To-End Slice

The first meaningful vertical slice should be:

1. user provides a delta-neutral strategy idea
2. `forge generate` creates:
   - `Agent Spec`
   - `Capability Manifest`
   - `Scenario Pack`
   - `scaffold.manifest.json`
3. `forge validate` confirms artifact integrity
4. `forge eval` runs sandbox scenarios with stage outcomes
5. `forge promote --target paper` produces a `Promotion Record`

This slice proves the product is more than just prompt generation.

## 9. Immediate Build Order

The next practical build order should be:

1. create `schemas/common` and `schemas/artifacts`
2. implement `src/aether_forge/artifacts.py` validation and normalization
3. create example fixtures under `examples/delta-neutral-btc`
4. implement `forge validate`
5. implement fast-mode artifact generation shell
6. implement scaffold manifest and regeneration metadata

Only after those exist should runtime, eval, and crypto layers proceed.

## 10. Risks And Controls

### Risk: Schema churn too early

Control:

- keep schemas narrow and versioned
- prefer additive changes in early iterations

### Risk: Generator outruns validator quality

Control:

- make validation blocking in CI
- require fixtures for each new artifact field

### Risk: Crypto work starts before effect semantics are enforced

Control:

- block live-capable crypto connectors until capability metadata and policy checks are in place

### Risk: Slow mode arrives before evaluation is solid

Control:

- keep slow mode behind artifact and evaluation core milestones

## 11. Recommendation

Start with the artifact kernel and local CLI, not the runtime UI.

The first implementation success condition is:

> Given an idea, the repo can generate, validate, and evaluate a typed artifact set locally with no secrets embedded and with clear promotion evidence.

That is the smallest slice that proves `Aether Forge` is a real spec-first framework instead of a loose bundle of agent utilities.

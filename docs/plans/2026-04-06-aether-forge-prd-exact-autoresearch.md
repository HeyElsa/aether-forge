# Aether Forge PRD Exact-Style Autoresearch

Date: 2026-04-06
Status: Supporting exact-style autoresearch for PRD v0.6.0
Baseline PRD: `docs/prd/aether-forge-prd-v0.5.0.md`
Resulting PRD: `docs/prd/aether-forge-prd-v0.6.0.md`
Results file: `docs/plans/2026-04-06-aether-forge-prd-exact-autoresearch-results.tsv`

## 1. Goal

This pass emulates the structure of `karpathy/autoresearch` more strictly than the earlier PRD refinement pass.

Instead of broadly improving the spec, this pass does the following:

1. Freezes an evaluator.
2. Scores the baseline PRD.
3. Generates a small number of candidate requirement variants.
4. Scores each candidate against the same evaluator.
5. Keeps only candidates that improve the score.
6. Advances the PRD only with the kept deltas.

## 2. Frozen Evaluator

The evaluator used for the entire comparison cycle is the `PRQ score`.

`PRQ` means `Product Requirement Quality`.

Score range: `0.0` to `25.0`

The five fixed dimensions are:

1. `Boundary clarity` `0.0 - 5.0`
How clearly the PRD assigns ownership and contracts between artifacts, runtime, policy, and ops.

2. `Testability` `0.0 - 5.0`
How well the requirements can be validated, unit-tested, integration-tested, or used for promotion gating.

3. `Runtime and policy enforceability` `0.0 - 5.0`
How directly the requirements support safe runtime enforcement, policy checks, and governed execution.

4. `Operational governability` `0.0 - 5.0`
How well the requirements define rollout, rollback, incident, audit, and evidence behavior.

5. `Scope discipline` `0.0 - 5.0`
How well the PRD stays minimal and avoids unnecessary scope while still closing real gaps.

Important rules:

- The evaluator stays fixed for the entire cycle.
- Candidate scoring must not add new scoring dimensions.
- Candidates that improve clarity but add too much scope can still lose on total score.
- Ties are treated as `discard`.

## 3. Fixed Experiment Budget

Each candidate experiment is limited to:

- one narrow requirement cluster
- at most five focused requirement deltas
- no product-direction changes
- no new top-level product module

This is the PRD analogue of a fixed experiment budget.

## 4. Baseline Score

Baseline artifact:

- `docs/prd/aether-forge-prd-v0.5.0.md`

Baseline `PRQ` score:

- Boundary clarity: `4.0`
- Testability: `3.5`
- Runtime and policy enforceability: `4.0`
- Operational governability: `3.5`
- Scope discipline: `4.5`
- Total: `19.5`

Baseline interpretation:

- strong product direction
- strong governance model
- still missing a few narrow requirement contracts around artifact evolution, credential handling, and side-effect semantics

## 5. Candidate Experiments

### Experiment A: `Artifact Evolution Contract`

Hypothesis:

If versioned artifacts explicitly declare compatibility and migration behavior, regeneration and promotion will become easier to validate without expanding product scope.

Change set:

- add compatibility status requirements for versioned artifacts
- add migration contract requirements for breaking or incompatible changes
- add generator version and input digest attribution for generated artifact sets

Score:

- Boundary clarity: `5.0`
- Testability: `4.5`
- Runtime and policy enforceability: `4.0`
- Operational governability: `4.0`
- Scope discipline: `4.0`
- Total: `21.5`

Decision:

- `keep`

Reason:

- clear score improvement over baseline with small added scope

### Experiment B: `Credential Handle Boundary`

Hypothesis:

If the PRD makes credentials handle-based instead of value-based, runtime safety and trace hygiene will become more enforceable with minimal scope change.

Change set:

- require specs to reference credentials only by handles or logical IDs
- require capability manifests to declare credential handle scope and environment bounds
- require runtime handle resolution without exposing raw secret material to ordinary agent logic or traces
- require policy checks against credential-handle scope

Score against current kept baseline:

- Boundary clarity: `5.0`
- Testability: `4.5`
- Runtime and policy enforceability: `4.5`
- Operational governability: `4.5`
- Scope discipline: `4.0`
- Total: `22.5`

Decision:

- `keep`

Reason:

- meaningful safety and enforceability gain with no material scope expansion

### Experiment C: `Explicit Effect Semantics Metadata`

Hypothesis:

If side-effecting capabilities explicitly declare idempotency, retry, duplicate-submit handling, and compensation class, runtime behavior and rollback semantics will become far more testable and governable.

Change set:

- require machine-readable effect semantics in `Capability Manifest`
- require explicit idempotency classes and compensation classes
- require runtime and crypto execution requirements to enforce declared effect semantics
- require rollback semantics to reference the declared compensation class

Score against current kept baseline:

- Boundary clarity: `5.0`
- Testability: `5.0`
- Runtime and policy enforceability: `5.0`
- Operational governability: `5.0`
- Scope discipline: `4.0`
- Total: `24.0`

Decision:

- `keep`

Reason:

- strongest score improvement of the cycle with a still-contained change surface

### Experiment D: `Time-Bounded Waiver Ownership`

Hypothesis:

If canary and production promotions require waiver ownership, expiry, and stronger two-person approval rules, governance will improve.

Change set:

- add stronger waiver ownership metadata
- add stronger waiver expiry requirements
- add stronger mandatory two-person approval semantics for waiver-backed promotion

Score against current kept baseline:

- Boundary clarity: `5.0`
- Testability: `5.0`
- Runtime and policy enforceability: `5.0`
- Operational governability: `5.0`
- Scope discipline: `3.5`
- Total: `23.5`

Decision:

- `discard`

Reason:

- governance improves, but total score drops because the added process overhead is too heavy for current v1 scope discipline

## 6. Final Result

Kept experiments:

- `Artifact Evolution Contract`
- `Credential Handle Boundary`
- `Explicit Effect Semantics Metadata`

Discarded experiment:

- `Time-Bounded Waiver Ownership`

Final kept PRD score:

- Boundary clarity: `5.0`
- Testability: `5.0`
- Runtime and policy enforceability: `5.0`
- Operational governability: `5.0`
- Scope discipline: `4.0`
- Total: `24.0`

## 7. Why `v0.6.0` Exists

`v0.6.0` exists because the exact-style pass found a real measurable improvement over `v0.5.0` under a fixed evaluator.

The kept improvements tighten the PRD in three places:

- artifact evolution and migration
- secret and credential handling boundaries
- side-effect semantics and compensation contracts

## 8. Main Lesson

Applying a stricter autoresearch loop to the PRD shows that the next improvements are no longer broad product-direction moves.

The high-value improvements are narrow contract improvements that:

- remove remaining ambiguity
- make the framework safer to implement
- preserve v1 scope discipline

# Aether Forge PRD Autoresearch

Date: 2026-04-06
Status: Supporting autoresearch for PRD v0.5.0
Baseline PRD: `docs/prd/aether-forge-prd-v0.4.0.md`
Resulting PRD: `docs/prd/aether-forge-prd-v0.5.0.md`

## 1. Purpose

This document captures a bounded autoresearch-style improvement loop run against the product spec itself.

The goal was not to change product direction. The goal was to improve the existing requirements so they are:

- clearer to implement
- easier to test
- lower in ambiguity
- stronger on safety and governance
- still minimal in added scope

## 2. Baseline

Baseline artifact under review:

- `docs/prd/aether-forge-prd-v0.4.0.md`

Baseline thesis retained:

- spec-first agent engineering system
- general core with crypto-native module layer
- fast and slow agent creation modes
- default-deny side effects
- staged evaluation and production promotion
- governed self-evolution

Baseline weakness found:

- the product direction was strong, but several requirement sections were still too broad to act as hard implementation contracts

## 3. Active Comparison Contract

This autoresearch pass used the following keep-or-discard criteria:

1. Clearer implementation boundary
2. Better testability
3. Lower ambiguity
4. Minimal added scope

Changes were rejected when they:

- expanded v1 product scope materially
- weakened spec-first ownership
- added process overhead without strong product value
- were too vague to test

## 4. Iteration Ledger

## Iteration A

Focus:

- spec artifacts
- scaffold ownership
- validation
- regeneration
- interoperability

Hypothesis:

If artifact ownership and regeneration behavior are made explicit, the PRD will become significantly more implementable without changing product direction.

Kept deltas:

- define canonical ownership per artifact
- assign shared artifact-set identity and compatibility metadata
- require machine-readable scaffold ownership metadata
- define regeneration modes: `safe update`, `propose patch`, `blocked`
- split validation into required classes
- require structured validation outputs
- define import/export boundaries for external standards
- require stable machine-readable export for core artifacts
- require fidelity declarations for officially supported imports

Discarded delta:

- bidirectional scaffold-to-spec sync

Discard rationale:

- added too much scope
- weakened spec-first ownership
- not required for v1 if regeneration and drift behavior are clearly defined

Decision:

- `keep`

## Iteration B

Focus:

- runtime execution
- policy enforcement
- slow mode loop mechanics
- mutation surfaces
- evidence capture

Hypothesis:

If slow mode and runtime execution are governed by immutable comparison contracts and explicit evidence chains, improvement claims will become much more trustworthy.

Kept deltas:

- require runtime step ledger for governed action attempts
- require fail-closed behavior when policy services are unavailable
- require canonical policy decision envelope linked to effect attempts
- require immutable active comparison contract per slow-mode cycle
- require machine-readable mutation-surface declarations per cycle
- require minimum evidence before a candidate can be marked `keep`
- require replay classification tags on runtime and evidence artifacts
- require evidence-chain linkage across candidate, artifact, runtime, and promotion records

Discarded deltas:

- require full regeneration of the entire implementation package on every iteration
- require universal numeric confidence scoring for all evidence

Discard rationale:

- over-constrained implementation
- added cost without enough value
- risked false precision

Decision:

- `keep`

## Iteration C

Focus:

- evaluation
- promotion
- rollout
- rollback
- incidents
- observability

Hypothesis:

If evaluation and operations are converted from descriptive principles into typed decision surfaces, the PRD will become far more actionable for serious agent systems.

Kept deltas:

- require explicit stage outcomes: `pass`, `pass with waiver`, `hold`, `fail`
- require structured promotion decision data in promotion evidence
- require machine-readable rollout limits
- require automatic rollout hold and rollback triggers
- require rollback targets and post-rollback verification
- require incident lifecycle states and severities
- require incident-to-regression closure
- require derived health signals and alerts
- require explicit drift surface definitions for v1

Discarded delta:

- mandatory formal postmortem artifact for all high-severity incidents in v1

Discard rationale:

- useful, but more process-heavy than necessary for the current product phase

Decision:

- `keep`

## 5. Final Keep Set

The autoresearch pass kept changes in four clusters.

### Artifact contract

- canonical ownership
- shared artifact-set identity
- machine-readable ownership metadata
- explicit regeneration modes
- stronger validation classes and outputs
- stronger interoperability boundaries

### Runtime and slow mode

- immutable comparison contracts
- minimum evidence for keep decisions
- machine-readable mutation surfaces
- policy decision envelopes
- fail-closed enforcement
- replay classification and evidence linkage

### Evaluation and promotion

- explicit stage outcomes
- structured promotion decisions
- rollout limits and automatic hold conditions
- stronger rollback semantics

### Operations

- incident lifecycle states
- incident-to-regression closure
- derived health signals
- explicit drift surfaces

## 6. Material Improvements From Baseline

Compared with `v0.4.0`, the improved requirements in `v0.5.0` now make these things much more explicit:

- what artifact owns which concern
- what is mutable during an active comparison cycle
- what evidence is required before a variant can be accepted
- what stays fixed while a candidate is being judged
- how promotion decisions are expressed and limited
- how rollout stops automatically when safety conditions fail
- how incidents feed back into evaluation

## 7. Why This Was A Minor Version Bump

This pass changed product requirements, not just wording.

It added or tightened:

- validation contracts
- regeneration semantics
- slow-mode decision rules
- runtime evidence contracts
- promotion and rollout semantics
- incident and observability requirements

That is a `minor` PRD change, not a patch.

## 8. Final Outcome

The autoresearch result was:

- `keep` the product direction
- `keep` the spec-first and crypto-native positioning
- `keep` fast/slow creation modes
- `improve` the requirement contract significantly

The main lesson from applying an autoresearch mindset to the PRD is that the framework should not merely claim that it improves agents.

It should require that improvements are:

- baseline-referenced
- fairly compared
- evidence-backed
- complexity-aware
- governed by fixed evaluation conditions during the active comparison cycle

# Aether Forge Schema Design

Date: 2026-04-06
Status: Draft
Related PRD: `docs/prd/aether-forge-prd-v0.7.0.md`

## 1. Purpose

This document turns the artifact requirements in PRD `v0.6.0` into a concrete schema design.

The goal is to define the typed artifact system that `Aether Forge` will use for:

- spec generation
- scaffold generation
- validation
- runtime execution
- evaluation
- memory
- promotion
- slow-mode autoresearch

This is a design document, not an implementation file. It makes the schema system concrete enough that implementation can begin without inventing structure ad hoc inside the codebase.

## 2. Design Decisions

### 2.1 Canonical Machine Format

Recommendation:

- canonical artifact format: `JSON`
- schema definition format: `JSON Schema 2020-12`
- portable identifier format: stable string IDs

Rationale:

- JSON is easy to validate, diff, store, and transmit.
- JSON Schema is ecosystem-friendly and language-neutral.
- TypeScript, Rust, Go, and Python tooling can all interoperate with JSON Schema cleanly.

Human-authored YAML may be added later as an authoring convenience, but the canonical normalized form should remain JSON.

### 2.2 One Envelope For Every Artifact

Every typed artifact should share a common envelope.

Required common fields:

- `artifactType`
- `schemaVersion`
- `artifactId`
- `artifactVersion`
- `artifactSetId`
- `title`
- `generator`
- `compatibility`
- `provenance`

This keeps artifact storage, validation, migration, and traceability consistent.

### 2.3 The Scaffold Needs A Typed Manifest

The generated scaffold is a directory tree, not a single JSON artifact.

To make it machine-checkable, the scaffold should include a typed file:

- `scaffold.manifest.json`

This file is the canonical machine-readable description of:

- generated zones
- user-owned zones
- protected zones
- regeneration behavior
- scaffold version linkage to the artifact set

### 2.4 References Are Explicit Objects

Cross-artifact links should use typed reference objects, not free-form strings.

Minimum `ArtifactRef` shape:

- `artifactType`
- `artifactId`
- `artifactVersion`

Version ranges may be added later, but v1 should prefer exact references for promotion safety.

## 3. Common Envelope

All top-level artifacts should begin with a shared envelope like this:

```json
{
  "artifactType": "agent-spec",
  "schemaVersion": "1.0.0",
  "artifactId": "agt_01H...",
  "artifactVersion": "0.1.0",
  "artifactSetId": "aset_01H...",
  "title": "Delta Neutral BTC Basis Agent",
  "generator": {
    "name": "aether-forge",
    "version": "0.1.0",
    "inputDigest": "sha256:..."
  },
  "compatibility": {
    "status": "backward-compatible",
    "previousArtifactVersion": "0.0.1",
    "migrationRef": null
  },
  "provenance": {
    "createdAt": "2026-04-06T12:00:00Z",
    "sourceMode": "slow",
    "sourcePromptDigest": "sha256:..."
  }
}
```

### 3.1 Generator Block

Required fields:

- `name`
- `version`
- `inputDigest`

Optional later:

- `templateVersion`
- `normalizerVersion`
- `importerVersions`

### 3.2 Compatibility Block

Required fields:

- `status`
- `previousArtifactVersion`
- `migrationRef`

Allowed `status` values:

- `backward-compatible`
- `forward-compatible`
- `breaking`
- `incompatible`

### 3.3 Provenance Block

Required fields:

- `createdAt`
- `sourceMode`

Optional fields:

- `sourcePromptDigest`
- `importSource`
- `derivedFrom`

## 4. Core Artifact Schemas

## 4.1 Agent Spec

Purpose:

- canonical expression of agent intent and control boundaries

Required top-level sections:

- envelope
- `metadata`
- `objective`
- `environmentContract`
- `capabilityRefs`
- `policyRefs`
- `evaluation`
- `promotion`

### `metadata`

Required fields:

- `name`
- `summary`
- `domain`

Optional fields:

- `owners`
- `tags`
- `status`

### `objective`

Required fields:

- `primaryGoal`
- `successMetrics`

Optional fields:

- `nonGoals`
- `constraintsSummary`
- `failureModes`

### `environmentContract`

Required fields:

- `allowedEnvironments`
- `defaultEnvironment`

Optional fields:

- `environmentNotes`
- `promotionPath`

### `capabilityRefs`

An array of `ArtifactRef` or manifest-local capability IDs.

### `policyRefs`

References to policy bundles or policy templates required for this agent.

### `evaluation`

Required fields:

- `scenarioPackRef`
- `requiredOutcomes`
- `successThresholds`

### `promotion`

Required fields:

- `allowedTargets`
- `requiredApprovals`

### Secret Rule

The `Agent Spec` must never contain raw credential values.

Only these are allowed:

- logical credential handle IDs
- references to capability requirements

## 4.2 Capability Manifest

Purpose:

- canonical inventory of executable capabilities and their boundaries

Required top-level sections:

- envelope
- `credentialHandles`
- `capabilities`

### `credentialHandles`

Each credential handle descriptor should define:

- `handleId`
- `kind`
- `allowedEnvironments`
- `maximumAccessScope`
- `rotationExpectation`
- `expiresAt` or `ttlPolicy`

This does not store secrets. It stores the logical contract around secret access.

### `capabilities`

Each capability should define:

- `capabilityId`
- `kind`
- `provider`
- `riskLevel`
- `allowedEnvironments`
- `requiredApproval`
- `credentialHandleId` when needed
- `providerConstraints`
- `effectSemantics` for side-effecting capabilities

Allowed `kind` values in v1 should at least support:

- `tool`
- `model`
- `wallet-action`
- `exchange-action`
- `onchain-action`
- `data-source`

### `effectSemantics`

Required for side-effecting capabilities.

Fields:

- `idempotencyClass`
- `duplicateSubmitBehavior`
- `retryPolicy`
- `compensationClass`

Allowed `idempotencyClass` values:

- `idempotent`
- `conditionally-idempotent`
- `non-idempotent`

Allowed `compensationClass` values:

- `revertible`
- `compensatable`
- `irreversible`

## 4.3 Scenario Pack

Purpose:

- canonical suite of evaluation scenarios and thresholds

Required top-level sections:

- envelope
- `scenarios`
- `thresholds`

Each scenario should define:

- `scenarioId`
- `category`
- `environmentKind`
- `inputs`
- `expectedOutcome`
- `blockingReasonIds`
- `metrics`
- `replayClass`

Allowed `category` values in v1:

- `baseline`
- `edge`
- `policy-violation`
- `incident-regression`
- `stress`

## 4.4 Research Record

Purpose:

- canonical evidence record for slow mode

Required top-level sections:

- envelope
- `researchPlan`
- `evidenceLog`
- `findings`
- `blockers`
- `activeComparisonContract`
- `iterationLedger`
- `stopRationale`

### `iterationLedger`

Each iteration entry should define:

- `candidateId`
- `parentCandidateId`
- `hypothesis`
- `changedSurfaces`
- `budgetConsumed`
- `evaluationConditions`
- `measuredOutcomes`
- `decisionStatus`
- `decisionRationale`

Allowed `decisionStatus` values:

- `keep`
- `discard`
- `blocked`
- `execution-failure`

## 4.5 Promotion Record

Purpose:

- canonical evidence package for environment promotion

Required top-level sections:

- envelope
- `artifactRefs`
- `evaluationSummary`
- `promotionDecision`
- `residualRisks`
- `rolloutPlan`

### `promotionDecision`

Required fields:

- `sourceEnvironment`
- `targetEnvironment`
- `decisionOutcome`
- `approvers`
- `policyBundleVersion`
- `scenarioPackVersion`
- `rolloutLimits`

Allowed `decisionOutcome` values:

- `approved`
- `approved-with-limits`
- `held`
- `rejected`

## 4.6 Memory Record

Purpose:

- canonical typed long-term memory record for governed cross-session context

Required top-level sections:

- envelope
- `ownerAgentId`
- `memoryType`
- `scope`
- `environment`
- `content`
- `summary`
- `source`
- `confidence`
- `sensitivity`
- `createdAt`
- `updatedAt`
- `provenanceRefs`
- `tags`

### Memory design rules

- memory is context, not authority
- memory must never override spec or policy
- memory records must be environment-scoped
- memory records must not contain raw credential material
- cross-environment promotion must preserve provenance

### `memoryType`

Recommended v1 values:

- `strategy-context`
- `operator-preference`
- `environment-fact`
- `venue-fact`
- `incident-learning`
- `evaluation-finding`
- `decision-history`

### `scope`

Recommended v1 values:

- `session`
- `agent`
- `project`
- `environment`

### `sensitivity`

Required values:

- `public`
- `internal`
- `sensitive`
- `restricted`

### Promotion-related fields

Recommended fields:

- `expiresAt`
- `retentionPolicy`
- `metadata.promotion`

Promotion metadata should preserve:

- source environment
- target environment
- approval reference
- requester or approver identity when available

## 4.7 Scaffold Manifest

Purpose:

- machine-readable representation of the scaffold contract

Required top-level sections:

- envelope
- `paths`
- `ownershipZones`
- `regenerationModes`

### `ownershipZones`

Each zone entry should define:

- `pathPattern`
- `zoneType`
- `regenerationMode`

Allowed `zoneType` values:

- `generated`
- `user-owned`
- `protected`

Allowed `regenerationMode` values:

- `safe-update`
- `propose-patch`
- `blocked`

## 5. Supporting Sub-Schemas

These types may be embedded inside core artifacts rather than stored as standalone artifacts in v1.

## 5.1 Active Comparison Contract

Fields:

- `comparisonId`
- `evaluatorVersion`
- `policyThresholdsDigest`
- `scenarioPackRef`
- `normalizationRules`
- `allowedMutationSurfaces`
- `budgetRules`
- `artifactSetId`

## 5.2 Policy Decision Record

Fields:

- `decisionId`
- `policyBundleVersion`
- `inputScope`
- `ruleMatches`
- `severity`
- `approvalPath`
- `finalDisposition`

## 5.3 Runtime Step Ledger Entry

Fields:

- `stepId`
- `stateSnapshotRef`
- `plannedAction`
- `policyDecisionRef`
- `approvalOutcome`
- `effectResult`
- `postActionInvariantResult`
- `resultingStateSnapshotRef`

## 5.4 Migration Contract

Fields:

- `fromVersion`
- `toVersion`
- `transformSteps`
- `lossyFields`
- `validationChecks`

## 5.5 Artifact Ref

Fields:

- `artifactType`
- `artifactId`
- `artifactVersion`

## 5.6 Memory Promotion Request

Fields:

- `memoryId`
- `sourceEnvironment`
- `targetEnvironment`
- `approvalRef`
- `requestedBy`

## 6. Validation Pipeline

Validation should happen in layers.

### 6.1 Schema Validation

- JSON shape
- enum values
- required fields
- string formats

### 6.2 Referential Validation

- every artifact ref resolves
- capability IDs exist
- credential handle IDs exist
- scenario pack refs exist

### 6.3 Compatibility Validation

- compatibility statuses are valid
- migration contracts exist when required
- cross-artifact version mismatches are rejected

### 6.4 Policy-Surface Validation

- capabilities with side effects define effect semantics
- credential-bearing capabilities define handle references
- forbidden secret fields are absent from spec artifacts
- memory records do not store recoverable secret material
- memory records declare sensitivity and environment scope

### 6.5 Environment Validation

- referenced environments are allowed by the artifact set
- capability environment availability is consistent

### 6.6 Import Validation

- imported MCP/OpenAPI fields map into canonical structures
- dropped or lossy fields are recorded

## 7. Suggested Future File Layout

```text
schemas/
  common/
    artifact-envelope.schema.json
    artifact-ref.schema.json
    compatibility.schema.json
    migration-contract.schema.json
  artifacts/
    agent-spec.schema.json
    capability-manifest.schema.json
    memory-record.schema.json
    scenario-pack.schema.json
    research-record.schema.json
    promotion-record.schema.json
    scaffold-manifest.schema.json
  runtime/
    active-comparison-contract.schema.json
    policy-decision-record.schema.json
    runtime-step-ledger-entry.schema.json
```

## 8. Deferred Decisions

These are intentionally left open for the implementation phase:

- whether YAML authoring is supported in v1 or only JSON
- whether artifact IDs use ULIDs, UUIDs, or slug-plus-digest forms
- whether importers for MCP/OpenAPI ship in the first implementation slice or a later one
- whether policy bundles are authored as JSON, code, or both

## 9. Recommendation

Use `JSON Schema 2020-12` as the canonical machine contract for `Aether Forge` artifacts.

Implement the schema system around:

- one shared envelope
- seven top-level artifact schemas
- a small set of embedded support records
- layered validation
- explicit compatibility, credential, effect-semantics, and memory-governance rules

That gives the framework the type safety and machine-checkability promised in PRD `v0.7.0` without prematurely overbuilding a heavier IDL system.

# Aether Forge Product Requirements Document

Version: `v0.7.0`
Status: `Draft`
Date: `2026-04-06`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.6.0.md`
Base PRD: `docs/prd/aether-forge-prd-v0.6.0.md`
Supporting design:

- `docs/plans/2026-04-06-aether-forge-schema-design.md`

## 1. Status

This PRD version inherits all unchanged requirements from `v0.6.0`.

`v0.7.0` adds one major product capability:

- a governed persistent memory layer

This memory layer is meant to provide long-term context without weakening the product's existing guarantees around:

- spec-first ownership
- policy enforcement
- environment separation
- evidence-backed promotion

## 2. Summary Of Changes

Compared with `v0.6.0`, this version adds:

1. a typed `Memory Record` artifact family
2. a product-level memory model where memory is context, not authority
3. explicit `memory.read`, `memory.write`, and `memory.promote` capability surfaces
4. environment-scoped memory stores
5. manual-only cross-environment memory promotion in v1
6. explicit provenance, sensitivity, retention, and expiry expectations for memory records

## 3. Product Decision

`Aether Forge` should support persistent memory, but it should not copy the default behavior of a personal agent system that silently accumulates durable context and injects it everywhere.

The correct design for `Aether Forge` is:

- persistent memory exists
- memory is typed
- memory is policy-controlled
- memory is environment-scoped
- memory access is auditable
- memory promotion is governed

The core rule is:

> Memory adds context. It does not change intent, permissions, or promotion state by itself.

This matters because `Aether Forge` is building governed agents, not just persistent assistants.

## 4. Memory Model

The product should distinguish three layers of context:

1. `Spec and policy`
The authority layer. Defines objective, permissions, capabilities, environments, and evaluation requirements.

2. `Runtime session state`
The active execution layer. Tracks the current plan, approved actions, observations, approvals, and recent step outcomes.

3. `Persistent memory`
The long-term context layer. Stores typed context records that can inform future planning, but never override the first two layers.

Authority order must remain:

- `Agent Spec`
- `Policy`
- `Runtime session state`
- `Persistent memory`

## 5. Memory Record Artifact

`Aether Forge` should introduce a typed `Memory Record` artifact family.

Each `Memory Record` should contain, at minimum:

- `memoryId`
- `schemaVersion`
- `artifactSetId` when relevant
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
- `expiresAt`
- `retentionPolicy`
- `provenanceRefs`
- `tags`

Recommended v1 `memoryType` values:

- `strategy-context`
- `operator-preference`
- `environment-fact`
- `venue-fact`
- `incident-learning`
- `evaluation-finding`
- `decision-history`

Recommended v1 `scope` values:

- `session`
- `agent`
- `project`
- `environment`

Required `sensitivity` values:

- `public`
- `internal`
- `sensitive`
- `restricted`

## 6. Memory Runtime Model

Persistent memory should not be silently treated as authoritative prompt state.

Instead, the runtime should expose memory through explicit capabilities:

- `memory.read`
- `memory.write`
- `memory.promote`

### `memory.read`

The planner may request a memory read when allowed by policy.

Reads should be filtered by:

- scope
- environment
- sensitivity
- memory type
- retention and expiry state

### `memory.write`

The runtime may persist a memory record when:

- the write capability is declared
- policy allows the write
- the record passes memory validation

Memory writes should never persist raw credential material or hidden authority changes.

### `memory.promote`

Promotion exists to move memory between scopes or environments under governance.

Promotion should create a traceable new record or record version with preserved provenance.

## 7. Memory Promotion Policy

V1 should use a conservative policy.

### Core rule

- same-environment memory writes are allowed when policy permits
- cross-environment memory promotion is manual in v1

### Non-negotiable v1 rule

Memory learned in `sandbox` must not automatically promote into:

- `paper`
- `canary-live`
- `production`

Such promotion must require explicit approval and a recorded approval reference.

### Default v1 safety posture

The recommended default implementation may be even stricter and require approval for all cross-environment promotion.

### Required promotion evidence

Every promoted memory record must preserve:

- source environment
- target environment
- approval reference when required
- provenance references to the originating record
- promotion timestamp

## 8. Memory And Environment Separation

Persistent memory should be environment-aware.

At minimum, the system should support separate memory surfaces for:

- `sandbox`
- `paper`
- `canary-live`
- `production`

The runtime should never assume that memory from one environment is safe to consume in another without explicit policy or promotion.

This matters especially for:

- strategy learnings
- incident learnings
- venue-specific heuristics
- execution assumptions

## 9. Memory Safety Rules

The following rules should hold in v1:

1. memory must not store raw credentials or secret-bearing values
2. memory must not override spec or policy
3. memory writes must be visible in the step ledger
4. memory reads must be visible in the step ledger
5. memory promotion must be auditable and reviewable
6. memory records must declare sensitivity and retention intent
7. expired memory records should not be returned by default reads

## 10. Capability Model Additions

The `Capability Manifest` should support memory capabilities explicitly.

Minimum memory capability kinds or IDs should support:

- `memory.read`
- `memory.write`
- `memory.promote`

Each memory capability should declare:

- allowed environments
- allowed scopes
- allowed memory types
- maximum sensitivity
- approval requirements for writes or promotion

## 11. Runtime And Policy Additions

The runtime should treat memory operations as governed actions.

### Planner behavior

- the planner may propose memory reads or writes
- the planner may not invent unmanaged memory channels

### Policy behavior

- `memory.read` policy should filter by scope, type, and sensitivity
- `memory.write` policy should validate type, scope, sensitivity, and retention
- `memory.promote` policy should enforce environment separation and approval requirements

### Step ledger behavior

Every memory operation should produce a ledger entry or effect record containing:

- operation type
- policy decision
- affected memory ID
- source and target environment when relevant
- approval reference when relevant

## 12. Functional Requirements Additions

The following requirements are added on top of `v0.6.0`.

### Memory artifacts

- The system must support a typed `Memory Record` schema.
- The system must reject memory records that contain raw credential material or secret-like keys.
- The system must support memory sensitivity, expiry, and retention fields.

### Memory runtime behavior

- The system must expose `memory.read`, `memory.write`, and `memory.promote` as governed capability surfaces.
- The system must keep memory environment-scoped.
- The system must prevent silent authority escalation through memory content.

### Memory promotion

- The system must require manual approval for sandbox-to-live-like memory promotion in v1.
- The system must preserve provenance and approval references on promoted memory.
- The system must support blocking promotion when required approval is absent.

## 13. Non-Functional Requirements Additions

- memory operations must be auditable
- memory reads must default to safe filtering
- memory promotion must be explicit and traceable
- secret-bearing material must not leak into persistent memory
- memory store behavior must remain deterministic enough for review and replay classification

## 14. Roadmap Implications

The memory layer should be introduced in stages.

### Stage 1

- typed `Memory Record` schema
- in-process memory interfaces
- secure default promotion policy

### Stage 2

- runtime memory capability enforcement
- memory-aware step ledger entries
- retention and expiry enforcement

### Stage 3

- optional external memory backends or provider adapters
- richer search and retrieval strategies
- stricter memory promotion workflows

## 15. Future Extensions

The following are intentionally deferred beyond the current product contract:

- automatic low-risk memory promotion
- vector or semantic retrieval as a required core dependency
- hidden free-form scratchpad persistence across sessions
- external memory provider standardization as part of v1

These may be added later, but only behind the same governance model.

## 16. Open Questions

- Which low-risk memory types, if any, should ever be auto-promotable later?
- Should `operator-preference` memory have lighter promotion requirements than strategy or incident memory?
- How much retention enforcement should be built into v1 versus delegated to the storage backend?
- Should memory records eventually become part of promotion evidence bundles automatically?

## 17. Final Recommendation

`Aether Forge` should add a persistent memory layer, but it should do so as a governed, typed context system.

The correct product posture is:

- explicit memory artifacts
- explicit memory capabilities
- explicit environment separation
- manual promotion from sandbox into live-like environments in v1

That gives the framework long-term learning and continuity without giving up the governance model that makes the product credible.

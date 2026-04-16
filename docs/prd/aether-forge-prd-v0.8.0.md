# Aether Forge Product Requirements Document

Version: `v0.8.0`
Status: `Draft`
Date: `2026-04-07`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.7.0.md`
Base PRD: `docs/prd/aether-forge-prd-v0.7.0.md`
Supporting design:

- `docs/plans/2026-04-06-aether-forge-schema-design.md`

## 1. Status

This PRD version inherits all unchanged requirements from `v0.7.0`.

`v0.8.0` marks the completion of several major product capabilities and adds one new integration surface:

- Governed persistent memory (implemented)
- Slow-mode autoresearch (implemented)
- Hermes adapter integration (implemented)
- Skills integration (new)
- Pure Python consolidation (change)
- Public API exports (change)

## 2. Summary Of Changes

Compared with `v0.7.0`, this version:

1. marks the governed persistent memory layer as implemented
2. marks the slow-mode autoresearch engine as implemented
3. adds Hermes adapter integration as an implemented planner backend
4. adds a skills integration surface with open-standard skill discovery, installation, and governance
5. records the removal of all TypeScript packages in favor of a pure Python SDK
6. records full public API exports from the Python package

## 3. Implementation Status Updates

### 3.1 Governed Persistent Memory (Implemented)

The governed persistent memory layer specified in `v0.7.0` is now implemented. The following components are operational:

- Memory store wired into `RuntimeSession` with `memory.read`, `memory.write`, and `memory.promote` surfaces
- Memory policy enforcement with sensitivity-per-environment rules and mandatory approval for cross-environment promotions
- Memory expiry filtering on default reads
- camelCase serialization for memory records
- Memory-aware planner that proposes `memory.read` automatically when relevant context may exist
- Memory context flows into planner prompts as governed context
- Evaluation harness supports `memory_store` injection for deterministic testing

All v0.7.0 memory requirements remain in force. The implementation satisfies the Stage 1 and Stage 2 roadmap items from v0.7.0 Section 14.

### 3.2 Slow-Mode Autoresearch (Implemented)

The Karpathy-style autoresearch loop specified in earlier PRD versions is now implemented. The following components are operational:

- `forge generate-slow` CLI command triggers the autoresearch workflow
- Baseline-first protocol: the system establishes a measurable baseline before generating candidate improvements
- Keep-or-discard loop: each candidate is scored against the current best and kept only if it improves the score
- Diminishing-returns early stopping: the loop terminates when successive iterations fail to produce meaningful improvement
- `research-record.json` artifact produced as output, containing the full iteration ledger with scores, decisions, and provenance
- Any `PlanningModel` can serve as the research backend, including OpenAI-compatible endpoints, Hermes, and static planning models

### 3.3 Hermes Adapter Integration (Implemented)

The Hermes planner backend is now integrated as a first-class planner mode:

- `hermes` planner mode available via CLI flag and configuration
- `HermesPlanner` class wraps `PlanningModel` and `HermesAdapterTranslator` to translate between Aether Forge planning semantics and the Hermes protocol
- Full factory wiring in `build_planner_factory` so `hermes` mode is selectable alongside other planner backends
- Hermes adapter exported from `adapters/__init__.py`

## 4. Skills Integration (New)

### 4.1 Product Decision

`Aether Forge` should support external skills as a governed extension mechanism. Skills allow agents to acquire new capabilities from open registries without requiring framework-level code changes.

The correct design for skills in `Aether Forge` is:

- skills follow the open `SKILL.md` standard (agentskills.io)
- skills are discoverable through registries
- skills map to capabilities in the capability manifest
- skills are subject to the same policy governance as any other capability
- skills from any registry go through the same policy gate

### 4.2 Skills CLI Surface

The following CLI commands are implemented:

- `forge skills-search <query>` -- search a skills registry for available skills
- `forge skills-add <source> --project <dir>` -- install a skill into a project
- `--skills` flag on `generate-fast` and `generate-slow` -- include skills during agent generation

### 4.3 Supported Registries

Skills can be sourced from multiple registries:

- `skills.sh` -- general-purpose skills registry
- `skills.bankr.bot` -- crypto and DeFi focused skills registry
- Any GitHub repository containing `SKILL.md` files

The `bankr:skill-name` shorthand resolves to the BankrBot/skills repository for convenience.

### 4.4 Skills And Capability Governance

Skills are not a bypass channel. Every skill maps to one or more capabilities in the capability manifest and is subject to:

- the same default-deny policy as any declared capability
- environment-scoped permission checks
- sensitivity classification
- approval requirements when the skill introduces side-effecting behavior

A skill that declares a side-effecting capability must satisfy all the side-effect governance rules from earlier PRD versions, including idempotency, retry, and compensation semantics.

### 4.5 Skills Safety Rules

The following rules apply to skills in v1:

1. skills must use the open `SKILL.md` standard
2. skills must map to declared capabilities before they can execute
3. skills from any registry must pass through the same policy gate
4. skills must not introduce unmanaged capability channels that bypass the capability manifest
5. skills that declare side-effecting capabilities must satisfy all existing side-effect governance
6. skill installation must be explicit and auditable

## 5. Pure Python Consolidation (Change)

The TypeScript `packages/` directory and all associated `node_modules` have been removed. The Python SDK under the repository root is the canonical and only implementation.

This change does not affect product requirements. It simplifies the implementation surface and removes a source of divergence between two codebases.

## 6. Public API Exports (Change)

The Python package now exports its full public API from `__init__.py`. The Hermes adapter is exported from `adapters/__init__.py`.

This supports clean programmatic usage of the framework without requiring knowledge of internal module paths.

## 7. Inherited Requirements

All requirements from `v0.7.0` (and transitively from `v0.6.0` through `v0.1.0`) remain in force unless explicitly updated in this document. In particular:

- The memory model, memory safety rules, memory promotion policy, and memory environment separation rules from v0.7.0 are unchanged
- The artifact compatibility, credential-handle, and effect-semantics requirements from v0.6.0 are unchanged
- The autoresearch loop mechanics, iteration ledger, and protected-evaluator requirements from v0.4.0 are unchanged
- The core lifecycle, environment model, and governance requirements from earlier versions are unchanged

## 8. Functional Requirements Additions

The following requirements are added on top of `v0.7.0`.

### Skills

- The system must support skill discovery through registry search.
- The system must support skill installation into a project directory.
- The system must map installed skills to capabilities in the capability manifest.
- The system must enforce the same policy governance on skill-sourced capabilities as on built-in capabilities.
- The system must support the `--skills` flag during both fast and slow agent generation.

### Hermes integration

- The system must support `hermes` as a selectable planner mode.
- The Hermes planner must translate between Aether Forge planning semantics and the Hermes protocol.
- The Hermes adapter must be importable from the public API surface.

## 9. Non-Functional Requirements Additions

- skill registry interactions must handle network failures gracefully
- skill installation must be idempotent
- the public API surface must remain stable across patch releases
- the pure Python implementation must not regress on any previously passing evaluation

## 10. Roadmap Implications

### Memory layer

Stage 1 and Stage 2 from the v0.7.0 roadmap are complete. Stage 3 (external memory backends, richer retrieval, stricter promotion workflows) remains future work.

### Skills

Skills integration is operational for v1. Future work includes:

- skill versioning and update tracking
- skill dependency resolution
- skill-level evaluation and scoring
- registry authentication and trust verification

### Hermes

The Hermes adapter is operational. Future work includes:

- expanded Hermes protocol coverage
- Hermes-native evaluation support
- Hermes adapter performance profiling

## 11. Open Questions

Inherited from v0.7.0:

- Which low-risk memory types, if any, should ever be auto-promotable later?
- Should `operator-preference` memory have lighter promotion requirements than strategy or incident memory?
- How much retention enforcement should be built into v1 versus delegated to the storage backend?
- Should memory records eventually become part of promotion evidence bundles automatically?

New in v0.8.0:

- Should skills declare their own sensitivity classification, or should that be inferred from their capability mappings?
- Should skill registries support signed skill manifests for trust verification?
- Should the `bankr:` shorthand be generalized to a configurable registry alias system?
- What is the upgrade path when an installed skill's `SKILL.md` changes in a breaking way?

## 12. Final Recommendation

`Aether Forge` v0.8.0 marks the transition from specification to working implementation for the governed memory layer, autoresearch engine, and Hermes adapter. It also introduces skills as a governed extension surface.

The correct product posture remains:

- spec-first ownership
- policy enforcement on all capability surfaces, including skills
- environment separation
- evidence-backed promotion
- explicit, auditable operations

Skills extend the capability surface without weakening governance. Memory, autoresearch, and Hermes are now operational and ready for real-world evaluation.

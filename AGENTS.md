# AGENTS.md

This file defines project-specific rules for any AI or automated collaborator working in this repository.

## 1. Project Purpose

`Aether Forge` is a spec-first, developer-first framework for turning an agent idea into a governed, testable, production-capable agent system.

The initial wedge is crypto, but the core framework must remain general enough to support other domains.

## 2. Canonical Product Documents

Read these before making product, architecture, or documentation changes:

1. `docs/prd/README.md`
2. `docs/prd/aether-forge-prd-v0.15.0.md`
3. `docs/prd/aether-forge-prd-v0.14.0.md`
4. `docs/prd/aether-forge-prd-v0.12.0.md`
5. `docs/prd/CHANGELOG.md`
6. `docs/plans/2026-04-06-aether-forge-research.md`
7. `docs/plans/2026-04-06-aether-forge-prd-autoresearch.md`
8. `docs/plans/2026-04-06-aether-forge-prd-exact-autoresearch.md`
9. `docs/plans/2026-04-06-aether-forge-schema-design.md`
10. `docs/plans/2026-04-06-aether-forge-v0.6.0-implementation-plan.md`
11. `docs/plans/2026-04-06-aether-forge-design.md`

If the PRD and the earlier design draft differ, the versioned PRD wins.

## 3. Product Non-Negotiables

Do not drift away from these without explicitly updating the PRD:

- `Aether Forge` is spec-first.
- It is developer-first, not consumer no-code first.
- It is general at the core and crypto-native at the module layer.
- Agent creation must support both `fast` and `slow` modes.
- `Slow` mode must use an autoresearch loop and present once it has materially improved the draft or hit a real blocker.
- `Slow` mode must establish a baseline and use measurable keep-or-discard decisions for candidate improvements.
- Agent specs must be typed, versioned, and machine-validatable.
- Artifact ownership and regeneration rules must stay explicit and machine-checkable.
- Artifact compatibility and migration rules must stay explicit and machine-checkable.
- Secret-bearing material should stay out of specs, prompts, traces, and persisted state when credential handles can be used instead.
- Persistent memory must stay typed, policy-aware, and environment-scoped.
- Memory must remain contextual and must not override spec or policy authority.
- Side-effecting capabilities must default to deny until explicitly allowed by policy.
- Side-effecting capabilities must declare idempotency, retry, duplicate-submit, and compensation semantics.
- The evaluation harness and policy thresholds used to judge a candidate must stay fixed during that comparison cycle.
- Promotion, rollout, and incident handling requirements must remain typed and evidence-backed, not just narrative.
- Sandbox-to-live-like memory promotion must require manual approval in v1.
- Skills must use the open `SKILL.md` standard (agentskills.io).
- Skills must map to capabilities in the capability manifest and follow capability governance.
- Skills from any registry must go through the same policy gate as built-in capabilities.
- Skills must not introduce unmanaged capability channels that bypass the capability manifest.
- Every agent must support ERC-8004 Agent Card generation.
- Agent trust assessment (ERC-8126) must be available before promotion to production.
- x402 payments must respect budget controls and circuit breakers.
- Session keys must never grant master wallet access.
- Prompt injection scanning must be enabled in canary and production.
- All wallet operations must go through the audit log.
- Protocol modules must remain stdlib-only (no web3 dependency in core).
- Sandbox and policy enforcement are core product value, not optional add-ons.
- Production promotion should be staged, evidence-backed, and capable of shadow/canary rollout where relevant.
- Production promotion must be governed.
- Self-evolution is allowed only through bounded, reviewable loops.
- Aether Forge agents are LLM-driven by default. `heuristic` mode is a labeled fallback for CI and cold-start, not a silent default.
- The framework MUST persist the operator's planner choice into the generated agent's `aether-forge.json` so the agent is self-contained and runnable by anyone with the same env.
- Memory is structured as four typed layers with distinct read/write semantics: replays (audit only), per-tick working set (in-process), durable per-agent SQLite memory (`memory.db`), and optional long-term semantic + temporal `KnowledgeStore` (MemPalace). Layers MUST NOT be collapsed or bypassed.
- `forge doctor` MUST verify runtime dependencies — including stateful components like memory layers — with functional round-trip checks, not just import existence.
- `forge doctor` MUST be scoped to runtime requirements an agent actually needs. Framework-contributor tooling (linters, test runners, build helpers) belongs in `[dev]` extras, not in the default doctor output.
- Generated agents MUST NOT depend on framework-developer packages (ruff, pytest, build, twine).
- Aether Forge MUST support MCP (Model Context Protocol) as a first-class capability source. Generated agents that declare `mcp_servers:` in their config MUST discover and call those tools at runtime via `McpDataSource`.
- Spawning MCP stdio subprocesses MUST NOT leak the full parent environment — only a safe baseline plus explicitly-declared `env:` entries are passed through.
- Tool filtering (`tools.include` / `tools.exclude`) MUST be honored per MCP server.
- The framework MUST NOT be named after a specific external framework or language model in a way that creates confusion with an unrelated project.
- On-chain agent registration (ERC-8004) MUST always be opt-in via explicit `forge agent-register`. Local registry tracking is automatic but can be opted out via `--no-registry`.
- Every agent SHOULD have a self-attestation (`attestation.json`) signed by its own wallet at generation time.
- Only the framework's published attestor wallet can issue "verified" tier attestations. The attestor address MUST be published in `ATTESTOR.md` and registered on-chain.
- `forge agent-discover` MUST show the trust tier (verified / self-attested / unverified) for every discovered agent so users can make informed decisions.
- Agent-to-agent payments MUST go through the same budget enforcement (`x402_state.json`, per-call and session caps) as Elsa x402 calls — one budget, multiple channels.
- Budget check + payment execution MUST be atomic (file lock held across both) to prevent race conditions.
- Agents accepting payments via `X402PaymentGate` MUST verify payment headers structurally before executing paid capabilities. Wrong address and insufficient amount MUST be rejected.
- All capability execution results from external sources (MCP, A2A, x402) MUST be scanned for prompt injection patterns before entering the planner's prompt context.

## 4. Documentation Rules

When product direction changes:

1. Create a new versioned PRD file under `docs/prd/`.
2. Update `docs/prd/README.md` with the new current version.
3. Append the change summary to `docs/prd/CHANGELOG.md`.
4. Keep older PRD versions intact.

Use semantic versioning for PRDs:

- patch for clarification
- minor for scope or requirement changes
- major for major direction changes

## 5. Planning Rules

- Treat `docs/prd/` as the canonical product source.
- Treat `docs/plans/` as exploration, planning, and design support material.
- If implementation choices are still undecided, do not silently invent permanent architecture. Document the decision first.
- Prefer smaller, composable plans over broad speculative platform work.

## 6. Implementation Guardrails

If code is added later, preserve these boundaries:

- spec generation should stay separate from runtime execution
- runtime execution should stay separate from policy enforcement
- side-effecting tools should never bypass policy checks
- sandbox and production behavior should share policy semantics where possible
- crypto-specific integrations should not leak unnecessary assumptions into the domain-agnostic core

## 7. Safety Guardrails

Any new capability that can move money, sign transactions, call exchanges, or trigger other sensitive side effects must include:

- explicit permission boundaries
- environment-aware execution behavior
- policy hooks
- auditability and trace support
- a sandbox or dry-run path before live use

Do not introduce live-capital execution paths without corresponding guardrails.

## 8. Collaboration Rules

- Do not overwrite user-authored intent in the PRD without leaving a versioned trail.
- Do not remove historical PRD files.
- Do not treat brainstorming notes as the canonical product contract when a versioned PRD exists.
- If you need to make a large architectural assumption, record it in planning docs before spreading it across code.

## 9. Current Default Bias

Until the user says otherwise, optimize for:

- developer usability
- readable generated artifacts
- strong runtime and safety primitives
- local-first and sandbox-first workflows
- crypto as the initial wedge, not the final boundary

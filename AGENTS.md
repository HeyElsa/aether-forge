# AGENTS.md

This file defines project-specific rules for any AI or automated collaborator working in this repository.

## 1. Project Purpose

`Aether Forge` is a spec-first, developer-first framework for turning an agent idea into a governed, testable, production-capable agent system.

The initial wedge is crypto, but the core framework must remain general enough to support other domains.

## 2. Canonical Product Documents

Read these before making product, architecture, or documentation changes:

1. `docs/prd/README.md`
2. `docs/prd/aether-forge-prd-v0.24.0.md`
3. `docs/prd/aether-forge-prd-v0.23.1.md`
4. `docs/prd/aether-forge-prd-v0.23.0.md`
5. `docs/prd/aether-forge-prd-v0.22.0.md`
6. `docs/prd/aether-forge-prd-v0.21.0.md`
7. `docs/prd/aether-forge-prd-v0.20.0.md`
8. `docs/prd/aether-forge-prd-v0.15.0.md`
9. `docs/prd/aether-forge-prd-v0.14.0.md`
10. `docs/prd/aether-forge-prd-v0.12.0.md`
11. `docs/prd/CHANGELOG.md`
12. `docs/plans/2026-04-06-aether-forge-research.md`
13. `docs/plans/2026-04-06-aether-forge-prd-autoresearch.md`
14. `docs/plans/2026-04-06-aether-forge-prd-exact-autoresearch.md`
15. `docs/plans/2026-04-06-aether-forge-schema-design.md`
16. `docs/plans/2026-04-06-aether-forge-v0.6.0-implementation-plan.md`
17. `docs/plans/2026-04-06-aether-forge-design.md`

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
- The five extension Protocols (`Planner`, `ExecutionRouter`, `PlanningModel`, `MemoryStore`, `DataSource`) MUST be exported from the top-level `aether_forge` package with `__all__` discipline and contract docstrings (one-paragraph summary + canonical signature + minimum-viable implementation example + pointer to the in-tree reference impl).
- Plugin discovery MUST use `importlib.metadata` entry points (`aether_forge.{planners,execution_routers,data_sources,skill_registries}` groups). A plugin whose `load()` raises MUST be logged at WARNING and skipped, never re-raised — third-party plugins MUST NOT be able to crash the framework on import.
- Generated agents MUST ship production batteries (`Dockerfile`, `.dockerignore`, `Makefile`, `.env.example`, `tests/__init__.py`, `tests/test_agent.py`) so a developer can `forge generate-fast → make test → make validate → make eval-pack` on day one with no further setup.
- The shared `tests/conftest.py` fixture surface (`tmp_agent_dir`, `memory_store`, `in_memory_store`, `static_planner`, `static_planning_model`, `mock_router`, `policy_gate`, `runtime_session`, `reset_plugin_cache`) is part of the contributor contract — fixture names and types MUST NOT change without a migration note.
- (v0.21.0) The `HeuristicPlanner` fallback in `PromptDrivenPlanner.propose_plan` MUST emit a structured `last_planner_parse_failure` event on `session.session_state` whenever it is triggered. The event MUST carry a `kind` discriminator (`parse-failure` / `parse-exception` / `model-error` / `empty-plan`), the originating `detail`, a truncated `responsePreview`, and an ISO `recordedAt` timestamp. Silent fallback (heuristic without a recorded reason) is a contract violation.
- (v0.21.0) `cli._autodetect_planner` MUST probe the cloud chain (`ANTHROPIC_API_KEY` → `OPENAI_API_KEY` → `GOOGLE_API_KEY`/`GEMINI_API_KEY` → `OPENROUTER_API_KEY`) before falling through to Ollama. It MUST NOT open a socket to localhost:11434 when any cloud key is set, unless `AETHER_FORGE_ALLOW_OLLAMA_AUTODETECT` is explicitly truthy. The returned dict MUST include a `source` discriminant (`"cloud" | "ollama" | "heuristic"`).
- (v0.21.0) Generated `aether-forge.json` MUST include `planner.source` (`"explicit"` or `"autodetected"`) and `planner.detectedAt` (ISO timestamp) so the planner-choice provenance is auditable post-hoc by `forge doctor` and log greppers.
- (v0.23.1) `AETHER_FORGE_PLANNER_MODE` and related planner env vars are explicit operator planner choices during `forge generate-fast`, equivalent to passing the corresponding CLI flags for provenance. They MUST stamp `planner.source: "explicit"` and MUST NOT be treated as autodetected.
- (v0.21.0) `MemoryRecord.schema_version` MUST be sourced from `aether_forge.memory.MEMORY_RECORD_SCHEMA_VERSION`. Hardcoded `"1.0.0"` strings in new code are a regression. `SqliteMemoryStore._init_schema` MUST stamp the value idempotently into the `schema_meta` table so the planned `MigrationRunner` can route old rows through transforms.
- (v0.21.0) Provider planning models (`OpenAICompatiblePlanningModel`, `AnthropicPlanningModel`, `GeminiPlanningModel`) MUST route their HTTP calls through `models._with_retry` and accept a `retry_attempts: int` dataclass field. The retry envelope MUST honor `Retry-After` on 429 and 503 responses and MUST raise immediately on non-transient HTTP codes (4xx other than 408/425/429). Stdlib-only — no new HTTP dependency.
- (v0.22.0) The `deploymentProfile` top-level field on `aether-forge.json` is part of the contract. `forge doctor` MUST escalate `production + autodetected`, `production + heuristic`, and `staging + autodetected` to a hard fail. `local` profile keeps autodetected as advisory-only (dev machines must not be punished). Generated configs MUST stamp the resolved profile at the top level.
- (v0.22.0) `MigrationRunner` MUST default to dry-run and MUST refuse contracts with non-empty `lossyFields` unless `policy.lossyOk` OR caller `lossy_ok=True`. Pre-mutation SQLite backups are mandatory before any row write. The `forge migrate` CLI MUST require `--apply` for any mutation. Migration contracts without `transformRef` MUST be treated as documentation-only — the runner refuses to execute them.
- (v0.23.1) `MigrationRunner.apply_to_memory_store` MUST only execute a transform for rows whose `MemoryRecord.schema_version` exactly equals the contract's `fromVersion`. Older rows require their own earlier migration step and MUST NOT be silently rewritten by a later transform.
- (v0.22.0) Provider `complete_with_tools(prompt, tools)` methods MUST raise `PlanningModelError` if `tools` is empty. Opting into tool-mode without a manifest is a configuration error, not a no-op. `PromptDrivenPlanner` tool-mode failures MUST record the same `last_planner_parse_failure` event shape as the legacy string path so observability stays consistent across both planner paths.
- (v0.22.0) `DelegatedSigner` (`aether_forge.crypto.signers`) is the canonical signing surface. New code MUST pass `signer=` to `X402Client`; the legacy `sign_typed_data_fn` keeps working with a deprecation warning and is scheduled for removal in v0.24.0. `SessionKeyConstrainedSigner` MUST refuse `intent=None` (fail-closed — without an intent there is nothing for the policy to check). `X402PaymentGate.verify_and_settle_onchain` MUST honor `allowed_payers` when provided, and the comparison MUST be case-insensitive.
- (v0.23.1) `SessionKeyConstrainedSigner` MUST fail closed when a policy constrains chains and the `SigningIntent` does not declare `chain_id`. Missing chain information is insufficient evidence to sign.
- (v0.23.0) The planner-output spec at `docs/specs/planner-output.md` (currently v1.0.0) is the cross-language contract. Both the Python reference (`aether_forge.planner._extract_json`) and the TypeScript reference (`@aether-forge/sdk` `parsePlannerOutput`) MUST conform to every shared fixture under `tests/fixtures/planner-outputs/`. Adding a new fixture is the canonical way to extend the contract; both reference implementations MUST be updated to handle it before the fixture lands on main.
- (v0.23.0) The committed `sdk-ts/src/schemas/generated/index.ts` MUST match a fresh `bun run generate:schemas`. CI fails the build on any drift. Authors who change a JSON schema MUST regenerate and commit the result in the same PR.
- (v0.23.0) The TypeScript SDK's ajv instance MUST pre-register every JSON schema published under `src/aether_forge/schemas/` — runtime network fetches for `$ref` resolution are a contract violation (the SDK MUST work in air-gapped, browser, and edge runtimes alike). New schemas added to the Python side MUST also be imported and addSchema'd in `sdk-ts/src/validate/index.ts`.
- (v0.23.0) `parsePlannerOutput` is a pure function with zero dependencies beyond the JavaScript stdlib. It MUST remain so as the SDK grows so it stays embeddable in any TS runtime. The same purity rule applies to the Python `_extract_json`.
- (v0.23.0) `@aether-forge/sdk` v0.1.x ships ZERO runtime behavior beyond schema validation and the planner-output parser. The runtime tick loop (`AgentRunner`), policy gate (`NativePolicyGate`), memory store implementations, autoresearch loop, and signer reference implementations are explicitly Python-only until cross-language usage data justifies porting any of them. They are the highest lockstep surfaces in the framework.
- (v0.24.0) Risky crypto tests MUST use explicit `integration`, `network`, `testnet`, and `live_capital` markers. Default contributor tests MUST NOT touch networks, testnets, or live capital.
- (v0.24.0) Network, testnet, and live-capital tests MUST require explicit operator opt-in and credentials. Missing enablement MUST skip, not silently call external providers.
- (v0.24.0) Runtime code MUST NOT synthesize fake live exchange fills or transaction IDs for non-dry-run live mode. Non-dry-run live execution requires an explicit submitter or project-specific exchange adapter.
- (v0.24.0) Generated agents MUST fail closed when live exchange adapters are absent, disabled, or misconfigured.
- (v0.24.0) Exchange-backed strategies SHOULD produce paper/live parity evidence before canary or production promotion.
- (v0.24.0) Live-capital documentation MUST include an explicit "Do Not Go Live Until" checklist and incident response path.
- (v0.24.0) Realistic crypto strategy examples MUST stay sandbox-first and document risks, permissions, policy limits, parity expectations, and live-readiness gates.

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

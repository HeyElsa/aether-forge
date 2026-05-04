# Aether Forge PRD v0.20.0

**Date**: 2026-05-03
**Status**: Approved
**Previous**: v0.19.0 (CHANGELOG.md)

---

## Summary

v0.20.0 is the **DX & Extensibility** release. Aether Forge's internal
architecture was already clean — typed Protocols for every extension point —
but those Protocols were not exported in the public API, there was no plugin
discovery, generated agents shipped JSON artifacts with no production
batteries (Dockerfile, Makefile, test scaffold, env template), and there was
no shared test harness for contributors.

This release closes those gaps in two waves: an additive surface + docs
wave (Wave 1) and a generator-template + tooling wave (Wave 2). For
existing users with no third-party plugins installed, behavior is
unchanged.

---

## What's New

### 1. Public extension Protocols

The five extension Protocols are now first-class members of the
`aether_forge` public API with contract docstrings:

| Protocol | Defined at | Built-in implementations |
|---|---|---|
| `Planner` | `runtime.py:110` | `HeuristicPlanner`, `PromptDrivenPlanner` |
| `ExecutionRouter` | `runtime.py:114` | `MockCryptoExecutionRouter` and 4 paper/live variants |
| `PlanningModel` | `planner.py:17` | `AnthropicPlanningModel`, `OpenAICompatiblePlanningModel`, `GeminiPlanningModel`, `StaticPlanningModel` |
| `MemoryStore` | `memory.py:139` | `InMemoryMemoryStore`, `SqliteMemoryStore` |
| `DataSource` (ABC) | `data_layer.py:92` | `HTTPDataSource`, `X402DataSource`, `WebSocketDataSource`, `McpDataSource`, `MockDataSource` |

Each Protocol's docstring includes a one-paragraph contract summary, the
canonical method signature, a 5-line minimum-viable implementation, and a
pointer to the in-tree reference implementation.

Additional supporting types now exported: `DataResult`, `DataRouter`,
`DataSourceCost`, `Subscription`, `StaticPlanningModel`.

### 2. Plugin discovery via `importlib.metadata`

Third parties can now publish framework extensions to PyPI without
forking. Four entry-point groups in `pyproject.toml`:

```toml
[project.entry-points."aether_forge.planners"]
[project.entry-points."aether_forge.execution_routers"]
[project.entry-points."aether_forge.data_sources"]
[project.entry-points."aether_forge.skill_registries"]
```

Implementation lives in `src/aether_forge/plugins.py` (cached lookup,
lazy import). Wiring:

- `config.py:build_planner_factory` — when `mode` doesn't match a
  built-in, looks up `aether_forge.planners` entry points before raising.
- `skills.py:get_registries()` — merges built-in `REGISTRIES` with any
  entries from `aether_forge.skill_registries`.

A plugin whose `load()` raises is logged at WARNING and skipped — it
**MUST NOT** crash the framework.

### 3. Generator emits production batteries

`forge generate-fast` now also emits four files into every new agent:

- `Dockerfile` (already shipped in v0.18.0; unchanged) +
  `.dockerignore` (new) — keeps `.env`, `.ows/`, `replays/`, `memory.db`,
  `knowledge/` out of images.
- `Makefile` — `validate`, `eval-pack`, `test`, `run-paper`,
  `run-sandbox`, `run-live` (with `CONFIRM_LIVE=yes` guard), `doctor`,
  `halt`, `resume`, `docker-build`, `docker-run`, `clean`.
- `.env.example` — every env var the agent might read at runtime, with
  inline comments explaining each provider.
- `tests/__init__.py` + `tests/test_agent.py` — a smoke test using the
  offline `HeuristicPlanner` that verifies (a) all artifacts validate
  against the framework's JSON schemas and (b) every declared scenario
  meets its expected outcome. **Green out of the box, no LLM key
  needed.**

A developer can now `forge generate-fast → cd → make test → make
validate → make eval-pack → make run-sandbox` immediately, with no
reading required.

### 4. `extending.mdx` — the "build on top" guide

New `docs-site/src/content/guides/extending.mdx` covers:

1. The Protocol contract pattern (with reference to the docstrings)
2. Worked example: custom `Planner` (xAI Grok via
   `OpenAICompatiblePlanningModel`)
3. Worked example: custom `DataSource` (private price feed)
4. Sketch: custom `MemoryStore` (Postgres backend)
5. Sketch: custom skill registry
6. PyPI plugin distribution snippet (full `pyproject.toml` for an
   `aether-forge-grok` plugin)
7. Testing patterns (cross-link to `tests/conftest.py`)

Linked from `README.md` and `CONTRIBUTING.md`.

### 5. Shared test fixtures

New `tests/conftest.py` provides reusable fixtures for both internal
tests and third-party extension tests:

| Fixture | Returns |
|---|---|
| `tmp_agent_dir` | Fresh fast-generated agent in `tmp_path` |
| `memory_store` | Clean `SqliteMemoryStore` (Layer 3) |
| `in_memory_store` | `InMemoryMemoryStore` |
| `static_planner` | `HeuristicPlanner` |
| `static_planning_model` | `StaticPlanningModel` returning canned JSON |
| `mock_router` | `MockCryptoExecutionRouter` |
| `policy_gate` | Sandbox-permissive `NativePolicyGate` |
| `runtime_session` | Fully-wired `RuntimeSession` ready to `.run()` |
| `reset_plugin_cache` | Clears entry-point discovery cache |

Demonstration tests at `tests/test_conftest_fixtures.py`.

### 6. Documentation gap-fills

- **`docs-site/src/content/reference/cli.mdx`** — added 12 missing
  commands (`artifact-compat`, `artifact-migration-plan`,
  `scaffold-{run,policy-sync,live-status}`, `resume-replay`,
  `x402-call`, `models-list`, `config-validate`, `init`, `wallet-info`,
  `completions`, `eval`).
- **`docs-site/src/content/reference/configuration.mdx`** — added the
  precedence chain (CLI > env > config > defaults), all
  `AETHER_FORGE_*` env vars, and a pointer to plugin-mode resolution.
- **`docs/README.md`** — new index mapping every topic to its
  authoritative source (the framework's repo-root standalone docs vs
  the docs-site).
- **`ARCHITECTURE.md`** — new at repo root. Runtime tick lifecycle,
  policy gate sequence, four-layer memory architecture, payment
  channels, "where to change things" table.

### 7. Contributor tooling

- **`mypy`** added to `[project.optional-dependencies].dev` and
  `[tool.mypy]` section in `pyproject.toml` (strict on the public-API
  surface — `__init__.py`, `runtime.py`, `planner.py`, `policy.py`,
  `memory.py`, `data_layer.py`, `plugins.py`). Wired into CI as a
  `continue-on-error: true` step (informational; flip to blocking once
  the surface is clean).
- **`pre-commit`** — new `.pre-commit-config.yaml` with `ruff
  format`/`ruff check`, file-hygiene hooks (trailing-whitespace, EOF
  newline, check-yaml/json/toml, large-file detection, private-key
  detection), and a fast `pytest --collect-only` hook to catch
  import-time errors. `pre-commit install` documented in
  `CONTRIBUTING.md`.

---

## Non-Negotiables Added

These are appended to `AGENTS.md` §3:

- The five extension Protocols (`Planner`, `ExecutionRouter`,
  `PlanningModel`, `MemoryStore`, `DataSource`) **MUST** be exported
  from the top-level `aether_forge` package with `__all__` discipline
  and contract docstrings.
- Plugin discovery **MUST** use `importlib.metadata` entry points; a
  plugin whose `load()` raises **MUST** be logged and skipped, never
  re-raised. Third-party plugins must not be able to crash the
  framework on import.
- Generated agents **MUST** ship production batteries (`Dockerfile`,
  `.dockerignore`, `Makefile`, `.env.example`, `tests/test_agent.py`)
  so a developer can `forge generate-fast → make test` on day one with
  no further setup.
- The shared `tests/conftest.py` fixture surface (`tmp_agent_dir`,
  `memory_store`, `static_planner`, `static_planning_model`,
  `mock_router`, `policy_gate`, `runtime_session`,
  `reset_plugin_cache`) is part of the contributor contract — fixture
  names and types **MUST NOT** be changed without a migration note.

---

## What Is Not Yet Done

Tracked but explicitly out of scope for v0.20.0:

- `forge mcp serve` (Aether Forge as an MCP server, exposing agent
  capabilities to external clients). Today agents *consume* MCP
  servers; serving is planned.
- ERC-8183 escrow contract deployment on Base mainnet (tx builder is
  ready; contract pending).
- Framework attestor wallet (`FRAMEWORK_ATTESTOR_ADDRESS` is empty in
  `attestation.py:65`); only `self-attested` and `unverified` tiers
  operate today.
- MCP streaming (SSE), resources, prompts, sampling.
- Structured error codes and a `forge debug --last` introspection
  command.
- Tightening `mypy` from informational to blocking once the public
  surface is fully typed.

---

## Verification

| Check | Result |
|---|---|
| Targeted regression (12 test files covering every changed module) | 105 passed |
| Broader sanity (full suite minus 10 known network-dependent integration files) | 387 passed, 11 skipped |
| Public-API import smoke (15 newly-exported symbols) | green |
| `forge generate-fast` end-to-end (validate, eval-pack, generated pytest, Makefile targets, 3-tick runtime) | all green |
| Fixture-name collision audit across all 47 test files | 0 collisions |
| `ruff check src/ tests/` | clean |
| Generator-honesty check (every `docs/*.md` reference resolves) | clean |

The 10 excluded files (`test_e2e`, `test_real_agent`, `test_a2a`,
`test_mcp_client`, `test_paper_trading`, `test_live_execution`,
`test_market_data`, `test_x402_client`, `test_runner`,
`test_onchain_registry`) are network-bound integration tests that
require outbound DNS to pypi/binance/Base mainnet — they pass in CI
where network is available; they don't touch any module modified in
this release.

---

## Files Changed

23 files: 15 modified + 8 new. **+1916 / −7** lines.

**New**:
`src/aether_forge/plugins.py`, `tests/conftest.py`,
`tests/test_plugins.py`, `tests/test_conftest_fixtures.py`,
`docs-site/src/content/guides/extending.mdx`, `docs/README.md`,
`ARCHITECTURE.md`, `.pre-commit-config.yaml`.

**Modified**:
`src/aether_forge/{__init__,runtime,planner,memory,data_layer,config,skills,generator}.py`,
`pyproject.toml`, `.github/workflows/ci.yml`, `README.md`,
`CONTRIBUTING.md`,
`docs-site/src/content/{guides/_meta.js,reference/{cli,configuration}.mdx}`.

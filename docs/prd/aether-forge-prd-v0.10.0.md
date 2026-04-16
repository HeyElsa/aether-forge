# Aether Forge Product Requirements Document

Version: `v0.10.0`
Status: `Draft`
Date: `2026-04-09`
Owners: `OpenCode + user`
Supersedes: `docs/prd/aether-forge-prd-v0.9.0.md`
Base PRD: `docs/prd/aether-forge-prd-v0.9.0.md`
Supporting design:

- `docs/plans/2026-04-06-aether-forge-schema-design.md`

## 1. Status

This PRD version inherits all unchanged requirements from `v0.9.0`.

`v0.10.0` is a minor capability expansion that moves the framework from prototype to developer-usable tool. It adds:

- Multi-provider LLM support with named provider shortcuts (new)
- Persistent memory backend via SQLite (new)
- Model discovery across providers (new)
- CI/CD pipeline and linting (new)
- End-to-end integration tests (new)
- Configuration documentation (updated)

## 2. Summary Of Changes

Compared with `v0.9.0`, this version:

1. adds native LLM adapter classes for Anthropic (Claude) and Google Gemini alongside the existing OpenAI-compatible adapter, enabling direct access to frontier models without proxies
2. adds named provider shortcuts (`anthropic`, `gemini`, `openai`, `openrouter`, `ollama`) that auto-resolve base URLs and API formats, removing the need for users to know provider-specific endpoints
3. adds a SQLite-backed persistent memory store (`SqliteMemoryStore`) so agent memory survives across sessions, alongside the existing in-memory store
4. adds a `models-list` CLI command for discovering available models from OpenRouter (351+ models), Ollama (local), and OpenAI
5. adds a CI/CD pipeline with GitHub Actions (pytest + ruff on Python 3.12/3.13)
6. adds end-to-end integration tests covering the full `generate → validate → eval → promote` pipeline
7. documents the configuration file format, environment variables, and provider setup in README

## 3. Multi-Provider LLM Support (New)

The planning and autoresearch subsystems now support multiple LLM providers natively. All providers satisfy the same `PlanningModel` and `ResearchModel` protocols: `complete(planning_prompt: str) -> str`.

### 3.1 Provider Model Classes

Three provider-specific model classes are available, each using stdlib `urllib` with no external SDK dependency:

| Class | API Shape | Default Base URL |
|---|---|---|
| `OpenAICompatiblePlanningModel` | `/chat/completions` (OpenAI format) | User-configured |
| `AnthropicPlanningModel` | `/v1/messages` (Anthropic format) | `https://api.anthropic.com` |
| `GeminiPlanningModel` | `/v1beta/models/{model}:generateContent` (Google format) | `https://generativelanguage.googleapis.com` |

All classes support injectable `request_fn` for testing without network calls.

Module: `src/aether_forge/models.py`

### 3.2 Named Provider Shortcuts

Named shortcuts auto-resolve to the correct model class and default base URL:

| CLI Mode | Backend Mode | Default Base URL | API Key Required |
|---|---|---|---|
| `anthropic` | `anthropic` | `https://api.anthropic.com` | Yes |
| `gemini` | `gemini` | `https://generativelanguage.googleapis.com` | Yes |
| `openai` | `openai-compatible` | `https://api.openai.com/v1` | Yes |
| `openrouter` | `openai-compatible` | `https://openrouter.ai/api/v1` | Yes |
| `ollama` | `openai-compatible` | `http://localhost:11434/v1` | No |
| `openai-compatible` | `openai-compatible` | User-configured | Yes |
| `hermes` | `hermes` | User-configured | Yes |
| `heuristic` | `heuristic` | N/A | No |
| `static` | `static` | N/A | No |

Named modes resolve in `resolve_planner_settings()`. Users can override the default base URL with `--planner-base-url` or `AETHER_FORGE_PLANNER_BASE_URL`.

Module: `src/aether_forge/config.py`

### 3.3 CLI Integration

All CLI commands that accept `--planner-mode` now support the full set of named providers:

```bash
forge generate-slow --planner-mode anthropic --planner-model claude-sonnet-4-20250514 --planner-api-key-env ANTHROPIC_API_KEY
forge generate-slow --planner-mode gemini --planner-model gemini-2.5-pro --planner-api-key-env GEMINI_API_KEY
forge generate-slow --planner-mode openrouter --planner-model meta-llama/llama-4-maverick --planner-api-key-env OPENROUTER_API_KEY
forge generate-slow --planner-mode ollama --planner-model llama3
```

Module: `src/aether_forge/cli.py`

### 3.4 Open-Source Model Access

OpenRouter provides access to 351+ models including open-source models (Llama, Mistral, DeepSeek, Qwen, Gemma) through the OpenAI-compatible API. Ollama provides local inference for any GGUF-quantized model. Both are first-class supported providers.

### 3.5 Provider Safety Rules

1. API keys must not appear in specs, prompts, traces, or persisted state; use `--planner-api-key-env` to reference environment variables
2. All provider model classes must remain stdlib-only (no `anthropic`, `openai`, or `google` SDK dependencies)
3. Provider selection does not affect policy enforcement, evaluation, or promotion requirements
4. Model responses are validated before use; malformed responses trigger fallback to the heuristic planner

## 4. Persistent Memory Backend (New)

Agent memory can now be persisted to a SQLite database, allowing agents to retain context across sessions. The SQLite backend satisfies the same `MemoryStore` protocol as the existing `InMemoryMemoryStore`.

### 4.1 SqliteMemoryStore

| Feature | Behavior |
|---|---|
| Storage | SQLite database file (WAL mode for concurrent reads) |
| Schema | Auto-initialized on first connection |
| Indexing | Scope, environment, memory type, and updated_at |
| Upsert | Writes use `INSERT ... ON CONFLICT DO UPDATE` for idempotent writes |
| Filtering | Scope, environment, type, sensitivity ceiling, tag, text search, expiry |
| Promotion | Same governed promotion policy as in-memory store |
| Secret rejection | Same `_find_secret_like_paths` validation as in-memory store |
| Context manager | Supports `with SqliteMemoryStore(path) as store:` |
| Export/Import | `export_records()` and `from_exported()` for backup and migration |

Module: `src/aether_forge/storage.py`

### 4.2 CLI Integration

```bash
forge eval-pack ./my-agent --memory-store sqlite --memory-db ./my-agent/memory.db
forge eval ./my-agent --scenario baseline --memory-store sqlite --memory-db ./memory.db
```

The `--memory-store` option is available on all runtime commands: `eval`, `eval-pack`, `promote-draft`, `resume-replay`, `scaffold-run`.

When `--memory-store sqlite` is used without `--memory-db`, the database defaults to `memory.db` in the artifact directory.

### 4.3 Memory Persistence Rules

1. The SQLite backend must enforce the same validation rules as the in-memory store (confidence bounds, secret rejection)
2. The SQLite backend must enforce the same promotion policy (manual approval for cross-environment moves)
3. The SQLite backend must be compatible with the `MemoryStore` protocol so it can be used as a drop-in replacement
4. Database files must be created with parent directories if they do not exist
5. The in-memory store remains the default for backward compatibility; SQLite is opt-in

## 5. Model Discovery (New)

A new `models-list` CLI command enables users to browse available models from supported providers before selecting one for planning or autoresearch.

### 5.1 Supported Providers

| Provider | Endpoint | Authentication | Response Fields |
|---|---|---|---|
| OpenRouter | `GET /api/v1/models` | Optional Bearer token | ID, name, context length, modality, pricing |
| Ollama | `GET /api/tags` | None | ID, parameter size, quantization |
| OpenAI | `GET /v1/models` | Bearer token | ID |

### 5.2 ModelInfo Schema

All provider responses are normalized to a common `ModelInfo` dataclass:

- `id` -- model identifier (e.g., `meta-llama/llama-4-maverick`)
- `name` -- human-readable name
- `provider` -- source provider
- `context_length` -- maximum context window (tokens)
- `modality` -- input/output modality (e.g., `text+image->text`)
- `prompt_price` -- cost per token for input (provider-specific units)
- `completion_price` -- cost per token for output
- `parameter_size` -- model parameter count (Ollama)
- `quantization` -- quantization level (Ollama)

### 5.3 CLI Usage

```bash
forge models-list --provider openrouter --query "llama" --limit 10
forge models-list --provider ollama
forge models-list --provider openai --api-key-env OPENAI_API_KEY
```

### 5.4 Filtering

The `--query` flag performs case-insensitive substring matching against both model ID and name. The `--limit` flag caps the number of displayed results (default: 50).

Module: `src/aether_forge/models.py` (discovery functions), `src/aether_forge/cli.py` (CLI command)

## 6. CI/CD Pipeline (New)

Automated testing and linting are now enforced via GitHub Actions.

### 6.1 Workflow

File: `.github/workflows/ci.yml`

| Job | Runner | Steps |
|---|---|---|
| `test` | ubuntu-latest, Python 3.12 + 3.13 | Install deps, ruff check, pytest |
| `lint` | ubuntu-latest, Python 3.12 | ruff format --check, ruff check |

### 6.2 Linting Configuration

Ruff is configured in `pyproject.toml`:

- Target: Python 3.12
- Line length: 120
- Rules: E, F, I, UP, B, SIM (pyflakes, pycodestyle, isort, pyupgrade, bugbear, simplify)
- E501 (line too long) is ignored in favor of the 120-char line length setting

### 6.3 CI Requirements

1. All tests must pass on Python 3.12 and 3.13 before merge to main
2. All code must pass ruff lint and format checks
3. CI runs on push to main and on pull requests targeting main

## 7. End-to-End Integration Tests (New)

Five integration tests validate the complete pipeline:

| Test | Coverage |
|---|---|
| `test_e2e_generate_validate_eval_promote_crypto` | Full pipeline for a crypto agent via Python API |
| `test_e2e_generate_validate_eval_promote_general` | Full pipeline for a general agent via Python API |
| `test_e2e_cli_generate_validate_eval` | Full pipeline via CLI entry points |
| `test_e2e_with_sqlite_memory` | Pipeline with SQLite memory persistence |
| `test_e2e_generate_with_skills` | Pipeline with Elsa skills integration |

Module: `tests/test_e2e.py`

### 7.1 Test Requirements

1. E2E tests must exercise `generate → validate → eval → promote` as a single flow
2. E2E tests must not require network access or API keys
3. E2E tests must cover both crypto and general agent domains
4. E2E tests must cover both Python API and CLI entry points

## 8. Configuration Documentation (Updated)

### 8.1 Config File Format

Aether Forge discovers configuration from `aether-forge.json` in the artifact directory or working directory:

```json
{
  "planner": {
    "mode": "anthropic",
    "model": "claude-sonnet-4-20250514",
    "apiKeyEnv": "ANTHROPIC_API_KEY"
  },
  "runtime": {
    "cryptoRouter": "mock"
  }
}
```

### 8.2 Environment Variables

| Variable | Purpose |
|---|---|
| `AETHER_FORGE_PLANNER_MODE` | Default planner mode |
| `AETHER_FORGE_PLANNER_MODEL` | Default model name |
| `AETHER_FORGE_PLANNER_BASE_URL` | Default base URL |
| `AETHER_FORGE_PLANNER_API_KEY` | API key (direct) |
| `AETHER_FORGE_PLANNER_API_KEY_ENV` | Name of env var holding the API key (indirect) |
| `AETHER_FORGE_CRYPTO_ROUTER` | Default crypto router backend |

### 8.3 Precedence

CLI flags > environment variables > config file > defaults.

## 9. Implementation Status Updates

### 9.1 New Modules

| Module | Purpose | Tests |
|---|---|---|
| `src/aether_forge/storage.py` | SQLite persistent memory backend | 15 tests |
| `tests/test_e2e.py` | End-to-end pipeline tests | 5 tests |
| `tests/test_storage.py` | SQLite memory store tests | 15 tests |
| `.github/workflows/ci.yml` | CI/CD pipeline | N/A |

### 9.2 Updated Modules

| Module | Change |
|---|---|
| `src/aether_forge/models.py` | Added `AnthropicPlanningModel`, `GeminiPlanningModel`, `ModelInfo`, `list_models()` |
| `src/aether_forge/config.py` | Added `_PROVIDER_DEFAULTS`, named mode resolution, anthropic/gemini factory |
| `src/aether_forge/cli.py` | Added `models-list` command, `--memory-store`/`--memory-db` options, updated `--planner-mode` choices |
| `src/aether_forge/planner.py` | Fixed memory store access to use protocol-compatible `read()` instead of internal `_records` |
| `src/aether_forge/__init__.py` | Exported new classes |
| `pyproject.toml` | Added ruff configuration |
| `README.md` | Added Configuration section with provider setup, env vars, memory store docs |

### 9.3 Test Count

| Version | Tests |
|---|---|
| v0.9.0 | 127 |
| v0.10.0 | 159 |

New tests: 15 (SQLite storage) + 5 (E2E) + 6 (provider config) + 2 (provider models) + 4 (model discovery) = 32.

## 10. Inherited Requirements

All requirements from `v0.9.0` (and transitively from `v0.8.0` through `v0.1.0`) remain in force unless explicitly updated in this document. In particular:

- The open agent economy protocols (ERC-8004, ERC-8126, ERC-8183, x402) from v0.9.0 are unchanged
- The security hardening module from v0.9.0 is unchanged
- The OWS wallet support from v0.9.0 is unchanged
- The memory model from v0.7.0 is unchanged; the SQLite backend is an additional implementation, not a replacement
- The autoresearch loop mechanics from v0.4.0 are unchanged; they now work with any supported LLM provider
- The core lifecycle, environment model, and governance requirements from earlier versions are unchanged

## 11. Functional Requirements Additions

### Multi-Provider LLM Support

- The system must support Anthropic Claude models via the native Messages API
- The system must support Google Gemini models via the native generateContent API
- The system must support OpenAI, OpenRouter, and Ollama models via the OpenAI-compatible chat completions API
- The system must resolve named provider shortcuts to the correct model class and default base URL
- The system must allow users to override default base URLs for any provider
- The system must fall back to the heuristic planner when model responses are malformed

### Persistent Memory

- The system must support SQLite-backed persistent memory as an opt-in alternative to in-memory storage
- The SQLite backend must enforce the same validation, promotion, and safety rules as the in-memory store
- The system must default to in-memory storage for backward compatibility
- The system must create database files and parent directories automatically when needed

### Model Discovery

- The system must support listing available models from OpenRouter, Ollama, and OpenAI
- The system must normalize model metadata to a common schema regardless of provider
- The system must support filtering models by name or ID substring

### CI/CD

- All tests must pass on Python 3.12 and 3.13 in CI before merge
- All code must pass ruff lint and format checks in CI

## 12. Non-Functional Requirements Additions

- Named provider resolution must add zero latency (resolved at config time, not request time)
- SQLite memory store must support WAL mode for concurrent read access
- Model listing must complete within 15 seconds per provider (network-dependent)
- All new modules must maintain the stdlib-only constraint (no new external dependencies)

## 13. Roadmap Implications

### LLM Integration

Multi-provider support is operational. Future work includes:

- Streaming response support for real-time planning feedback
- Token usage tracking and cost estimation per session
- Model-specific prompt optimization (system prompt format varies by provider)
- Retry with exponential backoff on provider errors
- Provider health monitoring and automatic failover

### Persistent Storage

SQLite memory is operational. Future work includes:

- File-backed artifact store (beyond memory records)
- Database migration support for schema evolution
- Memory compaction and archival for long-running agents
- Optional encryption at rest for sensitive memory records

### Developer Experience

CI and config documentation are operational. Future work includes:

- PyPI package publishing pipeline
- Interactive `forge init` setup wizard
- Config file validation command
- Shell completions for CLI commands

## 14. Open Questions

Inherited from v0.9.0 (all remain open):

- Should Agent Cards (ERC-8004) be auto-generated on every artifact build, or only on explicit request?
- What is the minimum trust score threshold for agent-to-agent job creation?
- Should circuit breaker thresholds be configurable per-agent, or global per-environment?
- Should audit logs support structured export for external SIEM integration in v1?
- Should wallet export require multi-factor confirmation?

New in v0.10.0:

- Should `models-list` cache results locally for faster repeated queries?
- Should the SQLite memory store support optional encryption at rest?
- Should provider selection be persisted in the config file after first use (wizard-style setup)?
- What is the upgrade path for SQLite schema changes in future versions?
- Should the framework provide built-in token counting for cost estimation across providers?
- Should Ollama model pulling (`ollama pull`) be integrated into the CLI for convenience?

## 15. Final Recommendation

`Aether Forge` v0.10.0 completes the transition from spec-driven prototype to developer-usable tool. The key improvements:

1. **Users can now use real LLMs** for planning and autoresearch across all major providers (Claude, Gemini, GPT, Llama, Mistral, etc.) with a single CLI flag
2. **Agent memory persists** across sessions via SQLite, enabling agents to learn and retain context over time
3. **Model discovery** helps users find and select from 351+ available models before committing to one
4. **CI/CD** protects the 159-test baseline from regression
5. **E2E tests** prove the full `generate → validate → eval → promote` pipeline works end-to-end

The correct product posture remains unchanged: spec-first, policy-governed, eval-driven, production-ready. These additions make that posture accessible to developers who want to use real models, persist real state, and iterate with confidence.

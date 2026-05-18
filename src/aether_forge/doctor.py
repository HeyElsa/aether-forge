"""Diagnostic utilities for Aether Forge environment validation."""

from __future__ import annotations

import importlib
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request as urllib_request


@dataclass(slots=True)
class CheckResult:
    name: str
    passed: bool
    message: str
    details: str = ""
    optional: bool = False


def run_doctor_checks(*, config_path: Path | None = None, verbose: bool = False) -> list[CheckResult]:
    """Run all diagnostic checks and return results.

    Checks are scoped to what an agent needs at *runtime*. Framework
    contributor tools (ruff, pytest, etc.) are not checked here — install
    them with ``pip install aether-forge[dev]`` if you're hacking on the
    framework itself.
    """
    results: list[CheckResult] = []
    results.append(_check_python_version())
    results.append(_check_jsonschema())
    results.append(_check_ows_sdk())
    results.append(_check_cryptography())
    results.append(_check_ollama_connectivity())
    results.append(_check_openrouter_connectivity())
    results.append(_check_sqlite_memory_store())
    results.append(_check_mempalace_knowledge_layer())
    if config_path:
        results.append(_check_config_file(config_path))
        results.append(_check_deployment_profile(config_path))
        results.append(_check_planner_source(config_path))
        # Probe any MCP servers declared in the config file. Informational —
        # a failed MCP probe does not fail the overall doctor check.
        results.extend(_check_mcp_servers(config_path))
    return results


def _load_config_safe(config_path: Path) -> dict | None:
    """Read aether-forge.json defensively; return None on any failure so callers
    can render a soft advisory rather than crashing the doctor pipeline."""
    if not config_path.exists():
        return None
    try:
        data = json.loads(config_path.read_text(encoding="utf8"))
    except (json.JSONDecodeError, OSError):
        return None
    return data if isinstance(data, dict) else None


def _check_deployment_profile(config_path: Path) -> CheckResult:
    """Surface ``deploymentProfile`` from aether-forge.json (Sprint 2.2 / FP-2).

    Validates that the value is one of {local, staging, production}; absence
    is treated as ``local`` (the safe default). The downstream
    ``_check_planner_source`` uses this profile to escalate ``autodetected``
    or ``heuristic`` from advisory to hard fail in non-local profiles.
    """
    from .config import DEPLOYMENT_PROFILES, DEFAULT_DEPLOYMENT_PROFILE

    if not config_path.exists():
        return CheckResult(
            name="Deployment profile",
            passed=True,
            message="No config file — skipping",
            optional=True,
        )
    data = _load_config_safe(config_path)
    if data is None:
        return CheckResult(
            name="Deployment profile",
            passed=True,
            message="Could not parse config (see Config file check)",
            optional=True,
        )
    profile = data.get("deploymentProfile", DEFAULT_DEPLOYMENT_PROFILE)
    if profile not in DEPLOYMENT_PROFILES:
        return CheckResult(
            name="Deployment profile",
            passed=False,
            message=f"Invalid deploymentProfile={profile!r}. Must be one of {DEPLOYMENT_PROFILES}.",
        )
    note = "" if "deploymentProfile" in data else " (implicit default)"
    return CheckResult(
        name="Deployment profile",
        passed=True,
        message=f"{profile}{note}",
    )


def _check_planner_source(config_path: Path) -> CheckResult:
    """Surface ``planner.source`` from aether-forge.json (Sprint 1.2 / FP-2).

    A generated agent stamps either ``"explicit"`` (operator passed
    ``--planner-mode`` or set ``AETHER_FORGE_PLANNER_MODE``) or
    ``"autodetected"`` (cli._autodetect_planner picked it). The Sprint 2.2
    deployment-profile work escalates the verdict:

    - profile=production AND source=autodetected → FAIL
    - profile=production AND mode=heuristic → FAIL
    - profile=staging AND source=autodetected → FAIL
    - profile=local (or unset) → advisory only
    """
    from .config import DEFAULT_DEPLOYMENT_PROFILE

    if not config_path.exists():
        return CheckResult(
            name="Planner source",
            passed=True,
            message="No config file — skipping",
            optional=True,
        )
    data = _load_config_safe(config_path)
    if data is None:
        return CheckResult(
            name="Planner source",
            passed=True,
            message="Could not parse config (see Config file check)",
            optional=True,
        )
    planner = data.get("planner") if isinstance(data, dict) else None
    if not isinstance(planner, dict):
        return CheckResult(
            name="Planner source",
            passed=True,
            message="No planner block declared (heuristic fallback at runtime)",
            optional=True,
        )
    source = planner.get("source")
    mode = planner.get("mode", "?")
    detected_at = planner.get("detectedAt")
    profile = data.get("deploymentProfile", DEFAULT_DEPLOYMENT_PROFILE)

    if mode == "heuristic" and profile != "local":
        return CheckResult(
            name="Planner source",
            passed=False,
            message=(
                f"heuristic planner is not allowed in {profile} profile. "
                "Configure an LLM provider before deploying."
            ),
        )
    if source == "autodetected" and profile == "production":
        suffix = f" at {detected_at}" if detected_at else ""
        return CheckResult(
            name="Planner source",
            passed=False,
            message=(
                f"production profile forbids autodetected planner (mode={mode}{suffix}). "
                "Pin with AETHER_FORGE_PLANNER_MODE or --planner-mode and regenerate."
            ),
        )
    if source == "autodetected" and profile == "staging":
        suffix = f" at {detected_at}" if detected_at else ""
        return CheckResult(
            name="Planner source",
            passed=False,
            message=(
                f"staging profile forbids autodetected planner (mode={mode}{suffix}). "
                "Pin explicitly before promoting to staging."
            ),
        )
    if source == "explicit":
        return CheckResult(
            name="Planner source",
            passed=True,
            message=f"explicit (mode={mode}) — production-safe",
        )
    if source == "autodetected":
        suffix = f" at {detected_at}" if detected_at else ""
        return CheckResult(
            name="Planner source",
            passed=True,
            message=(
                f"autodetected (mode={mode}){suffix}. Set AETHER_FORGE_PLANNER_MODE "
                f"or --planner-mode to pin this for production."
            ),
            optional=True,
        )
    # Older agents predate this field — informational only.
    return CheckResult(
        name="Planner source",
        passed=True,
        message=f"unstamped (mode={mode}). Regenerate to record planner provenance.",
        optional=True,
    )


def _check_python_version() -> CheckResult:
    v = sys.version_info
    passed = v >= (3, 12)
    return CheckResult(
        name="Python version",
        passed=passed,
        message=f"Python {v.major}.{v.minor}.{v.micro}" + (" (ok)" if passed else " (requires 3.12+)"),
    )


def _check_jsonschema() -> CheckResult:
    try:
        import jsonschema
        return CheckResult(name="jsonschema", passed=True, message=f"jsonschema {jsonschema.__version__}")
    except ImportError:
        return CheckResult(name="jsonschema", passed=False, message="Not installed (pip install jsonschema)")


def _check_ows_sdk() -> CheckResult:
    try:
        importlib.import_module("ows")
        return CheckResult(name="OWS SDK", passed=True, message="open-wallet-standard installed")
    except ImportError:
        return CheckResult(name="OWS SDK", passed=True, message="Not installed (optional — pip install aether-forge[wallet])", optional=True)


def _check_cryptography() -> CheckResult:
    """The cryptography package is required for encrypted wallet backups
    (AES-256-GCM + scrypt KDF). Without it, ``forge wallet-backup`` falls
    back to refusing to write a plaintext backup unless ``--unencrypted``
    is passed explicitly.
    """
    try:
        import cryptography
        return CheckResult(
            name="cryptography",
            passed=True,
            message=f"cryptography {cryptography.__version__} (encrypted backups available)",
        )
    except ImportError:
        return CheckResult(
            name="cryptography",
            passed=True,
            message="Not installed (optional — pip install cryptography; required for encrypted backups)",
            optional=True,
        )


def _check_ollama_connectivity() -> CheckResult:
    try:
        req = urllib_request.Request("http://localhost:11434/api/tags", method="GET")
        with urllib_request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf8"))
            count = len(data.get("models", []))
            return CheckResult(name="Ollama", passed=True, message=f"Connected ({count} models)")
    except Exception:
        return CheckResult(name="Ollama", passed=True, message="Not reachable (optional — install ollama)")


def _check_openrouter_connectivity() -> CheckResult:
    try:
        req = urllib_request.Request("https://openrouter.ai/api/v1/models", method="GET")
        with urllib_request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf8"))
            count = len(data.get("data", []))
            return CheckResult(name="OpenRouter", passed=True, message=f"Connected ({count} models)")
    except Exception:
        return CheckResult(name="OpenRouter", passed=True, message="Not reachable (check network)")


def _check_sqlite_memory_store() -> CheckResult:
    """Layer 3 — operational per-agent memory (in-tree, stdlib only).

    Spins up a temp SqliteMemoryStore, writes a sentinel record, reads it back.
    Verifies the schema migration runs cleanly and the round-trip works.
    """
    try:
        import tempfile
        from datetime import UTC, datetime

        from .memory import MemoryQuery, MemoryRecord
        from .storage import SqliteMemoryStore

        with tempfile.TemporaryDirectory() as tmp:
            store = SqliteMemoryStore(Path(tmp) / "doctor_memory.db")
            sentinel = MemoryRecord(
                memory_id="doctor-sentinel",
                memory_type="diagnostic",
                scope="session",
                environment="sandbox",
                content={"check": "doctor"},
                summary="doctor check",
                source="doctor",
                confidence=1.0,
                sensitivity="internal",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            store.write(sentinel)
            records = store.read(MemoryQuery(scope="session", environment="sandbox", limit=5))
            if not any(r.memory_id == "doctor-sentinel" for r in records):
                return CheckResult(
                    name="Memory store (SQLite)",
                    passed=False,
                    message="Round-trip failed: wrote sentinel but could not read it back",
                )
            return CheckResult(
                name="Memory store (SQLite)",
                passed=True,
                message="Layer 3 round-trip ok (write + read)",
            )
    except Exception as error:
        return CheckResult(
            name="Memory store (SQLite)",
            passed=False,
            message=f"Failed: {error}",
        )


def _check_mempalace_knowledge_layer() -> CheckResult:
    """Layer 4 — long-term semantic + temporal memory (optional dep).

    Tries to import mempalace, instantiate a temp KnowledgeStore, write a
    fact and a memory, and read them back. Reports clearly when the
    optional dep is missing so the operator knows the agent will run
    without long-term memory.
    """
    try:
        importlib.import_module("mempalace")
    except ImportError:
        return CheckResult(
            name="Knowledge layer (MemPalace)",
            passed=True,
            message="Not installed (optional — pip install mempalace; agents run without long-term memory)",
            optional=True,
        )

    try:
        import tempfile

        from .knowledge import KnowledgeStore

        with tempfile.TemporaryDirectory() as tmp:
            store = KnowledgeStore(Path(tmp) / "doctor_knowledge", wing="doctor")
            if not store.available:
                return CheckResult(
                    name="Knowledge layer (MemPalace)",
                    passed=False,
                    message="Imported but failed to initialize (check disk perms or chroma backend)",
                )
            store.add_fact("DOCTOR", "status", "ok", valid_from="2026-04-11")
            store.remember("Doctor sentinel observation", room="diagnostics", source="doctor")
            facts = store.query_entity("DOCTOR")
            if not facts:
                return CheckResult(
                    name="Knowledge layer (MemPalace)",
                    passed=False,
                    message="KG round-trip failed: wrote fact but query_entity returned empty",
                )
            try:
                version = importlib.import_module("mempalace").__version__  # type: ignore[attr-defined]
            except Exception:
                version = "?"
            return CheckResult(
                name="Knowledge layer (MemPalace)",
                passed=True,
                message=f"mempalace {version} — KG + semantic round-trip ok",
            )
    except Exception as error:
        return CheckResult(
            name="Knowledge layer (MemPalace)",
            passed=False,
            message=f"Failed: {error}",
        )


def _check_mcp_servers(config_path: Path) -> list[CheckResult]:
    """Probe MCP servers declared in an aether-forge.json file.

    Reads the ``mcp_servers`` block and tries to ``initialize`` + ``tools/list``
    each declared server. Reports one CheckResult per server. Failures are
    marked as optional so they don't flip the overall ``forge doctor`` verdict
    to UNHEALTHY — an unreachable MCP server is usually a config issue, not
    a missing runtime requirement.
    """
    results: list[CheckResult] = []
    if not config_path.exists():
        return results

    try:
        data = json.loads(config_path.read_text(encoding="utf8"))
    except (json.JSONDecodeError, OSError):
        return results

    servers = data.get("mcp_servers") if isinstance(data, dict) else None
    if not isinstance(servers, dict) or not servers:
        return results

    try:
        from .mcp_client import McpServerConfig, build_mcp_client
    except ImportError:
        return [
            CheckResult(
                name="MCP client",
                passed=True,
                message="mcp_client module unavailable (optional)",
                optional=True,
            )
        ]

    for name, spec in servers.items():
        try:
            cfg = McpServerConfig.from_dict(name, spec)
            client = build_mcp_client(cfg)
            try:
                tools = client.list_tools()
                results.append(
                    CheckResult(
                        name=f"MCP server [{name}]",
                        passed=True,
                        message=f"{len(tools)} tools available ({cfg.transport})",
                    )
                )
            finally:
                try:
                    client.close()
                except Exception:
                    pass
        except Exception as error:
            results.append(
                CheckResult(
                    name=f"MCP server [{name}]",
                    passed=True,
                    message=f"Unreachable (optional — {error})",
                    optional=True,
                )
            )
    return results


def _check_config_file(config_path: Path) -> CheckResult:
    if not config_path.exists():
        return CheckResult(name="Config file", passed=False, message=f"Not found: {config_path}")
    try:
        data = json.loads(config_path.read_text(encoding="utf8"))
        if not isinstance(data, dict):
            return CheckResult(name="Config file", passed=False, message="Must be a JSON object")
        return CheckResult(name="Config file", passed=True, message=f"Valid: {config_path}")
    except json.JSONDecodeError as e:
        return CheckResult(name="Config file", passed=False, message=f"Invalid JSON: {e}")


def validate_config(config_path: Path) -> list[CheckResult]:
    """Validate an aether-forge.json config file."""
    results: list[CheckResult] = []

    if not config_path.exists():
        results.append(CheckResult(name="File exists", passed=False, message=f"Not found: {config_path}"))
        return results
    results.append(CheckResult(name="File exists", passed=True, message=str(config_path)))

    try:
        data = json.loads(config_path.read_text(encoding="utf8"))
    except json.JSONDecodeError as e:
        results.append(CheckResult(name="Valid JSON", passed=False, message=str(e)))
        return results
    results.append(CheckResult(name="Valid JSON", passed=True, message="OK"))

    if not isinstance(data, dict):
        results.append(CheckResult(name="Top-level object", passed=False, message="Must be a JSON object"))
        return results
    results.append(CheckResult(name="Top-level object", passed=True, message="OK"))

    valid_top_keys = {"deploymentProfile", "planner", "runtime", "memory", "security", "market_data", "adapters", "mcp_servers"}
    unknown = set(data.keys()) - valid_top_keys
    if unknown:
        results.append(CheckResult(name="Known keys", passed=False, message=f"Unknown top-level keys: {unknown}"))
    else:
        results.append(CheckResult(name="Known keys", passed=True, message="OK"))

    planner = data.get("planner", {})
    if isinstance(planner, dict):
        valid_modes = {"heuristic", "static", "openai-compatible", "function-call", "anthropic", "gemini", "openai", "openrouter", "ollama"}
        mode = planner.get("mode")
        if mode and mode not in valid_modes:
            results.append(CheckResult(name="Planner mode", passed=False, message=f"Unknown mode: {mode}. Valid: {valid_modes}"))
        elif mode:
            results.append(CheckResult(name="Planner mode", passed=True, message=mode))

        api_key_env = planner.get("apiKeyEnv")
        if api_key_env and not os.getenv(api_key_env):
            results.append(CheckResult(name="API key env", passed=False, message=f"Environment variable '{api_key_env}' is not set"))
        elif api_key_env:
            results.append(CheckResult(name="API key env", passed=True, message=f"{api_key_env} is set"))

    runtime = data.get("runtime", {})
    if isinstance(runtime, dict):
        valid_routers = {"mock", "public-market-data", "paper-trading", "sim-wallet", "ows-wallet", "scaffold-live"}
        router = runtime.get("cryptoRouter")
        if router and router not in valid_routers:
            results.append(CheckResult(name="Crypto router", passed=False, message=f"Unknown router: {router}"))
        elif router:
            results.append(CheckResult(name="Crypto router", passed=True, message=router))

    return results


def generate_default_config(
    *,
    planner_mode: str = "heuristic",
    planner_model: str | None = None,
    api_key_env: str | None = None,
) -> dict[str, Any]:
    """Generate a default aether-forge.json config."""
    config: dict[str, Any] = {"planner": {"mode": planner_mode}}
    if planner_model:
        config["planner"]["model"] = planner_model
    if api_key_env:
        config["planner"]["apiKeyEnv"] = api_key_env
    config["runtime"] = {"cryptoRouter": "mock"}
    return config

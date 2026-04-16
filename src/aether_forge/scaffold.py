"""Helpers for working with generated scaffold projects."""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
from types import ModuleType
from typing import Any

from .config import load_config_file
from .crypto import AuthenticatedPaperTradingCryptoExecutionRouter, LiveExchangeAdapter


def inspect_scaffold_live_exchange_status(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    config = _load_scaffold_config(root)
    live_config = config.get("adapters", {}).get("liveExchange", {}) if isinstance(config.get("adapters"), dict) else {}

    if not live_config:
        return {
            "status": "missing-config",
            "projectRoot": str(root),
            "message": "No liveExchange adapter configuration was found in aether-forge.json.",
        }

    enabled = bool(live_config.get("enabled", False))
    module_path = root / str(live_config.get("modulePath", "src/runtime/live_exchange.py"))
    builder_name = str(live_config.get("builder", "build_live_exchange_adapter"))

    if not enabled:
        return {
            "status": "disabled",
            "projectRoot": str(root),
            "modulePath": str(module_path),
            "builder": builder_name,
            "message": "Live exchange adapter is disabled in scaffold config.",
        }

    if not module_path.exists():
        return {
            "status": "missing-module",
            "projectRoot": str(root),
            "modulePath": str(module_path),
            "builder": builder_name,
            "message": "Configured live exchange adapter module path does not exist.",
        }

    module = _load_module_from_path(module_path, module_name="generated_live_exchange_status")
    build_fn = getattr(module, builder_name, None)
    if not callable(build_fn):
        return {
            "status": "missing-builder",
            "projectRoot": str(root),
            "modulePath": str(module_path),
            "builder": builder_name,
            "message": f"Configured live exchange builder {builder_name} was not found.",
        }

    adapter = build_fn(root)
    if adapter is None:
        return {
            "status": "builder-returned-none",
            "projectRoot": str(root),
            "modulePath": str(module_path),
            "builder": builder_name,
            "message": "Live exchange adapter builder returned None while config is enabled.",
        }

    if not _looks_like_live_exchange_adapter(adapter):
        return {
            "status": "invalid-adapter",
            "projectRoot": str(root),
            "modulePath": str(module_path),
            "builder": builder_name,
            "message": "Live exchange adapter object does not implement the required protocol.",
        }

    return {
        "status": "ready",
        "projectRoot": str(root),
        "modulePath": str(module_path),
        "builder": builder_name,
        "adapterClass": adapter.__class__.__name__,
        "message": "Live exchange adapter is configured and ready.",
    }


def sync_scaffold_policy_bundle(project_root: str | Path) -> dict[str, Any]:
    root = Path(project_root).resolve()
    module = _load_module_from_path(root / "src" / "policies" / "policy_bundle.py", module_name="generated_policy_bundle")
    sync_fn = getattr(module, "sync_policy_bundle", None)
    if not callable(sync_fn):
        raise ValueError("Generated policy module does not expose sync_policy_bundle(project_root)")
    result = sync_fn(root)
    if not isinstance(result, dict):
        raise ValueError("sync_policy_bundle(project_root) must return the updated policy bundle dict")
    return result


def load_scaffold_live_exchange_adapter(project_root: str | Path) -> LiveExchangeAdapter | None:
    root = Path(project_root).resolve()
    config = _load_scaffold_config(root)
    live_config = config.get("adapters", {}).get("liveExchange", {}) if isinstance(config.get("adapters"), dict) else {}

    if not live_config:
        return None

    if not bool(live_config.get("enabled", False)):
        return None

    module_path = root / str(live_config.get("modulePath", "src/runtime/live_exchange.py"))
    builder_name = str(live_config.get("builder", "build_live_exchange_adapter"))
    module = _load_module_from_path(module_path, module_name="generated_live_exchange")
    build_fn = getattr(module, builder_name, None)
    if not callable(build_fn):
        raise ValueError(f"Generated live exchange module does not expose {builder_name}(project_root)")
    adapter = build_fn(root)
    if adapter is not None and not _looks_like_live_exchange_adapter(adapter):
        raise ValueError("Generated live exchange module returned an object that does not implement the live exchange adapter protocol")
    return adapter


def build_scaffold_live_exchange_router(project_root: str | Path) -> AuthenticatedPaperTradingCryptoExecutionRouter:
    adapter = load_scaffold_live_exchange_adapter(project_root)
    return AuthenticatedPaperTradingCryptoExecutionRouter(live_exchange_adapter=adapter)


def _load_module_from_path(module_path: Path, *, module_name: str) -> ModuleType:
    if not module_path.exists():
        raise ValueError(f"Generated scaffold module not found: {module_path}")

    spec = spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise ValueError(f"Unable to load generated scaffold module: {module_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_scaffold_config(project_root: Path) -> dict[str, Any]:
    config_path = project_root / "aether-forge.json"
    if not config_path.exists():
        return {}
    return load_config_file(config_path)


def _looks_like_live_exchange_adapter(adapter: object) -> bool:
    return all(hasattr(adapter, name) for name in ("place_order", "cancel_order", "get_account_snapshot"))

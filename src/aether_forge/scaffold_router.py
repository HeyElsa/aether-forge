"""Scaffold strategy router loader for Aether Forge.

The framework provides a generic configuration dataclass and a factory
that loads the generated scaffold's own ExecutionRouter implementation.
No provider-specific logic lives here — that's the agent's job.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class StrategyConfig:
    """Generic configuration for agent strategy routers.

    The scaffold's ``src/strategy/router.py`` receives this config
    and decides how to use it based on the agent's capabilities.
    """

    mode: str = "simulated"  # simulated | paper | live
    initial_balance_usd: float = 10_000.0
    price_data: dict[str, float] = field(default_factory=dict)
    chain: str = "base"  # Default chain for x402/data-layer calls
    # MCP servers the agent should connect to at runtime. Each entry mirrors
    # the ``mcp_servers:`` block in ``aether-forge.json``:
    #   {"hermes": {"command": "hermes", "args": ["mcp", "serve"]}, ...}
    mcp_servers: dict[str, dict[str, Any]] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


def load_scaffold_router(project_root: str | Path, config: StrategyConfig | None = None):
    """Load the execution router from a generated scaffold project.

    Looks for ``src/strategy/router.py`` with a ``build_router(config)``
    function. Falls back to the framework's mock router if not found.
    """
    root = Path(project_root).resolve()
    config = config or StrategyConfig()

    router_path = root / "src" / "strategy" / "router.py"
    if router_path.exists():
        if str(root) not in sys.path:
            sys.path.insert(0, str(root))
        try:
            spec = importlib.util.spec_from_file_location("src.strategy.router", router_path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "build_router"):
                    logger.info("Loaded strategy router from %s", router_path)
                    return mod.build_router(config)
        except Exception as error:
            logger.warning("Failed to load scaffold strategy router: %s", error)

    logger.info("No scaffold router found at %s, using framework mock", router_path)
    from .crypto import MockCryptoExecutionRouter
    return MockCryptoExecutionRouter()

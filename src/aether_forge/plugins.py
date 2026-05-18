"""Plugin discovery via ``importlib.metadata`` entry points.

Third parties publish extensions to Aether Forge by declaring entry points in
their ``pyproject.toml``::

    [project.entry-points."aether_forge.planners"]
    grok = "my_pkg:build_grok_planner"

    [project.entry-points."aether_forge.execution_routers"]
    custom = "my_pkg:build_custom_router"

    [project.entry-points."aether_forge.data_sources"]
    private-prices = "my_pkg:PrivatePricesSource"

    [project.entry-points."aether_forge.skill_registries"]
    my-registry = "my_pkg:RegistryUrl"

The framework loads them lazily on first use. A plugin that fails to import is
logged and skipped — it must never crash the framework. Each lookup is cached.

Entry-point group names are exposed as constants (``GROUP_*``) so internal
callers and tests can reference them in one place.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from functools import cache
from importlib.metadata import entry_points
from typing import Any

logger = logging.getLogger(__name__)

GROUP_PLANNERS = "aether_forge.planners"
GROUP_EXECUTION_ROUTERS = "aether_forge.execution_routers"
GROUP_DATA_SOURCES = "aether_forge.data_sources"
GROUP_SKILL_REGISTRIES = "aether_forge.skill_registries"
# v0.22.0+ (FP-4) — entry-point group for downstream packages that register
# MemoryRecord / artifact transforms with ``migrations.TransformRegistry``.
# A plugin entry point in this group MUST resolve to a callable taking a
# single ``TransformRegistry`` argument and calling ``.register(...)`` on it.
GROUP_MIGRATIONS = "aether_forge.migrations"

ALL_GROUPS = (
    GROUP_PLANNERS,
    GROUP_EXECUTION_ROUTERS,
    GROUP_DATA_SOURCES,
    GROUP_SKILL_REGISTRIES,
    GROUP_MIGRATIONS,
)


@cache
def _discover_group(group: str) -> tuple[tuple[str, Any], ...]:
    """Resolve every entry point in ``group`` to ``(name, target)`` pairs.

    Failures are logged and skipped; the framework never crashes because of a
    third-party plugin.
    """
    discovered: list[tuple[str, Any]] = []
    try:
        eps = entry_points(group=group)
    except Exception as exc:  # importlib.metadata raised — extremely rare
        logger.warning("plugin discovery for group %s failed: %s", group, exc)
        return ()

    for ep in eps:
        try:
            target = ep.load()
        except Exception as exc:
            logger.warning("plugin %r in group %s failed to load: %s", ep.name, group, exc)
            continue
        discovered.append((ep.name, target))
    return tuple(discovered)


def iter_entry_points(group: str) -> Iterator[tuple[str, Any]]:
    """Yield ``(name, loaded_target)`` pairs for every plugin in ``group``."""
    yield from _discover_group(group)


def find_entry_point(group: str, name: str) -> Any | None:
    """Return the loaded target for ``name`` in ``group`` or ``None``."""
    for ep_name, target in iter_entry_points(group):
        if ep_name == name:
            return target
    return None


def reset_cache() -> None:
    """Clear the discovery cache. Tests use this to install stub entry points."""
    _discover_group.cache_clear()

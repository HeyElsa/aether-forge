"""Tests for the entry-point plugin discovery layer."""

from __future__ import annotations

import importlib.metadata as md
from typing import Any

import pytest

from aether_forge import plugins
from aether_forge.config import PlannerSettings, build_planner_factory
from aether_forge.skills import get_registries


def _stub_entry_point(name: str, group: str, target: Any) -> md.EntryPoint:
    """Build an EntryPoint whose load() returns ``target``."""

    class _StubEP(md.EntryPoint):
        def load(self) -> Any:  # type: ignore[override]
            return target

    # EntryPoint is a NamedTuple-like with three slots (name, value, group).
    return _StubEP(name=name, value=f"stub:{name}", group=group)


@pytest.fixture(autouse=True)
def _clear_plugin_cache():
    plugins.reset_cache()
    yield
    plugins.reset_cache()


def _patch_entry_points(monkeypatch: pytest.MonkeyPatch, eps: list[md.EntryPoint]) -> None:
    def _fake(*, group: str | None = None, **_: Any) -> Any:
        if group is None:
            return md.EntryPoints(eps)
        return md.EntryPoints([ep for ep in eps if ep.group == group])

    monkeypatch.setattr(plugins, "entry_points", _fake)


def test_planner_entry_point_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """An unknown planner mode resolves through aether_forge.planners plugins."""

    sentinel_planner = object()

    def factory():
        return sentinel_planner

    _patch_entry_points(
        monkeypatch,
        [_stub_entry_point("custom-mode", plugins.GROUP_PLANNERS, factory)],
    )

    settings = PlannerSettings(
        mode="custom-mode",
        model=None,
        base_url=None,
        api_key=None,
        api_key_env=None,
        static_response_file=None,
    )

    built = build_planner_factory(settings)
    assert built() is sentinel_planner


def test_unknown_planner_mode_with_no_plugin_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_entry_points(monkeypatch, [])
    settings = PlannerSettings(
        mode="does-not-exist",
        model=None,
        base_url=None,
        api_key=None,
        api_key_env=None,
        static_response_file=None,
    )
    with pytest.raises(ValueError, match="Unsupported planner mode"):
        build_planner_factory(settings)


def test_skill_registries_merge(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_entry_points(
        monkeypatch,
        [_stub_entry_point("private", plugins.GROUP_SKILL_REGISTRIES, "https://internal.example.com")],
    )
    merged = get_registries()
    assert merged["private"] == "https://internal.example.com"
    # Built-in registries still present
    assert "skills.sh" in merged
    assert "elsa" in merged


def test_failing_plugin_is_skipped(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """A plugin whose load() raises is logged and skipped, not propagated."""

    class _ExplodingEP(md.EntryPoint):
        def load(self):  # type: ignore[override]
            raise RuntimeError("plugin import failed")

    bad = _ExplodingEP(name="broken", value="x:y", group=plugins.GROUP_PLANNERS)

    def good_target() -> object:
        return object()

    good = _stub_entry_point("works", plugins.GROUP_PLANNERS, good_target)

    _patch_entry_points(monkeypatch, [bad, good])

    found = dict(plugins.iter_entry_points(plugins.GROUP_PLANNERS))
    assert "broken" not in found
    assert "works" in found
    assert any("broken" in record.message for record in caplog.records)


def test_iter_entry_points_caches(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}

    def _counting(*, group: str | None = None, **_: Any) -> Any:
        calls["n"] += 1
        return md.EntryPoints([])

    monkeypatch.setattr(plugins, "entry_points", _counting)
    list(plugins.iter_entry_points(plugins.GROUP_PLANNERS))
    list(plugins.iter_entry_points(plugins.GROUP_PLANNERS))
    list(plugins.iter_entry_points(plugins.GROUP_PLANNERS))
    assert calls["n"] == 1, "discovery should be cached after first call"

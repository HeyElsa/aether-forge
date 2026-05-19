"""Public API boundary tests."""

from __future__ import annotations

import inspect

import aether_forge

EXTENSION_PROTOCOLS = (
    "Planner",
    "ExecutionRouter",
    "PlanningModel",
    "MemoryStore",
    "DataSource",
)


def test_all_top_level_exports_have_stability_labels() -> None:
    exported = set(aether_forge.__all__)
    assert set(aether_forge.API_STABILITY) == exported
    assert set(aether_forge.API_STABILITY.values()) <= {"stable", "experimental", "internal"}
    for name in exported:
        assert hasattr(aether_forge, name), f"missing top-level export: {name}"


def test_extension_protocols_are_stable_top_level_exports() -> None:
    for name in EXTENSION_PROTOCOLS:
        assert name in aether_forge.__all__
        assert aether_forge.API_STABILITY[name] == "stable"
        assert getattr(aether_forge, name) is not None


def test_extension_contract_docstrings_are_complete() -> None:
    for name in EXTENSION_PROTOCOLS:
        doc = inspect.getdoc(getattr(aether_forge, name)) or ""
        assert "Canonical signature" in doc, name
        assert "Minimum viable implementation" in doc, name
        assert "Reference implementation" in doc, name


def test_generation_request_object_is_public_and_stable() -> None:
    assert "FastGenerateRequest" in aether_forge.__all__
    assert aether_forge.API_STABILITY["FastGenerateRequest"] == "stable"

from __future__ import annotations

import pytest

from aether_forge import Forge


def test_forge_facade_happy_path(tmp_path) -> None:
    project = Forge.generate_fast(
        name="Research Brief Agent",
        idea="Summarize a webpage and save a short note.",
        output=tmp_path / "agent",
        planner="heuristic",
    )

    assert project.generated_artifacts is not None
    assert project.validate().ok is True

    summary, _sessions = project.eval_pack()
    assert summary.meets_expectations is True

    ticks = project.run(
        environment="sandbox",
        max_ticks=1,
        auto_approve=True,
        persist_memory=False,
        persist_replays=False,
    )
    assert len(ticks) == 1
    assert ticks[0].session_status == "complete"

    reopened = Forge.open(project.directory)
    assert reopened.validate().ok is True


def test_forge_project_run_requires_bounded_tick_count(tmp_path) -> None:
    project = Forge.generate_fast(
        name="Research Brief Agent",
        idea="Summarize a webpage and save a short note.",
        output=tmp_path / "agent",
        planner="heuristic",
    )

    with pytest.raises(ValueError, match="max_ticks >= 1"):
        project.run(max_ticks=0)

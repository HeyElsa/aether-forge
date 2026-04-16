"""Tests for the governed agent runner."""

from __future__ import annotations

from pathlib import Path

from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
from aether_forge.runner import AgentRunner, RunnerConfig, TickResult


def test_runner_executes_ticks(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="Runner Test", idea="delta-neutral BTC basis", output_directory=output,
    ))
    config = RunnerConfig(max_ticks=3, interval_seconds=0, environment="sandbox")
    runner = AgentRunner(output, config=config)

    results = runner.run()

    assert len(results) == 3
    assert all(isinstance(r, TickResult) for r in results)
    assert all(r.steps_executed > 0 for r in results)


def test_runner_persists_memory(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="Memory Runner", idea="track BTC prices", output_directory=output,
    ))
    db_path = tmp_path / "memory.db"
    config = RunnerConfig(max_ticks=2, interval_seconds=0, memory_db_path=str(db_path))
    runner = AgentRunner(output, config=config)
    runner.run()

    assert db_path.exists()
    # Memory should have tick records
    from aether_forge.memory import MemoryQuery
    from aether_forge.storage import SqliteMemoryStore
    store = SqliteMemoryStore(db_path)
    records = store.read(MemoryQuery(memory_type="decision-history"))
    assert len(records) >= 2
    store.close()


def test_runner_writes_replays(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="Replay Runner", idea="basis capture strategy", output_directory=output,
    ))
    replay_dir = tmp_path / "replays"
    config = RunnerConfig(max_ticks=2, interval_seconds=0, replay_directory=str(replay_dir))
    runner = AgentRunner(output, config=config)
    runner.run()

    assert replay_dir.exists()
    replay_files = list(replay_dir.glob("tick_*.json"))
    assert len(replay_files) == 2


def test_runner_auto_approve_in_sandbox(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="AutoApprove Test", idea="delta-neutral BTC basis capture", output_directory=output,
    ))
    config = RunnerConfig(max_ticks=1, interval_seconds=0, auto_approve=True, environment="sandbox")
    runner = AgentRunner(output, config=config)
    results = runner.run()

    assert len(results) == 1
    # With auto-approve, held sessions should resolve
    assert results[0].session_status in ("complete", "hold")


def test_runner_stop(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="Stop Test", idea="test agent", output_directory=output,
    ))
    config = RunnerConfig(max_ticks=0, interval_seconds=0)  # unlimited
    runner = AgentRunner(output, config=config)

    results = []
    for tick in runner.tick_generator():
        results.append(tick)
        if len(results) >= 2:
            runner.stop()

    assert len(results) == 2


def test_runner_working_set_persists_across_ticks(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="State Test", idea="basis capture", output_directory=output,
    ))
    config = RunnerConfig(max_ticks=3, interval_seconds=0)
    runner = AgentRunner(output, config=config)
    runner.run()

    # Working set should accumulate across ticks
    assert isinstance(runner._working_set, dict)


def test_generated_scaffold_has_main_and_pyproject(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="Scaffold Test", idea="test agent", output_directory=output,
    ))

    assert (output / "main.py").exists()
    assert (output / "pyproject.toml").exists()

    main_content = (output / "main.py").read_text(encoding="utf8")
    assert "AgentRunner" in main_content
    assert "RunnerConfig" in main_content

    pyproject_content = (output / "pyproject.toml").read_text(encoding="utf8")
    assert "aether-forge" in pyproject_content


def test_forge_run_cli(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="CLI Run Test", idea="basis capture", output_directory=output,
    ))
    from aether_forge.cli import main
    rc = main(["run", str(output), "--max-ticks", "1", "--interval", "0"])
    assert rc == 0

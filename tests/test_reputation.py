"""Tests for per-run reputation snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
from aether_forge.reputation import (
    RECORD_FILENAME,
    DefaultReputationScorer,
    ReputationInputs,
    build_reputation_record,
    collect_inputs_from_run,
)
from aether_forge.runner import AgentRunner, RunnerConfig


@dataclass
class _FakeTick:
    session_status: str
    steps_executed: int = 2
    pending_approvals: list[str] = field(default_factory=list)


def test_scorer_perfect_run_scores_strong() -> None:
    inputs = ReputationInputs(
        ticks_total=10, ticks_complete=10, steps_executed_total=20,
    )
    snapshot = DefaultReputationScorer().score(inputs)

    assert snapshot.score == 100.0
    assert snapshot.tier == "strong"
    assert "trading" in snapshot.unobserved


def test_scorer_mixed_run_weights_components() -> None:
    # 8/10 ticks complete (80), 15 executed vs 5 pending (75) → mean 77.5
    inputs = ReputationInputs(
        ticks_total=10, ticks_complete=8, ticks_failed=2,
        steps_executed_total=15, approvals_pending_total=5,
    )
    snapshot = DefaultReputationScorer().score(inputs)

    assert snapshot.components["reliability"]["score"] == 80.0
    assert snapshot.components["follow_through"]["score"] == 75.0
    assert snapshot.score == 77.5
    assert snapshot.tier == "developing"


def test_scorer_no_observations_scores_zero_not_neutral() -> None:
    snapshot = DefaultReputationScorer().score(ReputationInputs())

    assert snapshot.score == 0.0
    assert snapshot.components == {}
    assert set(snapshot.unobserved) == {"reliability", "follow_through", "trading"}


def test_collect_inputs_reads_tick_history_and_portfolio() -> None:
    ticks = [
        _FakeTick("complete"),
        _FakeTick("complete", pending_approvals=["step-1"]),
        _FakeTick("failed", steps_executed=0),
    ]
    working_set = {"elsa-get-portfolio": {"cash_usd": 10_250.0}}

    inputs = collect_inputs_from_run(ticks, working_set, initial_balance_usd=10_000.0)

    assert inputs.ticks_total == 3
    assert inputs.ticks_complete == 2
    assert inputs.ticks_failed == 1
    assert inputs.steps_executed_total == 4
    assert inputs.approvals_pending_total == 1
    assert inputs.trading_observed
    assert inputs.realized_pnl_usd == 250.0


def test_collect_inputs_marks_trading_unobserved_without_portfolio() -> None:
    inputs = collect_inputs_from_run([_FakeTick("complete")], {}, initial_balance_usd=10_000.0)

    assert not inputs.trading_observed
    assert inputs.realized_pnl_usd is None


def test_record_envelope_carries_identity() -> None:
    snapshot = DefaultReputationScorer().score(
        ReputationInputs(ticks_total=1, ticks_complete=1, steps_executed_total=1)
    )
    record = build_reputation_record(
        snapshot, artifact_set_id="afs_x", agent_name="Agent X", environment="sandbox",
    )

    assert record["kind"] == "aether-forge/reputation-record"
    assert record["artifactSetId"] == "afs_x"
    assert record["snapshot"]["inputs"]["tradingObserved"] is False


def test_runner_writes_reputation_record(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="Reputation Runner", idea="track BTC prices", output_directory=output,
    ))
    config = RunnerConfig(max_ticks=3, interval_seconds=0)
    runner = AgentRunner(output, config=config)
    runner.run()

    record_path = output / RECORD_FILENAME
    assert record_path.exists()
    record = json.loads(record_path.read_text(encoding="utf8"))
    snapshot = record["snapshot"]
    assert snapshot["inputs"]["ticksTotal"] == 3
    assert 0.0 <= snapshot["score"] <= 100.0
    assert snapshot["tier"] in {"strong", "developing", "weak"}


def test_runner_respects_opt_out(tmp_path: Path) -> None:
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="No Reputation Runner", idea="track BTC prices", output_directory=output,
    ))
    config = RunnerConfig(max_ticks=1, interval_seconds=0, emit_reputation_record=False)
    runner = AgentRunner(output, config=config)
    runner.run()

    assert not (output / RECORD_FILENAME).exists()

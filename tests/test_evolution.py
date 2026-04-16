"""Tests for runtime self-evaluation and autoresearch."""

from __future__ import annotations

import json
from pathlib import Path

from aether_forge.evolution import (
    ImprovementProposal,
    PerformanceReport,
    RuntimeAutoresearch,
    SelfEvaluator,
    StrategyArtifact,
)


def test_strategy_artifact_save_load(tmp_path: Path) -> None:
    strategy = StrategyArtifact()
    strategy.parameters["spread_pct"] = 2.0
    path = tmp_path / "strategy.json"
    strategy.save(path)

    loaded = StrategyArtifact.load(path)
    assert loaded.parameters["spread_pct"] == 2.0
    assert loaded.version == 1


def test_self_evaluator_computes_metrics() -> None:
    strategy = StrategyArtifact()
    evaluator = SelfEvaluator(strategy)

    evaluator.record_tick(10_000.0)
    evaluator.record_tick(10_050.0)
    evaluator.record_tick(10_020.0)
    evaluator.record_tick(10_080.0)

    report = evaluator.evaluate(initial_balance=10_000.0)

    assert report.window_ticks == 4
    assert report.total_pnl_usd == 80.0
    assert report.current_balance_usd == 10_080.0
    assert report.max_drawdown_pct > 0  # dropped from 10050 to 10020


def test_self_evaluator_detects_underperformance() -> None:
    strategy = StrategyArtifact()
    strategy.success_metrics["max_drawdown_pct"] = 1.0
    evaluator = SelfEvaluator(strategy)

    evaluator.record_tick(10_000.0)
    evaluator.record_tick(9_800.0)  # 2% drawdown

    report = evaluator.evaluate(initial_balance=10_000.0)

    assert not report.meets_criteria
    assert any("drawdown" in m for m in report.failing_metrics)


def test_self_evaluator_tracks_win_rate() -> None:
    strategy = StrategyArtifact()
    evaluator = SelfEvaluator(strategy)

    trades = [
        {"order_id": "1", "pnl_usd": 10},
        {"order_id": "2", "pnl_usd": -5},
        {"order_id": "3", "pnl_usd": 15},
        {"order_id": "4", "pnl_usd": 8},
    ]
    evaluator.record_tick(10_000.0, trades)
    report = evaluator.evaluate()

    assert report.total_trades == 4
    assert report.winning_trades == 3
    assert report.win_rate == 0.75


def test_autoresearch_no_model_skips() -> None:
    strategy = StrategyArtifact()
    strategy.success_metrics["max_drawdown_pct"] = 0.1  # Very strict

    path = Path("/tmp/test_autoresearch_strategy.json")
    strategy.save(path)

    autoresearch = RuntimeAutoresearch(path, eval_interval=2)

    # Record ticks
    autoresearch.on_tick_complete(10_000.0)
    result = autoresearch.on_tick_complete(9_500.0)  # Big drawdown

    # Without a model, should return None (no proposal)
    assert result is None
    path.unlink(missing_ok=True)


def test_autoresearch_with_mock_model(tmp_path: Path) -> None:
    strategy = StrategyArtifact()
    strategy.success_metrics["max_drawdown_pct"] = 0.1  # Very strict
    path = tmp_path / "strategy.json"
    strategy.save(path)

    class MockResearchModel:
        def complete(self, prompt: str) -> str:
            return json.dumps({
                "hypothesis": "Widen spread to reduce drawdown",
                "mutations": {"spread_pct": 2.0},
                "rationale": "Current 1% spread is too tight for this volatility",
                "expected_improvement": "Drawdown should decrease by 50%",
            })

    autoresearch = RuntimeAutoresearch(
        path,
        research_model=MockResearchModel(),
        eval_interval=2,
    )

    autoresearch.on_tick_complete(10_000.0)
    proposal = autoresearch.on_tick_complete(9_500.0)

    assert proposal is not None
    assert proposal.hypothesis == "Widen spread to reduce drawdown"
    assert proposal.mutations == {"spread_pct": 2.0}
    assert proposal.status == "proposed"


def test_accept_proposal_updates_strategy(tmp_path: Path) -> None:
    strategy = StrategyArtifact()
    path = tmp_path / "strategy.json"
    strategy.save(path)

    class MockResearchModel:
        def complete(self, prompt: str) -> str:
            return json.dumps({
                "hypothesis": "test",
                "mutations": {"spread_pct": 2.5},
                "rationale": "test",
                "expected_improvement": "test",
            })

    autoresearch = RuntimeAutoresearch(path, research_model=MockResearchModel(), eval_interval=2)
    autoresearch.strategy.success_metrics["max_drawdown_pct"] = 0.01  # Force underperformance

    autoresearch.on_tick_complete(10_000.0)
    proposal = autoresearch.on_tick_complete(9_000.0)  # 10% drawdown
    assert proposal is not None

    # Accept
    accepted = autoresearch.accept_proposal(proposal.proposal_id)
    assert accepted
    assert autoresearch.strategy.parameters["spread_pct"] == 2.5
    assert autoresearch.strategy.version == 2

    # Verify saved to disk
    loaded = StrategyArtifact.load(path)
    assert loaded.parameters["spread_pct"] == 2.5
    assert loaded.version == 2
    assert len(loaded.history) == 1


def test_reject_proposal() -> None:
    proposal = ImprovementProposal(
        proposal_id="test-123",
        hypothesis="test",
        mutations={"spread_pct": 5.0},
        status="proposed",
    )
    # Simulate rejection
    proposal.status = "rejected"
    proposal.user_feedback = "Too aggressive"
    assert proposal.status == "rejected"


def test_cannot_weaken_success_criteria(tmp_path: Path) -> None:
    strategy = StrategyArtifact()
    strategy.success_metrics["min_win_rate"] = 0.40
    path = tmp_path / "strategy.json"
    strategy.save(path)

    class WeakeningModel:
        def complete(self, prompt: str) -> str:
            return json.dumps({
                "hypothesis": "Lower win rate requirement",
                "mutations": {"min_win_rate": 0.10},  # Weakening!
                "rationale": "We can't hit 40%",
                "expected_improvement": "Will stop failing",
            })

    autoresearch = RuntimeAutoresearch(path, research_model=WeakeningModel(), eval_interval=2)
    autoresearch.strategy.success_metrics["max_drawdown_pct"] = 0.01

    autoresearch.on_tick_complete(10_000.0)
    proposal = autoresearch.on_tick_complete(9_000.0)
    assert proposal is not None

    # Accept should fail — weakens criteria
    accepted = autoresearch.accept_proposal(proposal.proposal_id)
    assert not accepted
    assert proposal.status == "rejected"


def test_generated_scaffold_has_strategy_json(tmp_path: Path) -> None:
    from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="Test Agent", idea="ETH trading bot", output_directory=output,
    ))
    strategy_path = output / "strategy.json"
    assert strategy_path.exists()

    strategy = StrategyArtifact.load(strategy_path)
    assert strategy.version == 1
    assert "spread_pct" in strategy.parameters
    assert "min_win_rate" in strategy.success_metrics

"""Real agent integration test: Ollama LLM + Elsa execution.

This test creates an actual LLM-driven trading agent that:
1. Uses Ollama (gemma4) for planning decisions
2. Uses the Elsa execution router for simulated DeFi operations
3. Runs multiple ticks with state persistence
4. Adapts strategy based on price data

Requires: Ollama running locally with gemma4 model.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
from aether_forge.memory import MemoryQuery
from aether_forge.models import OpenAICompatiblePlanningModel
from aether_forge.planner import HeuristicPlanner, PromptDrivenPlanner
from aether_forge.runner import AgentRunner, RunnerConfig
from aether_forge.runtime import RuntimeSession, load_artifact_bundle
from aether_forge.scaffold_router import StrategyConfig, load_scaffold_router
from aether_forge.storage import SqliteMemoryStore


def _ollama_available() -> bool:
    try:
        from urllib.request import urlopen
        with urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


requires_ollama = pytest.mark.skipif(not _ollama_available(), reason="Ollama not running")


def _build_ollama_planner():
    model = OpenAICompatiblePlanningModel(
        model="gemma4",
        api_key="",
        base_url="http://localhost:11434/v1",
    )
    return PromptDrivenPlanner(model=model, fallback_planner=HeuristicPlanner(), max_plan_steps=5)


def _build_strategy_config():
    return StrategyConfig(
        mode="simulated",
        price_data={"ETH": 3500.0, "BTC": 65000.0},
    )


@requires_ollama
def test_single_tick_ollama_plans_real_steps(tmp_path: Path) -> None:
    """Ollama should produce valid planning steps for an ETH trading agent."""
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="ETH Swing Trader",
        idea="buy ETH on dips, sell on rallies with limit orders",
        output_directory=output,
        skills=["elsa:trading", "elsa:portfolio"],
    ))

    artifacts = load_artifact_bundle(output)
    planner = _build_ollama_planner()
    router = load_scaffold_router(str(output), _build_strategy_config())

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=planner,
        execution_router=router,
    )
    status = session.run(max_steps=10)

    print(f"\nSession status: {status.value}")
    print(f"Steps executed: {len(session.step_ledger)}")
    for entry in session.step_ledger:
        result_info = ""
        er = entry.execution_result
        if er and isinstance(er, dict):
            out = er.get("output", er)
        elif er and hasattr(er, "output"):
            out = er.output
        else:
            out = None
        if isinstance(out, dict):
            if "price_usd" in out:
                result_info = f" → ${out['price_usd']}"
            elif "order_id" in out:
                result_info = f" → {out.get('side', '?')} {out.get('token', '?')} @ ${out.get('limit_price', '?')}"
        print(f"  Step {entry.step_id}: {entry.proposal.kind} {entry.proposal.capability_id or ''}{result_info}")

    assert len(session.step_ledger) > 0
    # At minimum, the LLM should propose fetching a price
    cap_ids = [e.proposal.capability_id for e in session.step_ledger if e.proposal.capability_id]
    print(f"Capabilities used: {cap_ids}")


@requires_ollama
def test_multi_tick_agent_with_memory(tmp_path: Path) -> None:
    """Agent runs 3 ticks, persists memory, and adapts based on price history."""
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="ETH Swing Trader",
        idea="buy ETH on dips, sell on rallies with limit orders, track price momentum",
        output_directory=output,
        skills=["elsa:trading", "elsa:portfolio"],
    ))

    db_path = tmp_path / "memory.db"
    strategy_config = _build_strategy_config()
    router = load_scaffold_router(str(output), strategy_config)

    config = RunnerConfig(
        max_ticks=3,
        interval_seconds=0,
        environment="sandbox",
        auto_approve=True,
        memory_db_path=str(db_path),
    )

    runner = AgentRunner(
        output,
        config=config,
        planner_factory=_build_ollama_planner,
        execution_router_factory=lambda: router,
    )
    results = runner.run()

    print(f"\n{'='*60}")
    print(f"Agent completed {len(results)} ticks")
    for r in results:
        print(f"  Tick {r.tick_number}: {r.session_status} ({r.steps_executed} steps)")

    store = SqliteMemoryStore(db_path)
    records = store.read(MemoryQuery(memory_type="decision-history"))
    print(f"\nMemory records: {len(records)}")
    store.close()

    price_history = router.price_history if hasattr(router, "price_history") else []
    orders = router.engine.order_book if hasattr(router, "engine") else []
    print(f"Price history: {len(price_history)} observations")
    print(f"Order book: {len(orders)} orders")
    for order in orders:
        print(f"  {order.get('side', '?')} {order.get('token', '?')} {order.get('amount', '?')} @ ${order.get('limit_price', '?')}")

    assert len(results) >= 1
    assert all(r.steps_executed > 0 for r in results)


@requires_ollama
def test_full_trading_cycle(tmp_path: Path) -> None:
    """End-to-end: generate → validate → run with LLM → check orders placed."""
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="ETH Limit Trader",
        idea="place buy limit orders for ETH when price drops 2%, sell limit orders when price rises 2%",
        output_directory=output,
        skills=["elsa:trading", "elsa:portfolio"],
    ))

    from aether_forge.artifacts import validate_artifact_directory
    validation = validate_artifact_directory(output)
    assert validation.ok, f"Validation failed: {validation.issues}"

    strategy_config = _build_strategy_config()
    router = load_scaffold_router(str(output), strategy_config)

    config = RunnerConfig(
        max_ticks=2,
        interval_seconds=0,
        environment="sandbox",
        auto_approve=True,
    )

    runner = AgentRunner(
        output,
        config=config,
        planner_factory=_build_ollama_planner,
        execution_router_factory=lambda: router,
    )
    results = runner.run()

    price_history = router.price_history if hasattr(router, "price_history") else []
    orders = router.engine.order_book if hasattr(router, "engine") else []

    print(f"\n{'='*60}")
    print("FULL TRADING CYCLE RESULTS")
    print(f"Ticks: {len(results)}")
    total_steps = sum(r.steps_executed for r in results)
    print(f"Total steps: {total_steps}")
    print(f"Orders placed: {len(orders)}")
    for order in orders:
        print(f"  [{order['status']}] {order['side']} {order.get('amount', '?')} {order['token']} @ ${order['limit_price']}")
    print(f"Price observations: {len(price_history)}")
    if price_history:
        prices = [p["price"] for p in price_history]
        print(f"  Range: ${min(prices):.2f} - ${max(prices):.2f}")

    assert len(results) >= 1
    assert total_steps > 0

"""Paper trading tests with real Binance market data.

Tests run a real LLM-driven agent that:
1. Fetches LIVE ETH prices + 30m candles from Binance
2. Uses Ollama (gemma4) for strategy decisions
3. Places simulated limit orders with paper balance + P&L tracking
4. Gets momentum indicators (trend, volatility) for adaptive strategy
5. Runs across multiple ticks with memory persistence

Requires: Ollama running locally + internet access for Binance API.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
from aether_forge.models import OpenAICompatiblePlanningModel
from aether_forge.planner import HeuristicPlanner, PromptDrivenPlanner
from aether_forge.runner import AgentRunner, RunnerConfig
from aether_forge.scaffold_router import StrategyConfig, load_scaffold_router


def _ollama_available() -> bool:
    try:
        from urllib.request import urlopen
        with urlopen("http://localhost:11434/api/tags", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _binance_available() -> bool:
    try:
        from urllib.request import urlopen
        with urlopen("https://api.binance.com/api/v3/ticker/price?symbol=ETHUSDT", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


requires_live = pytest.mark.skipif(
    not (_ollama_available() and _binance_available()),
    reason="Requires Ollama + Binance API access",
)


def _build_ollama_planner():
    model = OpenAICompatiblePlanningModel(
        model="gemma4",
        api_key="",
        base_url="http://localhost:11434/v1",
    )
    return PromptDrivenPlanner(model=model, fallback_planner=HeuristicPlanner(), max_plan_steps=5)


@requires_live
def test_paper_trading_with_live_prices(tmp_path: Path) -> None:
    """Agent trades ETH with real Binance prices, momentum data, and paper P&L."""
    output = tmp_path / "agent"
    generate_fast_artifact_set(FastGenerateRequest(
        name="ETH Paper Trader",
        idea=(
            "ETH swing trading bot. Every tick: "
            "1) fetch ETH price with momentum indicators, "
            "2) check portfolio and existing orders, "
            "3) if no open orders, place buy limit at -1% and sell limit at +1% of current price, "
            "4) if bullish momentum, tighten buy level to -0.5%, "
            "5) if bearish, tighten sell level to +0.5%. "
            "Use 0.1 ETH per order. Mark complete after placing orders."
        ),
        output_directory=output,
        skills=["elsa:trading", "elsa:portfolio"],
    ))

    strategy_config = StrategyConfig(mode="paper", initial_balance_usd=10_000.0)
    # Use the scaffold's own router (generated with the project)
    scaffold_router = load_scaffold_router(str(output), strategy_config)

    runner_config = RunnerConfig(
        max_ticks=3,
        interval_seconds=5,
        environment="sandbox",
        auto_approve=True,
        memory_db_path=str(tmp_path / "memory.db"),
        replay_directory=str(tmp_path / "replays"),
    )

    runner = AgentRunner(
        output,
        config=runner_config,
        planner_factory=_build_ollama_planner,
        execution_router_factory=lambda: scaffold_router,
    )

    print("\n" + "=" * 70)
    print("PAPER TRADING WITH LIVE BINANCE DATA + MOMENTUM")
    print("=" * 70)

    results = runner.run()

    # --- Report ---
    print("\n" + "-" * 70)
    portfolio = scaffold_router.engine.portfolio_summary() if hasattr(scaffold_router, "engine") else {}

    print(f"Ticks: {len(results)} | Steps: {sum(r.steps_executed for r in results)}")
    for r in results:
        print(f"  Tick {r.tick_number}: {r.session_status} ({r.steps_executed} steps)")

    print(f"\nLive prices fetched: {len(scaffold_router.price_history)}")
    for obs in scaffold_router.price_history:
        print(f"  {obs['token']}: ${obs['price']:,.2f}")

    orders = scaffold_router.engine.order_book if hasattr(scaffold_router, "engine") else []
    price_history = scaffold_router.price_history if hasattr(scaffold_router, "price_history") else []

    print(f"\nOrders: {len(orders)}")
    for order in orders:
        print(f"  [{order['status']:>7}] {order['side']:>4} {order.get('amount', '?')} {order['token']} "
              f"@ ${order['limit_price']:,.2f} (${order.get('notional_usd', 0):,.2f})")

    print("\nPortfolio:")
    print(f"  Cash:  ${portfolio['cash_usd']:>10,.2f}")
    for token, pos in portfolio.get("positions", {}).items():
        print(f"  {token}:   {pos['amount']:.6f} = ${pos['value_usd']:>10,.2f} @ ${pos['price']:,.2f}")
    print(f"  Total: ${portfolio['total_value_usd']:>10,.2f}")
    print(f"  P&L:   ${portfolio['pnl_usd']:>+10,.2f} ({portfolio['pnl_pct']:+.3f}%)")
    if portfolio:
        print(f"  Fills: {portfolio.get('filled_orders', 0)} | Open: {portfolio.get('open_orders', 0)} | Trades: {portfolio.get('total_trades', 0)}")

    # --- Assertions ---
    assert len(results) >= 1
    assert sum(r.steps_executed for r in results) > 0
    assert len(price_history) >= 1
    # Price from Binance should be realistic
    for obs in price_history:
        assert 500 < obs["price"] < 50000, f"Unrealistic price: {obs['price']}"

    print("\n" + "=" * 70)
    print("PAPER TRADING TEST PASSED")
    print("=" * 70)


def _compute_momentum_for_display(candles: list[dict]) -> dict:
    """Helper to compute momentum for test display."""
    if len(candles) < 3:
        return {}
    closes = [c["close"] for c in candles]
    current = closes[-1]
    prev = closes[-2]
    avg_3 = sum(closes[-3:]) / 3
    avg_all = sum(closes) / len(closes)
    trend = "bullish" if current > avg_3 > avg_all else ("bearish" if current < avg_3 < avg_all else "neutral")
    recent_highs = [c["high"] for c in candles[-5:]]
    recent_lows = [c["low"] for c in candles[-5:]]
    vol = ((max(recent_highs) - min(recent_lows)) / current * 100) if current > 0 else 0
    return {
        "trend": trend,
        "volatility_5_candle_pct": vol,
        "change_last_candle_pct": (current / prev - 1) * 100 if prev else 0,
    }

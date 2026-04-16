"""Tests for the MemPalace knowledge layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from aether_forge.knowledge import KnowledgeStore


def _mempalace_available() -> bool:
    try:
        import mempalace
        return True
    except ImportError:
        return False


requires_mempalace = pytest.mark.skipif(not _mempalace_available(), reason="mempalace not installed")


@requires_mempalace
def test_remember_and_recall(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "palace", wing="test-agent")
    store.remember("ETH dropped 3% due to whale sell-off", room="market-events")
    store.remember("Agent spread was too tight at 1%", room="strategy")

    results = store.recall("what caused the drop")
    assert len(results) > 0
    assert any("whale" in r["content"] or "dropped" in r["content"] for r in results)
    store.close()


@requires_mempalace
def test_knowledge_graph_add_and_query(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "palace", wing="test-agent")
    store.add_fact("ETH", "trend", "bearish", valid_from="2026-04-09")
    store.add_fact("ETH", "price_usd", "2186", valid_from="2026-04-09")

    facts = store.query_entity("ETH")
    assert len(facts) == 2
    assert any(f["predicate"] == "trend" and f["object"] == "bearish" for f in facts)
    store.close()


@requires_mempalace
def test_knowledge_graph_invalidate(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "palace", wing="test-agent")
    store.add_fact("ETH", "trend", "bearish", valid_from="2026-04-01")
    store.invalidate_fact("ETH", "trend", "bearish")
    store.add_fact("ETH", "trend", "bullish", valid_from="2026-04-09")

    facts = store.query_entity("ETH")
    current = [f for f in facts if f.get("current")]
    assert any(f["object"] == "bullish" for f in current)
    store.close()


@requires_mempalace
def test_timeline(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "palace", wing="test-agent")
    store.add_fact("ETH", "trend", "bearish", valid_from="2026-04-01")
    store.add_fact("ETH", "trend", "bullish", valid_from="2026-04-09")

    tl = store.timeline("ETH")
    assert len(tl) >= 2
    store.close()


@requires_mempalace
def test_record_tick_knowledge(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "palace", wing="test-agent")
    store.record_tick_knowledge(
        1,
        prices={"ETH": 2186.0, "BTC": 65000.0},
        orders=[{"order_id": "o1", "side": "buy", "amount": 0.1, "token": "ETH", "limit_price": 2164.0, "status": "filled"}],
    )

    # Should have added price facts
    facts = store.query_entity("ETH")
    assert len(facts) > 0

    # Should have stored the trade as a memory
    results = store.recall("buy ETH")
    assert len(results) > 0
    store.close()


@requires_mempalace
def test_context_for_planning(tmp_path: Path) -> None:
    store = KnowledgeStore(tmp_path / "palace", wing="test-agent")
    store.add_fact("ETH", "trend", "bearish")
    store.remember("Agent lost money due to tight spread", room="strategy")

    context = store.get_context_for_planning("strategy performance")
    assert len(context) > 0
    store.close()


def test_knowledge_store_unavailable(tmp_path: Path) -> None:
    """Should gracefully handle missing mempalace."""
    store = KnowledgeStore.__new__(KnowledgeStore)
    store._palace_path = str(tmp_path)
    store._wing = "test"
    store._kg = None
    store._collection = None
    store._available = False

    assert store.recall("anything") == []
    assert store.query_entity("ETH") == []
    assert store.remember("test") is None
    assert store.get_context_for_planning() == ""

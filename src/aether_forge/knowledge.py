"""Long-term knowledge layer using MemPalace.

Provides semantic search, temporal knowledge graph, and layered memory
for Aether Forge agents. Sits alongside SqliteMemoryStore:

- SqliteMemoryStore: operational data (tick state, balances, orders)
- KnowledgeStore: long-term knowledge (market patterns, strategy learnings,
  cross-session context, temporal facts)

Requires: pip install mempalace
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeStore:
    """Long-term knowledge layer backed by MemPalace.

    Uses ChromaDB for semantic search and SQLite for temporal knowledge graph.
    Each agent gets its own wing in the palace.

    Usage::

        store = KnowledgeStore(palace_path="./my-agent/knowledge")
        store.remember("ETH dropped 3% due to whale sell-off", room="market-events")
        store.add_fact("ETH", "trend", "bearish", valid_from="2026-04-09")
        results = store.recall("what caused the price drop")
        timeline = store.timeline("ETH")
    """

    def __init__(
        self,
        palace_path: str | Path,
        wing: str = "agent",
    ) -> None:
        self._palace_path = str(Path(palace_path).resolve())
        self._wing = wing
        self._kg = None
        self._collection = None
        self._available = False
        self._init()

    def _init(self) -> None:
        try:
            from mempalace.palace import get_collection
            from mempalace.knowledge_graph import KnowledgeGraph

            self._collection = get_collection(self._palace_path)
            kg_path = str(Path(self._palace_path) / "knowledge_graph.db")
            self._kg = KnowledgeGraph(kg_path)
            self._available = True
            logger.info("KnowledgeStore initialized: palace=%s wing=%s", self._palace_path, self._wing)
        except ImportError:
            logger.warning("MemPalace not installed — knowledge layer disabled. pip install mempalace")
        except Exception as error:
            logger.warning("KnowledgeStore init failed: %s", error)

    @property
    def available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    # Semantic memory (ChromaDB drawers)
    # ------------------------------------------------------------------

    def remember(
        self,
        content: str,
        *,
        room: str = "general",
        source: str = "agent",
        metadata: dict[str, Any] | None = None,
    ) -> str | None:
        """Store a memory in the palace. Returns the memory ID."""
        if not self._available:
            return None

        mem_id = f"mem_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{hash(content) % 10000:04d}"
        meta = {
            "wing": self._wing,
            "room": room,
            "source_file": source,
            "type": "drawer",
            "timestamp": datetime.now(UTC).isoformat(),
            **(metadata or {}),
        }

        try:
            self._collection.add(
                documents=[content],
                metadatas=[meta],
                ids=[mem_id],
            )
            logger.debug("Remembered: [%s/%s] %s", self._wing, room, content[:60])
            return mem_id
        except Exception as error:
            logger.warning("Failed to store memory: %s", error)
            return None

    def recall(
        self,
        query: str,
        *,
        room: str | None = None,
        n_results: int = 5,
    ) -> list[dict[str, Any]]:
        """Semantic search across memories. Returns relevant memories."""
        if not self._available:
            return []

        try:
            where_filter = {"wing": self._wing}
            if room:
                where_filter = {"$and": [{"wing": self._wing}, {"room": room}]}

            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=where_filter,
            )

            memories = []
            docs = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]

            for doc, meta, dist in zip(docs, metas, distances):
                memories.append({
                    "content": doc,
                    "room": meta.get("room", ""),
                    "source": meta.get("source_file", ""),
                    "timestamp": meta.get("timestamp", ""),
                    "relevance": round(1.0 - dist, 3) if dist else 0,
                })

            return memories
        except Exception as error:
            logger.warning("Recall failed: %s", error)
            return []

    # ------------------------------------------------------------------
    # Knowledge graph (temporal facts)
    # ------------------------------------------------------------------

    def add_fact(
        self,
        subject: str,
        predicate: str,
        obj: str,
        *,
        valid_from: str | None = None,
        confidence: float = 1.0,
    ) -> None:
        """Add a temporal fact to the knowledge graph."""
        if not self._available or not self._kg:
            return

        valid_from = valid_from or datetime.now(UTC).strftime("%Y-%m-%d")
        try:
            self._kg.add_triple(subject, predicate, obj, valid_from=valid_from, confidence=confidence)
            logger.debug("Fact added: %s %s %s (from %s)", subject, predicate, obj, valid_from)
        except Exception as error:
            logger.warning("Failed to add fact: %s", error)

    def invalidate_fact(self, subject: str, predicate: str, obj: str) -> None:
        """Mark a fact as no longer current."""
        if not self._available or not self._kg:
            return
        try:
            ended = datetime.now(UTC).strftime("%Y-%m-%d")
            self._kg.invalidate(subject, predicate, obj, ended=ended)
            logger.debug("Fact invalidated: %s %s %s", subject, predicate, obj)
        except Exception as error:
            logger.warning("Failed to invalidate fact: %s", error)

    def query_entity(self, entity: str) -> list[dict[str, Any]]:
        """Get all current facts about an entity."""
        if not self._available or not self._kg:
            return []
        try:
            return self._kg.query_entity(entity)
        except Exception as error:
            logger.warning("Entity query failed: %s", error)
            return []

    def timeline(self, entity: str) -> list[dict[str, Any]]:
        """Get chronological history of an entity."""
        if not self._available or not self._kg:
            return []
        try:
            return self._kg.timeline(entity)
        except Exception as error:
            logger.warning("Timeline query failed: %s", error)
            return []

    # ------------------------------------------------------------------
    # Agent integration helpers
    # ------------------------------------------------------------------

    def record_tick_knowledge(
        self,
        tick_num: int,
        *,
        prices: dict[str, float] | None = None,
        orders: list[dict[str, Any]] | None = None,
        momentum: dict[str, Any] | None = None,
        performance: dict[str, Any] | None = None,
    ) -> None:
        """Record knowledge from a completed tick."""
        timestamp = datetime.now(UTC).isoformat()

        # Price observations → knowledge graph
        if prices:
            for token, price in prices.items():
                self.add_fact(token, "price_usd", str(round(price, 2)))

        # Momentum → knowledge graph
        if momentum:
            for token, data in momentum.items() if isinstance(momentum, dict) and all(isinstance(v, dict) for v in momentum.values()) else []:
                trend = data.get("trend", "unknown")
                self.add_fact(token, "trend", trend)

        # Orders → semantic memory
        if orders:
            for order in orders:
                if order.get("status") == "filled":
                    content = (
                        f"Tick {tick_num}: {order.get('side', '?')} {order.get('amount', '?')} "
                        f"{order.get('token', '?')} @ ${order.get('limit_price', '?')}"
                    )
                    self.remember(content, room="trades", source=f"tick_{tick_num}")

        # Performance → semantic memory
        if performance:
            if performance.get("failing_metrics"):
                content = f"Tick {tick_num}: Underperforming — {', '.join(performance['failing_metrics'])}"
                self.remember(content, room="performance", source=f"tick_{tick_num}")

    def get_context_for_planning(self, query: str = "current market conditions and strategy performance") -> str:
        """Build a knowledge context string for the planning prompt."""
        parts: list[str] = []

        # Semantic recall
        memories = self.recall(query, n_results=3)
        if memories:
            parts.append("Recent knowledge:")
            for mem in memories:
                parts.append(f"  [{mem['room']}] {mem['content'][:120]}")

        # Current facts about traded tokens
        for token in ["ETH", "BTC", "SOL"]:
            facts = self.query_entity(token)
            current_facts = [f for f in facts if f.get("current")]
            if current_facts:
                fact_str = ", ".join(f"{f['predicate']}={f['object']}" for f in current_facts[:3])
                parts.append(f"  {token}: {fact_str}")

        return "\n".join(parts) if parts else ""

    def close(self) -> None:
        """Clean up resources."""
        if self._kg:
            try:
                self._kg.close()
            except Exception:
                pass

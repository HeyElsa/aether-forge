"""Local agent registry for Aether Forge.

Tracks every agent created through the framework in a SQLite database at
``~/.aether-forge/agents.db``. Provides the foundation for agent discovery,
inter-agent communication (A2A), and on-chain registration (ERC-8004).

Usage::

    from aether_forge.agent_registry import AgentRegistry

    reg = AgentRegistry()  # uses default path
    reg.register(
        agent_id="aset_eth_swing_abc123",
        name="eth-swing",
        output_dir="/Users/vj/aether-demo/demo-eth-swing",
        evm_address="0x0000000000000000000000000000000000000001",
    )
    agents = reg.list_agents()
    for a in agents:
        print(a["name"], a["evm_address"], a["status"])
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default registry path — lives outside any single agent directory so it
# survives across projects. Can be overridden via AETHER_FORGE_REGISTRY_PATH.
_DEFAULT_REGISTRY_DIR = Path.home() / ".aether-forge"
_DEFAULT_REGISTRY_DB = _DEFAULT_REGISTRY_DIR / "agents.db"


_CREATE_AGENTS_TABLE = """\
CREATE TABLE IF NOT EXISTS agents (
    agent_id       TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    output_dir     TEXT NOT NULL,
    evm_address    TEXT,
    a2a_endpoint   TEXT,
    provider       TEXT DEFAULT 'ows',
    chain          TEXT DEFAULT 'base',
    status         TEXT DEFAULT 'active',
    capabilities   TEXT DEFAULT '[]',
    planner_mode   TEXT,
    planner_model  TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
)
"""

_CREATE_PEERS_TABLE = """\
CREATE TABLE IF NOT EXISTS agent_peers (
    peer_address   TEXT PRIMARY KEY,
    name           TEXT,
    a2a_endpoint   TEXT,
    capabilities   TEXT DEFAULT '[]',
    trust_score    REAL,
    last_seen      TEXT,
    source         TEXT DEFAULT 'manual'
)
"""

_CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_agents_status ON agents (status)",
    "CREATE INDEX IF NOT EXISTS idx_agents_name ON agents (name)",
    "CREATE INDEX IF NOT EXISTS idx_agents_evm ON agents (evm_address)",
    "CREATE INDEX IF NOT EXISTS idx_peers_source ON agent_peers (source)",
]


class AgentRegistry:
    """SQLite-backed registry of Aether Forge agents.

    Each call to ``forge generate-fast`` (or ``generate-slow``) records the
    new agent here so ``forge agent-list`` can find it later. The registry
    also caches discovered peer agents from the ERC-8004 on-chain registry
    or from direct A2A interactions.
    """

    def __init__(self, db_path: str | Path | None = None) -> None:
        if db_path is None:
            env_path = os.getenv("AETHER_FORGE_REGISTRY_PATH")
            self._db_path = Path(env_path) if env_path else _DEFAULT_REGISTRY_DB
        else:
            self._db_path = Path(db_path)

        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()
        logger.debug("AgentRegistry opened at %s", self._db_path)

    def _init_schema(self) -> None:
        with self._conn:
            self._conn.execute(_CREATE_AGENTS_TABLE)
            self._conn.execute(_CREATE_PEERS_TABLE)
            for idx in _CREATE_INDEXES:
                self._conn.execute(idx)

    # ------------------------------------------------------------------
    # Agent CRUD
    # ------------------------------------------------------------------

    def register(
        self,
        *,
        agent_id: str,
        name: str,
        output_dir: str | Path,
        evm_address: str | None = None,
        a2a_endpoint: str | None = None,
        provider: str = "ows",
        chain: str = "base",
        capabilities: list[str] | None = None,
        planner_mode: str | None = None,
        planner_model: str | None = None,
    ) -> dict[str, Any]:
        """Record a newly created agent. Upserts on agent_id conflict."""
        now = datetime.now(UTC).isoformat()
        caps_json = json.dumps(capabilities or [])
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO agents (
                    agent_id, name, output_dir, evm_address, a2a_endpoint,
                    provider, chain, status, capabilities,
                    planner_mode, planner_model, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?, ?)
                ON CONFLICT(agent_id) DO UPDATE SET
                    name=excluded.name,
                    output_dir=excluded.output_dir,
                    evm_address=excluded.evm_address,
                    a2a_endpoint=excluded.a2a_endpoint,
                    provider=excluded.provider,
                    chain=excluded.chain,
                    capabilities=excluded.capabilities,
                    planner_mode=excluded.planner_mode,
                    planner_model=excluded.planner_model,
                    updated_at=excluded.updated_at
                """,
                (
                    agent_id, name, str(output_dir), evm_address, a2a_endpoint,
                    provider, chain, caps_json,
                    planner_mode, planner_model, now, now,
                ),
            )
        logger.info("Registered agent %s (%s) at %s", name, agent_id, output_dir)
        return self.get_agent(agent_id) or {}

    def get_agent(self, agent_id: str) -> dict[str, Any] | None:
        """Retrieve a single agent by its artifact set ID."""
        row = self._conn.execute(
            "SELECT * FROM agents WHERE agent_id = ?", (agent_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_agents(
        self,
        *,
        status: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """List agents, optionally filtered by status."""
        if status:
            rows = self._conn.execute(
                "SELECT * FROM agents WHERE status = ? ORDER BY created_at DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM agents ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_status(self, agent_id: str, status: str) -> None:
        """Change an agent's status (active, halted, archived)."""
        now = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute(
                "UPDATE agents SET status = ?, updated_at = ? WHERE agent_id = ?",
                (status, now, agent_id),
            )

    def remove(self, agent_id: str) -> None:
        """Archive (soft-delete) an agent. Does NOT delete the agent directory."""
        self.update_status(agent_id, "archived")
        logger.info("Archived agent %s", agent_id)

    # ------------------------------------------------------------------
    # Peer agents (discovered via registry or A2A)
    # ------------------------------------------------------------------

    def upsert_peer(
        self,
        *,
        peer_address: str,
        name: str | None = None,
        a2a_endpoint: str | None = None,
        capabilities: list[str] | None = None,
        trust_score: float | None = None,
        source: str = "manual",
    ) -> None:
        """Record or update a discovered peer agent."""
        now = datetime.now(UTC).isoformat()
        caps_json = json.dumps(capabilities or [])
        with self._conn:
            self._conn.execute(
                """
                INSERT INTO agent_peers (
                    peer_address, name, a2a_endpoint, capabilities,
                    trust_score, last_seen, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(peer_address) DO UPDATE SET
                    name=COALESCE(excluded.name, agent_peers.name),
                    a2a_endpoint=COALESCE(excluded.a2a_endpoint, agent_peers.a2a_endpoint),
                    capabilities=excluded.capabilities,
                    trust_score=COALESCE(excluded.trust_score, agent_peers.trust_score),
                    last_seen=excluded.last_seen,
                    source=excluded.source
                """,
                (peer_address, name, a2a_endpoint, caps_json, trust_score, now, source),
            )

    def list_peers(self, *, limit: int = 100) -> list[dict[str, Any]]:
        """List all known peer agents."""
        rows = self._conn.execute(
            "SELECT * FROM agent_peers ORDER BY last_seen DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def find_peers_by_capability(self, capability: str) -> list[dict[str, Any]]:
        """Find peers that advertise a specific capability."""
        rows = self._conn.execute(
            "SELECT * FROM agent_peers WHERE capabilities LIKE ?",
            (f'%"{capability}"%',),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    @property
    def db_path(self) -> Path:
        return self._db_path

    def agent_count(self) -> int:
        """Count of non-archived agents."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM agents WHERE status != 'archived'"
        ).fetchone()
        return row[0] if row else 0

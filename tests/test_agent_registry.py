"""Tests for the local agent registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from aether_forge.agent_registry import AgentRegistry


@pytest.fixture
def registry(tmp_path: Path) -> AgentRegistry:
    return AgentRegistry(db_path=tmp_path / "test_agents.db")


def test_register_and_list(registry: AgentRegistry) -> None:
    registry.register(
        agent_id="aset_test_abc",
        name="test-agent",
        output_dir="/tmp/test-agent",
        evm_address="0xabc",
    )
    agents = registry.list_agents()
    assert len(agents) == 1
    assert agents[0]["agent_id"] == "aset_test_abc"
    assert agents[0]["name"] == "test-agent"
    assert agents[0]["evm_address"] == "0xabc"
    assert agents[0]["status"] == "active"


def test_register_upserts_on_conflict(registry: AgentRegistry) -> None:
    registry.register(agent_id="aset_1", name="v1", output_dir="/tmp/v1")
    registry.register(agent_id="aset_1", name="v2", output_dir="/tmp/v2")
    agents = registry.list_agents()
    assert len(agents) == 1
    assert agents[0]["name"] == "v2"
    assert agents[0]["output_dir"] == "/tmp/v2"


def test_get_agent(registry: AgentRegistry) -> None:
    registry.register(agent_id="aset_x", name="x", output_dir="/tmp/x")
    agent = registry.get_agent("aset_x")
    assert agent is not None
    assert agent["name"] == "x"
    assert registry.get_agent("nonexistent") is None


def test_update_status(registry: AgentRegistry) -> None:
    registry.register(agent_id="aset_s", name="s", output_dir="/tmp/s")
    registry.update_status("aset_s", "halted")
    agent = registry.get_agent("aset_s")
    assert agent is not None
    assert agent["status"] == "halted"


def test_remove_archives(registry: AgentRegistry) -> None:
    registry.register(agent_id="aset_r", name="r", output_dir="/tmp/r")
    registry.remove("aset_r")
    agent = registry.get_agent("aset_r")
    assert agent is not None
    assert agent["status"] == "archived"
    # archived agents don't count in agent_count
    assert registry.agent_count() == 0


def test_list_filters_by_status(registry: AgentRegistry) -> None:
    registry.register(agent_id="a1", name="active1", output_dir="/tmp/a1")
    registry.register(agent_id="a2", name="active2", output_dir="/tmp/a2")
    registry.register(agent_id="a3", name="halted1", output_dir="/tmp/a3")
    registry.update_status("a3", "halted")
    active = registry.list_agents(status="active")
    assert len(active) == 2
    halted = registry.list_agents(status="halted")
    assert len(halted) == 1
    assert halted[0]["name"] == "halted1"


def test_capabilities_stored_as_json(registry: AgentRegistry) -> None:
    registry.register(
        agent_id="aset_c",
        name="c",
        output_dir="/tmp/c",
        capabilities=["cap-price", "cap-swap", "cap-balance"],
    )
    agent = registry.get_agent("aset_c")
    assert agent is not None
    import json
    caps = json.loads(agent["capabilities"])
    assert caps == ["cap-price", "cap-swap", "cap-balance"]


def test_planner_fields_stored(registry: AgentRegistry) -> None:
    registry.register(
        agent_id="aset_p",
        name="p",
        output_dir="/tmp/p",
        planner_mode="ollama",
        planner_model="gemma4:latest",
    )
    agent = registry.get_agent("aset_p")
    assert agent is not None
    assert agent["planner_mode"] == "ollama"
    assert agent["planner_model"] == "gemma4:latest"


def test_agent_count(registry: AgentRegistry) -> None:
    assert registry.agent_count() == 0
    registry.register(agent_id="a1", name="1", output_dir="/tmp/1")
    registry.register(agent_id="a2", name="2", output_dir="/tmp/2")
    assert registry.agent_count() == 2
    registry.remove("a1")
    assert registry.agent_count() == 1


# ---------------------------------------------------------------------------
# Peer agents
# ---------------------------------------------------------------------------

def test_upsert_peer_and_list(registry: AgentRegistry) -> None:
    registry.upsert_peer(
        peer_address="0x1234",
        name="peer-agent",
        a2a_endpoint="http://peer:8090",
        capabilities=["get-token-price"],
        trust_score=0.85,
        source="registry",
    )
    peers = registry.list_peers()
    assert len(peers) == 1
    assert peers[0]["peer_address"] == "0x1234"
    assert peers[0]["name"] == "peer-agent"
    assert peers[0]["trust_score"] == 0.85


def test_find_peers_by_capability(registry: AgentRegistry) -> None:
    registry.upsert_peer(peer_address="0xa", capabilities=["get-token-price", "get-balances"])
    registry.upsert_peer(peer_address="0xb", capabilities=["execute-swap"])
    registry.upsert_peer(peer_address="0xc", capabilities=["get-token-price"])
    matches = registry.find_peers_by_capability("get-token-price")
    assert len(matches) == 2
    addrs = {m["peer_address"] for m in matches}
    assert addrs == {"0xa", "0xc"}


def test_upsert_peer_updates_existing(registry: AgentRegistry) -> None:
    registry.upsert_peer(peer_address="0xd", name="old", trust_score=0.5)
    registry.upsert_peer(peer_address="0xd", name="new", trust_score=0.9)
    peers = registry.list_peers()
    assert len(peers) == 1
    assert peers[0]["name"] == "new"
    assert peers[0]["trust_score"] == 0.9


def test_db_path_property(registry: AgentRegistry) -> None:
    assert registry.db_path.name == "test_agents.db"

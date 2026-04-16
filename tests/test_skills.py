from __future__ import annotations

import json
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
from aether_forge.skills import (
    InstalledSkill,
    install_skill_to_project,
    install_skills_to_project,
    search_skills,
    skills_to_capabilities,
    skills_to_capability_refs,
    _read_skill_description,
)


def test_install_skill_creates_skill_md() -> None:
    tmp = Path(mkdtemp(prefix="aether-forge-skill-"))
    try:
        result = install_skill_to_project("test-skill", tmp, skill_name="my-skill")

        assert result is not None
        assert isinstance(result, InstalledSkill)

        skill_md = tmp / ".claude" / "skills" / "my-skill" / "SKILL.md"
        assert skill_md.exists()

        content = skill_md.read_text(encoding="utf8")
        assert "my-skill" in content

        assert result.capability_id == "skill-my-skill"
    finally:
        rmtree(tmp)


def test_install_skills_to_project_multiple() -> None:
    tmp = Path(mkdtemp(prefix="aether-forge-skill-"))
    try:
        results = install_skills_to_project(["skill-a", "skill-b"], tmp)

        assert len(results) == 2

        assert (tmp / ".claude" / "skills" / "skill-a" / "SKILL.md").exists()
        assert (tmp / ".claude" / "skills" / "skill-b" / "SKILL.md").exists()
    finally:
        rmtree(tmp)


def test_skills_to_capabilities() -> None:
    installed = [
        InstalledSkill(
            name="alpha",
            path=Path("/tmp/fake/alpha"),
            description="Alpha skill description",
            capability_id="skill-alpha",
        ),
        InstalledSkill(
            name="beta",
            path=Path("/tmp/fake/beta"),
            description="Beta skill description",
            capability_id="skill-beta",
        ),
    ]

    caps = skills_to_capabilities(installed)

    assert len(caps) == 2
    for cap in caps:
        assert "capabilityId" in cap
        assert cap["kind"] == "tool"
        assert cap["provider"].startswith("agent-skill/")
        assert "sandbox" in cap["allowedEnvironments"]


def test_skills_to_capability_refs() -> None:
    installed = [
        InstalledSkill(
            name="alpha",
            path=Path("/tmp/fake/alpha"),
            description="Alpha skill",
            capability_id="skill-alpha",
        ),
        InstalledSkill(
            name="beta",
            path=Path("/tmp/fake/beta"),
            description="Beta skill",
            capability_id="skill-beta",
        ),
    ]

    refs = skills_to_capability_refs(installed)

    assert refs == ["skill-alpha", "skill-beta"]


def test_generate_fast_with_skills() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))
    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="Skill Test Agent",
                idea="Build an agent that reads project context and produces a weekly research brief.",
                output_directory=output_dir,
                skills=["test-skill"],
            )
        )

        cap_manifest_path = output_dir / "capability-manifest.json"
        assert cap_manifest_path.exists()
        cap_manifest = json.loads(cap_manifest_path.read_text(encoding="utf8"))
        skill_caps = [
            c for c in cap_manifest.get("capabilities", [])
            if c.get("capabilityId", "").startswith("skill-")
        ]
        assert len(skill_caps) >= 1

        agent_spec_path = output_dir / "agent-spec.json"
        assert agent_spec_path.exists()
        agent_spec = json.loads(agent_spec_path.read_text(encoding="utf8"))
        skill_refs = [
            r for r in agent_spec.get("capabilityRefs", [])
            if r.startswith("skill-")
        ]
        assert len(skill_refs) >= 1
    finally:
        rmtree(output_dir)


def test_read_skill_description_from_skill_md() -> None:
    tmp = Path(mkdtemp(prefix="aether-forge-skill-"))
    try:
        skill_dir = tmp / "my-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\n"
            "name: my-skill\n"
            "description: A wonderful test skill\n"
            "---\n\n"
            "# my-skill\n\n"
            "Some body text.\n",
            encoding="utf8",
        )

        desc = _read_skill_description(skill_dir)
        assert desc == "A wonderful test skill"
    finally:
        rmtree(tmp)


def test_search_skills_returns_empty_on_network_error() -> None:
    result = search_skills("test-query")
    assert isinstance(result, list)


# ── Elsa x402 skills ────────────────────────────────────────────────────


def test_install_elsa_single_skill() -> None:
    tmp = Path(mkdtemp(prefix="aether-forge-elsa-"))
    try:
        from aether_forge.skills import _install_elsa_skill
        results = _install_elsa_skill("elsa:get-swap-quote", tmp)
        assert len(results) == 1
        assert results[0].name == "elsa-get-swap-quote"
        assert results[0].capability_id == "elsa-get-swap-quote"
        skill_md = results[0].path / "SKILL.md"
        assert skill_md.exists()
        content = skill_md.read_text()
        assert "x402" in content
        assert "heyelsa" in content
    finally:
        rmtree(tmp)


def test_install_elsa_all_skills() -> None:
    tmp = Path(mkdtemp(prefix="aether-forge-elsa-all-"))
    try:
        from aether_forge.skills import _install_elsa_skill, ELSA_ENDPOINTS
        results = _install_elsa_skill("elsa:all", tmp)
        assert len(results) == len(ELSA_ENDPOINTS)
        names = {r.name for r in results}
        assert "elsa-execute-swap" in names
        assert "elsa-get-gas-prices" in names
    finally:
        rmtree(tmp)


def test_install_elsa_by_category() -> None:
    tmp = Path(mkdtemp(prefix="aether-forge-elsa-cat-"))
    try:
        from aether_forge.skills import _install_elsa_skill
        results = _install_elsa_skill("elsa:trading", tmp)
        assert len(results) == 5  # 5 trading endpoints
        for r in results:
            assert "elsa-" in r.name
    finally:
        rmtree(tmp)


def test_elsa_skills_to_capabilities_has_effect_semantics() -> None:
    """Side-effecting Elsa skills must have effectSemantics."""
    tmp = Path(mkdtemp(prefix="aether-forge-elsa-fx-"))
    try:
        from aether_forge.skills import _install_elsa_skill
        results = _install_elsa_skill("elsa:execute-swap", tmp)
        caps = skills_to_capabilities(results)
        assert len(caps) == 1
        cap = caps[0]
        assert cap["kind"] == "exchange-action"
        assert cap["requiredApproval"] is True
        assert cap["riskLevel"] == "high"
        assert "effectSemantics" in cap
        assert cap["providerConstraints"]["protocol"] == "x402"
        assert cap["providerConstraints"]["priceUsd"] == 0.02
    finally:
        rmtree(tmp)


def test_generate_fast_with_elsa_skills() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-elsa-gen-"))
    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="Elsa DeFi Agent",
                idea="Monitor yield and swap tokens",
                output_directory=output_dir,
                skills=["elsa:portfolio", "elsa:get-swap-quote"],
            )
        )
        cap_manifest = json.loads((output_dir / "capability-manifest.json").read_text())
        elsa_caps = [c for c in cap_manifest["capabilities"] if c["capabilityId"].startswith("elsa-")]
        # portfolio category (4 endpoints) + 1 individual = 5
        assert len(elsa_caps) >= 5
        agent_spec = json.loads((output_dir / "agent-spec.json").read_text())
        elsa_refs = [r for r in agent_spec["capabilityRefs"] if r.startswith("elsa-")]
        assert len(elsa_refs) >= 5
    finally:
        rmtree(output_dir)

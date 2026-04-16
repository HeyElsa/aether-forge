"""Skills integration for Aether Forge.

Supports the open SKILL.md standard (agentskills.io) and multiple registries:
- skills.sh — general-purpose skill directory by Vercel Labs
- skills.bankr.bot — crypto/DeFi-focused skills by Bankr
- Elsa (x402.heyelsa.ai) — x402-paid DeFi trading endpoints
- Any GitHub repo containing SKILL.md files
- Local filesystem paths

All registries use the same SKILL.md format (YAML frontmatter + markdown body).
Elsa skills are x402-paid endpoints that map directly to forge capabilities.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request as urllib_request

# Known skill registries
REGISTRIES: dict[str, str] = {
    "skills.sh": "https://skills.sh",
    "bankr": "https://github.com/BankrBot/skills",
    "elsa": "https://x402.heyelsa.ai",
}

SKILLS_SH_API = "https://skills.sh"
BANKR_REPO = "BankrBot/skills"
ELSA_API = "https://x402-api.heyelsa.ai/api"
ELSA_SKILLS_REPO = "HeyElsa/elsa-x402-skills"

# Elsa x402 endpoint catalog — maps skill names to endpoint configs
ELSA_ENDPOINTS: dict[str, dict[str, Any]] = {
    # Portfolio & Analytics
    "search-token": {"endpoint": "search_token", "price_usd": 0.001, "category": "portfolio", "description": "Search tokens by symbol or address across 15+ chains"},
    "get-token-price": {"endpoint": "get_token_price", "price_usd": 0.002, "category": "portfolio", "description": "Get current token price with market data"},
    "get-balances": {"endpoint": "get_balances", "price_usd": 0.005, "category": "portfolio", "description": "Get wallet balances across all supported chains"},
    "get-portfolio": {"endpoint": "get_portfolio", "price_usd": 0.01, "category": "portfolio", "description": "Full portfolio view with DeFi positions"},
    "analyze-wallet": {"endpoint": "analyze_wallet", "price_usd": 0.02, "category": "analytics", "description": "Behavioral analysis and risk metrics for a wallet"},
    "get-pnl-report": {"endpoint": "get_pnl_report", "price_usd": 0.015, "category": "analytics", "description": "Profit and loss report over a time period"},
    # Trading
    "get-swap-quote": {"endpoint": "get_swap_quote", "price_usd": 0.01, "category": "trading", "description": "Best swap price across 20+ DEXes"},
    "execute-swap": {"endpoint": "execute_swap", "price_usd": 0.02, "category": "trading", "description": "Execute a token swap on the best route", "side_effect": True},
    "create-limit-order": {"endpoint": "create_limit_order", "price_usd": 0.05, "category": "trading", "description": "Create a limit order via CoW Protocol", "side_effect": True},
    "get-limit-orders": {"endpoint": "get_limit_orders", "price_usd": 0.002, "category": "trading", "description": "List pending and completed limit orders"},
    "cancel-limit-order": {"endpoint": "cancel_limit_order", "price_usd": 0.01, "category": "trading", "description": "Cancel a pending limit order", "side_effect": True},
    # Perpetuals
    "get-perp-positions": {"endpoint": "get_perp_positions", "price_usd": 0.002, "category": "perpetuals", "description": "View open perpetual positions"},
    "open-perp-position": {"endpoint": "open_perp_position", "price_usd": 0.05, "category": "perpetuals", "description": "Open a perpetual position on Hyperliquid or Avantis", "side_effect": True},
    "close-perp-position": {"endpoint": "close_perp_position", "price_usd": 0.05, "category": "perpetuals", "description": "Close a perpetual position", "side_effect": True},
    # Staking & Yield
    "get-stake-balances": {"endpoint": "get_stake_balances", "price_usd": 0.005, "category": "staking", "description": "View staking positions and APY"},
    "get-yield-suggestions": {"endpoint": "get_yield_suggestions", "price_usd": 0.02, "category": "staking", "description": "Personalized yield farming opportunities"},
    # Airdrops
    "check-airdrop": {"endpoint": "check_airdrop", "price_usd": 0.002, "category": "airdrops", "description": "Check airdrop eligibility for a wallet"},
    "claim-airdrop": {"endpoint": "claim_airdrop", "price_usd": 0.001, "category": "airdrops", "description": "Claim an eligible airdrop", "side_effect": True},
    # Transaction management
    "get-transaction-history": {"endpoint": "get_transaction_history", "price_usd": 0.003, "category": "transactions", "description": "Wallet transaction history"},
    "get-transaction-status": {"endpoint": "get_transaction_status", "price_usd": 0.001, "category": "transactions", "description": "Poll pipeline transaction status"},
    "get-gas-prices": {"endpoint": "get_gas_prices", "price_usd": 0.001, "category": "transactions", "description": "Current gas prices across chains"},
}


@dataclass(slots=True)
class SkillInfo:
    name: str
    description: str
    source: str
    author: str = ""
    version: str = ""
    license: str = ""
    installs: int = 0


@dataclass(slots=True)
class InstalledSkill:
    name: str
    path: Path
    description: str
    capability_id: str


# ---------------------------------------------------------------------------
# Search & fetch
# ---------------------------------------------------------------------------

def search_skills(query: str, limit: int = 10) -> list[SkillInfo]:
    """Search skills.sh leaderboard for skills matching a query."""
    try:
        url = f"{SKILLS_SH_API}/api/leaderboard/skills?q={_url_encode(query)}&limit={limit}"
        data = _api_get(url)
        results: list[SkillInfo] = []
        for item in (data if isinstance(data, list) else data.get("skills", data.get("results", []))):
            results.append(SkillInfo(
                name=item.get("name", item.get("slug", "")),
                description=item.get("description", ""),
                source=item.get("source", item.get("repo", item.get("github", ""))),
                author=item.get("author", item.get("metadata", {}).get("author", "")),
                version=item.get("version", item.get("metadata", {}).get("version", "")),
                license=item.get("license", ""),
                installs=item.get("installs", item.get("install_count", 0)),
            ))
        return results[:limit]
    except Exception as error:
        import logging
        logging.getLogger(__name__).debug("skills-search failed: %s", error)
        return []


def fetch_skill(source: str) -> SkillInfo | None:
    """Fetch details for a specific skill by slug or source."""
    try:
        slug = source.split("/")[-1] if "/" in source else source
        url = f"{SKILLS_SH_API}/api/skills/{_url_encode(slug)}"
        data = _api_get(url)
        return SkillInfo(
            name=data.get("name", slug),
            description=data.get("description", ""),
            source=data.get("source", data.get("repo", source)),
            author=data.get("author", data.get("metadata", {}).get("author", "")),
            version=data.get("version", ""),
            license=data.get("license", ""),
            installs=data.get("installs", 0),
        )
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Install skills into a forge project
# ---------------------------------------------------------------------------

def resolve_source(source: str) -> str:
    """Resolve shorthand sources to full paths.

    Supports:
    - "elsa:skill-name" → Elsa x402 endpoint (e.g., "elsa:get-swap-quote")
    - "elsa:all" → all Elsa endpoints
    - "bankr:skill-name" → "BankrBot/skills/tree/main/skill-name"
    - "owner/repo" → GitHub shorthand (passed through)
    - Full URLs → passed through
    - Local paths → passed through
    """
    if source.startswith("bankr:"):
        skill_name = source.split(":", 1)[1]
        return f"{BANKR_REPO}/tree/main/{skill_name}"
    if source.startswith("elsa:"):
        # Elsa sources are handled specially in install_skill_to_project
        return source
    return source


def _list_elsa_skills(category: str | None = None) -> list[str]:
    """List available Elsa endpoint skill names, optionally filtered by category."""
    if category:
        return [name for name, cfg in ELSA_ENDPOINTS.items() if cfg["category"] == category]
    return list(ELSA_ENDPOINTS.keys())


def _install_elsa_skill(
    elsa_key: str,
    project_dir: Path,
) -> list[InstalledSkill]:
    """Install Elsa x402 endpoint(s) as forge skills.

    Args:
        elsa_key: "elsa:skill-name", "elsa:category-name", or "elsa:all"
        project_dir: Target project directory
    """
    key = elsa_key.split(":", 1)[1] if ":" in elsa_key else elsa_key
    skills_dir = project_dir / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    # Resolve which endpoints to install
    if key == "all":
        endpoints_to_install = list(ELSA_ENDPOINTS.items())
    elif key in ELSA_ENDPOINTS:
        endpoints_to_install = [(key, ELSA_ENDPOINTS[key])]
    else:
        # Try as a category name
        category_skills = _list_elsa_skills(category=key)
        if category_skills:
            endpoints_to_install = [(n, ELSA_ENDPOINTS[n]) for n in category_skills]
        else:
            return []

    installed: list[InstalledSkill] = []
    for name, config in endpoints_to_install:
        skill_dir = skills_dir / f"elsa-{name}"
        skill_dir.mkdir(parents=True, exist_ok=True)

        is_side_effect = config.get("side_effect", False)
        risk = "high" if is_side_effect else "low"

        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            f"---\n"
            f"name: elsa-{name}\n"
            f"description: \"{config['description']}\"\n"
            f"metadata:\n"
            f"  provider: heyelsa\n"
            f"  protocol: x402\n"
            f"  endpoint: {ELSA_API}/{config['endpoint']}\n"
            f"  price_usd: {config['price_usd']}\n"
            f"  category: {config['category']}\n"
            f"  side_effect: {str(is_side_effect).lower()}\n"
            f"  risk_level: {risk}\n"
            f"  network: eip155:8453\n"
            f"---\n\n"
            f"# Elsa: {name}\n\n"
            f"{config['description']}\n\n"
            f"## Endpoint\n\n"
            f"```\n"
            f"POST {ELSA_API}/{config['endpoint']}\n"
            f"```\n\n"
            f"- **Price**: ${config['price_usd']} per request (USDC on Base)\n"
            f"- **Category**: {config['category']}\n"
            f"- **Side effects**: {'Yes — requires policy approval' if is_side_effect else 'No — read-only'}\n"
            f"- **Payment**: Automatic via x402 protocol\n\n"
            f"## Usage\n\n"
            f"This endpoint is called via the x402 payment protocol.\n"
            f"The agent wallet pays per request — no API keys needed.\n",
            encoding="utf8",
        )

        cap_id = f"elsa-{name}"
        installed.append(InstalledSkill(
            name=f"elsa-{name}",
            path=skill_dir,
            description=config["description"],
            capability_id=cap_id,
        ))

    return installed


def install_skill_to_project(
    source: str,
    project_dir: Path,
    skill_name: str | None = None,
) -> InstalledSkill | None:
    """Install a skill into a forge project.

    Accepts sources from any registry using the SKILL.md format:
    - Elsa: "elsa:skill-name" or "elsa:all" for x402 DeFi endpoints
    - skills.sh: "owner/repo" or skill name
    - bankr.bot: "bankr:skill-name" shorthand
    - GitHub: full URL or "owner/repo/tree/main/skill-name"
    - Local: filesystem path to a directory with SKILL.md

    Uses `npx skills add` if available, otherwise creates a placeholder.
    """
    source = resolve_source(source)

    # Handle Elsa x402 endpoints
    if source.startswith("elsa:"):
        results = _install_elsa_skill(source, project_dir)
        return results[0] if results else None
    skills_dir = project_dir / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)

    name = skill_name or source.split("/")[-1].lower().replace(" ", "-")
    skill_dir = skills_dir / name

    # Try npx skills add
    if _has_npx():
        try:
            result = subprocess.run(
                ["npx", "skills", "add", source, "-s", name, "-y", "--copy"],
                cwd=str(project_dir),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and skill_dir.exists():
                desc = _read_skill_description(skill_dir)
                cap_id = f"skill-{name}"
                return InstalledSkill(
                    name=name,
                    path=skill_dir,
                    description=desc,
                    capability_id=cap_id,
                )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

    # Fallback: create a SKILL.md placeholder
    skill_dir.mkdir(parents=True, exist_ok=True)
    info = fetch_skill(source)
    desc = info.description if info else f"Skill from {source}"

    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        f"---\n"
        f"name: {name}\n"
        f"description: {desc}\n"
        f"---\n\n"
        f"# {name}\n\n"
        f"Installed from: `{source}`\n\n"
        f"{desc}\n",
        encoding="utf8",
    )

    cap_id = f"skill-{name}"
    return InstalledSkill(
        name=name,
        path=skill_dir,
        description=desc,
        capability_id=cap_id,
    )


def install_skills_to_project(
    sources: list[str],
    project_dir: Path,
) -> list[InstalledSkill]:
    """Install multiple skills and return the installed list.

    Elsa sources like "elsa:all" or "elsa:trading" expand to multiple skills.
    """
    installed: list[InstalledSkill] = []
    for source in sources:
        resolved = resolve_source(source)
        if resolved.startswith("elsa:"):
            # Elsa can return multiple skills from one source
            results = _install_elsa_skill(resolved, project_dir)
            installed.extend(results)
        else:
            result = install_skill_to_project(source, project_dir)
            if result:
                installed.append(result)
    return installed


# ---------------------------------------------------------------------------
# Map skills to forge capabilities
# ---------------------------------------------------------------------------

def skills_to_capabilities(installed: list[InstalledSkill]) -> list[dict[str, Any]]:
    """Convert installed skills to forge capability-manifest entries."""
    capabilities: list[dict[str, Any]] = []
    for skill in installed:
        is_elsa = skill.name.startswith("elsa-")
        elsa_key = skill.name.removeprefix("elsa-") if is_elsa else None
        elsa_config = ELSA_ENDPOINTS.get(elsa_key, {}) if elsa_key else {}
        is_side_effect = elsa_config.get("side_effect", False)

        handle_id = f"cred-skill-{skill.name}" if is_elsa else f"cred-{skill.name}"
        cap: dict[str, Any] = {
            "capabilityId": skill.capability_id,
            "description": skill.description[:200],
            "kind": "exchange-action" if is_side_effect else ("data-source" if is_elsa else "tool"),
            "provider": f"elsa-x402/{skill.name}" if is_elsa else f"agent-skill/{skill.name}",
            "riskLevel": "high" if is_side_effect else "low",
            "credentialHandleId": handle_id,
            "allowedEnvironments": ["local", "sandbox", "paper"] + (["canary-live"] if not is_side_effect else []),
            "requiredApproval": is_side_effect,
            "providerConstraints": {
                "format": "x402" if is_elsa else "SKILL.md",
                "skillName": skill.name,
                "skillPath": str(skill.path),
            },
        }

        if is_elsa:
            cap["providerConstraints"].update({
                "endpoint": f"{ELSA_API}/{elsa_config.get('endpoint', '')}",
                "priceUsd": elsa_config.get("price_usd", 0),
                "network": "eip155:8453",
                "protocol": "x402",
            })

        if is_side_effect:
            cap["effectSemantics"] = {
                "idempotencyClass": "non-idempotent",
                "duplicateSubmitBehavior": "may-create-duplicate",
                "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
                "compensationClass": "compensatable",
            }

        capabilities.append(cap)
    return capabilities


def skills_to_capability_refs(installed: list[InstalledSkill]) -> list[str]:
    """Return capability IDs for agent-spec capabilityRefs."""
    return [skill.capability_id for skill in installed]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _api_get(url: str) -> Any:
    req = urllib_request.Request(url, headers={"Accept": "application/json"})
    with urllib_request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read().decode("utf8"))


def _url_encode(text: str) -> str:
    from urllib.parse import quote
    return quote(text, safe="")


def _has_npx() -> bool:
    return shutil.which("npx") is not None


def _read_skill_description(skill_dir: Path) -> str:
    """Read the description from a SKILL.md file's frontmatter."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        # Try to find any .md file
        md_files = list(skill_dir.glob("*.md"))
        if not md_files:
            return ""
        skill_md = md_files[0]

    text = skill_md.read_text(encoding="utf8")

    # Parse YAML frontmatter
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            frontmatter = parts[1]
            for line in frontmatter.strip().split("\n"):
                if line.startswith("description:"):
                    return line.split(":", 1)[1].strip().strip('"').strip("'")

    # Fallback: first non-empty, non-heading line
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith("#") and not line.startswith("---"):
            return line[:200]

    return ""

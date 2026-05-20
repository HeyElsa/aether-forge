"""Fast-mode artifact generation for Aether Forge."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from ._version import __version__

logger = logging.getLogger(__name__)


CRYPTO_HINTS = {
    "delta neutral", "delta-neutral", "basis", "perp", "spot", "funding", "hedge",
    "btc", "eth", "bitcoin", "ethereum", "solana", "defi", "dex", "cex",
    "binance", "coinbase", "uniswap", "aave", "compound", "lido", "rocket pool",
    "staking", "yield farm", "liquidity", "swap", "token", "wallet", "onchain",
    "on-chain", "nft", "usdc", "usdt", "stablecoin", "perpetual", "futures",
    "margin", "leverage", "liquidation", "airdrop", "bridge", "layer 2", "l2",
    "arbitrage", "mev", "flash loan", "vault", "lending", "borrow",
}


@dataclass(slots=True)
class FastGenerateRequest:
    name: str
    idea: str
    output_directory: Path
    skills: list[str] | None = None
    create_wallet: bool = False
    autonomous: bool = False
    wallet_chain: str = "evm"
    strategy_file: str | None = None  # Path to English/markdown/JSON strategy description
    # Planner config baked into the generated agent's aether-forge.json so
    # `forge run .` (no flags) inherits the operator's chosen LLM. Defaults to
    # heuristic — works on any machine, no API key, no LLM round-trip.
    planner_mode: str = "heuristic"
    planner_model: str | None = None
    planner_base_url: str | None = None
    planner_api_key_env: str | None = None
    # Provenance fields stamped into aether-forge.json so `forge doctor` and
    # log greppers can tell autodetected planners apart from explicit ones.
    # ``planner_source`` ∈ {"autodetected", "explicit", None}; "autodetected"
    # values originate from cli._autodetect_planner and trigger a hard fail
    # in ``forge doctor`` when ``deployment_profile == "production"``.
    planner_source: str | None = None
    planner_detected_at: str | None = None
    # Deployment profile stamped into aether-forge.json (v0.22.0+, FP-2 deepening).
    # ``local`` (default) tolerates autodetect / heuristic; ``staging`` requires
    # explicit planner; ``production`` is strict (no autodetect, no heuristic,
    # doctor fails loudly). Resolved by config.resolve_deployment_profile().
    deployment_profile: str = "local"


@dataclass(slots=True)
class AgentSummary:
    """Summary card shown after agent generation."""

    name: str
    artifact_set_id: str
    domain: str
    objective: str
    environment: str
    capabilities: list[str]
    skills: list[str]
    wallet_address: str | None
    wallet_chain: str | None
    evm_address: str | None = None
    solana_address: str | None = None
    bitcoin_address: str | None = None
    wallet_provider: str = "none"
    autonomous: bool = False
    strategy_version: int = 1
    strategy_params: dict[str, Any] = field(default_factory=dict)
    entry_rules: list[dict[str, str]] = field(default_factory=list)
    success_metrics: dict[str, float] = field(default_factory=dict)
    output_directory: str = ""
    has_strategy_file: bool = False
    has_dockerfile: bool = True

    def print_card(self) -> None:
        """Print a comprehensive agent summary card."""
        w = 66
        ln = f"  ╔{'═'*w}╗"
        sp = f"  ╠{'═'*w}╣"
        en = f"  ╚{'═'*w}╝"
        bl = f"  ║{' '*w}║"

        def r(label: str, value: str) -> str:
            txt = f"  {label:<14} {value}"
            return f"  ║{txt:<{w}}║"

        def sub(text: str) -> str:
            return f"  ║    {text:<{w-4}}║"

        print()
        print(ln)
        print(f"  ║{'':^{w}}║")
        print(f"  ║{'A G E N T   C R E A T E D':^{w}}║")
        print(f"  ║{'':^{w}}║")

        # ── Identity ──
        print(sp)
        print(r("Name:", self.name))
        print(r("ID:", self.artifact_set_id))
        print(r("Domain:", self.domain))
        obj_short = self.objective[:48] + "..." if len(self.objective) > 48 else self.objective
        print(r("Objective:", obj_short))

        # ── Wallet ──
        print(sp)
        if self.evm_address:
            print(r("Wallet:", f"OWS ({self.wallet_provider})" if self.wallet_provider != "none" else "Simulated"))
            print(r("EVM:", self.evm_address))
            if self.solana_address:
                print(r("Solana:", self.solana_address))
            if self.bitcoin_address:
                print(r("Bitcoin:", self.bitcoin_address))
        else:
            wallet_label = "(none — paper mode only)" if "crypto" in self.domain else "(none — sandbox only)"
            print(r("Wallet:", wallet_label))

        # ── Strategy ──
        print(sp)
        auto_label = "Self-improving (autoresearch)" if self.autonomous else "Fixed (manual edits only)"
        print(r("Mode:", auto_label))
        print(r("Strategy:", f"v{self.strategy_version}" + (" (from file)" if self.has_strategy_file else " (defaults)")))
        print(r("Environment:", self.environment))

        # Show key strategy parameters if available
        p = self.strategy_params
        if p:
            if "crypto" in self.domain:
                spread = p.get("spread_pct", "?")
                pos = p.get("position_size", p.get("position_size_pct", "?"))
                tokens = ", ".join(p.get("tokens", [])) or "?"
                print(sub(f"Tokens: {tokens}"))
                print(sub(f"Spread: {spread}%  |  Position: {pos}  |  Max orders: {p.get('max_open_orders', '?')}"))
                if p.get("stop_loss_pct"):
                    print(sub(f"Stop loss: {p['stop_loss_pct']}%  |  Max daily loss: ${p.get('max_daily_loss_usd', '?')}"))
            else:
                interval = p.get("review_interval_ticks", "?")
                max_items = p.get("max_items_per_tick", "?")
                confidence = p.get("confidence_threshold", "?")
                print(sub(f"Review interval: {interval} tick(s)  |  Max items: {max_items}"))
                print(sub(f"Confidence threshold: {confidence}"))

        # Show entry rules
        if self.entry_rules:
            print(bl)
            print(sub("Entry rules:"))
            for rule in self.entry_rules[:3]:
                action = rule.get("action", "?").upper()
                cond = rule.get("condition", "?")
                if len(cond) > 54:
                    cond = cond[:51] + "..."
                print(sub(f"  {action}: {cond}"))

        # Show success criteria
        if self.success_metrics:
            print(bl)
            parts = []
            if "min_win_rate" in self.success_metrics:
                parts.append(f"Win rate > {self.success_metrics['min_win_rate']*100:.0f}%")
            if "max_drawdown_pct" in self.success_metrics:
                parts.append(f"Drawdown < {self.success_metrics['max_drawdown_pct']}%")
            if "policyViolationRate" in self.success_metrics:
                parts.append(f"Policy violations = {self.success_metrics['policyViolationRate']}")
            if "minimumUsefulOutputs" in self.success_metrics:
                parts.append(f"Useful outputs >= {self.success_metrics['minimumUsefulOutputs']}")
            if parts:
                print(sub(f"Success: {' | '.join(parts)}"))

        # ── Capabilities ──
        print(sp)
        cap_count = len(self.capabilities)
        skill_count = len(self.skills)
        data_caps = [
            c for c in self.capabilities
            if c.startswith(("cap-market", "elsa-get", "elsa-search")) or c.endswith("-read") or "-read-" in c
        ]
        action_caps = [c for c in self.capabilities if c not in data_caps]
        print(r("Capabilities:", f"{cap_count} ({len(data_caps)} read, {len(action_caps)} write)"))
        if skill_count > 0:
            print(r("Skills:", ", ".join(self.skills)))

        # ── Deployment ──
        print(sp)
        deploy_items = ["Dockerfile", "docker-compose.yml", "main.py"]
        if self.autonomous:
            deploy_items.append("autoresearch")
        print(r("Deployment:", " | ".join(deploy_items)))
        print(r("Health:", "/health, /status, /ticks (--health-port 8080)"))

        # ── Output ──
        print(sp)
        out_short = str(self.output_directory)
        if len(out_short) > w - 4:
            out_short = "..." + out_short[-(w-7):]
        print(f"  ║  {out_short:<{w-2}}║")
        print(en)

        # ── Next Steps ──
        print()
        print("  Next steps:")
        print(f"    1. forge validate {self.output_directory}")
        print(f"    2. forge eval-pack {self.output_directory}")
        if "crypto" in self.domain and self.autonomous:
            print(f"    3. forge run {self.output_directory} --autoresearch --auto-approve --environment sandbox --mode paper")
        elif "crypto" in self.domain:
            print(f"    3. forge run {self.output_directory} --auto-approve --environment sandbox --mode paper")
        elif self.autonomous:
            print(f"    3. forge run {self.output_directory} --autoresearch --auto-approve --environment sandbox")
        else:
            print(f"    3. forge run {self.output_directory} --auto-approve --environment sandbox")
        if self.evm_address:
            print(f"    4. Fund wallet only after promotion evidence → send USDC to {self.evm_address}")
            print(f"    5. forge run {self.output_directory} --environment production --mode live  (after funding)")
        print()


@dataclass(slots=True)
class GeneratedArtifactSet:
    artifact_set_id: str
    output_directory: Path
    domain: str
    generated_files: list[Path]
    scaffold_files: list[Path]
    agent_summary: AgentSummary | None = None


def generate_fast_artifact_set(request: FastGenerateRequest) -> GeneratedArtifactSet:
    slug = _slugify(request.name)
    artifact_set_id = f"aset_{slug}_{uuid4().hex[:8]}"
    request.output_directory.mkdir(parents=True, exist_ok=True)

    domain = "crypto-trading" if _looks_like_crypto(request.idea) else "general-agent"
    logger.info("Generating fast artifact set: name=%s domain=%s", request.name, domain)
    title = request.name.strip()
    summary = _summarize_idea(request.idea)

    artifacts = _build_crypto_template(slug, artifact_set_id, title, summary, request.idea) if domain == "crypto-trading" else _build_general_template(slug, artifact_set_id, title, summary, request.idea)

    generated_files: list[Path] = []
    for file_name, payload in artifacts.items():
        file_path = request.output_directory / file_name
        file_path.write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf8")
        logger.debug("Wrote artifact: %s", file_path)
        generated_files.append(file_path)

    for directory in [
        request.output_directory / "src" / "generated",
        request.output_directory / "src" / "protocols",
        request.output_directory / "src" / "policies",
        request.output_directory / "src" / "strategy",
        request.output_directory / "src" / "runtime",
        request.output_directory / "docs",
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    scaffold_files = _write_scaffold_files(
        output_directory=request.output_directory,
        title=title,
        domain=domain,
        artifact_set_id=artifact_set_id,
        summary=summary,
        idea=request.idea,
        artifacts=artifacts,
        request=request,
    )

    # ── Skills integration ──────────────────────────────────────────────
    if request.skills:
        from .skills import install_skills_to_project, skills_to_capabilities, skills_to_capability_refs

        installed = install_skills_to_project(request.skills, request.output_directory)
        if installed:
            skill_capabilities = skills_to_capabilities(installed)
            skill_refs = skills_to_capability_refs(installed)

            # Append skill capabilities and credential handles to capability-manifest.json
            cap_manifest_path = request.output_directory / "capability-manifest.json"
            cap_manifest = json.loads(cap_manifest_path.read_text(encoding="utf8"))
            cap_manifest.setdefault("capabilities", []).extend(skill_capabilities)
            # Add credential handle declarations for skill capabilities
            existing_handles = {h["handleId"] for h in cap_manifest.get("credentialHandles", [])}
            for cap in skill_capabilities:
                handle_id = cap.get("credentialHandleId")
                if handle_id and handle_id not in existing_handles:
                    is_elsa = "elsa" in cap.get("provider", "")
                    cap_manifest.setdefault("credentialHandles", []).append({
                        "handleId": handle_id,
                        "kind": "x402-payment" if is_elsa else "api-token",
                        "allowedEnvironments": cap.get("allowedEnvironments", ["local", "sandbox", "paper"]),
                        "maximumAccessScope": {"resources": [f"{cap.get('capabilityId', '')}:invoke"]},
                        "rotationExpectation": "90d",
                        "ttlPolicy": {"maxSessionMinutes": 60},
                    })
                    existing_handles.add(handle_id)
            cap_manifest_path.write_text(f"{json.dumps(cap_manifest, indent=2)}\n", encoding="utf8")

            # Append skill capability refs to agent-spec.json
            agent_spec_path = request.output_directory / "agent-spec.json"
            agent_spec = json.loads(agent_spec_path.read_text(encoding="utf8"))
            agent_spec.setdefault("capabilityRefs", []).extend(skill_refs)
            agent_spec_path.write_text(f"{json.dumps(agent_spec, indent=2)}\n", encoding="utf8")

            # Add installed skill paths to generated_files
            for skill in installed:
                generated_files.append(skill.path)

    # ── Strategy file injection ──────────────────────────────────────
    if request.strategy_file:
        from .strategy_parser import parse_strategy_file

        strategy_content = Path(request.strategy_file).read_text(encoding="utf8")

        # Parse strategy text into structured parameters
        parsed = parse_strategy_file(strategy_content)

        # Update strategy.json with parsed parameters
        strategy_path = request.output_directory / "strategy.json"
        strategy_data = json.loads(strategy_path.read_text(encoding="utf8"))
        if parsed.get("parameters"):
            strategy_data["parameters"].update(parsed["parameters"])
        if parsed.get("entry_rules"):
            strategy_data["entry_rules"] = parsed["entry_rules"]
        if parsed.get("success_metrics"):
            strategy_data["success_metrics"].update(parsed["success_metrics"])
        strategy_path.write_text(json.dumps(strategy_data, indent=2) + "\n", encoding="utf8")

        # Embed strategy description into agent-spec
        agent_spec_path = request.output_directory / "agent-spec.json"
        agent_spec = json.loads(agent_spec_path.read_text(encoding="utf8"))
        agent_spec["objective"]["strategyDescription"] = strategy_content
        agent_spec_path.write_text(json.dumps(agent_spec, indent=2) + "\n", encoding="utf8")

        # Save as strategy-description.md for reference
        (request.output_directory / "strategy-description.md").write_text(
            f"# Strategy Description\n\n{strategy_content}\n", encoding="utf8"
        )
        logger.info(
            "Strategy file parsed: %d params, %d rules, %d metrics from %s",
            len(parsed.get("parameters", {})),
            len(parsed.get("entry_rules", [])),
            len(parsed.get("success_metrics", {})),
            request.strategy_file,
        )

    # ── Wallet provisioning ───────────────────────────────────────────
    wallet_address = None
    wallet_chain = None
    wallet_info_dict: dict[str, Any] = {}
    if request.create_wallet:
        from .wallet import provision_wallet

        # Determine allowed chains from domain
        allowed_chains = ["ethereum", "base"]
        if domain == "crypto-trading":
            allowed_chains = ["ethereum", "base", "arbitrum", "optimism", "polygon", "solana", "bitcoin"]

        wallet_result = provision_wallet(
            agent_name=slug,
            output_directory=request.output_directory,
            allowed_chains=allowed_chains,
        )
        wallet_address = wallet_result.evm_address
        wallet_chain = "evm, solana, bitcoin"
        wallet_info_dict = {
            "evm_address": wallet_result.evm_address,
            "solana_address": wallet_result.solana_address,
            "bitcoin_address": wallet_result.bitcoin_address,
            "wallet_id": wallet_result.wallet_id,
            "provider": wallet_result.provider,
        }

    # ── Autonomy config ────────────────────────────────────────────────
    if request.autonomous:
        # Update aether-forge.json with autoresearch defaults
        config_path = request.output_directory / "aether-forge.json"
        if config_path.exists():
            config = json.loads(config_path.read_text(encoding="utf8"))
            config["autoresearch"] = {
                "enabled": True,
                "evalInterval": 6,
            }
            config_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf8")

    # ── Build summary ──────────────────────────────────────────────────
    cap_manifest = json.loads((request.output_directory / "capability-manifest.json").read_text(encoding="utf8"))
    cap_ids = [c["capabilityId"] for c in cap_manifest.get("capabilities", []) if "capabilityId" in c]
    skill_names = [s for s in (request.skills or [])]

    # Load strategy for display
    strategy_data = json.loads((request.output_directory / "strategy.json").read_text(encoding="utf8"))

    summary_card = AgentSummary(
        name=title,
        artifact_set_id=artifact_set_id,
        domain=domain,
        objective=summary,
        environment="sandbox",
        capabilities=cap_ids,
        skills=skill_names,
        wallet_address=wallet_address,
        wallet_chain=wallet_chain,
        evm_address=wallet_info_dict.get("evm_address"),
        solana_address=wallet_info_dict.get("solana_address"),
        bitcoin_address=wallet_info_dict.get("bitcoin_address"),
        wallet_provider=wallet_info_dict.get("provider", "none"),
        autonomous=request.autonomous,
        strategy_version=strategy_data.get("version", 1),
        strategy_params=strategy_data.get("parameters", {}),
        entry_rules=strategy_data.get("entry_rules", []),
        success_metrics=strategy_data.get("success_metrics", {}),
        output_directory=str(request.output_directory),
        has_strategy_file=request.strategy_file is not None,
    )

    return GeneratedArtifactSet(
        artifact_set_id=artifact_set_id,
        output_directory=request.output_directory,
        domain=domain,
        generated_files=generated_files,
        scaffold_files=scaffold_files,
        agent_summary=summary_card,
    )


def _build_crypto_template(
    slug: str,
    artifact_set_id: str,
    title: str,
    summary: str,
    idea: str,
) -> dict[str, dict[str, Any]]:
    agent_id = f"agt_{slug}"
    capability_manifest_id = f"capm_{slug}"
    scenario_pack_id = f"scen_{slug}"
    scaffold_manifest_id = f"scaffold_{slug}"

    common = _common_envelope(artifact_set_id, title)

    return {
        "agent-spec.json": {
            **common,
            "artifactType": "agent-spec",
            "artifactId": agent_id,
            "metadata": {
                "name": title,
                "summary": summary,
                "domain": "crypto-trading",
                "tags": ["crypto", "fast-mode"],
                "status": "draft",
            },
            "objective": {
                "primaryGoal": idea.strip(),
                "successMetrics": [
                    {"metric": "policyViolationRate", "target": "== 0"},
                    {"metric": "riskAdjustedPnL", "target": ">= 0"},
                ],
                "nonGoals": ["Unbounded leverage", "Undeclared venue usage"],
                "constraintsSummary": [
                    "Use declared capabilities only",
                    "Respect venue exposure limits",
                    "Pause on stale data or policy holds",
                ],
                "failureModes": ["Stale market data", "Policy denial", "Venue outage"],
            },
            "environmentContract": {
                "allowedEnvironments": ["local", "sandbox", "paper", "canary-live"],
                "defaultEnvironment": "sandbox",
                "promotionPath": ["sandbox", "paper", "canary-live", "production"],
            },
            "capabilityRefs": [
                "cap-market-btc-price",
                "cap-market-basis",
                "cap-exchange-order",
                "cap-exchange-balance",
                "cap-wallet-manage",
            ],
            "policyRefs": [f"policy_{slug}_core"],
            "evaluation": {
                "scenarioPackRef": {
                    "artifactType": "scenario-pack",
                    "artifactId": scenario_pack_id,
                    "artifactVersion": "0.1.0",
                },
                "requiredOutcomes": ["pass"],
                "successThresholds": {
                    "policyViolationRate": 0,
                    "maxReplayDriftBps": 5,
                },
            },
            "promotion": {
                "allowedTargets": ["paper", "canary-live"],
                "requiredApprovals": 1,
            },
        },
        "capability-manifest.json": {
            **common,
            "artifactType": "capability-manifest",
            "artifactId": capability_manifest_id,
            "credentialHandles": [
                {
                    "handleId": "cred_market_data",
                    "kind": "api-token",
                    "allowedEnvironments": ["local", "sandbox", "shadow", "paper", "canary-live", "production"],
                    "maximumAccessScope": {"resources": ["market-data:read"]},
                    "rotationExpectation": "90d",
                    "ttlPolicy": {"maxSessionMinutes": 60},
                },
                {
                    "handleId": "cred_exchange_trade",
                    "kind": "exchange-api-key",
                    "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
                    "maximumAccessScope": {"resources": ["orders:write", "balances:read", "positions:read"]},
                    "rotationExpectation": "30d",
                    "ttlPolicy": {"maxSessionMinutes": 15},
                },
                {
                    "handleId": "cred_wallet_access",
                    "kind": "wallet-session",
                    "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
                    "maximumAccessScope": {"resources": ["wallet:create", "wallet:read", "wallet:sign"]},
                    "rotationExpectation": "session",
                    "ttlPolicy": {"maxSessionMinutes": 15},
                },
            ],
            "capabilities": [
                {
                    "capabilityId": "cap-market-btc-price",
                    "kind": "data-source",
                    "provider": "binance-spot-public",
                    "riskLevel": "low",
                    "allowedEnvironments": ["local", "sandbox", "shadow", "paper", "canary-live", "production"],
                    "requiredApproval": False,
                    "credentialHandleId": "cred_market_data",
                    "providerConstraints": {"symbol": "BTC/USDT", "stalenessBudgetMs": 5000},
                },
                {
                    "capabilityId": "cap-market-basis",
                    "kind": "data-source",
                    "provider": "binance-futures-public",
                    "riskLevel": "low",
                    "allowedEnvironments": ["local", "sandbox", "shadow", "paper", "canary-live", "production"],
                    "requiredApproval": False,
                    "credentialHandleId": "cred_market_data",
                    "providerConstraints": {"symbol": "BTCUSDT", "stalenessBudgetMs": 5000},
                },
                {
                    "capabilityId": "cap-exchange-order",
                    "kind": "exchange-action",
                    "provider": "paper-exchange",
                    "riskLevel": "high",
                    "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
                    "requiredApproval": False,
                    "credentialHandleId": "cred_exchange_trade",
                    "providerConstraints": {"venue": "paper-exchange", "marketType": "perpetual", "maxLeverage": 2, "maxNotionalUsd": 100000},
                    "effectSemantics": {
                        "idempotencyClass": "conditionally-idempotent",
                        "duplicateSubmitBehavior": "client-order-id",
                        "retryPolicy": {"mode": "bounded", "maxAttempts": 2},
                        "compensationClass": "compensatable",
                    },
                },
                {
                    "capabilityId": "cap-exchange-balance",
                    "kind": "data-source",
                    "provider": "paper-account",
                    "riskLevel": "low",
                    "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
                    "requiredApproval": False,
                    "credentialHandleId": "cred_exchange_trade",
                    "providerConstraints": {"fields": ["balances", "positions"]},
                },
                {
                    "capabilityId": "cap-wallet-manage",
                    "kind": "wallet-action",
                    "provider": "ows-wallet",
                    "riskLevel": "high",
                    "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
                    "requiredApproval": False,
                    "credentialHandleId": "cred_wallet_access",
                    "providerConstraints": {"chain": "evm", "walletName": slug},
                    "effectSemantics": {
                        "idempotencyClass": "conditionally-idempotent",
                        "duplicateSubmitBehavior": "none",
                        "retryPolicy": {"mode": "bounded", "maxAttempts": 1},
                        "compensationClass": "compensatable",
                    },
                },
            ],
        },
        "policy-bundle.json": {
            **common,
            "artifactType": "policy-bundle",
            "artifactId": f"policy_{slug}_core",
            "bundleName": f"{title} Core Policy Bundle",
            "defaultAction": "deny",
            "rules": {
                "maxNotionalUsd": 100000,
                "walletAllowedChains": ["evm", "ethereum"],
                "maxWalletTransferAmount": 5,
                "requireApprovalEnvironments": ["canary-live", "production"],
                "requireWalletApprovalEnvironments": ["canary-live", "production"],
                "enforceStalenessChecks": True,
            },
        },
        "scenario-pack.json": {
            **common,
            "artifactType": "scenario-pack",
            "artifactId": scenario_pack_id,
            "scenarios": [
                {
                    "scenarioId": f"scen_{slug}_baseline",
                    "category": "baseline",
                    "environmentKind": "sandbox",
                    "inputs": {"basisBps": 20, "volatilityRegime": "normal"},
                    "expectedOutcome": {"stageOutcome": "pass"},
                    "blockingReasonIds": [],
                    "metrics": {"minimumBasisCaptureBps": 1},
                    "replayClass": "approximately-replayable",
                },
                {
                    "scenarioId": f"scen_{slug}_policy_limit",
                    "category": "policy-violation",
                    "environmentKind": "sandbox",
                    "inputs": {"requestedNotionalUsd": 250000},
                    "expectedOutcome": {"stageOutcome": "hold"},
                    "blockingReasonIds": ["exposure-limit"],
                    "metrics": {"mustDeny": True},
                    "replayClass": "exactly-replayable",
                },
            ],
            "thresholds": {
                "policyViolationRate": 0,
                "requiredPasses": 1,
            },
        },
        "scaffold.manifest.json": {
            **common,
            "artifactType": "scaffold-manifest",
            "artifactId": scaffold_manifest_id,
            "paths": {
                "root": ".",
                "generated": "src/generated",
                "policies": "src/policies",
                "runtime": "src/runtime",
                "docs": "docs",
            },
            "ownershipZones": [
                {"pathPattern": "src/generated/**", "zoneType": "generated", "regenerationMode": "safe-update"},
                {"pathPattern": "src/policies/**", "zoneType": "user-owned", "regenerationMode": "propose-patch"},
                {"pathPattern": "src/runtime/**", "zoneType": "protected", "regenerationMode": "blocked"},
            ],
            "regenerationModes": {
                "safe-update": ["src/generated/**"],
                "propose-patch": ["src/policies/**"],
                "blocked": ["src/runtime/**"],
            },
        },
    }


def _build_general_template(
    slug: str,
    artifact_set_id: str,
    title: str,
    summary: str,
    idea: str,
) -> dict[str, dict[str, Any]]:
    agent_id = f"agt_{slug}"
    capability_manifest_id = f"capm_{slug}"
    scenario_pack_id = f"scen_{slug}"
    scaffold_manifest_id = f"scaffold_{slug}"

    common = _common_envelope(artifact_set_id, title)

    return {
        "agent-spec.json": {
            **common,
            "artifactType": "agent-spec",
            "artifactId": agent_id,
            "metadata": {
                "name": title,
                "summary": summary,
                "domain": "general-agent",
                "tags": ["general", "fast-mode"],
                "status": "draft",
            },
            "objective": {
                "primaryGoal": idea.strip(),
                "successMetrics": [{"metric": "policyViolationRate", "target": "== 0"}],
                "nonGoals": ["Undeclared capabilities"],
                "constraintsSummary": ["Use declared tools only", "Operate inside the chosen environment"],
                "failureModes": ["Missing capability", "Policy denial"],
            },
            "environmentContract": {
                "allowedEnvironments": ["local", "sandbox"],
                "defaultEnvironment": "sandbox",
                "promotionPath": ["sandbox", "paper"],
            },
            "capabilityRefs": ["cap-context-read"],
            "policyRefs": [f"policy_{slug}_core"],
            "evaluation": {
                "scenarioPackRef": {
                    "artifactType": "scenario-pack",
                    "artifactId": scenario_pack_id,
                    "artifactVersion": "0.1.0",
                },
                "requiredOutcomes": ["pass"],
                "successThresholds": {"policyViolationRate": 0},
            },
            "promotion": {
                "allowedTargets": ["paper"],
                "requiredApprovals": 1,
            },
        },
        "capability-manifest.json": {
            **common,
            "artifactType": "capability-manifest",
            "artifactId": capability_manifest_id,
            "credentialHandles": [],
            "capabilities": [
                {
                    "capabilityId": "cap-context-read",
                    "kind": "tool",
                    "provider": "context-reader",
                    "riskLevel": "low",
                    "allowedEnvironments": ["local", "sandbox"],
                    "requiredApproval": False,
                    "providerConstraints": {"mode": "read-only"},
                }
            ],
        },
        "policy-bundle.json": {
            **common,
            "artifactType": "policy-bundle",
            "artifactId": f"policy_{slug}_core",
            "bundleName": f"{title} Core Policy Bundle",
            "defaultAction": "deny",
            "rules": {
                "maxNotionalUsd": 0,
                "walletAllowedChains": ["evm", "ethereum"],
                "maxWalletTransferAmount": 1,
                "requireApprovalEnvironments": ["paper"],
                "requireWalletApprovalEnvironments": ["paper"],
                "enforceStalenessChecks": True,
            },
        },
        "scenario-pack.json": {
            **common,
            "artifactType": "scenario-pack",
            "artifactId": scenario_pack_id,
            "scenarios": [
                {
                    "scenarioId": f"scen_{slug}_baseline",
                    "category": "baseline",
                    "environmentKind": "sandbox",
                    "inputs": {},
                    "expectedOutcome": {"stageOutcome": "pass"},
                    "blockingReasonIds": [],
                    "metrics": {"mustStayGoverned": True},
                    "replayClass": "approximately-replayable",
                }
            ],
            "thresholds": {"policyViolationRate": 0},
        },
        "scaffold.manifest.json": {
            **common,
            "artifactType": "scaffold-manifest",
            "artifactId": scaffold_manifest_id,
            "paths": {
                "root": ".",
                "generated": "src/generated",
                "policies": "src/policies",
                "runtime": "src/runtime",
                "docs": "docs",
            },
            "ownershipZones": [
                {"pathPattern": "src/generated/**", "zoneType": "generated", "regenerationMode": "safe-update"},
                {"pathPattern": "src/policies/**", "zoneType": "user-owned", "regenerationMode": "propose-patch"},
                {"pathPattern": "src/runtime/**", "zoneType": "protected", "regenerationMode": "blocked"},
            ],
            "regenerationModes": {
                "safe-update": ["src/generated/**"],
                "propose-patch": ["src/policies/**"],
                "blocked": ["src/runtime/**"],
            },
        },
    }


def _common_envelope(artifact_set_id: str, title: str) -> dict[str, Any]:
    return {
        "schemaVersion": "1.0.0",
        "artifactVersion": "0.1.0",
        "artifactSetId": artifact_set_id,
        "title": title,
        "generator": {
            "name": "aether-forge",
            "version": __version__,
            "inputDigest": f"sha256:{artifact_set_id}",
        },
        "compatibility": {
            "status": "backward-compatible",
            "previousArtifactVersion": None,
            "migrationRef": None,
        },
        "provenance": {
            "createdAt": "2026-04-06T12:00:00Z",
            "sourceMode": "fast",
        },
    }


def _project_config_json(request: FastGenerateRequest | None = None) -> str:
    """Build the per-agent aether-forge.json. Honors the planner choice from
    the operator so the generated agent's `forge run .` (no flags) resolves to
    the same model that was selected at generation time.

    Also stamps ``planner.source`` and ``planner.detectedAt`` when the choice
    came from cli._autodetect_planner — gives ``forge doctor`` and future
    deployment-profile checks (FP-2 Sprint 2) the audit trail to flag silent
    autodetect picks in production.
    """
    planner_block: dict[str, Any] = {
        "mode": (request.planner_mode if request else None) or "heuristic",
    }
    if request and request.planner_model:
        planner_block["model"] = request.planner_model
    if request and request.planner_base_url:
        planner_block["baseUrl"] = request.planner_base_url
    if request and request.planner_api_key_env:
        planner_block["apiKeyEnv"] = request.planner_api_key_env
    if request and request.planner_source:
        planner_block["source"] = request.planner_source
    if request and request.planner_detected_at:
        planner_block["detectedAt"] = request.planner_detected_at

    profile = (request.deployment_profile if request else None) or "local"

    payload = {
        "deploymentProfile": profile,
        "planner": planner_block,
        "runtime": {
            "cryptoRouter": "mock",
        },
        "adapters": {
            "liveExchange": {
                "enabled": False,
                "modulePath": "src/runtime/live_exchange.py",
                "builder": "build_live_exchange_adapter",
            }
        },
    }
    return f"{json.dumps(payload, indent=2)}\n"


def _project_example_config_json() -> str:
    payload = {
        "planner": {
            "mode": "function-call",
            "model": "your-model-name",
            "baseUrl": "https://your-provider.example/v1",
            "apiKeyEnv": "AETHER_FORGE_PLANNER_API_KEY",
        },
        "runtime": {
            "cryptoRouter": "paper-trading",
        },
        "adapters": {
            "liveExchange": {
                "enabled": False,
                "modulePath": "src/runtime/live_exchange.py",
                "builder": "build_live_exchange_adapter",
            }
        },
    }
    return f"{json.dumps(payload, indent=2)}\n"


def _write_scaffold_files(
    *,
    output_directory: Path,
    title: str,
    domain: str,
    artifact_set_id: str,
    summary: str,
    idea: str,
    artifacts: dict[str, dict[str, Any]],
    request: FastGenerateRequest | None = None,
) -> list[Path]:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or "agent"
    scaffold_files = {
        Path("pyproject.toml"): _project_pyproject_toml(title, slug, summary),
        Path("main.py"): _project_main_py(title),
        Path("aether-forge.json"): _project_config_json(request),
        Path("aether-forge.example.json"): _project_example_config_json(),
        Path("README.md"): _root_readme(title, domain, summary),
        Path("docs/README.md"): _docs_readme(title, artifact_set_id, idea),
        Path("docs/live-exchange.md"): _live_exchange_docs(title),
        Path("docs/planner.md"): _planner_docs(title),
        Path("src/__init__.py"): '"""Generated scaffold package root."""\n',
        Path("src/generated/__init__.py"): '"""Generated project artifacts for this Aether Forge scaffold."""\n',
        Path("src/generated/agent_context.py"): _agent_context_module(title, artifact_set_id, artifacts),
        Path("src/protocols/__init__.py"): _protocols_init_module(title, summary, domain),
        Path("src/policies/__init__.py"): '"""User-owned policy overrides live here."""\n',
        Path("src/policies/policy_bundle.py"): _policy_bundle_module(title),
        Path("src/runtime/__init__.py"): '"""Runtime helpers for the generated scaffold."""\n',
        Path("src/runtime/run_agent.py"): _runtime_runner_module(title),
        Path("src/runtime/wallet.py"): _runtime_wallet_module(title),
        Path("src/runtime/live_exchange.py"): _runtime_live_exchange_module(title),
        Path("src/strategy/__init__.py"): _strategy_init_module(),
        Path("src/strategy/price_feed.py"): _strategy_price_feed_module(),
        Path("src/strategy/momentum.py"): _strategy_momentum_module(),
        Path("src/strategy/paper_trading.py"): _strategy_paper_trading_module(),
        Path("src/strategy/router.py"): _strategy_router_module(title, domain),
        Path("AGENT.md"): _agent_md(title, slug, artifact_set_id, domain, summary, idea, request or FastGenerateRequest(name=title, idea=idea, output_directory=output_directory)),
        Path("strategy.json"): _project_strategy_json(title, domain),
        Path("Dockerfile"): _project_dockerfile(),
        Path(".dockerignore"): _project_dockerignore(),
        Path("docker-compose.yml"): _project_docker_compose(title, slug),
        Path("Makefile"): _project_makefile(slug),
        Path(".env.example"): _project_env_example(),
        Path("tests/__init__.py"): _project_tests_init(),
        Path("tests/test_agent.py"): _project_test_agent(title),
    }

    written_paths: list[Path] = []
    for relative_path, content in scaffold_files.items():
        file_path = output_directory / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf8")
        written_paths.append(file_path)

    return written_paths


def _project_pyproject_toml(title: str, slug: str, summary: str) -> str:
    return (
        "[build-system]\n"
        'requires = ["setuptools>=69"]\n'
        'build-backend = "setuptools.build_meta"\n\n'
        "[project]\n"
        f'name = "{slug}"\n'
        'version = "0.1.0"\n'
        f'description = "{summary[:120]}"\n'
        'requires-python = ">=3.12"\n'
        "dependencies = [\n"
        '  "aether-forge>=0.1.0",\n'
        "]\n\n"
        "[tool.setuptools.packages.find]\n"
        'where = ["."]\n'
        'include = ["src*"]\n'
    )


def _project_main_py(title: str) -> str:
    return (
        f'"""Entry point for {title}.\n\n'
        "Run directly:  python main.py\n"
        f"Or via forge:  forge run .\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "import sys\n"
        "from pathlib import Path\n\n"
        "# Ensure project root is importable\n"
        "PROJECT_ROOT = Path(__file__).resolve().parent\n"
        "if str(PROJECT_ROOT) not in sys.path:\n"
        "    sys.path.insert(0, str(PROJECT_ROOT))\n\n"
        "from aether_forge.runner import AgentRunner, RunnerConfig\n"
        "from src.strategy.router import build_router\n"
        "from aether_forge.scaffold_router import StrategyConfig\n\n\n"
        "def main():\n"
        "    # Configure strategy router (paper mode = real prices, simulated orders)\n"
        "    strategy_config = StrategyConfig(mode='paper', initial_balance_usd=10_000.0)\n"
        "    router = build_router(strategy_config)\n\n"
        "    config = RunnerConfig(\n"
        "        interval_seconds=30,\n"
        '        environment="sandbox",\n'
        "        auto_approve=True,\n"
        "    )\n"
        "    runner = AgentRunner(\n"
        "        PROJECT_ROOT,\n"
        "        config=config,\n"
        "        execution_router_factory=lambda: router,\n"
        "    )\n"
        "    runner.run()\n\n\n"
        'if __name__ == "__main__":\n'
        "    main()\n"
    )


def _root_readme(title: str, domain: str, summary: str) -> str:
    run_command = (
        "forge run . --environment sandbox --mode paper --auto-approve"
        if "crypto" in domain
        else "forge run . --environment sandbox --auto-approve"
    )
    run_note = (
        "\nFor crypto scaffolds, `--environment` controls policy and `--mode` controls the trading backend."
        if "crypto" in domain
        else ""
    )
    return (
        f"# {title}\n\n"
        f"Generated by `Aether Forge` in `fast` mode.\n\n"
        f"- Domain: `{domain}`\n"
        f"- Summary: {summary}\n\n"
        "## Files\n\n"
        "- `aether-forge.json`: scaffold-local planner/runtime/adapter/MCP config\n"
        "- `aether-forge.example.json`: example config for provider-backed planning and adapters\n"
        "- `agent-spec.json`: canonical agent contract\n"
        "- `capability-manifest.json`: declared capabilities and effect semantics\n"
        "- `policy-bundle.json`: runtime policy rules and approval defaults\n"
        "- `scenario-pack.json`: evaluation scenarios and thresholds\n"
        "- `scaffold.manifest.json`: scaffold ownership and regeneration rules\n"
        "- `src/generated/agent_context.py`: generated Python context from the artifact set\n"
        "- `src/policies/policy_bundle.py`: user-owned policy extension point\n"
        "- `src/runtime/run_agent.py`: runtime helper wrapper\n"
        "- `src/runtime/wallet.py`: OWS-backed wallet helper wrapper\n"
        "- `src/runtime/live_exchange.py`: developer template for custom live exchange adapters\n"
        "- `docs/live-exchange.md`: guide for enabling and implementing a project-local live adapter\n"
        "- `docs/planner.md`: guide for enabling a provider-backed planner\n\n"
        "## Quick Start\n\n"
        "```bash\n"
        "pip install -e .          # Install with aether-forge dependency\n"
        "forge validate .          # Validate artifacts\n"
        "forge eval-pack .         # Run scenario evaluations\n"
        f"{run_command}  # Start the governed agent loop\n"
        "python main.py            # Or run directly\n"
        "```\n"
        f"{run_note}\n\n"
        "## Adding external tools via MCP\n\n"
        "This agent is an MCP client. Declare any [Model Context Protocol](https://modelcontextprotocol.io)\n"
        "server in `aether-forge.json` and its tools become available to the planner at runtime:\n\n"
        "```json\n"
        "{\n"
        '  "mcp_servers": {\n'
        '    "hermes": {"command": "hermes", "args": ["mcp", "serve"]},\n'
        '    "filesystem": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]}\n'
        "  }\n"
        "}\n"
        "```\n\n"
        "Run `forge doctor` to probe declared MCP servers and verify they are reachable.\n"
    )


def _docs_readme(title: str, artifact_set_id: str, idea: str) -> str:
    return (
        f"# {title} Notes\n\n"
        f"Artifact set: `{artifact_set_id}`\n\n"
        "## Original Idea\n\n"
        f"{idea.strip()}\n\n"
        "## Next Steps\n\n"
        "1. Review `agent-spec.json` and tighten the objective.\n"
        "2. Review `capability-manifest.json` and confirm provider choices.\n"
        "3. Edit `src/policies/policy_bundle.py` with project-specific rules.\n"
        "4. Run `forge scaffold-policy-sync <project-root>` to write policy changes back into `policy-bundle.json`.\n"
        "5. Copy values from `aether-forge.example.json` into `aether-forge.json` if you want provider-backed planning.\n"
        "6. Read `docs/planner.md` before enabling any real planner backend.\n"
        "7. Flip `adapters.liveExchange.enabled` in `aether-forge.json` only when your project-local live adapter is ready.\n"
        "8. Implement `src/runtime/live_exchange.py` only when you are ready to supply a real venue backend.\n"
        "9. Read `docs/live-exchange.md` before enabling any live adapter path.\n"
        "10. Run eval scenarios before drafting promotion evidence.\n"
    )


def _live_exchange_docs(title: str) -> str:
    return (
        f"# {title} Live Exchange Adapter\n\n"
        "This project ships with a project-local live exchange adapter template at `src/runtime/live_exchange.py`.\n\n"
        "## Default State\n\n"
        "Live execution is disabled by default. The generated `aether-forge.json` file sets:\n\n"
        "```json\n"
        '{\n'
        '  "adapters": {\n'
        '    "liveExchange": {\n'
        '      "enabled": false,\n'
        '      "modulePath": "src/runtime/live_exchange.py",\n'
        '      "builder": "build_live_exchange_adapter"\n'
        '    }\n'
        '  }\n'
        '}\n'
        "```\n\n"
        "## Enable Path\n\n"
        "1. Implement `ProjectLiveExchangeAdapter` in `src/runtime/live_exchange.py`.\n"
        "2. Keep the methods typed to the `LiveExchangeAdapter` protocol.\n"
        "3. Flip `adapters.liveExchange.enabled` to `true` in `aether-forge.json`.\n"
        "4. Run the project with `--crypto-router scaffold-live`.\n"
        "5. Do not enable live execution before policy and promotion evidence are ready.\n\n"
        "The generated runtime does not build placeholder transactions or sign synthetic order payloads. If the adapter is disabled or missing, live exchange actions fail closed.\n\n"
        "## Safety Expectations\n\n"
        "- All live actions must still pass runtime policy checks.\n"
        "- Credential handling must stay behind the framework's credential resolver.\n"
        "- The adapter must not bypass the step ledger or effect semantics.\n"
        "- Start with paper or simulated equivalents before real venue access.\n"
    )


def _planner_docs(title: str) -> str:
    return (
        f"# {title} Planner Configuration\n\n"
        "This scaffold defaults to the native heuristic planner.\n\n"
        "## Provider-Backed Planner\n\n"
        "You can switch the scaffold to a provider-backed planner by copying values from `aether-forge.example.json` into `aether-forge.json`.\n\n"
        "Example planner block:\n\n"
        "```json\n"
        '{\n'
        '  "planner": {\n'
        '    "mode": "function-call",\n'
        '    "model": "your-model-name",\n'
        '    "baseUrl": "https://your-provider.example/v1",\n'
        '    "apiKeyEnv": "AETHER_FORGE_PLANNER_API_KEY"\n'
        '  }\n'
        '}\n'
        "```\n\n"
        "## Safety Notes\n\n"
        "- Provider-backed planning still uses the same bounded step protocol.\n"
        "- Invalid model output falls back to the heuristic planner.\n"
        "- Planner config does not bypass capabilities, policy checks, or promotion rules.\n"
    )


def _agent_context_module(title: str, artifact_set_id: str, artifacts: dict[str, dict[str, Any]]) -> str:
    objective = artifacts["agent-spec.json"]["objective"]["primaryGoal"]
    capability_ids = artifacts["agent-spec.json"]["capabilityRefs"]
    scenario_ids = [scenario["scenarioId"] for scenario in artifacts["scenario-pack.json"]["scenarios"]]
    return (
        '"""Generated runtime context for this scaffold.\n\n'
        "Do not edit generated constants by hand; regenerate from Aether Forge\n"
        'when the artifact set changes.\n"""\n\n'
        f'TITLE = {title!r}\n'
        f'ARTIFACT_SET_ID = {artifact_set_id!r}\n'
        f'OBJECTIVE = {objective!r}\n'
        f'CAPABILITY_IDS = {capability_ids!r}\n'
        f'SCENARIO_IDS = {scenario_ids!r}\n'
    )


def _policy_bundle_module(title: str) -> str:
    return (
        '"""User-owned policy customizations for the generated scaffold.\n\n'
        "This file is intentionally user-owned. Aether Forge may propose patches\n"
        'here but should not overwrite your edits directly.\n"""\n\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "from pathlib import Path\n\n"
        f'POLICY_BUNDLE_NAME = {title!r}\n'
        'POLICY_BUNDLE_VERSION = "0.1.0"\n\n'
        'def extra_policy_rules() -> dict[str, object]:\n'
        '    """Return project-specific policy rule overrides merged into policy-bundle.json."""\n'
        '    return {}\n\n'
        'def sync_policy_bundle(project_root: str | Path) -> dict[str, object]:\n'
        '    root = Path(project_root)\n'
        '    bundle_path = root / "policy-bundle.json"\n'
        '    bundle = json.loads(bundle_path.read_text(encoding="utf8"))\n'
        '    bundle["bundleName"] = POLICY_BUNDLE_NAME\n'
        '    bundle["artifactVersion"] = POLICY_BUNDLE_VERSION\n'
        '    bundle.setdefault("rules", {}).update(extra_policy_rules())\n'
        '    bundle_path.write_text(f"{json.dumps(bundle, indent=2)}\\n", encoding="utf8")\n'
        '    return bundle\n'
    )


def _runtime_runner_module(title: str) -> str:
    return (
        '"""Runtime helpers for the generated scaffold."""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "from aether_forge.evals import evaluate_scenario_pack\n"
        "from aether_forge.runtime import load_artifact_bundle\n\n"
        "from src.generated.agent_context import ARTIFACT_SET_ID\n\n"
        f'DEFAULT_PROJECT_NAME = {title!r}\n\n'
        "def load_current_bundle(project_root: str | Path):\n"
        "    root = Path(project_root)\n"
        "    return load_artifact_bundle(root)\n\n"
        "def run_eval_pack(project_root: str | Path):\n"
        "    root = Path(project_root)\n"
        "    return evaluate_scenario_pack(root)\n\n"
        "if __name__ == \"__main__\":\n"
        "    summary, _sessions = run_eval_pack(Path(__file__).resolve().parents[2])\n"
        "    print(f\"Artifact set {ARTIFACT_SET_ID}: {summary.total_scenarios} scenarios, {summary.matched_expectations} matched expectations\")\n"
    )


def _runtime_wallet_module(title: str) -> str:
    return (
        '"""Wallet helpers for the generated scaffold.\n\n'
        "These helpers wrap the Aether Forge Open Wallet Standard adapter so the\n"
        'generated project has a clear local entry point for wallet operations.\n"""\n\n'
        "from __future__ import annotations\n\n"
        "from aether_forge.crypto import OpenWalletStandardAdapter\n\n"
        f'DEFAULT_WALLET_NAME = {title.lower().replace(" ", "-")!r}\n\n'
        "def create_wallet(name: str | None = None, vault_path: str | None = None):\n"
        "    adapter = OpenWalletStandardAdapter(vault_path=vault_path)\n"
        "    return adapter.create_wallet(name or DEFAULT_WALLET_NAME)\n\n"
        "def get_account(chain: str, name: str | None = None, vault_path: str | None = None):\n"
        "    adapter = OpenWalletStandardAdapter(vault_path=vault_path)\n"
        "    return adapter.get_account(name or DEFAULT_WALLET_NAME, chain)\n\n"
        "def sign_message(chain: str, message: str, name: str | None = None, vault_path: str | None = None):\n"
        "    adapter = OpenWalletStandardAdapter(vault_path=vault_path)\n"
        "    return adapter.sign_message(name or DEFAULT_WALLET_NAME, chain, message)\n"
        "\n"
        "def sign_transaction(chain: str, tx_hex: str, name: str | None = None, vault_path: str | None = None):\n"
        "    adapter = OpenWalletStandardAdapter(vault_path=vault_path)\n"
        "    return adapter.sign_transaction(name or DEFAULT_WALLET_NAME, chain, tx_hex)\n"
        "\n"
        "def send_transaction(chain: str, tx_hex: str, name: str | None = None, rpc_url: str | None = None, vault_path: str | None = None):\n"
        "    adapter = OpenWalletStandardAdapter(vault_path=vault_path)\n"
        "    return adapter.sign_transaction(name or DEFAULT_WALLET_NAME, chain, tx_hex, send=True, rpc_url=rpc_url)\n"
    )


def _runtime_live_exchange_module(title: str) -> str:
    return (
        '"""Developer template for custom live exchange adapters.\n\n'
        "This file is user-owned. Implement the protocol when you are ready to\n"
        'connect a real venue backend under Aether Forge policy and ledger controls.\n"""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n"
        "from typing import Any\n\n"
        "from aether_forge.crypto import CredentialLease, LiveExchangeAdapter\n\n"
        f'DEFAULT_VENUE_NAME = {title.lower().replace(" ", "-")!r}\n\n'
        "LIVE_EXCHANGE_ENABLED = False\n\n"
        "class ProjectLiveExchangeAdapter(LiveExchangeAdapter):\n"
        '    """Project-local live exchange adapter template.\n\n'
        "    Replace the `raise NotImplementedError` blocks with your venue-specific\n"
        '    implementation while preserving the typed contract.\n"""\n\n'
        "    def place_order(\n"
        "        self,\n"
        "        *,\n"
        "        venue: str,\n"
        "        symbol: str,\n"
        "        requested_notional_usd: float,\n"
        "        side: str,\n"
        "        credential_lease: CredentialLease,\n"
        "        metadata: dict[str, Any] | None = None,\n"
        "    ) -> dict[str, Any]:\n"
        '        raise NotImplementedError("Implement live order placement for your venue backend")\n\n'
        "    def cancel_order(\n"
        "        self,\n"
        "        *,\n"
        "        venue: str,\n"
        "        order_id: str,\n"
        "        credential_lease: CredentialLease,\n"
        "    ) -> dict[str, Any]:\n"
        '        raise NotImplementedError("Implement live order cancellation for your venue backend")\n\n'
        "    def get_account_snapshot(\n"
        "        self,\n"
        "        *,\n"
        "        venue: str,\n"
        "        credential_lease: CredentialLease,\n"
        "    ) -> dict[str, Any]:\n"
        '        raise NotImplementedError("Implement live account reads for your venue backend")\n'
        "\n"
        "def build_live_exchange_adapter(project_root: str | Path):\n"
        '    """Return a project-local live exchange adapter or None when disabled."""\n'
        "    _ = Path(project_root)\n"
        "    if not LIVE_EXCHANGE_ENABLED:\n"
        "        return None\n"
        "    return ProjectLiveExchangeAdapter()\n"
    )


def _protocols_init_module(title: str, summary: str, domain: str) -> str:
    x402_enabled = "True" if "crypto" in domain else "False"
    budget_limit = "50.0" if "crypto" in domain else "0.0"
    return (
        '"""Protocol stack for this agent \u2014 ERC-8004, ERC-8126, ERC-8183, x402."""\n'
        '\n'
        '# Agent identity (ERC-8004)\n'
        'AGENT_CARD = {\n'
        f'    "name": {title!r},\n'
        f'    "description": {summary!r},\n'
        f'    "x402Support": {x402_enabled},\n'
        '    "active": True,\n'
        '    "supportedTrustTypes": ["erc8126"],\n'
        '    "services": [],\n'
        '}\n'
        '\n'
        '# Security defaults\n'
        'SECURITY_CONFIG = {\n'
        '    "maxSpendPerTxUsd": 10.0,\n'
        '    "maxSpendPerDayUsd": 100.0,\n'
        '    "maxTransactionsPerHour": 20,\n'
        '    "circuitBreakerVelocityThreshold": 3.0,\n'
        '}\n'
        '\n'
        '# x402 payment config\n'
        'X402_CONFIG = {\n'
        '    "network": "eip155:8453",  # Base mainnet\n'
        f'    "budgetLimitUsd": {budget_limit},\n'
        '    "enabled": False,  # Enable when wallet is configured\n'
        '}\n'
    )


def _agent_md(title: str, slug: str, artifact_set_id: str, domain: str, summary: str, idea: str, request: FastGenerateRequest) -> str:
    """Generate comprehensive AGENT.md documentation."""
    has_wallet = request.create_wallet
    is_autonomous = request.autonomous
    skills_list = "\n".join(f"- `{s}`" for s in (request.skills or [])) or "- (none)"

    wallet_section = ""
    if has_wallet:
        wallet_section = """
## Wallet

This agent has a multi-chain wallet provisioned at creation.

| Chain | Status | Config |
|-------|--------|--------|
| EVM (ETH, Base, Arbitrum, Optimism, Polygon) | Created | `wallet.json` |
| Solana | Created | `wallet.json` |
| Bitcoin | Created | `wallet.json` |

**Important:**
- Fund the wallet with USDC before enabling live mode
- The wallet addresses are in `wallet.json` — keep the mnemonic secure
- Never commit `wallet.json` with real keys to version control
"""
    else:
        wallet_section = """
## Wallet

No wallet was created. This agent runs in paper mode only.

To create a wallet later:
```bash
forge generate-fast --name "{title}" --idea "..." --output . --wallet
```
"""

    autonomy_section = ""
    if is_autonomous:
        autonomy_section = """
## Self-Improvement (Autoresearch)

This agent has runtime autoresearch enabled. It will:

1. **Self-evaluate** every 6 ticks — measure win rate, P&L, drawdown
2. **Detect underperformance** — compare metrics against `strategy.json` thresholds
3. **Propose mutations** — ask the LLM to suggest parameter changes
4. **Present proposals** — print improvement suggestions for your review
5. **Wait for approval** — never auto-applies changes (you decide)

### Accept or reject proposals

When a proposal appears:
```
  IMPROVEMENT PROPOSAL [prop_abc123]
  Hypothesis: Widen spread to 1.5% due to high volatility
  Changes: spread_pct: 1.0 → 1.5
```

Accept: `forge strategy accept . prop_abc123`
Reject: `forge strategy reject . prop_abc123 --reason "too aggressive"`

### Protected evaluator

The agent CANNOT:
- Lower `min_win_rate` (currently 0.40)
- Raise `max_drawdown_pct` (currently 10%)
- Remove safety constraints
- Auto-apply changes without your review

### View current strategy

```bash
forge strategy view .
```
"""
    else:
        autonomy_section = """
## Strategy

This agent uses a fixed strategy defined in `strategy.json`.
Edit the parameters directly to change behavior.

To enable self-improvement:
```bash
forge run . --autoresearch --eval-interval 6
```
"""

    if "crypto" not in domain:
        return f"""# {title}

> {summary}

## Overview

| Field | Value |
|-------|-------|
| Agent ID | `{artifact_set_id}` |
| Domain | `{domain}` |
| Created by | Aether Forge (fast mode) |
| Default environment | `sandbox` |
| Autonomous | {'Yes' if is_autonomous else 'No'} |

## Objective

{idea}

## Quick Start

```bash
# 1. Validate artifacts
forge validate .

# 2. Run scenario evaluations
forge eval-pack .

# 3. Start the agent with local mock execution
forge run . --auto-approve --environment sandbox --planner-mode heuristic

# 4. Start with autoresearch after adding meaningful eval scenarios
forge run . --autoresearch --auto-approve --environment sandbox --planner-mode heuristic

# 5. Deploy with Docker
docker-compose up -d
```

## Skills

{skills_list}

## Capabilities

Declared in `capability-manifest.json`. The agent can only use capabilities
listed there — the policy gate enforces this at runtime.

| Kind | Description |
|------|-------------|
| `tool` | Project-local or external tools declared in the manifest |
| `data-source` | Read-only data from configured providers |
| `memory-action` | Typed memory reads and writes through the runtime |

{wallet_section}

{autonomy_section}

## Architecture

```
{slug}/
├── AGENT.md                 ← you are here
├── agent-spec.json          ← agent contract (objective, capabilities, eval)
├── capability-manifest.json ← declared capabilities + credential handles
├── policy-bundle.json       ← safety rules and approval defaults
├── scenario-pack.json       ← evaluation scenarios
├── strategy.json            ← tunable runtime parameters
├── scaffold.manifest.json   ← ownership zones (generated vs user-owned)
├── aether-forge.json        ← local config (planner, runtime, MCP)
├── main.py                  ← standalone entry point
├── pyproject.toml           ← pip installable
├── Dockerfile               ← container deployment
├── docker-compose.yml       ← orchestration
├── src/
│   ├── strategy/router.py   ← YOUR execution router
│   ├── generated/           ← auto-generated context (don't edit)
│   ├── policies/            ← user-owned policy overrides
│   ├── runtime/             ← runtime helpers
│   └── protocols/           ← ERC-8004/8126/8183/x402 metadata
├── docs/                    ← additional documentation
├── replays/                 ← tick replay files (created at runtime)
└── memory.db                ← persistent memory (created at runtime)
```

## Editing the Strategy

The strategy is in `strategy.json`:

```json
{{
  "parameters": {{
    "review_interval_ticks": 1,
    "max_items_per_tick": 5,
    "confidence_threshold": 0.7
  }},
  "entry_rules": [
    {{"condition": "new context or requested task is available", "action": "read declared context"}}
  ],
  "success_metrics": {{
    "policyViolationRate": 0,
    "minimumUsefulOutputs": 1
  }}
}}
```

## Editing the Router

The execution router is in `src/strategy/router.py`. Add handlers for the tools
and data sources declared in `capability-manifest.json`.

## Governance

Every agent action goes through:

```
Planner → Policy Gate → Execute → Step Ledger
```

- **Policy gate** enforces environment restrictions, capability declarations, and approval requirements
- **Step ledger** records every action for audit and replay
- **Approval** is required whenever policy says a side effect needs review
- **Auto-approve** is available in sandbox for testing

## Deployment

```bash
docker build -t {slug} .
docker-compose up -d
```

## Promotion Pipeline

```
Sandbox → Paper → Canary Live → Production
```

Each promotion requires:
1. Passing scenario evaluations
2. Evidence-backed promotion record
3. Approver sign-off

```bash
forge promote-draft . --target paper --approver "your-name"
```
"""

    return f"""# {title}

> {summary}

## Overview

| Field | Value |
|-------|-------|
| Agent ID | `{artifact_set_id}` |
| Domain | `{domain}` |
| Created by | Aether Forge (fast mode) |
| Default environment | `sandbox` |
| Autonomous | {'Yes' if is_autonomous else 'No'} |

## Objective

{idea}

## Quick Start

```bash
# 1. Validate artifacts
forge validate .

# 2. Run scenario evaluations
forge eval-pack .

# 3. Start the agent in sandbox policy mode with simulated trading
forge run . --auto-approve --environment sandbox --mode paper --planner-mode ollama --planner-model gemma4

# 4. Start with autoresearch (self-improving)
forge run . --autoresearch --auto-approve --environment sandbox --mode paper --planner-mode ollama --planner-model gemma4

# 5. Deploy with Docker
docker-compose up -d
```

## Skills

{skills_list}

## Capabilities

Declared in `capability-manifest.json`. The agent can only use capabilities
listed there — the policy gate enforces this at runtime.

| Kind | Description |
|------|-------------|
| `data-source` | Read-only data (prices, balances, quotes) |
| `exchange-action` | Side-effecting trades (orders, swaps) — require approval |
| `wallet-action` | Wallet operations (signing, sending) — require approval |

{wallet_section}

{autonomy_section}

## Architecture

```
{slug}/
├── AGENT.md                 ← you are here
├── agent-spec.json          ← agent contract (objective, capabilities, eval)
├── capability-manifest.json ← declared capabilities + credential handles
├── policy-bundle.json       ← safety rules (notional limits, approvals)
├── scenario-pack.json       ← evaluation scenarios
├── strategy.json            ← tunable strategy parameters (autoresearch mutates this)
├── scaffold.manifest.json   ← ownership zones (generated vs user-owned)
├── aether-forge.json        ← local config (planner, runtime, wallet)
├── wallet.json              ← multi-chain wallet addresses (if created)
├── main.py                  ← standalone entry point
├── pyproject.toml           ← pip installable
├── Dockerfile               ← container deployment
├── docker-compose.yml       ← orchestration
├── src/
│   ├── strategy/
│   │   ├── router.py        ← YOUR execution router (routes by capability kind)
│   │   ├── price_feed.py    ← market data (Binance, CoinGecko, multi-source)
│   │   ├── momentum.py      ← trend detection and indicators
│   │   └── paper_trading.py ← simulated order execution + P&L
│   ├── generated/           ← auto-generated context (don't edit)
│   ├── policies/            ← user-owned policy overrides
│   ├── runtime/             ← runtime helpers (wallet, live exchange)
│   └── protocols/           ← ERC-8004/8126/8183/x402 config
├── docs/                    ← additional documentation
├── replays/                 ← tick replay files (created at runtime)
└── memory.db                ← persistent memory (created at runtime)
```

## Editing the Strategy

The strategy is in `strategy.json`:

```json
{{
  "parameters": {{
    "spread_pct": 1.0,        // % spread for limit orders
    "position_size_pct": 1.0,  // % of balance per trade
    "max_open_orders": 4,      // max simultaneous orders
    "momentum_threshold": 0.5, // momentum signal strength
    "volatility_multiplier": 1.0
  }},
  "entry_rules": [
    {{"condition": "...", "action": "buy"}},
    {{"condition": "...", "action": "sell"}}
  ],
  "success_metrics": {{
    "min_win_rate": 0.40,
    "max_drawdown_pct": 10.0
  }}
}}
```

## Editing the Router

The execution router is in `src/strategy/router.py`. It routes capabilities by `kind`:

- `data-source` → price feeds, balances, quotes
- `exchange-action` → limit orders, swaps, cancellations

To add a new provider or capability, add a handler method and update the routing logic.

## Governance

Every agent action goes through:

```
Planner → Policy Gate → Execute → Step Ledger
```

- **Policy gate** enforces: environment restrictions, notional limits, approval requirements
- **Step ledger** records every action for audit and replay
- **Approval** required for side-effecting actions in canary/production environments
- **Auto-approve** available in sandbox/paper for testing

## Deployment

### Docker

```bash
docker build -t {slug} .
docker run -p 8080:8080 {slug}
```

### docker-compose

```bash
docker-compose up -d
curl http://localhost:8080/health   # Health check
curl http://localhost:8080/status   # Agent status
curl http://localhost:8080/ticks    # Recent tick history
```

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `AETHER_FORGE_PLANNER_MODE` | LLM provider (ollama, openrouter, anthropic, etc.) |
| `AETHER_FORGE_PLANNER_MODEL` | Model name |
| `AETHER_FORGE_PLANNER_API_KEY` | API key (for cloud providers) |

## Promotion Pipeline

```
Sandbox → Paper → Canary Live → Production
```

Each promotion requires:
1. Passing scenario evaluations
2. Evidence-backed promotion record
3. Approver sign-off

```bash
forge promote-draft . --target paper --approver "your-name"
```
"""


def _project_strategy_json(title: str, domain: str) -> str:
    is_crypto = "crypto" in domain
    if is_crypto:
        strategy = {
            "version": 1,
            "parameters": {
                "spread_pct": 1.0,
                "position_size_pct": 1.0,
                "max_open_orders": 4,
                "momentum_threshold": 0.5,
                "volatility_multiplier": 1.0,
                "rebalance_interval_ticks": 6,
                "tokens": ["ETH"],
            },
            "entry_rules": [
                {"condition": "momentum.trend == 'bearish' AND change_last_candle_pct < -0.3", "action": "buy"},
                {"condition": "momentum.trend == 'bullish' AND change_last_candle_pct > 0.3", "action": "sell"},
            ],
            "success_metrics": {
                "min_win_rate": 0.40,
                "max_drawdown_pct": 10.0,
                "min_profit_per_tick": 0.0,
            },
            "history": [],
        }
    else:
        strategy = {
            "version": 1,
            "parameters": {
                "review_interval_ticks": 1,
                "max_items_per_tick": 5,
                "confidence_threshold": 0.7,
            },
            "entry_rules": [
                {"condition": "new context or requested task is available", "action": "read declared context"},
                {"condition": "policy gate denies an action", "action": "report the blocker and wait"},
            ],
            "success_metrics": {
                "policyViolationRate": 0,
                "minimumUsefulOutputs": 1,
            },
            "history": [],
        }
    return json.dumps(strategy, indent=2) + "\n"


def _project_dockerfile() -> str:
    return (
        "# syntax=docker/dockerfile:1.7\n"
        "# Multi-stage build for production deployment.\n"
        "# - Stage 1 builds dependencies into a wheel cache\n"
        "# - Stage 2 is a slim runtime image with a non-root user\n\n"
        "FROM python:3.12-slim AS builder\n"
        "WORKDIR /build\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends \\\n"
        "      build-essential git \\\n"
        "    && rm -rf /var/lib/apt/lists/*\n"
        "COPY pyproject.toml ./\n"
        "RUN pip install --no-cache-dir --upgrade pip && \\\n"
        "    pip install --no-cache-dir --target=/install \\\n"
        "      'aether-forge[all] @ git+https://github.com/HeyElsa/aether-forge.git'\n\n"
        "FROM python:3.12-slim AS runtime\n"
        "# Create non-root user\n"
        "RUN groupadd --system aether && useradd --system --gid aether --create-home aether\n"
        "ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1\n"
        "ENV PATH=/install/bin:$PATH PYTHONPATH=/install\n"
        "WORKDIR /app\n"
        "# Copy dependencies from builder\n"
        "COPY --from=builder /install /install\n"
        "# Copy agent code (owned by aether user)\n"
        "COPY --chown=aether:aether . /app/\n"
        "# Create runtime dirs with correct ownership\n"
        "RUN mkdir -p /app/logs /app/replays && chown -R aether:aether /app\n"
        "USER aether\n\n"
        "# Deep readiness check (uses /ready, not /health — distinguishes\n"
        "# liveness from agent-is-actually-working)\n"
        "HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \\\n"
        '  CMD python -c "import urllib.request; urllib.request.urlopen(\'http://localhost:8080/ready\')" || exit 1\n\n'
        "EXPOSE 8080\n"
        '# Default: paper mode with health + Prometheus metrics + JSON logs\n'
        'ENTRYPOINT ["forge", "run", ".", "--health-port", "8080", "--json-log", "/app/logs/agent.jsonl"]\n'
        'CMD ["--interval", "30", "--auto-approve", "--environment", "sandbox", "--mode", "paper"]\n'
    )


def _project_docker_compose(title: str, slug: str) -> str:
    return (
        "version: '3.8'\n\n"
        "services:\n"
        f"  {slug}:\n"
        "    build: .\n"
        "    container_name: " + slug + "\n"
        "    restart: unless-stopped\n"
        "    ports:\n"
        '      - "8080:8080"  # Health/status endpoint\n'
        "    volumes:\n"
        "      - ./memory.db:/app/memory.db\n"
        "      - ./replays:/app/replays\n"
        "      - ./logs:/app/logs\n"
        "    environment:\n"
        "      - AETHER_FORGE_PLANNER_MODE=heuristic\n"
        "      # For LLM-backed planning, set these instead:\n"
        "      # - AETHER_FORGE_PLANNER_MODE=anthropic\n"
        "      # - AETHER_FORGE_PLANNER_MODEL=claude-sonnet-4.5\n"
        "      # - AETHER_FORGE_PLANNER_API_KEY=your-key-here\n"
        "      # Local Ollama also works when explicitly selected:\n"
        "      # - AETHER_FORGE_PLANNER_MODE=ollama\n"
        "      # - AETHER_FORGE_PLANNER_MODEL=gemma4:latest\n"
        "      # - AETHER_FORGE_PLANNER_BASE_URL=http://host.docker.internal:11434/v1\n"
    )


def _project_tests_init() -> str:
    return '"""Tests for this generated agent. Run with: pytest tests/ -v"""\n'


def _project_test_agent(title: str) -> str:
    return (
        f'"""Smoke tests for {title}.\n\n'
        "These tests run with the offline HeuristicPlanner so they need no\n"
        "LLM API key. They verify that the agent's artifacts validate against\n"
        "the framework's JSON schemas and that every declared scenario reaches\n"
        "its expected outcome.\n"
        '"""\n\n'
        "from __future__ import annotations\n\n"
        "from pathlib import Path\n\n"
        "from aether_forge import (\n"
        "    HeuristicPlanner,\n"
        "    MockCryptoExecutionRouter,\n"
        "    evaluate_scenario_pack,\n"
        "    validate_artifact_directory,\n"
        ")\n\n"
        "AGENT_DIR = Path(__file__).resolve().parents[1]\n\n\n"
        "def test_artifacts_validate():\n"
        '    """All JSON artifacts conform to their schemas."""\n'
        "    result = validate_artifact_directory(AGENT_DIR)\n"
        "    assert result.ok, (\n"
        "        f\"Artifact validation failed:\\n\"\n"
        '        + "\\n".join(f"  {issue.code}: {issue.message}" for issue in result.issues)\n'
        "    )\n\n\n"
        "def test_scenario_pack_meets_expectations():\n"
        '    """Every scenario\'s actual stage outcome matches its expectedOutcome."""\n'
        "    summary, _sessions = evaluate_scenario_pack(\n"
        "        AGENT_DIR,\n"
        "        planner_factory=HeuristicPlanner,\n"
        "        execution_router_factory=MockCryptoExecutionRouter,\n"
        "    )\n"
        "    assert summary.total_scenarios > 0, \"scenario-pack.json defined no scenarios\"\n"
        "    assert summary.meets_expectations, (\n"
        '        f"Scenarios did not meet expectations: matched="\n'
        '        f"{summary.matched_expectations}/{summary.total_scenarios}, "\n'
        '        f"counts={summary.counts_by_stage}"\n'
        "    )\n"
    )


def _project_dockerignore() -> str:
    return (
        "# Build artifacts\n"
        "__pycache__/\n"
        "*.py[cod]\n"
        "*.egg-info/\n"
        ".pytest_cache/\n"
        ".ruff_cache/\n"
        ".mypy_cache/\n"
        "\n# Local state — never bake into images\n"
        ".env\n"
        ".env.*\n"
        "!.env.example\n"
        ".ows/\n"
        "wallet-backup-*.json\n"
        "memory.db\n"
        "memory.db-journal\n"
        "memory.db-wal\n"
        "memory.db-shm\n"
        "knowledge/\n"
        "replays/\n"
        "logs/\n"
        "x402_state.json\n"
        "x402_audit.jsonl\n"
        "halt\n"
        "\n# Dev / VCS noise\n"
        ".git/\n"
        ".gitignore\n"
        ".vscode/\n"
        ".idea/\n"
        ".venv/\n"
        "venv/\n"
        "node_modules/\n"
    )


def _project_makefile(slug: str) -> str:
    return (
        "# Generated agent Makefile — common workflows\n"
        ".PHONY: help validate eval-pack test run-paper run-sandbox run-live "
        "doctor halt resume clean docker-build docker-run\n\n"
        "help:\n"
        "\t@echo 'Common targets:'\n"
        "\t@echo '  make validate     — validate all artifacts (agent-spec, policy-bundle, ...)'\n"
        "\t@echo '  make eval-pack    — run the scenario pack against the runtime'\n"
        "\t@echo '  make test         — run pytest in tests/'\n"
        "\t@echo '  make run-paper    — run continuously in paper mode (real prices, simulated orders)'\n"
        "\t@echo '  make run-sandbox  — run continuously in sandbox (mock everything)'\n"
        "\t@echo '  make run-live     — run continuously in LIVE mode (requires enabled live adapter)'\n"
        "\t@echo '  make doctor       — diagnostic round-trip checks'\n"
        "\t@echo '  make halt         — activate kill switch (blocks all live x402 calls)'\n"
        "\t@echo '  make resume       — clear kill switch'\n"
        "\t@echo '  make docker-build — build the production Docker image'\n"
        "\t@echo '  make docker-run   — run the image with paper-mode defaults'\n"
        "\t@echo '  make clean        — remove caches, replays, logs, memory.db (PRESERVES wallet)'\n\n"
        "validate:\n"
        "\tforge validate .\n\n"
        "eval-pack:\n"
        "\tforge eval-pack .\n\n"
        "test:\n"
        "\tpytest tests/ -v\n\n"
        "run-paper:\n"
        "\tforge run . --auto-approve --environment sandbox --mode paper --interval 30 "
        "--health-port 8080 --json-log ./logs/agent.jsonl\n\n"
        "run-sandbox:\n"
        "\tforge run . --auto-approve --environment sandbox --mode simulated --interval 30\n\n"
        "run-live:\n"
        "\t@echo '⚠  Live mode requires an enabled live adapter and may submit real venue orders. Confirm by setting CONFIRM_LIVE=yes.'\n"
        "\t@[ \"$$CONFIRM_LIVE\" = \"yes\" ] || (echo 'aborted' && exit 1)\n"
        "\tforge run . --environment production --mode live --interval 30 "
        "--health-port 8080 --json-log ./logs/agent.jsonl\n\n"
        "doctor:\n"
        "\tforge doctor\n\n"
        "halt:\n"
        "\tforge halt .\n\n"
        "resume:\n"
        "\tforge resume .\n\n"
        "docker-build:\n"
        f"\tdocker build -t {slug}:latest .\n\n"
        "docker-run:\n"
        f"\tdocker run --rm -p 8080:8080 --env-file .env {slug}:latest\n\n"
        "clean:\n"
        "\trm -rf __pycache__ .pytest_cache .ruff_cache .mypy_cache \\\n"
        "\t       replays/ logs/ memory.db memory.db-* knowledge/\n"
    )


def _project_env_example() -> str:
    return (
        "# Copy to .env and fill in. NEVER commit .env to git.\n"
        "# The framework reads these env vars at runtime; precedence is\n"
        "# CLI flag > env var > aether-forge.json > built-in default.\n\n"
        "# ---- LLM providers (pick one — auto-detect probes cloud keys first) ----\n"
        "# Anthropic\n"
        "# ANTHROPIC_API_KEY=sk-ant-...\n\n"
        "# OpenAI\n"
        "# OPENAI_API_KEY=sk-...\n\n"
        "# Google Gemini\n"
        "# GEMINI_API_KEY=...\n"
        "# GOOGLE_API_KEY=...\n\n"
        "# OpenRouter (gateway to many providers)\n"
        "# OPENROUTER_API_KEY=sk-or-...\n\n"
        "# Local Ollama (no key needed; auto-detected only when no cloud key is set)\n"
        "# AETHER_FORGE_PLANNER_MODE=ollama\n"
        "# AETHER_FORGE_PLANNER_MODEL=gemma4:latest\n\n"
        "# ---- Wallet (only if you ran generate-fast --wallet) ----\n"
        "# OWS_API_KEY=ows_key_...\n\n"
        "# ---- Local registry override (defaults to ~/.aether-forge/agents.db) ----\n"
        "# AETHER_FORGE_REGISTRY_PATH=/var/lib/aether-forge/agents.db\n\n"
        "# ---- MCP server credentials (only if your aether-forge.json declares them) ----\n"
        "# GITHUB_TOKEN=ghp_...\n"
    )


def _strategy_init_module() -> str:
    return (
        '"""Agent strategy module — project-specific routing and helpers.\n\n'
        "This code is part of YOUR agent, not the framework.\n"
        'Edit freely to implement your agent behavior.\n"""\n'
    )


def _strategy_price_feed_module() -> str:
    return '''"""Real-time price feeds from Binance public API.

No API key required. Fetches spot prices and 30-minute candles.
"""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib import request as urllib_request

logger = logging.getLogger(__name__)

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/24hr"
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"


def fetch_price(token: str, *, request_fn=None) -> dict[str, Any]:
    """Fetch current price + 24h stats for a token from Binance."""
    symbol = f"{token.upper()}USDT"
    fetcher = request_fn or _binance_get
    data = fetcher(f"{BINANCE_TICKER_URL}?symbol={symbol}")
    price = float(data["lastPrice"])
    logger.info("Price %s: $%.2f (24h: %s%%)", token, price, data.get("priceChangePercent", "?"))
    return {
        "token": token,
        "price_usd": price,
        "change_24h_pct": float(data.get("priceChangePercent", 0)),
        "volume_24h_usd": float(data.get("quoteVolume", 0)),
        "high_24h": float(data.get("highPrice", 0)),
        "low_24h": float(data.get("lowPrice", 0)),
        "source": "binance-live",
    }


def fetch_candles(token: str, *, interval: str = "30m", limit: int = 10, request_fn=None) -> list[dict[str, Any]]:
    """Fetch recent candles for a token from Binance."""
    symbol = f"{token.upper()}USDT"
    fetcher = request_fn or _binance_get
    raw = fetcher(f"{BINANCE_KLINES_URL}?symbol={symbol}&interval={interval}&limit={limit}")
    candles = []
    for c in raw:
        candles.append({
            "open": float(c[1]),
            "high": float(c[2]),
            "low": float(c[3]),
            "close": float(c[4]),
            "volume": float(c[5]),
        })
    return candles


def _binance_get(url: str) -> Any:
    req = urllib_request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib_request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read().decode("utf8"))
'''


def _strategy_momentum_module() -> str:
    return '''"""Momentum indicators computed from candle data.

Simple trend detection, volatility, and moving average crossovers.
"""

from __future__ import annotations

from typing import Any


def compute_momentum(candles: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute momentum indicators from candle data."""
    if len(candles) < 3:
        return {"trend": "insufficient-data", "num_candles": len(candles)}

    closes = [c["close"] for c in candles]
    current = closes[-1]
    prev = closes[-2]
    avg_3 = sum(closes[-3:]) / 3
    avg_all = sum(closes) / len(closes)

    trend = "bullish" if current > avg_3 > avg_all else ("bearish" if current < avg_3 < avg_all else "neutral")

    recent_highs = [c["high"] for c in candles[-5:]]
    recent_lows = [c["low"] for c in candles[-5:]]
    volatility_pct = ((max(recent_highs) - min(recent_lows)) / current * 100) if current > 0 else 0

    return {
        "trend": trend,
        "price_vs_avg3_pct": round((current / avg_3 - 1) * 100, 3) if avg_3 else 0,
        "price_vs_avg_all_pct": round((current / avg_all - 1) * 100, 3) if avg_all else 0,
        "change_last_candle_pct": round((current / prev - 1) * 100, 3) if prev else 0,
        "volatility_5_candle_pct": round(volatility_pct, 3),
        "num_candles": len(candles),
    }
'''


def _strategy_paper_trading_module() -> str:
    return '''"""Paper trading engine with balance tracking and P&L.

Simulates order execution against real market prices.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class PaperTradingEngine:
    """Simulated order book with balance and holdings tracking."""

    def __init__(self, initial_balance_usd: float = 10_000.0) -> None:
        self.initial_balance_usd = initial_balance_usd
        self.balance_usd = initial_balance_usd
        self.holdings: dict[str, float] = {}
        self.order_book: list[dict[str, Any]] = []
        self.trade_log: list[dict[str, Any]] = []
        self._order_counter = 0
        self._prices: dict[str, float] = {}

    def update_price(self, token: str, price: float) -> None:
        self._prices[token] = price

    def create_limit_order(self, *, side: str, token: str, amount: float, limit_price: float) -> dict[str, Any]:
        self._order_counter += 1
        order_id = f"paper_{self._order_counter}"
        notional = amount * limit_price

        # Validate
        if side == "buy" and notional > self.balance_usd:
            return {"order_id": order_id, "status": "rejected", "reason": f"Insufficient balance: need ${notional:.2f}, have ${self.balance_usd:.2f}"}
        if side == "sell" and amount > self.holdings.get(token, 0):
            return {"order_id": order_id, "status": "rejected", "reason": f"Insufficient {token}: need {amount}, have {self.holdings.get(token, 0)}"}

        order = {
            "order_id": order_id,
            "side": side,
            "token": token,
            "amount": amount,
            "limit_price": limit_price,
            "notional_usd": round(notional, 2),
            "status": "filled",  # Immediate fill in paper mode
            "source": "paper",
        }

        # Execute fill
        if side == "buy":
            self.balance_usd -= notional
            self.holdings[token] = self.holdings.get(token, 0) + amount
        elif side == "sell":
            self.balance_usd += notional
            self.holdings[token] = self.holdings.get(token, 0) - amount

        self.order_book.append(order)
        self.trade_log.append({**order, "action": "fill"})

        logger.info("Paper fill: %s %.6f %s @ $%.2f | Balance: $%.2f | %s: %.6f",
                     side, amount, token, limit_price, self.balance_usd, token, self.holdings.get(token, 0))
        return order

    def get_orders(self) -> list[dict[str, Any]]:
        return list(self.order_book)

    def cancel_order(self, order_id: str) -> dict[str, Any]:
        for order in self.order_book:
            if order["order_id"] == order_id and order["status"] == "open":
                order["status"] = "cancelled"
                return {"order_id": order_id, "status": "cancelled"}
        return {"order_id": order_id, "status": "not-found"}

    def portfolio_summary(self) -> dict[str, Any]:
        total_value = self.balance_usd
        positions = {}
        for token, amount in self.holdings.items():
            price = self._prices.get(token, 0)
            value = amount * price
            total_value += value
            positions[token] = {"amount": round(amount, 8), "price": price, "value_usd": round(value, 2)}

        pnl = total_value - self.initial_balance_usd
        return {
            "cash_usd": round(self.balance_usd, 2),
            "positions": positions,
            "total_value_usd": round(total_value, 2),
            "pnl_usd": round(pnl, 2),
            "pnl_pct": round(pnl / self.initial_balance_usd * 100, 3) if self.initial_balance_usd else 0,
            "open_orders": len([o for o in self.order_book if o.get("status") == "open"]),
            "filled_orders": len([o for o in self.order_book if o.get("status") == "filled"]),
            "total_trades": len(self.trade_log),
        }
'''


def _strategy_router_module(title: str, domain: str) -> str:
    return '''"""Execution router for this agent — ''' + title + '''.

THIS FILE IS PART OF YOUR AGENT, NOT THE FRAMEWORK.
Edit it to add custom providers, change routing logic, or add new capabilities.

Routes capability executions based on kind and provider fields
from the capability manifest. Supports any skill provider.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from aether_forge.runtime import ExecutionResult, RuntimeSession, StepProposal

logger = logging.getLogger(__name__)

# Load capabilities from the manifest at import time
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST_PATH = _PROJECT_ROOT / "capability-manifest.json"
_CAPABILITIES: dict[str, dict[str, Any]] = {}
if _MANIFEST_PATH.exists():
    _raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf8"))
    _CAPABILITIES = {c["capabilityId"]: c for c in _raw.get("capabilities", []) if "capabilityId" in c}


class AgentExecutionRouter:
    """Capability-driven router that dispatches by kind and provider.

    Reads the capability manifest to determine how to handle each
    capability. No hardcoded provider names — add handlers for any
    skill provider your agent uses.
    """

    def __init__(self, config=None) -> None:
        from aether_forge.scaffold_router import StrategyConfig
        self.config = config or StrategyConfig()
        self.mode = self.config.mode

        from src.strategy.paper_trading import PaperTradingEngine
        self.engine = PaperTradingEngine(
            initial_balance_usd=self.config.initial_balance_usd,
        )
        self._price_history: list[dict[str, Any]] = []

        # ----- Data layer ------------------------------------------------
        # The DataRouter is the single entry point for all read-only data.
        # Sources are selected by mode:
        #   paper -> free public sources (Binance, CoinGecko)
        #   live  -> paid x402 sources (Elsa) with free fallback chain
        # See src/aether_forge/data_layer.py for the full source catalog.
        self.data_router = self._build_data_router()

    def _build_data_router(self):
        """Build the per-mode data router. Override to add custom sources."""
        from aether_forge.data_layer import (
            DataRouter,
            build_binance_source,
            build_coingecko_source,
            build_elsa_source,
        )

        sources = []
        if self.mode == "live":
            # Live mode: prefer paid Elsa (richer data, includes swaps) and
            # fall back to free Binance/CoinGecko if x402 fails or is gated.
            try:
                project_root = Path(__file__).resolve().parents[2]
                sources.append(build_elsa_source(
                    project_root,
                    confirmed=True,
                    max_per_call_usd=0.05,
                    max_session_usd=1.0,
                    chain="base",
                ))
            except Exception as error:
                logger.warning("Elsa x402 source unavailable: %s", error)
        sources.append(build_binance_source())
        sources.append(build_coingecko_source())
        return DataRouter(sources)

    @staticmethod
    def _to_binance_symbol(token: str) -> str:
        """Map a token symbol like ETH to a Binance trading pair like ETHUSDT."""
        token = (token or "ETH").upper()
        if token.endswith("USDT") or token.endswith("USDC"):
            return token
        return f"{token}USDT"

    # Minimal symbol -> contract address registry per chain. Edit/extend
    # as your agent's universe grows. Required by some x402 providers
    # (e.g. Elsa) which key off contract addresses, not symbols.
    _TOKEN_REGISTRY: dict[str, dict[str, str]] = {
        "base": {
            "ETH":  "0x4200000000000000000000000000000000000006",  # WETH on Base
            "WETH": "0x4200000000000000000000000000000000000006",
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "USDbC": "0xd9aAEc86B65D86f6A7B5B1b0c42FFA531710b6CA",
            "CBBTC": "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",
            "DAI":  "0x50c5725949A6F0c72E6C4a641F24049A917DB0Cb",
        },
        "ethereum": {
            "ETH":  "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "USDC": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
            "USDT": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
        },
    }

    def _resolve_token_address(self, token: str) -> str | None:
        """Resolve a token symbol to its contract address on the configured chain."""
        chain = (self.config.chain or "base").lower()
        return self._TOKEN_REGISTRY.get(chain, {}).get((token or "").upper())

    def execute(
        self,
        session: RuntimeSession,
        proposal: StepProposal,
        capability: dict[str, Any],
    ) -> ExecutionResult:
        cap_id = proposal.capability_id or ""
        payload = proposal.payload or {}
        kind = capability.get("kind", "")
        provider = capability.get("provider", "")

        # Route by capability kind
        if kind == "data-source":
            return self._handle_data_source(cap_id, payload, capability)
        if kind == "exchange-action":
            return self._handle_exchange_action(session, cap_id, payload, capability)
        if kind == "wallet-action":
            return self._handle_wallet_action(cap_id, payload, capability)
        if kind == "tool":
            return self._handle_tool(cap_id, payload, capability)

        # Generic fallback
        return ExecutionResult(success=True, output={"capability": cap_id, "kind": kind, "handled": False})

    # ------------------------------------------------------------------
    # Data source handlers (read-only, no side effects)
    # ------------------------------------------------------------------

    def _handle_data_source(self, cap_id: str, payload: dict, capability: dict) -> ExecutionResult:
        # Price fetching — works for any provider that offers price data
        if "price" in cap_id or "token-price" in cap_id:
            return self._fetch_price(payload)

        # Balance / portfolio — try Elsa via data router in live mode,
        # otherwise return paper engine state.
        if "balance" in cap_id or "portfolio" in cap_id:
            if self.mode == "live":
                try:
                    result = self.data_router.fetch(
                        "get-portfolio" if "portfolio" in cap_id else "get-balances",
                        _body={
                            "chain": self.config.chain or "base",
                            "address": payload.get("address") or self._wallet_address(),
                        },
                    )
                    return ExecutionResult(success=True, output={
                        "source": result.source,
                        "data": result.data,
                        "cost_usd": result.cost.amount_usd,
                    })
                except Exception as error:
                    logger.warning("Live portfolio fetch failed, using paper engine: %s", error)
            return ExecutionResult(success=True, output=self.engine.portfolio_summary())

        # Order listing — query Elsa in live mode, fall through to engine otherwise
        if "order" in cap_id and ("get" in cap_id or "list" in cap_id):
            if self.mode == "live":
                try:
                    result = self.data_router.fetch(
                        "get-limit-orders",
                        _body={
                            "chain": self.config.chain or "base",
                            "address": payload.get("address") or self._wallet_address(),
                        },
                    )
                    return ExecutionResult(success=True, output={
                        "source": result.source,
                        "orders": result.data,
                        "cost_usd": result.cost.amount_usd,
                    })
                except Exception as error:
                    logger.warning("Live order list failed, using paper engine: %s", error)
            return ExecutionResult(success=True, output={
                "orders": self.engine.get_orders(), "total": len(self.engine.order_book),
            })

        # Swap quote — Elsa in live mode (real on-chain quote), engine sim otherwise
        if "quote" in cap_id or "swap-quote" in cap_id:
            from_token = payload.get("from_token", "USDC")
            to_token = payload.get("to_token", "ETH")
            amount = float(payload.get("amount", 100))
            if self.mode == "live":
                try:
                    result = self.data_router.fetch(
                        "get-swap-quote",
                        _body={
                            "chain": self.config.chain or "base",
                            "from_token": from_token,
                            "to_token": to_token,
                            "amount": amount,
                            "address": payload.get("address") or self._wallet_address(),
                        },
                    )
                    return ExecutionResult(success=True, output={
                        "source": result.source,
                        "quote": result.data,
                        "cost_usd": result.cost.amount_usd,
                    })
                except Exception as error:
                    logger.warning("Live swap quote failed, using paper engine: %s", error)
            price = self.engine._prices.get(to_token, 3500.0)
            return ExecutionResult(success=True, output={
                "from_token": from_token, "to_token": to_token,
                "output_amount": round(amount / price, 8) if price else 0, "price": price,
                "source": "simulated",
            })

        # Try the data router for any capability whose name matches a known
        # source capability (e.g., gas-prices, transaction-status, candles).
        # The router will return the first source that supports the slug.
        try:
            normalized = cap_id.replace("_", "-")
            for slug in (cap_id, normalized, normalized.split(".")[-1]):
                for source in self.data_router.sources:
                    if source.supports(slug):
                        result = self.data_router.fetch(slug, _body={"chain": self.config.chain or "base", **payload})
                        return ExecutionResult(success=True, output={
                            "source": result.source,
                            "data": result.data,
                            "cost_usd": result.cost.amount_usd,
                        })
        except Exception as error:
            logger.debug("Data router could not handle %s: %s", cap_id, error)

        # Generic data source
        return ExecutionResult(success=True, output={"capability": cap_id, "source": self.mode})

    def _wallet_address(self) -> str:
        """Read the agent's primary EVM address from wallet.json (cached)."""
        if not hasattr(self, "_cached_wallet_address"):
            try:
                wallet_path = Path(__file__).resolve().parents[2] / "wallet.json"
                wallet = json.loads(wallet_path.read_text(encoding="utf8"))
                self._cached_wallet_address = (
                    wallet.get("addresses", {}).get("evm")
                    or next((a["address"] for a in wallet.get("accounts", []) if a.get("chainId", "").startswith("eip155:")), "")
                )
            except Exception:
                self._cached_wallet_address = ""
        return self._cached_wallet_address

    # ------------------------------------------------------------------
    # Exchange action handlers (side effects — orders, swaps)
    # ------------------------------------------------------------------

    def _handle_exchange_action(self, session: RuntimeSession, cap_id: str, payload: dict, capability: dict) -> ExecutionResult:
        # Live mode: route through the project-local live exchange adapter.
        if self.mode == "live":
            return self._handle_live_exchange_action(session, cap_id, payload, capability)

        # Create order (limit or market) — paper/simulated mode
        if "create" in cap_id or ("order" in cap_id and "cancel" not in cap_id and "get" not in cap_id):
            result = self.engine.create_limit_order(
                side=payload.get("side", "buy"),
                token=payload.get("token", "ETH"),
                amount=float(payload.get("amount", 0.1)),
                limit_price=float(payload.get("limit_price", 0)),
            )
            if result.get("status") == "rejected":
                return ExecutionResult(success=False, failure_reason=result.get("reason", ""))
            return ExecutionResult(success=True, output=result)

        # Cancel order
        if "cancel" in cap_id:
            return ExecutionResult(success=True, output=self.engine.cancel_order(payload.get("order_id", "")))

        # Swap (treat as market order)
        if "swap" in cap_id:
            token = payload.get("to_token", "ETH")
            amount = float(payload.get("amount", 100))
            price = self.engine._prices.get(token, 3500.0)
            return ExecutionResult(success=True, output=self.engine.create_limit_order(
                side="buy", token=token, amount=amount / price if price else 0, limit_price=price,
            ))

        return ExecutionResult(success=True, output={"capability": cap_id, "exchange_action": True})

    # ------------------------------------------------------------------
    # Wallet + tool handlers
    # ------------------------------------------------------------------

    def _handle_live_exchange_action(self, session: RuntimeSession, cap_id: str, payload: dict, capability: dict) -> ExecutionResult:
        """Live mode: route through the project-local live exchange adapter."""
        from aether_forge.crypto import ManifestCredentialResolver
        from aether_forge.scaffold import load_scaffold_live_exchange_adapter
        from pathlib import Path

        project_root = Path(__file__).resolve().parents[2]
        adapter = load_scaffold_live_exchange_adapter(project_root)
        if adapter is None:
            return ExecutionResult(
                success=False,
                failure_reason=(
                    "Live exchange execution is disabled. Implement src/runtime/live_exchange.py, "
                    "set LIVE_EXCHANGE_ENABLED=True, and enable adapters.liveExchange in aether-forge.json."
                ),
            )

        handle_id = capability.get("credentialHandleId")
        if not isinstance(handle_id, str):
            return ExecutionResult(success=False, failure_reason="Live exchange capability is missing credentialHandleId")
        try:
            lease = ManifestCredentialResolver().resolve(
                handle_id,
                session.environment,
                session.artifacts.capability_manifest,
            )
        except Exception as error:
            return ExecutionResult(success=False, failure_reason=f"Live exchange credential resolution failed: {error}")

        venue = capability.get("providerConstraints", {}).get("venue", capability.get("provider", "live-exchange"))

        if "create" in cap_id or ("order" in cap_id and "cancel" not in cap_id):
            try:
                token = payload.get("token") or payload.get("symbol") or capability.get("providerConstraints", {}).get("symbol", "ETH")
                symbol = self._symbol(str(token))
                amount = float(payload.get("amount", 0.0))
                limit_price = float(payload.get("limit_price", payload.get("price", 0.0)))
                requested_notional_usd = float(payload.get("requested_notional_usd", amount * limit_price))
                result = adapter.place_order(
                    venue=str(venue),
                    symbol=symbol,
                    requested_notional_usd=requested_notional_usd,
                    side=str(payload.get("side", "buy")),
                    credential_lease=lease,
                    metadata={"capabilityId": cap_id, "payload": payload},
                )
                return ExecutionResult(success=True, output=result)
            except Exception as error:
                return ExecutionResult(success=False, failure_reason=f"Live execution failed: {error}")

        if "cancel" in cap_id:
            try:
                return ExecutionResult(success=True, output=adapter.cancel_order(
                    venue=str(venue),
                    order_id=str(payload.get("order_id", "")),
                    credential_lease=lease,
                ))
            except Exception as error:
                return ExecutionResult(success=False, failure_reason=f"Live cancel failed: {error}")

        return ExecutionResult(success=False, failure_reason=f"Live exchange action {cap_id} is not implemented by the generated router")

    def _handle_wallet_action(self, cap_id: str, payload: dict, capability: dict) -> ExecutionResult:
        return ExecutionResult(success=True, output={"capability": cap_id, "wallet": True, "mock": True})

    def _handle_tool(self, cap_id: str, payload: dict, capability: dict) -> ExecutionResult:
        return ExecutionResult(success=True, output={"capability": cap_id, "tool": True})

    # ------------------------------------------------------------------
    # Price fetching (real or simulated based on mode)
    # ------------------------------------------------------------------

    def _fetch_price(self, payload: dict) -> ExecutionResult:
        token = payload.get("token", "ETH")
        cost_usd = 0.0
        source_name = "simulated"

        # Live mode: prefer paid Elsa source, fall back to free sources via the router
        if self.mode == "live":
            try:
                token_address = self._resolve_token_address(token)
                body = {"chain": self.config.chain or "base"}
                if token_address:
                    body["token_address"] = token_address
                else:
                    body["token"] = token  # let upstream resolve by symbol if it can
                result = self.data_router.fetch("get-token-price", _body=body)
                price_usd = self._extract_price_usd(result.data, token)
                if price_usd is not None:
                    self.engine.update_price(token, price_usd)
                    self._price_history.append({"token": token, "price": price_usd, "source": result.source})
                    return ExecutionResult(success=True, output={
                        "token": token,
                        "price_usd": price_usd,
                        "source": result.source,
                        "cost_usd": result.cost.amount_usd,
                        "paid": result.cost.paid,
                    })
            except Exception as error:
                logger.warning("Elsa x402 price fetch failed for %s: %s", token, error)

        # Paper mode (or live fallback): use the free Binance source via the router
        try:
            symbol = self._to_binance_symbol(token)
            result = self.data_router.call_source("binance", "spot-price", symbol=symbol)
            body = result.data or {}
            price_usd = float(body.get("price", 0)) if isinstance(body, dict) else 0.0
            if price_usd > 0:
                # Optionally get candles + momentum from the local helper if it exists
                try:
                    from src.strategy.price_feed import fetch_candles
                    from src.strategy.momentum import compute_momentum
                    candles = fetch_candles(token)
                    momentum = compute_momentum(candles)
                except Exception:
                    candles = []
                    momentum = None

                self.engine.update_price(token, price_usd)
                self._price_history.append({"token": token, "price": price_usd, "source": result.source})
                return ExecutionResult(success=True, output={
                    "token": token,
                    "price_usd": price_usd,
                    "source": result.source,
                    "cost_usd": 0.0,
                    "candles_30m": candles[-5:] if candles else [],
                    "momentum": momentum,
                })
        except Exception as error:
            logger.warning("Free price source failed for %s: %s, using simulated", token, error)

        # Simulated fallback (only if every real source failed)
        import random
        price = self.config.price_data.get(token, 3500.0) * (1 + random.uniform(-0.02, 0.02))
        self.config.price_data[token] = price
        self.engine.update_price(token, price)
        self._price_history.append({"token": token, "price": round(price, 2), "source": "simulated"})
        return ExecutionResult(success=True, output={"token": token, "price_usd": round(price, 2), "source": "simulated"})

    @staticmethod
    def _extract_price_usd(data: Any, token: str) -> float | None:
        """Best-effort extraction of a USD price from heterogeneous source responses."""
        if data is None:
            return None
        if isinstance(data, (int, float)):
            return float(data)
        if isinstance(data, dict):
            # Common shapes: {"price_usd": ...}, {"price": ...}, {"ETH": {"usd": ...}}
            for key in ("price_usd", "price", "usd", "value"):
                if key in data and isinstance(data[key], (int, float, str)):
                    try:
                        return float(data[key])
                    except (TypeError, ValueError):
                        pass
            token_key = token.upper()
            if token_key in data and isinstance(data[token_key], dict):
                inner = data[token_key]
                if "usd" in inner:
                    try:
                        return float(inner["usd"])
                    except (TypeError, ValueError):
                        pass
            for v in data.values():
                if isinstance(v, dict):
                    found = AgentExecutionRouter._extract_price_usd(v, token)
                    if found is not None:
                        return found
        return None

    def cost_summary(self) -> dict[str, Any]:
        """Aggregate cost across all data sources used by this router."""
        return self.data_router.status()

    @property
    def price_history(self) -> list[dict[str, Any]]:
        return list(self._price_history)


def build_router(config=None):
    """Build the execution router for this agent."""
    return AgentExecutionRouter(config=config)
'''


def _looks_like_crypto(idea: str) -> bool:
    lowered = idea.lower()
    return any(hint in lowered for hint in CRYPTO_HINTS)


def _summarize_idea(idea: str) -> str:
    cleaned = " ".join(idea.split())
    return cleaned[:160] if len(cleaned) > 160 else cleaned


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"

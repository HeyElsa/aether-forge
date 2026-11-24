from __future__ import annotations

import json
import py_compile
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from aether_forge.artifacts import validate_artifact_directory
from aether_forge.evals import evaluate_scenario_pack
from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set


def test_generate_fast_crypto_artifact_set_is_valid() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))

    try:
        generated = generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        result = validate_artifact_directory(generated.output_directory)

        assert generated.domain == "crypto-trading"
        assert result.ok is True
        assert result.issues == []
    finally:
        rmtree(output_dir)


def test_generate_fast_general_artifact_set_is_valid() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))

    try:
        generated = generate_fast_artifact_set(
            FastGenerateRequest(
                name="Research Brief Agent",
                idea="Build an agent that reads project context and produces a weekly research brief.",
                output_directory=output_dir,
            )
        )

        result = validate_artifact_directory(generated.output_directory)

        assert generated.domain == "general-agent"
        assert result.ok is True
        assert result.issues == []
    finally:
        rmtree(output_dir)


def test_generate_fast_general_scaffold_uses_general_defaults() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="Research Brief Agent",
                idea="Summarize a webpage and save a short note.",
                output_directory=output_dir,
            )
        )

        strategy = json.loads((output_dir / "strategy.json").read_text(encoding="utf8"))
        agent_doc = (output_dir / "AGENT.md").read_text(encoding="utf8")
        protocol_source = (output_dir / "src" / "protocols" / "__init__.py").read_text(encoding="utf8")

        assert "spread_pct" not in strategy["parameters"]
        assert "review_interval_ticks" in strategy["parameters"]
        assert "paper trading" not in agent_doc.lower()
        assert "limit orders" not in agent_doc.lower()
        assert '"x402Support": False' in protocol_source
        assert '"budgetLimitUsd": 0.0' in protocol_source
    finally:
        rmtree(output_dir)


def test_generate_fast_crypto_scaffold_keeps_trading_defaults() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        strategy = json.loads((output_dir / "strategy.json").read_text(encoding="utf8"))
        protocol_source = (output_dir / "src" / "protocols" / "__init__.py").read_text(encoding="utf8")
        readme = (output_dir / "README.md").read_text(encoding="utf8")
        makefile = (output_dir / "Makefile").read_text(encoding="utf8")
        dockerfile = (output_dir / "Dockerfile").read_text(encoding="utf8")

        assert "spread_pct" in strategy["parameters"]
        assert strategy["parameters"]["tokens"] == ["ETH"]
        assert '"x402Support": True' in protocol_source
        assert '"budgetLimitUsd": 50.0' in protocol_source
        assert "--environment sandbox --mode paper" in readme
        assert "--environment sandbox --mode paper" in makefile
        assert '"--environment", "sandbox", "--mode", "paper"' in dockerfile
        assert "--environment production --mode live" in makefile
    finally:
        rmtree(output_dir)


def test_generated_crypto_artifact_set_runs_under_native_planner() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        summary, _sessions = evaluate_scenario_pack(output_dir)

        assert summary.meets_expectations is True
        assert summary.total_scenarios == 2
    finally:
        rmtree(output_dir)


def test_generated_general_artifact_set_runs_under_native_planner() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="Research Brief Agent",
                idea="Build an agent that reads project context and produces a weekly research brief.",
                output_directory=output_dir,
            )
        )

        summary, _sessions = evaluate_scenario_pack(output_dir)

        assert summary.meets_expectations is True
        assert summary.total_scenarios == 1
    finally:
        rmtree(output_dir)


def test_generate_fast_writes_scaffold_code_files() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))

    try:
        generated = generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        expected_files = {
            output_dir / "aether-forge.json",
            output_dir / "aether-forge.example.json",
            output_dir / "README.md",
            output_dir / "docs" / "README.md",
            output_dir / "docs" / "live-exchange.md",
            output_dir / "docs" / "planner.md",
            output_dir / "src" / "__init__.py",
            output_dir / "src" / "generated" / "__init__.py",
            output_dir / "src" / "generated" / "agent_context.py",
            output_dir / "src" / "policies" / "__init__.py",
            output_dir / "src" / "policies" / "policy_bundle.py",
            output_dir / "src" / "runtime" / "__init__.py",
            output_dir / "src" / "runtime" / "run_agent.py",
            output_dir / "src" / "runtime" / "wallet.py",
            output_dir / "src" / "runtime" / "live_exchange.py",
        }

        assert expected_files.issubset(set(generated.scaffold_files))
        for file_path in expected_files:
            assert file_path.exists()

        py_compile.compile(str(output_dir / "src" / "generated" / "agent_context.py"), doraise=True)
        py_compile.compile(str(output_dir / "src" / "policies" / "policy_bundle.py"), doraise=True)
        py_compile.compile(str(output_dir / "src" / "runtime" / "run_agent.py"), doraise=True)
        py_compile.compile(str(output_dir / "src" / "runtime" / "wallet.py"), doraise=True)
        py_compile.compile(str(output_dir / "src" / "runtime" / "live_exchange.py"), doraise=True)
    finally:
        rmtree(output_dir)


def test_generate_fast_strategy_file_marks_rule_provenance() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))
    strategy_path = output_dir / "input-strategy.md"
    strategy_path.write_text(
        "# Basis capture\n\n"
        "If perp-spot basis > 20 bps: open 0.5 BTC spot long and 0.5 BTC perp short.\n"
        "Exit when basis < 10 bps.\n",
        encoding="utf8",
    )

    try:
        generated = generate_fast_artifact_set(
            FastGenerateRequest(
                name="Basis Provenance Agent",
                idea="Delta neutral BTC basis capture on spot and perp markets.",
                output_directory=output_dir,
                strategy_file=str(strategy_path),
            )
        )

        strategy = json.loads((output_dir / "strategy.json").read_text(encoding="utf8"))
        # No BUY/SELL lines were extractable — the template rules survive,
        # and that must be visible in the artifact and the summary card.
        assert strategy["entry_rules_provenance"] == "template_default"
        assert strategy["parse_report"]["entry_rules_extracted"] == 0
        assert generated.agent_summary.strategy_rules_source == "template_default"
    finally:
        rmtree(output_dir)


def test_generate_fast_strategy_file_with_rules_marks_file_provenance() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-generate-"))
    strategy_path = output_dir / "input-strategy.md"
    strategy_path.write_text(
        "# Momentum\n\n"
        "- BUY when: momentum turns bearish and price dips 0.3%\n"
        "- SELL when: momentum turns bullish and price rips 0.3%\n",
        encoding="utf8",
    )

    try:
        generated = generate_fast_artifact_set(
            FastGenerateRequest(
                name="Momentum Provenance Agent",
                idea="Momentum swing trading agent for BTC.",
                output_directory=output_dir,
                strategy_file=str(strategy_path),
            )
        )

        strategy = json.loads((output_dir / "strategy.json").read_text(encoding="utf8"))
        assert strategy["entry_rules_provenance"] == "strategy_file"
        assert strategy["parse_report"]["entry_rules_extracted"] == 2
        assert generated.agent_summary.strategy_rules_source == "strategy_file"
    finally:
        rmtree(output_dir)

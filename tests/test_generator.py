from __future__ import annotations

from pathlib import Path
import py_compile
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

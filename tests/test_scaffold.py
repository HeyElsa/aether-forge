from __future__ import annotations

import json
from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp

from aether_forge.cli import main
from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
from aether_forge.scaffold import build_scaffold_live_exchange_router, inspect_scaffold_live_exchange_status, load_scaffold_live_exchange_adapter


def test_generated_scaffold_live_exchange_loader_returns_none_by_default() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-scaffold-live-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        adapter = load_scaffold_live_exchange_adapter(output_dir)
        status = inspect_scaffold_live_exchange_status(output_dir)

        assert adapter is None
        assert status["status"] == "disabled"
    finally:
        rmtree(output_dir)


def test_generated_scaffold_live_exchange_loader_can_enable_project_adapter() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-scaffold-live-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        live_exchange_path = output_dir / "src" / "runtime" / "live_exchange.py"
        source = live_exchange_path.read_text(encoding="utf8")
        source = source.replace("LIVE_EXCHANGE_ENABLED = False", "LIVE_EXCHANGE_ENABLED = True", 1)
        live_exchange_path.write_text(source, encoding="utf8")

        config_path = output_dir / "aether-forge.json"
        config = json.loads(config_path.read_text(encoding="utf8"))
        config["adapters"]["liveExchange"]["enabled"] = True
        config_path.write_text(f"{json.dumps(config, indent=2)}\n", encoding="utf8")

        adapter = load_scaffold_live_exchange_adapter(output_dir)
        router = build_scaffold_live_exchange_router(output_dir)
        status = inspect_scaffold_live_exchange_status(output_dir)

        assert adapter is not None
        assert hasattr(adapter, "place_order")
        assert hasattr(router.live_exchange_adapter, "place_order")
        assert status["status"] == "ready"
    finally:
        rmtree(output_dir)


def test_generated_scaffold_live_exchange_loader_stays_disabled_without_config_enable() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-scaffold-live-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        live_exchange_path = output_dir / "src" / "runtime" / "live_exchange.py"
        source = live_exchange_path.read_text(encoding="utf8")
        source = source.replace("LIVE_EXCHANGE_ENABLED = False", "LIVE_EXCHANGE_ENABLED = True", 1)
        live_exchange_path.write_text(source, encoding="utf8")

        adapter = load_scaffold_live_exchange_adapter(output_dir)
        status = inspect_scaffold_live_exchange_status(output_dir)

        assert adapter is None
        assert status["status"] == "disabled"
    finally:
        rmtree(output_dir)


def test_scaffold_live_status_cli_reports_disabled_project() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-scaffold-live-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        exit_code = main(["scaffold-live-status", str(output_dir)])

        assert exit_code == 1
    finally:
        rmtree(output_dir)

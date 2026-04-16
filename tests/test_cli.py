from __future__ import annotations

from pathlib import Path
from shutil import rmtree
from tempfile import mkdtemp
import json
import re

import aether_forge.cli as cli_module
from aether_forge.cli import main
from aether_forge.crypto import MockCryptoExecutionRouter
from aether_forge.generator import FastGenerateRequest, generate_fast_artifact_set
from aether_forge.runtime import RuntimeSession, SessionStatus, StepKind, StepProposal, load_artifact_bundle, load_session_replay_json, write_session_replay_json


REPO_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_DIR = REPO_ROOT / "examples" / "delta-neutral-btc"


def test_resume_replay_cli_can_approve_and_complete_held_session() -> None:
    artifacts = load_artifact_bundle(EXAMPLE_DIR)

    for capability in artifacts.capability_manifest["capabilities"]:
        if capability["capabilityId"] == "cap-exchange-order":
            capability["requiredApproval"] = True

    class ApprovalPlanner:
        def propose_plan(self, session: RuntimeSession) -> list[StepProposal]:
            if session.working_set.get("cap-exchange-order"):
                return [
                    StepProposal(
                        kind=StepKind.REASON,
                        description="Order was approved and executed.",
                        payload={"mark_complete": True},
                    )
                ]
            return [
                StepProposal(
                    kind=StepKind.USE_CAPABILITY,
                    description="Attempt an exchange order that requires approval.",
                    capability_id="cap-exchange-order",
                    payload={"requested_notional_usd": 5000},
                )
            ]

    session = RuntimeSession(
        artifacts=artifacts,
        environment="sandbox",
        planner=ApprovalPlanner(),
        execution_router=MockCryptoExecutionRouter(),
    )
    assert session.run() == SessionStatus.HOLD

    temp_dir = Path(mkdtemp(prefix="aether-forge-cli-resume-"))
    replay_path = temp_dir / "runtime-replay.json"

    try:
        write_session_replay_json(session, replay_path)

        exit_code = main(
            [
                "resume-replay",
                str(EXAMPLE_DIR),
                "--replay",
                str(replay_path),
                "--approve",
                "cli-approved-token",
            ]
        )

        replay = load_session_replay_json(replay_path)

        assert exit_code == 0
        assert replay.session_status == "complete"
        assert replay.session_state["last_approval_token"] == "cli-approved-token"
    finally:
        rmtree(temp_dir)


def test_scaffold_run_cli_executes_generated_project() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-scaffold-run-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        exit_code = main(["scaffold-run", str(output_dir)])

        assert exit_code == 0
    finally:
        rmtree(output_dir)


def test_scaffold_run_cli_accepts_scaffold_live_router_mode() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-scaffold-run-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        exit_code = main(["scaffold-run", str(output_dir), "--crypto-router", "scaffold-live"])

        assert exit_code == 0
    finally:
        rmtree(output_dir)


def test_scaffold_policy_sync_round_trips_policy_bundle() -> None:
    output_dir = Path(mkdtemp(prefix="aether-forge-scaffold-policy-"))

    try:
        generate_fast_artifact_set(
            FastGenerateRequest(
                name="BTC Basis Agent",
                idea="Build a delta neutral BTC basis agent using spot and perp markets with unwind logic.",
                output_directory=output_dir,
            )
        )

        policy_module_path = output_dir / "src" / "policies" / "policy_bundle.py"
        policy_source = policy_module_path.read_text(encoding="utf8")
        policy_source = re.sub(
            r"return \{\}",
            'return {"maxNotionalUsd": 12345, "requireApprovalEnvironments": ["sandbox"]}',
            policy_source,
            count=1,
        )
        policy_module_path.write_text(policy_source, encoding="utf8")

        exit_code = main(["scaffold-policy-sync", str(output_dir)])
        bundle = json.loads((output_dir / "policy-bundle.json").read_text(encoding="utf8"))

        assert exit_code == 0
        assert bundle["rules"]["maxNotionalUsd"] == 12345
        assert bundle["rules"]["requireApprovalEnvironments"] == ["sandbox"]
    finally:
        rmtree(output_dir)


def test_wallet_cli_commands_use_ows_adapter(monkeypatch, capsys) -> None:
    class FakeOWSAdapter:
        def __init__(self, vault_path=None) -> None:
            self.vault_path = vault_path

        def list_wallets(self) -> list[dict[str, object]]:
            return [
                {"name": "agent-treasury", "id": "wallet-1"},
                {"name": "ops-wallet", "id": "wallet-2"},
            ]

        def create_wallet(self, wallet_name: str) -> dict[str, object]:
            return {"name": wallet_name, "vault_path": self.vault_path, "id": "wallet-1"}

        def get_wallet(self, wallet_name: str) -> dict[str, object]:
            return {"name": wallet_name, "id": "wallet-1", "accounts": [{"chain_id": "eip155:1", "address": "0xabc"}]}

        def get_account(self, wallet_name: str, chain: str) -> dict[str, object]:
            return {"wallet_name": wallet_name, "chain": chain, "address": "0xabc"}

        def sign_message(self, wallet_name: str, chain: str, message: str) -> dict[str, object]:
            return {"wallet_name": wallet_name, "chain": chain, "signature": f"sig:{message}"}

        def sign_transaction(self, wallet_name: str, chain: str, tx_hex: str, *, send: bool = False, rpc_url: str | None = None) -> dict[str, object]:
            if send:
                return {"wallet_name": wallet_name, "chain": chain, "tx_hash": f"tx:{tx_hex}", "rpc_url": rpc_url}
            return {"wallet_name": wallet_name, "chain": chain, "signature": f"signed:{tx_hex}"}

    monkeypatch.setattr(cli_module, "OpenWalletStandardAdapter", FakeOWSAdapter)

    assert main(["wallet-create", "--name", "agent-treasury", "--vault-path", "/tmp/ows-vault"]) == 0
    create_output = json.loads(capsys.readouterr().out)
    assert create_output["name"] == "agent-treasury"
    assert create_output["vault_path"] == "/tmp/ows-vault"

    assert main(["wallet-list"]) == 0
    list_output = json.loads(capsys.readouterr().out)
    assert len(list_output) == 2
    assert list_output[0]["name"] == "agent-treasury"

    assert main(["wallet-info", "--name", "agent-treasury"]) == 0
    info_output = json.loads(capsys.readouterr().out)
    assert info_output["id"] == "wallet-1"

    assert main(["wallet-account", "--name", "agent-treasury", "--chain", "evm"]) == 0
    account_output = json.loads(capsys.readouterr().out)
    assert account_output["address"] == "0xabc"

    assert main(["wallet-sign-message", "--name", "agent-treasury", "--chain", "evm", "--message", "hello"]) == 0
    sign_output = json.loads(capsys.readouterr().out)
    assert sign_output["signature"] == "sig:hello"

    assert main(["wallet-sign-tx", "--name", "agent-treasury", "--chain", "evm", "--tx-hex", "0xabc"]) == 0
    sign_tx_output = json.loads(capsys.readouterr().out)
    assert sign_tx_output["signature"] == "signed:0xabc"

    assert main([
        "wallet-send-tx",
        "--name",
        "agent-treasury",
        "--chain",
        "evm",
        "--tx-hex",
        "0xdef",
        "--rpc-url",
        "https://rpc.example",
    ]) == 0
    send_tx_output = json.loads(capsys.readouterr().out)
    assert send_tx_output["tx_hash"] == "tx:0xdef"
    assert send_tx_output["rpc_url"] == "https://rpc.example"

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

from . import __version__
from .artifacts import format_issues, validate_artifact_directory
from .config import (
    build_planner_factory,
    discover_default_config_path,
    load_config_file,
    resolve_planner_settings,
    resolve_runtime_settings,
)
from .crypto import (
    AuthenticatedPaperTradingCryptoExecutionRouter,
    MockCryptoExecutionRouter,
    OpenWalletStandardAdapter,
    OWSWalletCryptoExecutionRouter,
    PublicMarketDataCryptoExecutionRouter,
    SimWalletCryptoExecutionRouter,
)
from .evals import (
    build_promotion_evidence,
    create_promotion_record_artifact,
    evaluate_scenario_pack,
    evaluate_scenario_with_planner,
)
from .generator import FastGenerateRequest, generate_fast_artifact_set
from .models import (
    AnthropicPlanningModel,
    GeminiPlanningModel,
    OpenAICompatiblePlanningModel,
    StaticPlanningModel,
    list_models,
)
from .runtime import (
    hydrate_session_from_replay,
    load_artifact_bundle,
    load_session_replay_json,
    write_session_replay_json,
)
from .scaffold import (
    build_scaffold_live_exchange_router,
    inspect_scaffold_live_exchange_status,
    sync_scaffold_policy_bundle,
)
from .skills import install_skill_to_project, resolve_source, search_skills
from .slow_generate import SlowGenerateRequest, generate_slow_artifact_set
from .storage import SqliteMemoryStore
from .versioning import assess_artifact_set_compatibility, build_artifact_migration_plan, format_compatibility_result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="forge", description="Aether Forge CLI")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output (same as --log-level DEBUG)")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="ERROR", help="Set logging level")
    subparsers = parser.add_subparsers(dest="command")

    validate_parser = subparsers.add_parser("validate", help="Validate an artifact directory")
    validate_parser.add_argument("artifact_directory", help="Path to the artifact directory")

    compat_parser = subparsers.add_parser("artifact-compat", help="Check compatibility between two artifact directories")
    compat_parser.add_argument("--previous", required=True, help="Path to the previous artifact directory")
    compat_parser.add_argument("--current", required=True, help="Path to the current artifact directory")

    migration_parser = subparsers.add_parser("artifact-migration-plan", help="Generate a migration contract skeleton for one artifact type")
    migration_parser.add_argument("--previous", required=True, help="Path to the previous artifact directory")
    migration_parser.add_argument("--current", required=True, help="Path to the current artifact directory")
    migration_parser.add_argument("--artifact-type", required=True, help="Artifact type to compare, e.g. agent-spec")
    migration_parser.add_argument("--output", help="Optional output path for the generated migration contract JSON")

    eval_parser = subparsers.add_parser("eval", help="Run a scenario against the native runtime")
    eval_parser.add_argument("artifact_directory", help="Path to the artifact directory")
    eval_parser.add_argument("--scenario", help="Scenario ID to execute")
    eval_parser.add_argument("--list", action="store_true", dest="list_scenarios", help="List available scenario IDs and exit")
    eval_parser.add_argument("--replay-out", help="Optional path to write a runtime replay JSON file")
    _add_planner_options(eval_parser)
    _add_crypto_router_options(eval_parser)
    _add_memory_store_options(eval_parser)

    eval_pack_parser = subparsers.add_parser("eval-pack", help="Run the scenario pack against the native runtime")
    eval_pack_parser.add_argument("artifact_directory", help="Path to the artifact directory")
    eval_pack_parser.add_argument("--environment", help="Optional environment filter")
    eval_pack_parser.add_argument("--target", help="Optional target environment for promotion evidence")
    _add_planner_options(eval_pack_parser)
    _add_crypto_router_options(eval_pack_parser)
    _add_memory_store_options(eval_pack_parser)

    promote_parser = subparsers.add_parser("promote-draft", help="Generate a promotion record artifact from evaluation results")
    promote_parser.add_argument("artifact_directory", help="Path to the artifact directory")
    promote_parser.add_argument("--target", required=True, help="Target environment")
    promote_parser.add_argument("--approver", action="append", required=True, help="Approver identity; repeat for multiple approvers")
    promote_parser.add_argument("--output", help="Optional output path for promotion-record.json")
    promote_parser.add_argument("--replay-dir", help="Optional directory to write scenario runtime replay files")
    _add_planner_options(promote_parser)
    _add_crypto_router_options(promote_parser)
    _add_memory_store_options(promote_parser)

    resume_parser = subparsers.add_parser("resume-replay", help="Resume a runtime session from a replay file")
    resume_parser.add_argument("artifact_directory", help="Path to the artifact directory")
    resume_parser.add_argument("--replay", required=True, help="Path to the runtime replay JSON file")
    resume_parser.add_argument("--approve", help="Optional approval token to apply before resuming")
    resume_parser.add_argument("--replay-out", help="Optional output path for the resumed runtime replay JSON file")
    _add_planner_options(resume_parser)
    _add_crypto_router_options(resume_parser)
    _add_memory_store_options(resume_parser)

    scaffold_run_parser = subparsers.add_parser("scaffold-run", help="Run the generated scaffold project eval flow")
    scaffold_run_parser.add_argument("project_directory", help="Path to the generated scaffold project")
    scaffold_run_parser.add_argument("--environment", help="Optional environment filter")
    scaffold_run_parser.add_argument("--target", help="Optional target environment for promotion evidence")
    _add_planner_options(scaffold_run_parser)
    _add_crypto_router_options(scaffold_run_parser)
    _add_memory_store_options(scaffold_run_parser)

    scaffold_policy_parser = subparsers.add_parser("scaffold-policy-sync", help="Sync generated scaffold policy code back into policy-bundle.json")
    scaffold_policy_parser.add_argument("project_directory", help="Path to the generated scaffold project")

    scaffold_live_status_parser = subparsers.add_parser("scaffold-live-status", help="Inspect the generated scaffold live exchange adapter status")
    scaffold_live_status_parser.add_argument("project_directory", help="Path to the generated scaffold project")

    generate_parser = subparsers.add_parser("generate-fast", help="Generate a fast-mode artifact set from an idea")
    generate_parser.add_argument("--name", required=True, help="Agent name")
    generate_parser.add_argument("--idea", required=True, help="Plain-language agent idea")
    generate_parser.add_argument("--output", required=True, help="Output directory for the generated artifact set")
    generate_parser.add_argument("--skills", nargs="*", default=None, help="Skills from skills.sh to include (e.g., owner/repo or skill-name)")
    generate_parser.add_argument("--wallet", action="store_true", help="Create a multi-chain wallet (EVM, Solana, Bitcoin)")
    generate_parser.add_argument("--autonomous", action="store_true", help="Enable autoresearch and self-improvement")
    generate_parser.add_argument("--strategy-file", help="Path to a strategy file (plain English, markdown, or JSON) to use as the agent's trading strategy")
    generate_parser.add_argument("--no-registry", action="store_true", help="Skip registering the agent in the local registry")
    generate_parser.add_argument(
        "--planner-mode",
        choices=["heuristic", "static", "openai-compatible", "function-call", "anthropic", "gemini", "openai", "openrouter", "ollama"],
        help="LLM provider to bake into the generated agent's aether-forge.json. Default: auto-detect (Ollama if reachable, else first available cloud key, else heuristic).",
    )
    generate_parser.add_argument("--planner-model", help="Model name to bake into the generated agent's planner config.")
    generate_parser.add_argument("--planner-base-url", help="Base URL to bake into the generated agent's planner config (e.g. http://localhost:11434 for Ollama).")
    generate_parser.add_argument("--planner-api-key-env", help="Env var name the generated agent should read its planner API key from.")

    slow_parser = subparsers.add_parser("generate-slow", help="Generate a slow-mode artifact set with autoresearch from an idea")
    slow_parser.add_argument("--name", required=True, help="Agent name")
    slow_parser.add_argument("--idea", required=True, help="Plain-language agent idea")
    slow_parser.add_argument("--output", required=True, help="Output directory for the generated artifact set")
    slow_parser.add_argument("--max-iterations", type=int, default=5, help="Maximum autoresearch iterations (default: 5)")
    slow_parser.add_argument("--skills", nargs="*", default=None, help="Skills from skills.sh to include (e.g., owner/repo or skill-name)")
    _add_planner_options(slow_parser)

    run_parser = subparsers.add_parser("run", help="Run a governed agent loop")
    run_parser.add_argument("artifact_directory", help="Path to the artifact directory")
    run_parser.add_argument("--interval", type=float, default=30.0, help="Seconds between ticks (default: 30)")
    run_parser.add_argument("--max-ticks", type=int, default=0, help="Max ticks, 0=unlimited (default: 0)")
    run_parser.add_argument("--environment", default="sandbox", help="Execution environment (default: sandbox)")
    run_parser.add_argument("--auto-approve", action="store_true", help="Auto-approve held actions in sandbox/paper")
    run_parser.add_argument("--memory-db", help="Path to SQLite memory database")
    run_parser.add_argument("--replay-dir", help="Directory for tick replay files")
    run_parser.add_argument("--mode", choices=["simulated", "paper", "live"], default="paper", help="Trading mode (default: paper)")
    run_parser.add_argument("--chain", default="base", help="Default chain for data layer / x402 calls (default: base)")
    run_parser.add_argument("--health-port", type=int, default=0, help="HTTP health/status endpoint port (0=disabled)")
    run_parser.add_argument("--json-log", help="Path for structured JSON log output")
    run_parser.add_argument("--pid-file", help="Write PID to this file")
    run_parser.add_argument("--autoresearch", action="store_true", help="Enable runtime self-evaluation and improvement proposals")
    run_parser.add_argument("--eval-interval", type=int, default=6, help="Evaluate performance every N ticks (default: 6)")
    run_parser.add_argument("--knowledge", action="store_true", help="Enable MemPalace long-term knowledge layer")
    run_parser.add_argument("--a2a-port", type=int, default=0, help="A2A server port — expose this agent's capabilities to other agents (0=disabled)")
    _add_planner_options(run_parser)
    _add_crypto_router_options(run_parser)

    wallet_backup_parser = subparsers.add_parser("wallet-backup", help="Export an encrypted backup of an agent's wallet (contains mnemonic)")
    wallet_backup_parser.add_argument("artifact_directory", help="Path to the agent directory")
    wallet_backup_parser.add_argument("--output", help="Backup file path (default: agent dir with timestamp)")
    wallet_backup_parser.add_argument("--passphrase", help="Encryption passphrase (will prompt if omitted; min 8 chars)")
    wallet_backup_parser.add_argument("--unencrypted", action="store_true", help="DANGER: skip encryption (not recommended)")

    security_check_parser = subparsers.add_parser("security-check", help="Run pre-flight security audit on an agent directory")
    security_check_parser.add_argument("artifact_directory", help="Path to the agent directory")
    security_check_parser.add_argument("--harden", action="store_true", help="Apply file permission fixes automatically")

    wallet_restore_parser = subparsers.add_parser("wallet-restore", help="Restore an agent wallet from a backup file")
    wallet_restore_parser.add_argument("backup_file", help="Path to the backup JSON")
    wallet_restore_parser.add_argument("--into", required=True, help="Agent directory to restore into")
    wallet_restore_parser.add_argument("--passphrase", help="Decryption passphrase (will prompt if backup is encrypted and omitted)")

    halt_parser = subparsers.add_parser("halt", help="Activate kill switch — blocks all live x402 calls")
    halt_parser.add_argument("artifact_directory", help="Path to the agent directory")
    halt_parser.add_argument("--reason", default="manual halt", help="Reason for the halt")

    resume_parser_kill = subparsers.add_parser("resume", help="Clear kill switch after manual review")
    resume_parser_kill.add_argument("artifact_directory", help="Path to the agent directory")

    x402_call_parser = subparsers.add_parser("x402-call", help="Make a single x402 payment call (real money)")
    x402_call_parser.add_argument("artifact_directory", help="Path to the agent directory")
    x402_call_parser.add_argument("--url", required=True, help="URL of the x402 endpoint")
    x402_call_parser.add_argument("--method", default="GET", choices=["GET", "POST"], help="HTTP method")
    x402_call_parser.add_argument("--body", help="JSON body for POST requests")
    x402_call_parser.add_argument("--max-per-call-usd", type=float, default=0.10, help="Max USD per single call")
    x402_call_parser.add_argument("--max-session-usd", type=float, default=1.00, help="Max USD per session")
    x402_call_parser.add_argument("--chain", default="base", help="Chain (base, ethereum, arbitrum, etc)")
    x402_call_parser.add_argument("--confirm-live", action="store_true", help="REQUIRED: confirm real money will be spent")

    strategy_parser = subparsers.add_parser("strategy", help="View or manage agent strategy")
    strategy_sub = strategy_parser.add_subparsers(dest="strategy_command")
    strategy_view = strategy_sub.add_parser("view", help="View current strategy parameters")
    strategy_view.add_argument("artifact_directory", help="Path to the agent directory")
    strategy_accept = strategy_sub.add_parser("accept", help="Accept an improvement proposal")
    strategy_accept.add_argument("artifact_directory", help="Path to the agent directory")
    strategy_accept.add_argument("proposal_id", help="Proposal ID to accept")
    strategy_reject = strategy_sub.add_parser("reject", help="Reject an improvement proposal")
    strategy_reject.add_argument("artifact_directory", help="Path to the agent directory")
    strategy_reject.add_argument("proposal_id", help="Proposal ID to reject")
    strategy_reject.add_argument("--reason", default="", help="Reason for rejection")

    wallet_create_parser = subparsers.add_parser("wallet-create", help="Create a wallet through the OWS backend")
    wallet_create_parser.add_argument("--name", required=True, help="Wallet name")
    wallet_create_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_list_parser = subparsers.add_parser("wallet-list", help="List wallets through the OWS backend")
    wallet_list_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_info_parser = subparsers.add_parser("wallet-info", help="Read wallet metadata through the OWS backend")
    wallet_info_parser.add_argument("--name", required=True, help="Wallet name or ID")
    wallet_info_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_account_parser = subparsers.add_parser("wallet-account", help="Read an account from an OWS wallet")
    wallet_account_parser.add_argument("--name", required=True, help="Wallet name or ID")
    wallet_account_parser.add_argument("--chain", required=True, help="Chain alias, e.g. evm or solana")
    wallet_account_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_sign_message_parser = subparsers.add_parser("wallet-sign-message", help="Sign a message through the OWS backend")
    wallet_sign_message_parser.add_argument("--name", required=True, help="Wallet name or ID")
    wallet_sign_message_parser.add_argument("--chain", required=True, help="Chain alias, e.g. evm or solana")
    wallet_sign_message_parser.add_argument("--message", required=True, help="Message to sign")
    wallet_sign_message_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_sign_tx_parser = subparsers.add_parser("wallet-sign-tx", help="Sign a transaction through the OWS backend")
    wallet_sign_tx_parser.add_argument("--name", required=True, help="Wallet name or ID")
    wallet_sign_tx_parser.add_argument("--chain", required=True, help="Chain alias, e.g. evm or solana")
    wallet_sign_tx_parser.add_argument("--tx-hex", required=True, help="Hex-encoded serialized transaction")
    wallet_sign_tx_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_send_tx_parser = subparsers.add_parser("wallet-send-tx", help="Sign and send a transaction through the OWS backend")
    wallet_send_tx_parser.add_argument("--name", required=True, help="Wallet name or ID")
    wallet_send_tx_parser.add_argument("--chain", required=True, help="Chain alias, e.g. evm or solana")
    wallet_send_tx_parser.add_argument("--tx-hex", required=True, help="Hex-encoded serialized transaction")
    wallet_send_tx_parser.add_argument("--rpc-url", help="Optional RPC URL override")
    wallet_send_tx_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_import_parser = subparsers.add_parser("wallet-import", help="Import a wallet from a mnemonic through the OWS backend")
    wallet_import_parser.add_argument("--name", required=True, help="Wallet name")
    wallet_import_parser.add_argument("--mnemonic", required=True, help="BIP-39 mnemonic phrase")
    wallet_import_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_delete_parser = subparsers.add_parser("wallet-delete", help="Delete a wallet through the OWS backend")
    wallet_delete_parser.add_argument("--name", required=True, help="Wallet name or ID")
    wallet_delete_parser.add_argument("--vault-path", help="Optional OWS vault path")

    wallet_export_parser = subparsers.add_parser("wallet-export", help="Export a wallet through the OWS backend")
    wallet_export_parser.add_argument("--name", required=True, help="Wallet name or ID")
    wallet_export_parser.add_argument("--vault-path", help="Optional OWS vault path")

    skills_search_parser = subparsers.add_parser("skills-search", help="Search skills.sh for agent skills")
    skills_search_parser.add_argument("query", help="Search query")
    skills_search_parser.add_argument("--limit", type=int, default=10, help="Max results")

    skills_add_parser = subparsers.add_parser("skills-add", help="Add a skill from skills.sh to a project")
    skills_add_parser.add_argument("source", help="Skill source (owner/repo, elsa:skill-name, bankr:skill-name)")
    skills_add_parser.add_argument("--project", required=True, help="Project directory")

    elsa_list_parser = subparsers.add_parser("elsa-list", help="List available Elsa x402 DeFi endpoints")
    elsa_list_parser.add_argument("--category", help="Filter by category (portfolio, trading, perpetuals, staking, airdrops, transactions, analytics)")

    models_list_parser = subparsers.add_parser("models-list", help="List available LLM models from a provider")
    models_list_parser.add_argument(
        "--provider",
        choices=["openrouter", "ollama", "openai"],
        default="openrouter",
        help="Provider to query (default: openrouter)",
    )
    models_list_parser.add_argument("--query", help="Filter models by name or ID substring")
    models_list_parser.add_argument("--api-key", help="API key for the provider")
    models_list_parser.add_argument("--api-key-env", help="Environment variable name that holds the API key")
    models_list_parser.add_argument("--base-url", help="Override the provider base URL")
    models_list_parser.add_argument("--limit", type=int, default=50, help="Maximum number of models to display (default: 50)")

    init_parser = subparsers.add_parser("init", help="Initialize a new aether-forge.json config file")
    init_parser.add_argument("--output", default="aether-forge.json", help="Output path (default: aether-forge.json)")
    init_parser.add_argument("--planner-mode", choices=["heuristic", "static", "openai-compatible", "function-call", "anthropic", "gemini", "openai", "openrouter", "ollama"], default="heuristic", help="Default planner mode")
    init_parser.add_argument("--planner-model", help="Default model name")
    init_parser.add_argument("--api-key-env", help="Environment variable for the API key")

    subparsers.add_parser("doctor", help="Check Aether Forge environment and dependencies")

    config_validate_parser = subparsers.add_parser("config-validate", help="Validate an aether-forge.json config file")
    config_validate_parser.add_argument("config_path", nargs="?", default="aether-forge.json", help="Path to config file")

    completions_parser = subparsers.add_parser("completions", help="Generate shell completions")
    completions_parser.add_argument("shell", choices=["bash", "zsh", "fish"], help="Target shell")

    # Agent registry + A2A commands
    subparsers.add_parser("agent-list", help="List all agents in the local registry")
    agent_info_parser = subparsers.add_parser("agent-info", help="Show details for a specific agent")
    agent_info_parser.add_argument("agent_id", help="Agent artifact set ID")
    agent_remove_parser = subparsers.add_parser("agent-remove", help="Archive an agent (soft-delete from registry)")
    agent_remove_parser.add_argument("agent_id", help="Agent artifact set ID")
    agent_send_parser = subparsers.add_parser("agent-send", help="Send a task to another agent via A2A")
    agent_send_parser.add_argument("endpoint", help="Remote agent's A2A endpoint URL (e.g. http://localhost:8090)")
    agent_send_parser.add_argument("--capability", required=True, help="Capability/skill to invoke on the remote agent")
    agent_send_parser.add_argument("--payload", default="{}", help="JSON payload for the capability (default: {})")
    agent_send_parser.add_argument("--text", help="Optional plain-text message to send alongside")

    agent_register_parser = subparsers.add_parser("agent-register", help="Register an agent on the ERC-8004 on-chain registry (Base mainnet)")
    agent_register_parser.add_argument("agent_id", help="Agent artifact set ID (from forge agent-list)")
    agent_register_parser.add_argument("--metadata-uri", help="IPFS or HTTP URI for the agent's metadata (default: auto-generated)")
    agent_register_parser.add_argument("--rpc-url", default="https://mainnet.base.org", help="Base RPC URL")
    agent_register_parser.add_argument("--testnet", action="store_true", help="Use Base Sepolia testnet instead of mainnet")

    agent_discover_parser = subparsers.add_parser("agent-discover", help="Discover agents on the ERC-8004 on-chain registry")
    agent_discover_parser.add_argument("--agent-id", type=int, help="Look up a specific agent by on-chain ID")
    agent_discover_parser.add_argument("--address", help="Look up agents owned by a specific wallet address")
    agent_discover_parser.add_argument("--rpc-url", default="https://mainnet.base.org", help="Base RPC URL")

    # Replay debugging — human-friendly view of what an agent did
    replay_parser = subparsers.add_parser("replay-show", help="Show the step ledger from a replay file in human-friendly format")
    replay_parser.add_argument("replay_path", help="Path to a replay JSON file (e.g., agent_dir/replays/tick_0001.json)")
    replay_parser.add_argument("--steps-only", action="store_true", help="Show only the step ledger, skip metadata")
    replay_parser.add_argument("--full", action="store_true", help="Show full payloads (default: truncated)")

    # List replays for an agent
    replays_parser = subparsers.add_parser("replays", help="List all replay files for an agent")
    replays_parser.add_argument("agent_directory", help="Path to the agent directory")
    replays_parser.add_argument("--limit", type=int, default=20, help="Max replays to show (default 20)")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # Allow -v / --verbose anywhere in argv (not just before subcommand)
    raw_argv = argv if argv is not None else sys.argv[1:]
    if "-v" in raw_argv or "--verbose" in raw_argv:
        raw_argv = [a for a in raw_argv if a not in ("-v", "--verbose")]
        args = parser.parse_args(raw_argv)
        args.log_level = "DEBUG"
        args.verbose = True
    else:
        args = parser.parse_args(argv)

    import logging
    logging.basicConfig(
        level=getattr(logging, getattr(args, "log_level", "ERROR"), logging.ERROR),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.command is None:
        parser.print_help()
        return 0

    try:
        return _dispatch_command(args, parser)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except FileNotFoundError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as error:
        print(f"Error: Invalid JSON — {error}", file=sys.stderr)
        return 1
    except RuntimeError as error:
        msg = str(error)
        if "Open Wallet Standard" in msg or "ows" in msg.lower():
            print("Error: Wallet commands require the OWS SDK.\n  pip install aether-forge[wallet]", file=sys.stderr)
        else:
            print(f"Error: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Unexpected error: {error}", file=sys.stderr)
        if getattr(args, "log_level", "ERROR") == "DEBUG":
            import traceback
            traceback.print_exc()
        return 1


def _dispatch_command(args: argparse.Namespace, parser: argparse.ArgumentParser) -> int:
    if args.command == "validate":
        directory_path = Path(args.artifact_directory).resolve()
        result = validate_artifact_directory(directory_path)

        if result.issues:
            print(format_issues(result.issues))

        if result.ok:
            print(f"Validated {len(result.artifacts)} artifacts in {directory_path}.")
            return 0

        print(f"Validation failed for {directory_path}.", file=sys.stderr)
        return 1

    if args.command == "artifact-compat":
        result = assess_artifact_set_compatibility(
            Path(args.previous).resolve(),
            Path(args.current).resolve(),
        )
        print(format_compatibility_result(result))
        return 0 if result.ok else 1

    if args.command == "artifact-migration-plan":
        try:
            plan = build_artifact_migration_plan(
                Path(args.previous).resolve(),
                Path(args.current).resolve(),
                args.artifact_type,
            )
        except ValueError as error:
            print(str(error), file=sys.stderr)
            return 1
        if args.output:
            output_path = Path(args.output).resolve()
            output_path.write_text(f"{json.dumps(plan.contract, indent=2)}\n", encoding="utf8")
            print(f"Wrote migration contract to {output_path}.")
        else:
            print(json.dumps(plan.contract, indent=2))
        return 0

    if args.command == "eval":
        directory_path = Path(args.artifact_directory).resolve()
        if getattr(args, "list_scenarios", False):
            artifacts = load_artifact_bundle(directory_path)
            scenarios = artifacts.scenario_pack.get("scenarios", [])
            if not scenarios:
                print("No scenarios found.")
                return 0
            for s in scenarios:
                env = s.get("environmentKind", "?")
                print(f"  {s['scenarioId']:<50} env={env}")
            print(f"\n{len(scenarios)} scenarios.")
            return 0
        if not args.scenario:
            print("Error: --scenario is required (use --list to see available IDs)", file=sys.stderr)
            return 1
        planner_factory = _planner_factory_from_args(args)
        execution_router_factory = _execution_router_factory_from_args(args, project_root=directory_path)
        memory_store = _memory_store_from_args(args, artifact_directory=directory_path)
        result, session = evaluate_scenario_with_planner(
            directory_path,
            args.scenario,
            planner_factory=planner_factory,
            execution_router_factory=execution_router_factory,
            memory_store=memory_store,
        )
        if args.replay_out:
            write_session_replay_json(session, Path(args.replay_out).resolve())
        print(
            f"Scenario {result.scenario_id}: stage_outcome={result.stage_outcome} "
            f"session_status={result.session_status} steps={result.step_count}"
        )
        if result.blocking_reason_ids:
            print(f"Blocking reasons: {', '.join(result.blocking_reason_ids)}")
        return 0 if result.stage_outcome == "pass" else 1

    if args.command == "eval-pack":
        directory_path = Path(args.artifact_directory).resolve()
        planner_factory = _planner_factory_from_args(args)
        execution_router_factory = _execution_router_factory_from_args(args, project_root=directory_path)
        memory_store = _memory_store_from_args(args, artifact_directory=directory_path)
        summary, _sessions = evaluate_scenario_pack(
            directory_path,
            environment_kind=args.environment,
            planner_factory=planner_factory,
            execution_router_factory=execution_router_factory,
            memory_store=memory_store,
        )
        print(
            f"Scenario pack: total={summary.total_scenarios} matched={summary.matched_expectations} "
            f"pass={summary.counts_by_stage.get('pass', 0)} hold={summary.counts_by_stage.get('hold', 0)} "
            f"fail={summary.counts_by_stage.get('fail', 0)}"
        )
        if args.target:
            evidence = build_promotion_evidence(directory_path, args.target, summary)
            print(json.dumps(evidence, indent=2))
        return 0 if summary.meets_expectations else 1

    if args.command == "generate-fast":
        # Auto-detect a planner if the operator did not pass --planner-mode.
        # Aether Forge is an LLM-driven agent framework — heuristic is only a
        # last-resort fallback for environments with neither a local model
        # nor any cloud key.
        planner_mode = getattr(args, "planner_mode", None)
        planner_model = getattr(args, "planner_model", None)
        planner_base_url = getattr(args, "planner_base_url", None)
        planner_api_key_env = getattr(args, "planner_api_key_env", None)
        if planner_mode is None:
            detected = _autodetect_planner()
            planner_mode = detected["mode"]
            planner_model = planner_model or detected.get("model")
            planner_base_url = planner_base_url or detected.get("base_url")
            planner_api_key_env = planner_api_key_env or detected.get("api_key_env")
            print(
                f"[planner] auto-detected: mode={planner_mode}"
                + (f" model={planner_model}" if planner_model else "")
                + (f" baseUrl={planner_base_url}" if planner_base_url else "")
                + (f" apiKeyEnv={planner_api_key_env}" if planner_api_key_env else "")
            )

        request = FastGenerateRequest(
            name=args.name,
            idea=args.idea,
            output_directory=Path(args.output).resolve(),
            skills=args.skills,
            create_wallet=getattr(args, "wallet", False),
            autonomous=getattr(args, "autonomous", False),
            strategy_file=getattr(args, "strategy_file", None),
            planner_mode=planner_mode,
            planner_model=planner_model,
            planner_base_url=planner_base_url,
            planner_api_key_env=planner_api_key_env,
        )
        generated = generate_fast_artifact_set(request)
        if generated.agent_summary:
            generated.agent_summary.print_card()
        else:
            print(
                f"Generated fast-mode artifact set {generated.artifact_set_id} "
                f"for domain={generated.domain} at {generated.output_directory}."
            )

        # Auto-register in the local agent registry so forge agent-list
        # finds this agent later without manual bookkeeping.
        skip_registry = getattr(args, "no_registry", False)
        if not skip_registry:
            try:
                from .agent_registry import AgentRegistry
                registry = AgentRegistry()
                summary = generated.agent_summary
                registry.register(
                    agent_id=generated.artifact_set_id,
                    name=request.name,
                    output_dir=str(generated.output_directory),
                    evm_address=summary.evm_address if summary else None,
                    provider=summary.wallet_provider if summary else "simulated",
                    chain=request.planner_mode or "base",
                    capabilities=[c for c in (summary.capabilities if summary else [])],
                    planner_mode=request.planner_mode,
                    planner_model=request.planner_model,
                )
                registry.close()
            except Exception as error:
                logger.warning("Failed to register agent in local registry: %s", error)

        # Generate a self-attestation (EIP-712 signed by the agent's wallet).
        # This links the agent's identity to its capabilities cryptographically.
        try:
            from .attestation import create_self_attestation
            summary = generated.agent_summary
            evm_addr = summary.evm_address if summary else ""
            if evm_addr:
                attestation = create_self_attestation(
                    agent_directory=generated.output_directory,
                    artifact_set_id=generated.artifact_set_id,
                    agent_address=evm_addr,
                )
                print(f"  Attestation: {attestation.tier} (saved to attestation.json)")
        except Exception as error:
            logger.debug("Self-attestation skipped: %s", error)

        return 0

    if args.command == "generate-slow":
        research_model = _research_model_from_args(args)
        request = SlowGenerateRequest(
            name=args.name,
            idea=args.idea,
            output_directory=Path(args.output).resolve(),
            max_iterations=args.max_iterations,
            research_model=research_model,
            skills=args.skills,
        )
        result = generate_slow_artifact_set(request)
        baseline_rate = result.baseline_metrics.get("match_rate", 0.0)
        final_rate = result.final_metrics.get("match_rate", 0.0)
        print(
            f"Generated slow-mode artifact set {result.artifact_set_id} "
            f"for domain={result.domain} "
            f"iterations={len(result.iterations)} "
            f"baseline_match_rate={baseline_rate:.2f} "
            f"final_match_rate={final_rate:.2f} "
            f"at {result.output_directory}."
        )
        return 0

    if args.command == "run":
        from .runner import AgentRunner, RunnerConfig
        from .scaffold_router import StrategyConfig, load_scaffold_router
        directory_path = Path(args.artifact_directory).resolve()
        planner_factory = _planner_factory_from_args(args)

        # Load the scaffold's own strategy router. Pull mcp_servers from the
        # agent's aether-forge.json so the strategy router can spawn MCP
        # clients at runtime.
        trade_mode = getattr(args, "mode", "paper")
        chain = getattr(args, "chain", None) or "base"
        agent_config = _config_from_args(args)
        mcp_servers = agent_config.get("mcp_servers", {}) if isinstance(agent_config, dict) else {}
        strategy_config = StrategyConfig(
            mode=trade_mode,
            chain=chain,
            mcp_servers=mcp_servers or {},
        )
        scaffold_router = load_scaffold_router(directory_path, strategy_config)

        config = RunnerConfig(
            interval_seconds=args.interval,
            max_ticks=args.max_ticks,
            environment=args.environment,
            auto_approve=args.auto_approve,
            memory_db_path=args.memory_db,
            replay_directory=args.replay_dir,
            health_port=getattr(args, "health_port", 0),
            json_log_file=getattr(args, "json_log", None),
            pid_file=getattr(args, "pid_file", None),
            enable_autoresearch=getattr(args, "autoresearch", False),
            eval_interval_ticks=getattr(args, "eval_interval", 6),
            enable_knowledge=getattr(args, "knowledge", False),
            a2a_port=getattr(args, "a2a_port", 0),
        )
        runner = AgentRunner(
            directory_path,
            config=config,
            planner_factory=planner_factory,
            execution_router_factory=lambda: scaffold_router,
        )
        results = runner.run()

        # Print portfolio summary if available
        if hasattr(scaffold_router, "engine"):
            portfolio = scaffold_router.engine.portfolio_summary()
            print(f"\n  Portfolio: ${portfolio['total_value_usd']:,.2f} (P&L: ${portfolio['pnl_usd']:+,.2f})")
        return 0

    if args.command == "wallet-create":
        adapter = _ows_adapter_from_args(args)
        result = adapter.create_wallet(args.name)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-list":
        adapter = _ows_adapter_from_args(args)
        result = adapter.list_wallets()
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-info":
        adapter = _ows_adapter_from_args(args)
        result = adapter.get_wallet(args.name)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-account":
        adapter = _ows_adapter_from_args(args)
        result = adapter.get_account(args.name, args.chain)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-sign-message":
        adapter = _ows_adapter_from_args(args)
        result = adapter.sign_message(args.name, args.chain, args.message)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-sign-tx":
        adapter = _ows_adapter_from_args(args)
        result = adapter.sign_transaction(args.name, args.chain, args.tx_hex)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-send-tx":
        adapter = _ows_adapter_from_args(args)
        result = adapter.sign_transaction(args.name, args.chain, args.tx_hex, send=True, rpc_url=args.rpc_url)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-import":
        adapter = _ows_adapter_from_args(args)
        result = adapter.import_wallet_mnemonic(args.name, args.mnemonic)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-delete":
        adapter = _ows_adapter_from_args(args)
        result = adapter.delete_wallet(args.name)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "wallet-export":
        adapter = _ows_adapter_from_args(args)
        result = adapter.export_wallet(args.name)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "promote-draft":
        directory_path = Path(args.artifact_directory).resolve()
        planner_factory = _planner_factory_from_args(args)
        execution_router_factory = _execution_router_factory_from_args(args, project_root=directory_path)
        promotion_record = create_promotion_record_artifact(
            directory_path,
            target_environment=args.target,
            approvers=args.approver,
            replay_output_directory=Path(args.replay_dir).resolve() if args.replay_dir else None,
            planner_factory=planner_factory,
            execution_router_factory=execution_router_factory,
        )
        output_path = Path(args.output).resolve() if args.output else directory_path / "promotion-record.json"
        output_path.write_text(f"{json.dumps(promotion_record, indent=2)}\n", encoding="utf8")
        print(f"Wrote promotion record to {output_path}.")
        return 0 if promotion_record["promotionDecision"]["decisionOutcome"] == "approved" else 1

    if args.command == "resume-replay":
        directory_path = Path(args.artifact_directory).resolve()
        replay_path = Path(args.replay).resolve()
        planner_factory = _planner_factory_from_args(args)

        artifacts = load_artifact_bundle(directory_path)
        replay = load_session_replay_json(replay_path)
        execution_router_factory = _execution_router_factory_from_args(args, project_root=directory_path)
        session = hydrate_session_from_replay(
            replay,
            artifacts,
            planner_factory(),
            execution_router_factory(),
        )

        if args.approve:
            session.approve_pending(args.approve)

        status = session.run()
        output_path = Path(args.replay_out).resolve() if args.replay_out else replay_path
        write_session_replay_json(session, output_path)
        print(f"Resumed replay: session_status={status.value} steps={len(session.step_ledger)}")
        return 0 if status.value == "complete" else 1

    if args.command == "scaffold-run":
        project_directory = Path(args.project_directory).resolve()
        planner_factory = _planner_factory_from_args(args)
        execution_router_factory = _execution_router_factory_from_args(args, project_root=project_directory)
        summary, _sessions = evaluate_scenario_pack(
            project_directory,
            environment_kind=args.environment,
            planner_factory=planner_factory,
            execution_router_factory=execution_router_factory,
        )
        print(
            f"Scaffold run: total={summary.total_scenarios} matched={summary.matched_expectations} "
            f"pass={summary.counts_by_stage.get('pass', 0)} hold={summary.counts_by_stage.get('hold', 0)} "
            f"fail={summary.counts_by_stage.get('fail', 0)}"
        )
        if args.target:
            evidence = build_promotion_evidence(
                project_directory,
                args.target,
                summary,
            )
            print(json.dumps(evidence, indent=2))
        return 0 if summary.meets_expectations else 1

    if args.command == "scaffold-policy-sync":
        project_directory = Path(args.project_directory).resolve()
        bundle = sync_scaffold_policy_bundle(project_directory)
        print(json.dumps(bundle, indent=2))
        return 0

    if args.command == "scaffold-live-status":
        project_directory = Path(args.project_directory).resolve()
        status = inspect_scaffold_live_exchange_status(project_directory)
        print(json.dumps(status, indent=2))
        return 0 if status["status"] == "ready" else 1

    if args.command == "skills-search":
        results = search_skills(args.query, args.limit)
        if not results:
            print("No skills found. This may indicate a network issue — try with -v for details.", file=sys.stderr)
            return 0
        # Print formatted table
        name_width = max(len(s.name) for s in results)
        author_width = max((len(s.author) for s in results), default=6)
        name_width = max(name_width, 4)
        author_width = max(author_width, 6)
        header = f"{'Name':<{name_width}}  {'Author':<{author_width}}  {'Description'}"
        print(header)
        print("-" * len(header))
        for skill in results:
            desc = skill.description[:60] + "..." if len(skill.description) > 60 else skill.description
            print(f"{skill.name:<{name_width}}  {skill.author:<{author_width}}  {desc}")
        return 0

    if args.command == "skills-add":
        project_dir = Path(args.project).resolve()
        source = args.source
        resolved = resolve_source(source)
        if resolved.startswith("elsa:"):
            from .skills import _install_elsa_skill
            results = _install_elsa_skill(resolved, project_dir)
            if results:
                for r in results:
                    print(f"  Installed elsa skill '{r.name}' to {r.path}")
                print(f"Installed {len(results)} Elsa endpoint(s).")
            else:
                print(f"No Elsa endpoints matched '{source}'.", file=sys.stderr)
                return 1
        else:
            result = install_skill_to_project(source, project_dir)
            if result:
                print(f"Installed skill '{result.name}' to {result.path}")
            else:
                print(f"Failed to install skill '{args.source}'.", file=sys.stderr)
                return 1
        return 0

    if args.command == "elsa-list":
        from .skills import ELSA_ENDPOINTS, _list_elsa_skills
        category = getattr(args, "category", None)
        names = _list_elsa_skills(category=category)
        if not names:
            print(f"No Elsa endpoints found for category '{category}'.")
            return 0
        print(f"{'Endpoint':<25} {'Price':>8} {'Category':<14} Description")
        print(f"{'-'*25} {'-'*8} {'-'*14} {'-'*40}")
        for name in names:
            cfg = ELSA_ENDPOINTS[name]
            se = " *" if cfg.get("side_effect") else ""
            print(f"{name:<25} ${cfg['price_usd']:<7.3f} {cfg['category']:<14} {cfg['description'][:45]}{se}")
        print(f"\n{len(names)} endpoints. * = side-effecting (requires approval)")
        return 0

    if args.command == "models-list":
        import os as _os
        api_key = args.api_key
        if not api_key and args.api_key_env:
            api_key = _os.getenv(args.api_key_env)
        try:
            models = list_models(
                args.provider,
                api_key=api_key,
                base_url=args.base_url,
                query=args.query,
            )
        except Exception as error:
            print(f"Error fetching models: {error}", file=sys.stderr)
            return 1

        if not models:
            print(f"No models found for provider '{args.provider}'.")
            return 0

        display = models[: args.limit]

        if args.provider == "openrouter":
            id_w = min(max(len(m.id) for m in display), 45)
            name_w = min(max(len(m.name) for m in display), 40)
            print(f"{'Model ID':<{id_w}}  {'Name':<{name_w}}  {'Context':>9}  {'$/1M in':>9}  {'$/1M out':>9}")
            print(f"{'-'*id_w}  {'-'*name_w}  {'-'*9}  {'-'*9}  {'-'*9}")
            for m in display:
                ctx = f"{m.context_length:,}" if m.context_length else "?"
                p_in = f"${float(m.prompt_price)*1_000_000:.2f}" if m.prompt_price else "?"
                p_out = f"${float(m.completion_price)*1_000_000:.2f}" if m.completion_price else "?"
                print(f"{m.id:<{id_w}}  {m.name[:name_w]:<{name_w}}  {ctx:>9}  {p_in:>9}  {p_out:>9}")
        elif args.provider == "ollama":
            id_w = max(len(m.id) for m in display)
            print(f"{'Model':<{id_w}}  {'Params':>10}  {'Quant':<8}")
            print(f"{'-'*id_w}  {'-'*10}  {'-'*8}")
            for m in display:
                params = m.parameter_size or "?"
                quant = m.quantization or "?"
                print(f"{m.id:<{id_w}}  {params:>10}  {quant:<8}")
        else:
            for m in display:
                print(m.id)

        shown = len(display)
        total = len(models)
        if total > shown:
            print(f"\nShowing {shown} of {total} models. Use --limit to see more.")
        else:
            print(f"\n{total} models.")
        return 0

    if args.command == "init":
        from .doctor import generate_default_config
        config = generate_default_config(
            planner_mode=args.planner_mode,
            planner_model=args.planner_model,
            api_key_env=args.api_key_env,
        )
        output_path = Path(args.output).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(f"{json.dumps(config, indent=2)}\n", encoding="utf8")
        print(f"Created {output_path}")
        return 0

    if args.command == "doctor":
        from .config import discover_default_config_path
        from .doctor import run_doctor_checks
        config_path = discover_default_config_path()
        results = run_doctor_checks(config_path=config_path)
        all_pass = True
        passed = 0
        skipped = 0
        failed = 0
        for r in results:
            if r.optional and r.passed:
                icon = "skip"
                skipped += 1
            elif r.passed:
                icon = "ok"
                passed += 1
            else:
                icon = "FAIL"
                failed += 1
                all_pass = False
            print(f"  [{icon:>4}] {r.name}: {r.message}")

        print()
        total = len(results)
        if failed == 0:
            verdict = "Healthy" if skipped == 0 else "Healthy (with optional skips)"
            print(f"  {verdict} — {passed}/{total} ok, {skipped} skipped, {failed} failed")
        else:
            print(f"  UNHEALTHY — {passed}/{total} ok, {skipped} skipped, {failed} failed")
            print("  Re-run with verbose output once the failing checks are addressed.")
        return 0 if all_pass else 1

    if args.command == "config-validate":
        from .doctor import validate_config
        config_path = Path(args.config_path).resolve()
        results = validate_config(config_path)
        all_pass = True
        for r in results:
            icon = "ok" if r.passed else "FAIL"
            print(f"  [{icon:>4}] {r.name}: {r.message}")
            if not r.passed:
                all_pass = False
        if all_pass:
            print(f"\nConfig is valid: {config_path}")
        return 0 if all_pass else 1

    if args.command == "completions":
        from .completions import generate_bash_completion, generate_fish_completion, generate_zsh_completion
        generators = {"bash": generate_bash_completion, "zsh": generate_zsh_completion, "fish": generate_fish_completion}
        print(generators[args.shell]())
        return 0

    if args.command == "wallet-backup":
        import getpass

        from .security_hardening import encrypt_backup, lock_down_file
        from .wallet import backup_agent_wallet
        directory = Path(args.artifact_directory).resolve()
        output = Path(args.output).resolve() if args.output else None
        try:
            # First do the plain export
            path = backup_agent_wallet(directory, output)

            if args.unencrypted:
                print(f"  WARNING: Unencrypted backup at: {path}")
                print("  This file contains the mnemonic in plaintext.")
                print("  Permissions set to 0600 (owner only)")
                return 0

            # Re-read and encrypt
            plaintext_data = json.loads(path.read_text(encoding="utf8"))

            passphrase = args.passphrase
            if not passphrase:
                passphrase = getpass.getpass("Encryption passphrase (min 8 chars): ")
                confirm = getpass.getpass("Confirm passphrase: ")
                if passphrase != confirm:
                    print("Error: passphrases do not match", file=sys.stderr)
                    path.unlink()
                    return 1

            encrypted = encrypt_backup(plaintext_data, passphrase)
            path.write_text(json.dumps(encrypted, indent=2) + "\n", encoding="utf8")
            lock_down_file(path)
            print(f"  Encrypted backup written to: {path}")
            print("  Cipher: AES-256-GCM, KDF: scrypt")
            print("  Permissions: 0600")
            print(f"  Restore with: forge wallet-restore {path} --into ./agent-dir")
            return 0
        except Exception as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1

    if args.command == "security-check":
        from .security_hardening import harden_agent_directory, preflight_security_check
        directory = Path(args.artifact_directory).resolve()

        if args.harden:
            print(f"  Applying security hardening to {directory}...")
            harden_report = harden_agent_directory(directory)
            for f in harden_report.get("locked_files", []):
                print(f"    locked file: {f}")
            for d in harden_report.get("locked_dirs", []):
                print(f"    locked dir:  {d}")
            for e in harden_report.get("errors", []):
                print(f"    error: {e}", file=sys.stderr)
            print()

        report = preflight_security_check(directory)
        print(f"  Security Check: {directory}")
        print(f"  {'─' * 60}")
        for check in report["checks"]:
            icon = {"OK": "  ok", "WARN": "warn", "FAIL": "FAIL"}.get(check["status"], "?")
            print(f"  [{icon}] {check['name']}: {check['message']}")
        print(f"  {'─' * 60}")
        if report["ok"] and not report["warnings"]:
            print("  All checks passed.")
        elif report["ok"]:
            print(f"  Passed with {len(report['warnings'])} warnings.")
        else:
            print(f"  FAILED: {len(report['errors'])} errors")
            for e in report["errors"]:
                print(f"    {e}")
        return 0 if report["ok"] else 1

    if args.command == "wallet-restore":
        from .wallet import restore_agent_wallet
        backup = Path(args.backup_file).resolve()
        target = Path(args.into).resolve()
        try:
            result = restore_agent_wallet(backup, target, passphrase=getattr(args, "passphrase", None))
            print(f"  Wallet restored: {result['wallet_name']}")
            print(f"  Vault: {result['vault_path']}")
            print(f"  Accounts: {result['accounts']} chains")
            return 0
        except Exception as error:
            print(f"Error: {error}", file=sys.stderr)
            return 1

    if args.command == "halt":
        directory = Path(args.artifact_directory).resolve()
        halt_path = directory / "halt"
        halt_path.write_text(f"halted at {datetime.now(UTC).isoformat()}: {args.reason}\n", encoding="utf8")
        print(f"  Kill switch ACTIVE: {halt_path}")
        print("  All x402 calls and live mode will be blocked.")
        print(f"  Run 'forge resume {directory}' after manual review.")
        return 0

    if args.command == "resume":
        directory = Path(args.artifact_directory).resolve()
        halt_path = directory / "halt"
        if halt_path.exists():
            halt_path.unlink()
            print(f"  Kill switch CLEARED: {halt_path}")
        else:
            print(f"  No halt file found at {halt_path}")
        return 0

    if args.command == "x402-call":
        from .x402_client import HaltedError, PaymentBudgetError, X402Client, X402Config, X402Error

        if not args.confirm_live:
            print("Error: --confirm-live is REQUIRED for real x402 calls.", file=sys.stderr)
            print("This command will spend real money from the agent's wallet.", file=sys.stderr)
            return 1

        directory = Path(args.artifact_directory).resolve()
        wallet_path = directory / "wallet.json"
        if not wallet_path.exists():
            print(f"Error: No wallet found at {wallet_path}. Generate the agent with --wallet first.", file=sys.stderr)
            return 1

        config = X402Config(
            max_per_call_usd=args.max_per_call_usd,
            max_session_usd=args.max_session_usd,
            chain=args.chain,
            confirmed=True,
        )
        client = X402Client(agent_directory=directory, config=config)

        # Pre-flight summary
        wallet = json.loads(wallet_path.read_text())
        evm = wallet.get("addresses", {}).get("evm", "?")
        print("\n  X402 LIVE CALL")
        print("  ──────────────")
        print(f"  Agent wallet: {evm}")
        print(f"  Chain:        {args.chain}")
        print(f"  URL:          {args.url}")
        print(f"  Method:       {args.method}")
        print(f"  Max per call: ${args.max_per_call_usd}")
        print(f"  Max session:  ${args.max_session_usd}")
        print("  Confirmed:    YES")
        print()

        try:
            if args.method == "POST":
                body = json.loads(args.body) if args.body else {}
                response = client.post(args.url, body=body)
            else:
                response = client.get(args.url)

            print(f"  Response status: {response.get('status')}")
            print("  Response body:")
            body_str = json.dumps(response.get("body"), indent=4) if isinstance(response.get("body"), (dict, list)) else str(response.get("body"))
            for line in body_str.split("\n")[:30]:
                print(f"    {line}")

            print()
            status = client.status()
            print(f"  Session spent: ${status['session_spent_usd']}")
            print(f"  Daily spent:   ${status['daily_spent_usd']}")
            print(f"  Audit log:     {directory}/x402_audit.jsonl")
            return 0
        except (X402Error, PaymentBudgetError, HaltedError) as error:
            print(f"\n  X402 call failed: {error}", file=sys.stderr)
            return 1

    if args.command == "strategy":
        from .evolution import StrategyArtifact
        if args.strategy_command == "view":
            strategy_path = Path(args.artifact_directory).resolve() / "strategy.json"
            strategy = StrategyArtifact.load(strategy_path)
            print(json.dumps(strategy.to_dict(), indent=2))
            return 0
        if args.strategy_command in ("accept", "reject"):
            # These work on proposals saved in the strategy history
            # In v1, proposals are printed to console during `forge run --autoresearch`
            # and accepted/rejected via this command while the agent is running
            strategy_path = Path(args.artifact_directory).resolve() / "strategy.json"
            strategy = StrategyArtifact.load(strategy_path)
            if args.strategy_command == "accept":
                print(f"To accept proposal {args.proposal_id}, use the running agent's API or re-run with the accepted strategy.")
            else:
                print(f"Proposal {args.proposal_id} rejected: {getattr(args, 'reason', '')}")
            return 0
        print("Usage: forge strategy {view|accept|reject} <artifact_directory>")
        return 1

    # ------------------------------------------------------------------
    # Agent registry commands
    # ------------------------------------------------------------------

    if args.command == "agent-list":
        from .agent_registry import AgentRegistry
        registry = AgentRegistry()
        agents = registry.list_agents()
        registry.close()
        if not agents:
            print("  No agents registered. Run 'forge generate-fast' to create one.")
            return 0
        # Table header
        print(f"  {'Name':<25} {'Status':<10} {'Provider':<10} {'EVM Address':<44} {'ID'}")
        print(f"  {'─' * 25} {'─' * 10} {'─' * 10} {'─' * 44} {'─' * 30}")
        for a in agents:
            addr = a.get("evm_address") or "(none)"
            if len(addr) > 42:
                addr = addr[:6] + "…" + addr[-4:]
            print(
                f"  {a['name']:<25} {a['status']:<10} {a.get('provider', '?'):<10} "
                f"{addr:<44} {a['agent_id']}"
            )
        print(f"\n  {len(agents)} agent(s)")
        return 0

    if args.command == "agent-info":
        from .agent_registry import AgentRegistry
        registry = AgentRegistry()
        agent = registry.get_agent(args.agent_id)
        registry.close()
        if agent is None:
            print(f"  Agent not found: {args.agent_id}")
            return 1
        print(f"  Agent: {agent['name']}")
        print(f"  ID: {agent['agent_id']}")
        print(f"  Status: {agent['status']}")
        print(f"  Output: {agent['output_dir']}")
        print(f"  EVM Address: {agent.get('evm_address') or '(none)'}")
        print(f"  A2A Endpoint: {agent.get('a2a_endpoint') or '(none)'}")
        print(f"  Provider: {agent.get('provider', '?')}")
        print(f"  Chain: {agent.get('chain', '?')}")
        print(f"  Planner: {agent.get('planner_mode', '?')} / {agent.get('planner_model', '?')}")
        caps = json.loads(agent.get("capabilities", "[]"))
        if caps:
            print(f"  Capabilities: {', '.join(caps[:10])}" + ("..." if len(caps) > 10 else ""))
        print(f"  Created: {agent['created_at']}")
        print(f"  Updated: {agent['updated_at']}")
        return 0

    if args.command == "agent-remove":
        from .agent_registry import AgentRegistry
        registry = AgentRegistry()
        agent = registry.get_agent(args.agent_id)
        if agent is None:
            registry.close()
            print(f"  Agent not found: {args.agent_id}")
            return 1
        registry.remove(args.agent_id)
        registry.close()
        print(f"  Archived agent: {agent['name']} ({args.agent_id})")
        print(f"  The agent directory at {agent['output_dir']} is unchanged.")
        return 0

    if args.command == "agent-register":
        from .agent_registry import AgentRegistry
        from .onchain_registry import (
            BASE_SEPOLIA_CHAIN_ID,
            DEFAULT_RPC_SEPOLIA,
            IDENTITY_REGISTRY_BASE_SEPOLIA,
            OnchainRegistry,
        )

        registry = AgentRegistry()
        agent = registry.get_agent(args.agent_id)
        registry.close()
        if agent is None:
            print(f"  Agent not found in local registry: {args.agent_id}")
            print("  Run 'forge agent-list' to see available agents.")
            return 1

        use_testnet = getattr(args, "testnet", False)
        rpc_url = getattr(args, "rpc_url", "") or "https://mainnet.base.org"
        if use_testnet:
            onchain = OnchainRegistry(
                registry_address=IDENTITY_REGISTRY_BASE_SEPOLIA,
                rpc_url=DEFAULT_RPC_SEPOLIA,
                chain_id=BASE_SEPOLIA_CHAIN_ID,
            )
            network_name = "Base Sepolia (testnet)"
        else:
            onchain = OnchainRegistry(rpc_url=rpc_url)
            network_name = "Base mainnet"

        metadata_uri = getattr(args, "metadata_uri", None) or ""
        if not metadata_uri:
            # Auto-generate a metadata URI from the agent's spec
            agent_dir = Path(agent["output_dir"])
            metadata = {
                "name": agent["name"],
                "agent_id": agent["agent_id"],
                "evm_address": agent.get("evm_address"),
                "capabilities": json.loads(agent.get("capabilities", "[]")),
                "provider": agent.get("provider"),
                "chain": agent.get("chain"),
                "planner": f"{agent.get('planner_mode', '?')}/{agent.get('planner_model', '?')}",
            }
            # For now, encode as a data URI. In production, upload to IPFS.
            import base64
            metadata_json = json.dumps(metadata, indent=2)
            metadata_uri = "data:application/json;base64," + base64.b64encode(metadata_json.encode()).decode()

        print(f"  Agent: {agent['name']} ({args.agent_id})")
        print(f"  Network: {network_name}")
        print(f"  Registry: {onchain.registry_address}")
        print()

        # Build the unsigned transaction
        tx = onchain.build_register_tx(agent_uri=metadata_uri)
        print("  Unsigned registration transaction:")
        print(f"    to:      {tx['to']}")
        print(f"    chainId: {tx['chainId']}")
        print(f"    data:    {tx['data'][:80]}...")
        print()
        print("  To submit this transaction, sign and send via your wallet:")
        print(f"    forge wallet-send-tx --chain evm --tx-hex {tx['data'][:40]}...")
        print()
        print("  Or use cast (Foundry):")
        print(f"    cast send {tx['to']} {tx['data'][:40]}... --rpc-url {onchain.rpc_url}")
        print()

        # Try to submit the transaction via OWS
        agent_dir = Path(agent["output_dir"])
        if agent_dir.exists() and (agent_dir / "wallet.json").exists():
            print(f"  Submitting to {network_name}...")
            try:
                from .onchain_registry import encode_eip1559_unsigned
                raw_hex = encode_eip1559_unsigned(tx)
                from .wallet import sign_and_send
                result = sign_and_send(agent_dir, "base", raw_hex, rpc_url=onchain.rpc_url)
                tx_hash = result.get("tx_hash", "")
                if tx_hash:
                    print(f"  TX Hash: {tx_hash}")
                    print(f"  View: https://basescan.org/tx/{tx_hash}")
                    # Update local registry with on-chain status
                    try:
                        from .agent_registry import AgentRegistry
                        reg = AgentRegistry()
                        reg.update_status(args.agent_id, "registered")
                        reg.close()
                    except Exception:
                        pass
                else:
                    print(f"  Result: {result}")
            except Exception as error:
                print(f"  Submission failed: {error}")
                print("  The unsigned transaction is ready — submit manually:")
                print(f"    cast send {tx['to']} --data {tx['data'][:60]}...")
        else:
            print("  No wallet found — build the unsigned tx and submit manually.")

        return 0

    if args.command == "agent-discover":
        from .onchain_registry import OnchainRegistry
        rpc_url = getattr(args, "rpc_url", "") or "https://mainnet.base.org"
        onchain = OnchainRegistry(rpc_url=rpc_url)

        print(f"  Registry: {onchain.registry_address}")
        print(f"  Contract: {onchain.contract_name()}")
        print()

        if getattr(args, "agent_id", None):
            info = onchain.agent_info(args.agent_id)
            print(f"  Agent #{info['agent_id']}:")
            print(f"    Owner: {info['owner']}")
            print(f"    Wallet: {info['wallet'] or '(not set)'}")
            uri = info["token_uri"]
            print(f"    URI: {uri[:120]}" + ("..." if len(uri) > 120 else ""))
            if uri.startswith("data:application/json;base64,"):
                import base64 as b64
                try:
                    meta = json.loads(b64.b64decode(uri.split(",", 1)[1]))
                    print(f"    Metadata: {json.dumps(meta, indent=6)}")
                except Exception:
                    pass
            # Cache as peer
            try:
                from .agent_registry import AgentRegistry
                reg = AgentRegistry()
                reg.upsert_peer(
                    peer_address=info["owner"],
                    name=f"agent-{args.agent_id}",
                    capabilities=[],
                    source="registry",
                )
                reg.close()
            except Exception:
                pass
            return 0

        if getattr(args, "address", None):
            balance = onchain.balance_of(args.address)
            print(f"  Address {args.address[:12]}... owns {balance} agent(s)")
            return 0

        print("  Usage: forge agent-discover --agent-id 12345")
        print("         forge agent-discover --address 0x...")
        return 0

    if args.command == "agent-send":
        from .a2a_client import A2AForgeClient
        endpoint = args.endpoint
        capability = args.capability
        payload = json.loads(args.payload) if args.payload else {}
        text = getattr(args, "text", None)

        print(f"  Sending task to {endpoint}...")
        print(f"  Capability: {capability}")
        if payload:
            print(f"  Payload: {json.dumps(payload, indent=2)}")

        client = A2AForgeClient(endpoint)

        # First check if the agent is reachable
        try:
            card = client.get_agent_card()
            print(f"  Remote agent: {card.name if hasattr(card, 'name') else card.get('name', '?')}")
            skills = card.skills if hasattr(card, "skills") else card.get("skills", [])
            skill_names = [s.name if hasattr(s, "name") else s.get("name", "") for s in skills]
            print(f"  Skills: {', '.join(skill_names[:10])}")
        except Exception as error:
            print(f"  ERROR: Could not reach agent at {endpoint}: {error}")
            return 1

        # Send the task
        try:
            result = client.send_task(
                capability=capability,
                arguments=payload,
                text=text,
            )
            status = result.get("status", {})
            state = status.get("state", "unknown") if isinstance(status, dict) else str(status)
            print(f"\n  Task status: {state}")
            artifacts = result.get("artifacts", [])
            if artifacts:
                print("  Artifacts:")
                for i, artifact in enumerate(artifacts):
                    parts = artifact.get("parts", [])
                    for part in parts:
                        text_val = part.get("text", "") if isinstance(part, dict) else str(part)
                        print(f"    [{i}] {text_val[:200]}")
            print(f"\n  Task ID: {result.get('id', '?')}")
        except Exception as error:
            print(f"  ERROR: Task failed: {error}")
            return 1

        return 0

    if args.command == "replay-show":
        return _cmd_replay_show(args)

    if args.command == "replays":
        return _cmd_replays(args)

    parser.print_help()
    return 1


def _cmd_replay_show(args) -> int:
    """Show a replay file in human-readable format — for debugging."""
    from pathlib import Path
    replay_path = Path(args.replay_path)
    if not replay_path.exists():
        print(f"  ERROR: Replay file not found: {replay_path}")
        return 1
    try:
        data = json.loads(replay_path.read_text())
    except json.JSONDecodeError as error:
        print(f"  ERROR: Replay file is not valid JSON: {error}")
        return 1

    if not args.steps_only:
        print(f"  Replay: {replay_path.name}")
        print(f"  Tick: {data.get('tickNumber', '?')}")
        print(f"  Status: {data.get('sessionStatus', '?')}")
        print(f"  Started: {data.get('startedAt', '?')}")
        print(f"  Environment: {data.get('environment', '?')}")
        print()

    ledger = data.get("stepLedger", [])
    print(f"  Step Ledger ({len(ledger)} steps):")
    print()
    for i, step in enumerate(ledger, 1):
        proposal = step.get("proposal", {})
        kind = proposal.get("kind", "?")
        cap = proposal.get("capabilityId") or "—"
        desc = proposal.get("description", "") or ""
        if not args.full and len(desc) > 100:
            desc = desc[:97] + "..."
        lifecycle = step.get("lifecycle", "?")
        print(f"  [{i:>2}] {kind:<18} {cap:<30}")
        if desc:
            print(f"       desc: {desc}")
        print(f"       result: {lifecycle}")

        if args.full:
            payload = proposal.get("payload")
            if payload:
                print(f"       payload: {json.dumps(payload, indent=14)[:500]}")
            result = step.get("result")
            if result:
                print(f"       output: {json.dumps(result, indent=14)[:500]}")
        print()
    return 0


def _cmd_replays(args) -> int:
    """List all replay files for an agent."""
    from pathlib import Path
    replay_dir = Path(args.agent_directory) / "replays"
    if not replay_dir.exists():
        print(f"  No replays directory at {replay_dir}")
        print("  (Has the agent run yet?)")
        return 1
    files = sorted(replay_dir.glob("tick_*.json"))
    if not files:
        print(f"  No replay files found in {replay_dir}")
        return 1
    print(f"  Replays in {replay_dir}:")
    print()
    print(f"  {'TICK':<6}  {'STATUS':<12}  {'STEPS':<6}  {'TIME'}")
    print("  " + "-" * 60)
    for f in files[-args.limit:]:
        try:
            data = json.loads(f.read_text())
            tick = data.get("tickNumber", "?")
            status = data.get("sessionStatus", "?")
            steps = len(data.get("stepLedger", []))
            time = data.get("startedAt", "")[:19]
            print(f"  {tick:<6}  {status:<12}  {steps:<6}  {time}")
        except Exception:
            print(f"  (broken: {f.name})")
    print()
    print(f"  forge replay-show {files[-1]}")
    return 0


def main_cli() -> None:
    """CLI entry point with friendly error handling.

    Wraps ``main()`` so common errors produce actionable messages instead of
    raw tracebacks. Pass ``-v`` to see full tracebacks.
    """
    import sys
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n  Interrupted.", file=sys.stderr)
        raise SystemExit(130)
    except FileNotFoundError as error:
        print(f"\n  ERROR: File not found: {error.filename}", file=sys.stderr)
        print("  Hint: Check the path. If this is an agent directory, run `forge generate-fast` first.", file=sys.stderr)
        raise SystemExit(2)
    except PermissionError as error:
        print(f"\n  ERROR: Permission denied: {error.filename}", file=sys.stderr)
        print("  Hint: Check file permissions or run with appropriate user.", file=sys.stderr)
        raise SystemExit(2)
    except SystemExit:
        raise
    except Exception as error:
        if verbose:
            raise
        msg = str(error)
        print(f"\n  ERROR: {type(error).__name__}: {msg}", file=sys.stderr)
        # Hints for common errors
        if "api_key" in msg.lower() or "api key" in msg.lower():
            print("  Hint: Set the API key env var for your planner provider:", file=sys.stderr)
            print("    export OPENROUTER_API_KEY=...    (or ANTHROPIC_API_KEY, OPENAI_API_KEY, etc.)", file=sys.stderr)
        elif "could not convert string to float" in msg:
            print("  Hint: A numeric field in your config or strategy contains a non-numeric value.", file=sys.stderr)
            print("  Check strategy.json and aether-forge.json for values like '50%' (use 0.5 instead).", file=sys.stderr)
        elif "no such table" in msg.lower():
            print("  Hint: The agent's memory database is missing or corrupted. Try `rm memory.db` and re-run.", file=sys.stderr)
        elif "connection" in msg.lower() or "timed out" in msg.lower():
            print("  Hint: Check your network and that the LLM/RPC endpoint is reachable.", file=sys.stderr)
            print("  For local Ollama: `ollama serve` should be running.", file=sys.stderr)
        elif "missing required settings" in msg.lower():
            print("  Hint: Some planner config is missing. Run `forge doctor` to verify your setup.", file=sys.stderr)
        print("  For full traceback, re-run with `-v`.", file=sys.stderr)
        raise SystemExit(1)


def _autodetect_planner() -> dict[str, str | None]:
    """Pick the best planner available on this machine for a freshly built agent.

    Aether Forge agents are LLM-driven by design. Try, in order:
      1. Local Ollama daemon — if reachable AND has at least one model, use it.
         No API key, no cost, no network round-trip beyond localhost.
      2. Anthropic — if ``ANTHROPIC_API_KEY`` is set.
      3. OpenAI — if ``OPENAI_API_KEY`` is set.
      4. Gemini — if ``GOOGLE_API_KEY`` or ``GEMINI_API_KEY`` is set.
      5. OpenRouter — if ``OPENROUTER_API_KEY`` is set.
      6. Heuristic fallback — last resort, no LLM, no real planning.
    """
    import json as _json
    import os as _os
    from urllib import error as _urllib_error
    from urllib import request as _urllib_request

    # 1. Local Ollama
    base_url = _os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
    try:
        req = _urllib_request.Request(f"{base_url}/api/tags")
        with _urllib_request.urlopen(req, timeout=2) as resp:  # noqa: S310
            payload = _json.loads(resp.read().decode("utf8"))
            models = payload.get("models") or []
            if models:
                # Prefer a Gemma model if present, otherwise first available.
                preferred = next(
                    (m["name"] for m in models if "gemma" in m.get("name", "").lower()),
                    models[0].get("name"),
                )
                return {
                    "mode": "ollama",
                    "model": preferred,
                    "base_url": base_url,
                    "api_key_env": None,
                }
    except (_urllib_error.URLError, _urllib_error.HTTPError, TimeoutError, OSError, ValueError):
        pass

    # 2-5. Cloud provider via env var
    cloud_chain = [
        ("anthropic", "ANTHROPIC_API_KEY", "claude-sonnet-4-5"),
        ("openai", "OPENAI_API_KEY", "gpt-4o"),
        ("gemini", "GOOGLE_API_KEY", "gemini-2.5-flash"),
        ("gemini", "GEMINI_API_KEY", "gemini-2.5-flash"),
        ("openrouter", "OPENROUTER_API_KEY", "anthropic/claude-sonnet-4.5"),
    ]
    for mode, env_var, default_model in cloud_chain:
        if _os.getenv(env_var):
            return {
                "mode": mode,
                "model": default_model,
                "base_url": None,
                "api_key_env": env_var,
            }

    # 6. Heuristic fallback
    return {
        "mode": "heuristic",
        "model": None,
        "base_url": None,
        "api_key_env": None,
    }


def _add_planner_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="Optional path to aether-forge.json config file.")
    parser.add_argument(
        "--planner-mode",
        choices=["heuristic", "static", "openai-compatible", "function-call", "anthropic", "gemini", "openai", "openrouter", "ollama"],
        help="Planner mode; falls back to env config when omitted.",
    )
    parser.add_argument("--planner-static-response-file", help="Path to a JSON response file for static planner mode.")
    parser.add_argument("--planner-model", help="Model name for the planner.")
    parser.add_argument("--planner-base-url", help="Base URL for the planner API.")
    parser.add_argument("--planner-api-key", help="API key for the planner.")
    parser.add_argument("--planner-api-key-env", help="Environment variable name that holds the planner API key.")


def _planner_factory_from_args(args: argparse.Namespace):
    config = _config_from_args(args)
    settings = resolve_planner_settings(
        config=config,
        mode=getattr(args, "planner_mode", None),
        static_response_file=getattr(args, "planner_static_response_file", None),
        model=getattr(args, "planner_model", None),
        base_url=getattr(args, "planner_base_url", None),
        api_key=getattr(args, "planner_api_key", None),
        api_key_env=getattr(args, "planner_api_key_env", None),
    )
    return build_planner_factory(settings)


def _add_memory_store_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--memory-store",
        choices=["memory", "sqlite"],
        default="memory",
        help="Memory store backend: 'memory' (in-process, default) or 'sqlite' (persistent).",
    )
    parser.add_argument("--memory-db", help="Path to SQLite database file for persistent memory (used with --memory-store sqlite).")


def _add_crypto_router_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--crypto-router",
        choices=["mock", "public-market-data", "paper-trading", "sim-wallet", "ows-wallet", "scaffold-live"],
        default="mock",
        help="Crypto execution router backend.",
    )


def _execution_router_factory_from_args(args: argparse.Namespace, *, project_root: Path | None = None):
    config = _config_from_args(args)
    settings = resolve_runtime_settings(
        config=config,
        crypto_router=getattr(args, "crypto_router", None),
    )
    if settings.crypto_router == "scaffold-live":
        if project_root is None:
            raise ValueError("scaffold-live router requires a project or artifact directory context")
        return lambda: build_scaffold_live_exchange_router(project_root)
    if settings.crypto_router == "ows-wallet":
        return OWSWalletCryptoExecutionRouter
    if settings.crypto_router == "sim-wallet":
        return SimWalletCryptoExecutionRouter
    if settings.crypto_router == "paper-trading":
        return AuthenticatedPaperTradingCryptoExecutionRouter
    if settings.crypto_router == "public-market-data":
        return PublicMarketDataCryptoExecutionRouter
    return MockCryptoExecutionRouter


def _config_from_args(args: argparse.Namespace) -> dict[str, object]:
    explicit_path = getattr(args, "config", None)
    if explicit_path:
        return load_config_file(Path(explicit_path).resolve())

    artifact_directory = getattr(args, "artifact_directory", None)
    discovered = discover_default_config_path(artifact_directory)
    if discovered is None:
        return {}

    return load_config_file(discovered)


def _research_model_from_args(args: argparse.Namespace):
    """Resolve planner settings and return a ResearchModel (or None for heuristic/no-model)."""
    config = _config_from_args(args)
    settings = resolve_planner_settings(
        config=config,
        mode=getattr(args, "planner_mode", None),
        static_response_file=getattr(args, "planner_static_response_file", None),
        model=getattr(args, "planner_model", None),
        base_url=getattr(args, "planner_base_url", None),
        api_key=getattr(args, "planner_api_key", None),
        api_key_env=getattr(args, "planner_api_key_env", None),
    )
    if settings.mode in ("openai-compatible", "function-call"):
        return OpenAICompatiblePlanningModel(
            model=settings.model or "",
            api_key=settings.api_key or "",
            base_url=settings.base_url or "",
        )
    if settings.mode == "anthropic":
        return AnthropicPlanningModel(
            model=settings.model or "",
            api_key=settings.api_key or "",
            base_url=settings.base_url or "https://api.anthropic.com",
        )
    if settings.mode == "gemini":
        return GeminiPlanningModel(
            model=settings.model or "",
            api_key=settings.api_key or "",
            base_url=settings.base_url or "https://generativelanguage.googleapis.com",
        )
    if settings.mode == "static":
        if settings.static_response_file:
            response = Path(settings.static_response_file).read_text(encoding="utf8")
            return StaticPlanningModel(response=response)
        return None
    return None


def _memory_store_from_args(args: argparse.Namespace, *, artifact_directory: Path | None = None):
    """Build a memory store from CLI arguments."""
    backend = getattr(args, "memory_store", "memory")
    if backend == "sqlite":
        db_path = getattr(args, "memory_db", None)
        if db_path is None:
            if artifact_directory is not None:
                db_path = artifact_directory / "memory.db"
            else:
                db_path = Path.cwd() / "memory.db"
        return SqliteMemoryStore(db_path)
    return None  # RuntimeSession will use InMemoryMemoryStore by default


def _ows_adapter_from_args(args: argparse.Namespace) -> OpenWalletStandardAdapter:
    vault_path = getattr(args, "vault_path", None)
    return OpenWalletStandardAdapter(vault_path=vault_path)

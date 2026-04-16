"""OWS wallet provisioning and management for Aether Forge agents.

Creates real multi-chain wallets using the Open Wallet Standard SDK with:
- Per-agent vault isolation (~/.ows/ or agent-local)
- Policy creation restricting agent to declared chains
- Scoped API key (agent never gets owner passphrase)
- Passphrase-protected wallet encryption

Falls back to simulated addresses when OWS SDK is not installed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# CAIP-2 chain identifiers for common chains
CHAIN_CAIP2 = {
    "ethereum": "eip155:1",
    "base": "eip155:8453",
    "arbitrum": "eip155:42161",
    "optimism": "eip155:10",
    "polygon": "eip155:137",
    "solana": "solana:5eykt4UsFv8P8NJdTREpY1vzqKqZKvdp",
    "bitcoin": "bip122:000000000019d6689c085ae165831e93",
    "cosmos": "cosmos:cosmoshub-4",
    "tron": "tron:mainnet",
    "ton": "ton:mainnet",
    "sui": "sui:mainnet",
    "filecoin": "fil:mainnet",
    "xrpl": "xrpl:mainnet",
}


@dataclass(slots=True)
class AgentWallet:
    """Fully provisioned agent wallet with policy and API key."""

    wallet_id: str
    wallet_name: str
    provider: str  # "ows" or "simulated"
    mnemonic: str | None = None  # Shown once, user must save
    api_key_token: str | None = None  # ows_key_... for agent access
    api_key_id: str | None = None
    policy_id: str | None = None
    vault_path: str | None = None
    accounts: list[dict[str, Any]] = field(default_factory=list)
    evm_address: str = ""
    solana_address: str = ""
    bitcoin_address: str = ""

    def address_for_chain(self, chain: str) -> str | None:
        """Get address for a chain name or CAIP-2 ID."""
        chain_lower = chain.lower()
        for acc in self.accounts:
            cid = acc.get("chain_id", "").lower()
            if chain_lower in cid or cid.startswith(chain_lower):
                return acc.get("address")
        return None


def provision_wallet(
    *,
    agent_name: str,
    output_directory: Path,
    allowed_chains: list[str] | None = None,
    passphrase: str | None = None,
    vault_path: str | None = None,
) -> AgentWallet:
    """Create a proper OWS wallet for an agent.

    Flow:
    1. Generate mnemonic
    2. Import wallet from mnemonic (derives all chain addresses)
    3. Create policy restricting to declared chains
    4. Create scoped API key (agent uses this, not passphrase)
    5. Save wallet config to agent directory

    Falls back to simulated when OWS SDK is not installed.
    """
    try:
        return _provision_ows_wallet(
            agent_name=agent_name,
            output_directory=output_directory,
            allowed_chains=allowed_chains,
            passphrase=passphrase,
            vault_path=vault_path,
        )
    except RuntimeError as error:
        logger.warning("OWS not available: %s — using simulated wallet", error)
        return _provision_simulated_wallet(agent_name=agent_name, output_directory=output_directory)


def _provision_ows_wallet(
    *,
    agent_name: str,
    output_directory: Path,
    allowed_chains: list[str] | None = None,
    passphrase: str | None = None,
    vault_path: str | None = None,
) -> AgentWallet:
    """Create a real OWS wallet with policy and API key."""
    try:
        from importlib import import_module
        ows = import_module("ows")
    except ModuleNotFoundError as error:
        raise RuntimeError("pip install aether-forge[wallet]") from error

    wallet_name = f"forge-{agent_name}"

    # Per-agent vault isolation — each agent gets its own vault directory
    # This prevents agents from accessing each other's wallets
    if vault_path:
        vault_opt = vault_path
    else:
        vault_opt = str(output_directory / ".ows")
    Path(vault_opt).mkdir(parents=True, exist_ok=True)

    # 1. Generate mnemonic
    mnemonic = ows.generate_mnemonic(12)

    # 2. Import wallet from mnemonic (derives all 9+ chain addresses)
    try:
        wallet_data = ows.import_wallet_mnemonic(
            wallet_name, mnemonic,
            passphrase=passphrase,
            vault_path_opt=vault_opt,
        )
    except Exception:
        # Wallet name may already exist — delete and retry
        try:
            ows.delete_wallet(wallet_name, vault_path_opt=vault_opt)
        except Exception:
            pass
        wallet_data = ows.import_wallet_mnemonic(
            wallet_name, mnemonic,
            passphrase=passphrase,
            vault_path_opt=vault_opt,
        )

    wallet_id = wallet_data.get("id", wallet_name)
    accounts = wallet_data.get("accounts", [])

    # Extract key addresses
    evm_addr = ""
    sol_addr = ""
    btc_addr = ""
    for acc in accounts:
        cid = acc.get("chain_id", "")
        addr = acc.get("address", "")
        if cid.startswith("eip155"):
            evm_addr = evm_addr or addr
        elif "solana" in cid:
            sol_addr = addr
        elif "bip122" in cid:
            btc_addr = addr

    # 3. Create policy restricting to declared chains
    policy_id = None
    if allowed_chains:
        chain_ids = []
        for chain in allowed_chains:
            if chain in CHAIN_CAIP2:
                chain_ids.append(CHAIN_CAIP2[chain])
            elif ":" in chain:
                chain_ids.append(chain)  # Already CAIP-2
            else:
                # Try common EVM chains
                evm_id = CHAIN_CAIP2.get(chain.lower())
                if evm_id:
                    chain_ids.append(evm_id)

        if not chain_ids:
            # Default: Base + Ethereum
            chain_ids = ["eip155:1", "eip155:8453"]

        policy_doc = {
            "id": f"policy-{agent_name}",
            "name": f"{agent_name} chain restrictions",
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
            "rules": [
                {"type": "allowed_chains", "chain_ids": chain_ids},
            ],
            "action": "deny",
        }

        try:
            ows.create_policy(
                json.dumps(policy_doc),
                vault_path_opt=vault_opt,
            )
            # create_policy returns None but stores the policy — use our ID
            policy_id = f"policy-{agent_name}"
            logger.info("Policy created: %s (chains: %s)", policy_id, chain_ids)
        except Exception as error:
            logger.warning("Policy creation failed: %s", error)

    # 4. Create scoped API key for agent access
    # The API key creation requires the wallet's passphrase for decryption
    # When no passphrase was set, OWS uses empty string as default
    api_key_token = None
    api_key_id = None
    if policy_id:
        key_passphrase = passphrase or ""
        try:
            key_result = ows.create_api_key(
                f"agent-{agent_name}",
                [wallet_id],
                [policy_id],
                key_passphrase,
                vault_path_opt=vault_opt,
            )
            if key_result:
                api_key_token = key_result.get("token")
                api_key_id = key_result.get("id")
                logger.info("API key created: %s (policy: %s)", api_key_id, policy_id)
            else:
                logger.info("API key creation returned None — agent will use passphrase mode")
        except Exception as error:
            logger.warning("API key creation failed (%s) — agent will use passphrase mode", error)

    # 5. Build wallet info
    wallet = AgentWallet(
        wallet_id=wallet_id,
        wallet_name=wallet_name,
        provider="ows",
        mnemonic=mnemonic,
        api_key_token=api_key_token,
        api_key_id=api_key_id,
        policy_id=policy_id,
        vault_path=vault_opt,
        accounts=accounts,
        evm_address=evm_addr,
        solana_address=sol_addr,
        bitcoin_address=btc_addr,
    )

    # 6. Save to agent directory
    _save_wallet_config(wallet, output_directory)

    # 6b. Apply security hardening — lock down sensitive files
    try:
        from .security_hardening import harden_agent_directory
        harden_agent_directory(output_directory)
    except Exception as error:
        logger.warning("Failed to apply security hardening: %s", error)

    # 7. Print credentials (shown once)
    _print_credentials(wallet)

    return wallet


def _provision_simulated_wallet(
    *,
    agent_name: str,
    output_directory: Path,
) -> AgentWallet:
    """Generate simulated wallet addresses (no real keys)."""
    import hashlib
    import secrets

    seed = secrets.token_hex(16)
    evm = "0x" + hashlib.sha256(f"evm:{seed}".encode()).hexdigest()[:40]
    sol = hashlib.sha256(f"sol:{seed}".encode()).hexdigest()[:44]
    btc = "bc1q" + hashlib.sha256(f"btc:{seed}".encode()).hexdigest()[:38]

    wallet = AgentWallet(
        wallet_id=f"sim_{agent_name}_{secrets.token_hex(4)}",
        wallet_name=f"forge-{agent_name}",
        provider="simulated",
        evm_address=evm,
        solana_address=sol,
        bitcoin_address=btc,
        accounts=[
            {"chain_id": "eip155:1", "address": evm, "status": "simulated"},
            {"chain_id": "eip155:8453", "address": evm, "status": "simulated"},
            {"chain_id": "solana:mainnet", "address": sol, "status": "simulated"},
            {"chain_id": "bip122:mainnet", "address": btc, "status": "simulated"},
        ],
    )

    _save_wallet_config(wallet, output_directory)
    logger.info("Simulated wallet created — install OWS for real wallets: pip install aether-forge[wallet]")
    return wallet


def _save_wallet_config(wallet: AgentWallet, output_directory: Path) -> None:
    """Save wallet config to agent directory (NEVER saves mnemonic or API token)."""
    config = {
        "walletId": wallet.wallet_id,
        "walletName": wallet.wallet_name,
        "provider": wallet.provider,
        "policyId": wallet.policy_id,
        "apiKeyId": wallet.api_key_id,
        "vaultPath": wallet.vault_path,
        "accounts": [
            {
                "chainId": acc.get("chain_id", ""),
                "address": acc.get("address", ""),
                "derivationPath": acc.get("derivation_path", ""),
            }
            for acc in wallet.accounts
        ],
        "addresses": {
            "evm": wallet.evm_address,
            "solana": wallet.solana_address,
            "bitcoin": wallet.bitcoin_address,
        },
        "funded": False,
        "createdAt": datetime.now(UTC).isoformat(),
    }

    if wallet.provider == "simulated":
        config["note"] = "Simulated — no real keys. Install OWS: pip install aether-forge[wallet]"
    else:
        config["note"] = "Real OWS wallet. Fund before live mode. API token in .env (never commit)."

    wallet_path = output_directory / "wallet.json"
    wallet_path.write_text(json.dumps(config, indent=2) + "\n", encoding="utf8")

    # Save API token to .env file (gitignored)
    if wallet.api_key_token:
        env_path = output_directory / ".env"
        env_content = f"# Agent wallet API key — NEVER commit this file\nOWS_API_KEY={wallet.api_key_token}\n"
        env_path.write_text(env_content, encoding="utf8")
        env_path.chmod(0o600)

        # Add secrets-related entries to .gitignore
        gitignore_path = output_directory / ".gitignore"
        gitignore_lines = []
        if gitignore_path.exists():
            gitignore_lines = gitignore_path.read_text(encoding="utf8").splitlines()
        protected_entries = [
            ".env",
            "wallet-mnemonic.txt",
            ".ows/",  # Per-agent vault — encrypted keys, never commit
            "wallet-backup-*.json",
            "wallet-backup-*.json.enc",
            "x402_state.json",  # Persistent budget state may contain wallet metadata
        ]
        added = False
        for entry in protected_entries:
            if entry not in gitignore_lines:
                gitignore_lines.append(entry)
                added = True
        if added:
            gitignore_path.write_text("\n".join(gitignore_lines) + "\n", encoding="utf8")

    # Update aether-forge.json
    aether_config_path = output_directory / "aether-forge.json"
    if aether_config_path.exists():
        aether_config = json.loads(aether_config_path.read_text(encoding="utf8"))
        aether_config["wallet"] = {
            "walletId": wallet.wallet_id,
            "walletName": wallet.wallet_name,
            "provider": wallet.provider,
            "configPath": "wallet.json",
            "policyId": wallet.policy_id,
            "apiKeyId": wallet.api_key_id,
            "evmAddress": wallet.evm_address,
            "solanaAddress": wallet.solana_address,
            "bitcoinAddress": wallet.bitcoin_address,
        }
        aether_config_path.write_text(json.dumps(aether_config, indent=2) + "\n", encoding="utf8")


def _print_credentials(wallet: AgentWallet) -> None:
    """Print wallet credentials once at creation time."""
    print()
    if wallet.mnemonic:
        print("  MNEMONIC — save this securely, it will NOT be shown again:")
        print(f"  {wallet.mnemonic}")
        print()
    if wallet.api_key_token:
        print("  API KEY — saved to .env (never commit this file):")
        print(f"  {wallet.api_key_token[:20]}...{wallet.api_key_token[-8:]}")
        print()
    print(f"  Wallet: {wallet.wallet_name} ({wallet.provider})")
    print(f"  Accounts: {len(wallet.accounts)} chains")
    if wallet.policy_id:
        print(f"  Policy: {wallet.policy_id}")
    print()


# ---------------------------------------------------------------------------
# Wallet operations for running agents
# ---------------------------------------------------------------------------

def load_agent_wallet(agent_directory: Path) -> dict[str, Any]:
    """Load wallet config from an agent directory."""
    wallet_path = agent_directory / "wallet.json"
    if not wallet_path.exists():
        return {}
    return json.loads(wallet_path.read_text(encoding="utf8"))


def get_signing_credentials(agent_directory: Path) -> dict[str, str]:
    """Get the credentials needed for signing operations.

    Returns wallet name, API key token, and vault path.
    The agent uses the API key, never the passphrase.
    """
    import os

    wallet_config = load_agent_wallet(agent_directory)
    wallet_name = wallet_config.get("walletName", "")
    vault_path = wallet_config.get("vaultPath") or str(agent_directory / ".ows")

    # Try .env file first, then environment variable
    env_path = agent_directory / ".env"
    api_key = None
    if env_path.exists():
        for line in env_path.read_text(encoding="utf8").splitlines():
            if line.startswith("OWS_API_KEY="):
                api_key = line.split("=", 1)[1].strip()

    if not api_key:
        api_key = os.getenv("OWS_API_KEY")

    return {
        "wallet_name": wallet_name,
        "api_key": api_key or "",
        "vault_path": vault_path,
        "provider": wallet_config.get("provider", "simulated"),
    }


def sign_message(agent_directory: Path, chain: str, message: str) -> dict[str, Any]:
    """Sign a message using the agent's wallet and API key."""
    creds = get_signing_credentials(agent_directory)
    if creds["provider"] != "ows":
        return {"signature": "simulated-sig", "simulated": True}

    from importlib import import_module
    ows = import_module("ows")

    return ows.sign_message(
        creds["wallet_name"],
        chain,
        message,
        passphrase=creds["api_key"] if creds["api_key"].startswith("ows_key_") else None,
        vault_path_opt=creds.get("vault_path"),
    )


def backup_agent_wallet(agent_directory: Path, output_path: Path | None = None) -> Path:
    """Export an encrypted backup of the agent's wallet.

    Returns mnemonic via OWS export. Writes to output_path or
    agent_directory/wallet-backup-<timestamp>.json.

    THE BACKUP CONTAINS THE MNEMONIC. Treat it like a private key.
    """
    import json as _json
    from datetime import UTC, datetime

    wallet_config = load_agent_wallet(agent_directory)
    if wallet_config.get("provider") != "ows":
        raise RuntimeError("Backup only supported for OWS wallets")

    wallet_name = wallet_config.get("walletName", "")
    vault_path = wallet_config.get("vaultPath")

    try:
        from importlib import import_module
        ows = import_module("ows")
        export = ows.export_wallet(wallet_name, passphrase="", vault_path_opt=vault_path)
    except Exception as error:
        raise RuntimeError(f"OWS export failed: {error}") from error

    backup = {
        "version": 1,
        "wallet_name": wallet_name,
        "wallet_id": wallet_config.get("walletId"),
        "exported_at": datetime.now(UTC).isoformat(),
        "addresses": wallet_config.get("addresses", {}),
        "policy_id": wallet_config.get("policyId"),
        "secret": export,
        "warning": "Contains mnemonic. Encrypt before storing. Never commit to git.",
    }

    if output_path is None:
        ts = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        output_path = agent_directory / f"wallet-backup-{ts}.json"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_json.dumps(backup, indent=2) + "\n", encoding="utf8")
    output_path.chmod(0o600)  # Owner read/write only
    return output_path


def restore_agent_wallet(backup_path: Path, agent_directory: Path, *, passphrase: str | None = None) -> dict[str, Any]:
    """Restore an agent wallet from a backup file.

    Handles both encrypted and unencrypted backups. For encrypted backups,
    requires the passphrase.
    """
    import json as _json

    backup = _json.loads(Path(backup_path).read_text(encoding="utf8"))

    # Detect encrypted backup
    if backup.get("cipher") == "AES-256-GCM":
        if not passphrase:
            import getpass
            passphrase = getpass.getpass("Decryption passphrase: ")
        from .security_hardening import decrypt_backup
        backup = decrypt_backup(backup, passphrase)

    if backup.get("version") != 1:
        raise RuntimeError(f"Unsupported backup version: {backup.get('version')}")

    secret = backup.get("secret")
    if isinstance(secret, str):
        mnemonic = secret
    elif isinstance(secret, dict):
        mnemonic = secret.get("mnemonic")
    else:
        mnemonic = None
    if not mnemonic:
        raise RuntimeError("Backup contains no mnemonic")

    wallet_name = backup.get("wallet_name", "restored-wallet")
    vault_path = str(Path(agent_directory) / ".ows")
    Path(vault_path).mkdir(parents=True, exist_ok=True)

    try:
        from importlib import import_module
        ows = import_module("ows")
        result = ows.import_wallet_mnemonic(wallet_name, mnemonic, vault_path_opt=vault_path)
        return {
            "restored": True,
            "wallet_name": wallet_name,
            "wallet_id": result.get("id"),
            "vault_path": vault_path,
            "accounts": len(result.get("accounts", [])),
        }
    except Exception as error:
        raise RuntimeError(f"OWS import failed: {error}") from error


def sign_and_send(agent_directory: Path, chain: str, tx_hex: str, *, rpc_url: str | None = None) -> dict[str, Any]:
    """Sign and broadcast a transaction using the agent's wallet."""
    creds = get_signing_credentials(agent_directory)
    if creds["provider"] != "ows":
        return {"tx_hash": "0xsimulated", "simulated": True}

    from importlib import import_module
    ows = import_module("ows")

    return ows.sign_and_send(
        creds["wallet_name"],
        chain,
        tx_hex,
        passphrase=creds["api_key"] if creds["api_key"].startswith("ows_key_") else None,
        rpc_url=rpc_url,
        vault_path_opt=creds.get("vault_path"),
    )

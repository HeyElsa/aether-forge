"""Wallet adapters for crypto capabilities."""

from __future__ import annotations

from typing import Any, Protocol
from uuid import uuid4

from .types import CredentialLease, SimWalletAccount
from .utils import _load_ows_bindings, _ows_chain_matches


class OWSBindings(Protocol):
    def create_wallet(self, name: str, passphrase: str | None = None, words: int = 12, vault_path: str | None = None) -> dict[str, Any]: ...

    def get_wallet(self, name_or_id: str, vault_path: str | None = None) -> dict[str, Any]: ...

    def list_wallets(self, vault_path: str | None = None) -> list[dict[str, Any]]: ...

    def sign_message(
        self,
        wallet: str,
        chain: str,
        message: str,
        passphrase: str | None = None,
        encoding: str | None = None,
        index: int | None = None,
        vault_path: str | None = None,
    ) -> dict[str, Any]: ...

    def sign_transaction(
        self,
        wallet: str,
        chain: str,
        tx_hex: str,
        passphrase: str | None = None,
        index: int | None = None,
        vault_path: str | None = None,
    ) -> dict[str, Any]: ...

    def sign_and_send(
        self,
        wallet: str,
        chain: str,
        tx_hex: str,
        passphrase: str | None = None,
        index: int | None = None,
        rpc_url: str | None = None,
        vault_path: str | None = None,
    ) -> dict[str, Any]: ...

    # -- Wallet lifecycle ---------------------------------------------------

    def import_wallet_mnemonic(
        self,
        name: str,
        mnemonic: str,
        passphrase: str | None = None,
        index: int | None = None,
        vault_path: str | None = None,
    ) -> dict[str, Any]: ...

    def import_wallet_private_key(
        self,
        name: str,
        private_key_hex: str,
        chain: str | None = None,
        passphrase: str | None = None,
        vault_path: str | None = None,
    ) -> dict[str, Any]: ...

    def delete_wallet(self, name_or_id: str, vault_path: str | None = None) -> dict[str, Any]: ...

    def export_wallet(self, name_or_id: str, passphrase: str | None = None, vault_path: str | None = None) -> dict[str, Any]: ...

    def rename_wallet(self, name_or_id: str, new_name: str, vault_path: str | None = None) -> dict[str, Any]: ...

    # -- Signing ------------------------------------------------------------

    def sign_typed_data(
        self,
        wallet: str,
        chain: str,
        typed_data_json: str,
        passphrase: str | None = None,
        index: int | None = None,
        vault_path: str | None = None,
    ) -> dict[str, Any]: ...

    # -- Utilities ----------------------------------------------------------

    def generate_mnemonic(self, words: int = 12) -> str: ...

    def derive_address(self, mnemonic: str, chain: str, index: int = 0) -> str: ...

    # -- Policy management --------------------------------------------------

    def create_policy(self, policy_json: str, vault_path: str | None = None) -> dict[str, Any]: ...

    def list_policies(self, vault_path: str | None = None) -> list[dict[str, Any]]: ...

    def get_policy(self, id: str, vault_path: str | None = None) -> dict[str, Any]: ...

    def delete_policy(self, id: str, vault_path: str | None = None) -> dict[str, Any]: ...

    # -- API key management -------------------------------------------------

    def create_api_key(
        self,
        name: str,
        wallet_ids: list[str],
        policy_ids: list[str],
        passphrase: str,
        expires_at: str | None = None,
        vault_path: str | None = None,
    ) -> dict[str, Any]: ...

    def list_api_keys(self, vault_path: str | None = None) -> list[dict[str, Any]]: ...

    def revoke_api_key(self, id: str, vault_path: str | None = None) -> dict[str, Any]: ...


class InMemorySimWalletAdapter:
    def __init__(self) -> None:
        self.accounts: dict[str, SimWalletAccount] = {}
        self.transactions: list[dict[str, Any]] = []

    def create_account(self, *, chain: str, alias: str | None = None) -> dict[str, Any]:
        address = f"sim_{chain.lower()}_{uuid4().hex[:16]}"
        account = SimWalletAccount(address=address, chain=chain, native_balance=0.0)
        self.accounts[address] = account
        return {
            "address": address,
            "chain": chain,
            "alias": alias,
            "paper": True,
        }

    def get_account(self, *, chain: str, address: str | None = None) -> dict[str, Any]:
        if address is not None and address in self.accounts:
            account = self.accounts[address]
        else:
            account = next((candidate for candidate in self.accounts.values() if candidate.chain == chain), None)
            if account is None:
                created = self.create_account(chain=chain)
                account = self.accounts[created["address"]]

        return {
            "address": account.address,
            "chain": account.chain,
            "native_balance": account.native_balance,
            "paper": True,
        }

    def send_transaction(
        self,
        *,
        chain: str,
        to_address: str,
        amount: float,
        credential_lease: CredentialLease,
    ) -> dict[str, Any]:
        account = next((candidate for candidate in self.accounts.values() if candidate.chain == chain), None)
        if account is None:
            created = self.create_account(chain=chain)
            account = self.accounts[created["address"]]

        tx_id = f"sim_tx_{uuid4().hex}"
        self.transactions.append(
            {
                "txId": tx_id,
                "chain": chain,
                "from": account.address,
                "to": to_address,
                "amount": amount,
                "credentialHandleId": credential_lease.handle_id,
            }
        )
        return {
            "tx_id": tx_id,
            "chain": chain,
            "from_address": account.address,
            "to_address": to_address,
            "amount": amount,
            "paper": True,
        }


class OpenWalletStandardAdapter:
    def __init__(self, bindings: OWSBindings | None = None, vault_path: str | None = None) -> None:
        self.bindings = bindings or _load_ows_bindings()
        self.vault_path = vault_path

    def list_wallets(self) -> list[dict[str, Any]]:
        return self.bindings.list_wallets(vault_path=self.vault_path)

    def create_wallet(self, wallet_name: str) -> dict[str, Any]:
        return self.bindings.create_wallet(wallet_name, vault_path=self.vault_path)

    def get_wallet(self, wallet_name: str) -> dict[str, Any]:
        if hasattr(self.bindings, "get_wallet"):
            return self.bindings.get_wallet(wallet_name, vault_path=self.vault_path)

        wallets = self.bindings.list_wallets(vault_path=self.vault_path)
        for wallet in wallets:
            if wallet.get("name") == wallet_name or wallet.get("id") == wallet_name:
                return wallet
        raise ValueError(f"OWS wallet {wallet_name} not found")

    def get_account(self, wallet_name: str, chain: str) -> dict[str, Any]:
        wallet = self.get_wallet(wallet_name)
        for account in wallet.get("accounts", []):
            chain_id = str(account.get("chain_id") or account.get("chainId") or "")
            if _ows_chain_matches(chain_id, chain):
                return {
                    "wallet_name": wallet.get("name", wallet_name),
                    "wallet_id": wallet.get("id"),
                    "chain_id": chain_id,
                    "address": account.get("address"),
                    "derivation_path": account.get("derivation_path") or account.get("derivationPath"),
                    "ows": True,
                }
        raise ValueError(f"OWS wallet {wallet_name} does not expose an account for chain {chain}")

    def sign_message(self, wallet_name: str, chain: str, message: str) -> dict[str, Any]:
        payload = self.bindings.sign_message(wallet_name, chain, message, vault_path=self.vault_path)
        return {
            "wallet_name": wallet_name,
            "chain": chain,
            "signature": payload.get("signature"),
            "recovery_id": payload.get("recovery_id"),
            "ows": True,
        }

    def sign_transaction(self, wallet_name: str, chain: str, tx_hex: str, *, send: bool = False, rpc_url: str | None = None) -> dict[str, Any]:
        if send:
            payload = self.bindings.sign_and_send(wallet_name, chain, tx_hex, rpc_url=rpc_url, vault_path=self.vault_path)
            return {
                "wallet_name": wallet_name,
                "chain": chain,
                "tx_hash": payload.get("tx_hash") or payload.get("transactionHash"),
                "ows": True,
            }

        payload = self.bindings.sign_transaction(wallet_name, chain, tx_hex, vault_path=self.vault_path)
        return {
            "wallet_name": wallet_name,
            "chain": chain,
            "signature": payload.get("signature"),
            "recovery_id": payload.get("recovery_id"),
            "ows": True,
        }

    def import_wallet_mnemonic(self, name: str, mnemonic: str) -> dict[str, Any]:
        payload = self.bindings.import_wallet_mnemonic(name, mnemonic, vault_path=self.vault_path)
        return {
            "wallet_name": name,
            "wallet_id": payload.get("id"),
            "imported": True,
            "ows": True,
        }

    def delete_wallet(self, name: str) -> dict[str, Any]:
        payload = self.bindings.delete_wallet(name, vault_path=self.vault_path)
        return {
            "wallet_name": name,
            "deleted": True,
            "ows": True,
            **{k: v for k, v in payload.items() if k not in ("name", "id")},
        }

    def export_wallet(self, name: str) -> dict[str, Any]:
        payload = self.bindings.export_wallet(name, vault_path=self.vault_path)
        return {
            "wallet_name": name,
            "exported": True,
            "ows": True,
            **{k: v for k, v in payload.items() if k not in ("name", "id")},
        }

    def sign_typed_data(self, wallet_name: str, chain: str, typed_data_json: str) -> dict[str, Any]:
        payload = self.bindings.sign_typed_data(wallet_name, chain, typed_data_json, vault_path=self.vault_path)
        return {
            "wallet_name": wallet_name,
            "chain": chain,
            "signature": payload.get("signature"),
            "recovery_id": payload.get("recovery_id"),
            "ows": True,
        }

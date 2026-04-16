"""Security hardening utilities for Aether Forge agents.

Production-grade safeguards for systems handling real money:
- Encrypted wallet backups (passphrase-derived AES-256-GCM)
- File permission enforcement (0600 for secrets, 0700 for vaults)
- Log sanitization (strip mnemonics, API keys, signatures)
- Secret scanner for generated agent directories
- Pre-flight security checks before live operations

All functions are stdlib-only except encrypt/decrypt which use the
``cryptography`` package (already an optional dep via mempalace).
"""

from __future__ import annotations

import json
import logging
import re
import secrets
import stat
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Secret patterns — anything matching these should never appear in logs/audits
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    # 12/24-word BIP-39 mnemonics — rough heuristic: 12 or 24 lowercase words
    re.compile(r"\b(?:[a-z]+ ){11}[a-z]+\b"),
    re.compile(r"\b(?:[a-z]+ ){23}[a-z]+\b"),
    # OWS API keys
    re.compile(r"ows_key_[a-fA-F0-9]{32,}"),
    # Hex private keys (32 bytes)
    re.compile(r"\b0x[a-fA-F0-9]{64}\b"),
    # API tokens (sk_live_, sk-, ghp_, etc.)
    re.compile(r"\b(?:sk_live_|sk-|ghp_|sk_test_|api_key_)[a-zA-Z0-9_]{20,}\b"),
    # ETH-style signatures (130 hex chars)
    re.compile(r"\b0x[a-fA-F0-9]{130}\b"),
    # Anything labeled MNEMONIC
    re.compile(r"MNEMONIC[:=]\s*[\w\s]{50,}", re.IGNORECASE),
]

SECRET_FIELD_NAMES = {
    "mnemonic", "private_key", "privatekey", "secret", "passphrase",
    "api_key", "apikey", "ows_api_key", "signature", "seed", "seedphrase",
}


def sanitize_string(text: str) -> str:
    """Replace any secret patterns in text with [REDACTED]."""
    if not isinstance(text, str):
        return text
    sanitized = text
    for pattern in SECRET_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def sanitize_dict(data: Any) -> Any:
    """Recursively sanitize a dict, redacting secret-like fields."""
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            if isinstance(key, str) and key.lower() in SECRET_FIELD_NAMES:
                result[key] = "[REDACTED]"
            else:
                result[key] = sanitize_dict(value)
        return result
    if isinstance(data, list):
        return [sanitize_dict(item) for item in data]
    if isinstance(data, str):
        return sanitize_string(data)
    return data


# ---------------------------------------------------------------------------
# File permission enforcement
# ---------------------------------------------------------------------------

def lock_down_file(path: Path) -> None:
    """Set file to 0600 (owner read/write only)."""
    try:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception as error:
        logger.warning("Failed to lock down %s: %s", path, error)


def lock_down_directory(path: Path) -> None:
    """Set directory to 0700 (owner only) and all files inside to 0600."""
    try:
        path.chmod(stat.S_IRWXU)  # 0700
        for child in path.rglob("*"):
            if child.is_file():
                lock_down_file(child)
            elif child.is_dir():
                child.chmod(stat.S_IRWXU)
    except Exception as error:
        logger.warning("Failed to lock down %s: %s", path, error)


def harden_agent_directory(agent_directory: Path) -> dict[str, Any]:
    """Apply file perms to all sensitive files in an agent directory.

    Returns a report of what was changed.
    """
    report = {"locked_files": [], "locked_dirs": [], "errors": []}

    sensitive_files = [".env", "wallet.json", "x402_state.json", "memory.db", "halt"]
    sensitive_dirs = [".ows", "knowledge", "replays"]

    for fname in sensitive_files:
        path = agent_directory / fname
        if path.exists() and path.is_file():
            try:
                lock_down_file(path)
                report["locked_files"].append(str(path))
            except Exception as error:
                report["errors"].append(f"{path}: {error}")

    # Backup files
    for backup in agent_directory.glob("wallet-backup-*.json*"):
        try:
            lock_down_file(backup)
            report["locked_files"].append(str(backup))
        except Exception as error:
            report["errors"].append(f"{backup}: {error}")

    for dname in sensitive_dirs:
        path = agent_directory / dname
        if path.exists() and path.is_dir():
            try:
                lock_down_directory(path)
                report["locked_dirs"].append(str(path))
            except Exception as error:
                report["errors"].append(f"{path}: {error}")

    return report


# ---------------------------------------------------------------------------
# Encrypted backup
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class EncryptedBackup:
    """Schema for an encrypted wallet backup."""

    version: int
    cipher: str  # "AES-256-GCM"
    kdf: str  # "scrypt"
    salt: str  # base64
    nonce: str  # base64
    ciphertext: str  # base64 (encrypted JSON)
    metadata: dict[str, Any]


def encrypt_backup(plaintext: dict[str, Any], passphrase: str) -> dict[str, Any]:
    """Encrypt a wallet backup dict with a user passphrase.

    Uses scrypt for key derivation, AES-256-GCM for encryption.
    Requires the ``cryptography`` package.
    """
    if not passphrase or len(passphrase) < 8:
        raise ValueError("Passphrase must be at least 8 characters")

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as error:
        raise RuntimeError(
            "Encrypted backup requires the 'cryptography' package. "
            "Install with: pip install cryptography (already in mempalace deps)"
        ) from error

    salt = secrets.token_bytes(16)
    kdf = Scrypt(salt=salt, length=32, n=2**16, r=8, p=1)
    key = kdf.derive(passphrase.encode("utf8"))

    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    plaintext_bytes = json.dumps(plaintext).encode("utf8")
    ciphertext = aesgcm.encrypt(nonce, plaintext_bytes, None)

    # Sanitize metadata — only safe fields
    metadata = {
        "wallet_id": plaintext.get("wallet_id"),
        "wallet_name": plaintext.get("wallet_name"),
        "exported_at": plaintext.get("exported_at"),
        "addresses": plaintext.get("addresses", {}),
    }

    return {
        "version": 1,
        "cipher": "AES-256-GCM",
        "kdf": "scrypt",
        "kdf_params": {"n": 2**16, "r": 8, "p": 1, "length": 32},
        "salt": urlsafe_b64encode(salt).decode("ascii"),
        "nonce": urlsafe_b64encode(nonce).decode("ascii"),
        "ciphertext": urlsafe_b64encode(ciphertext).decode("ascii"),
        "metadata": metadata,
        "warning": "Encrypted with user passphrase. Decryption requires the same passphrase.",
    }


def decrypt_backup(encrypted: dict[str, Any], passphrase: str) -> dict[str, Any]:
    """Decrypt an encrypted backup with the user passphrase."""
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
    except ImportError as error:
        raise RuntimeError("Decryption requires the 'cryptography' package") from error

    if encrypted.get("cipher") != "AES-256-GCM":
        raise ValueError(f"Unsupported cipher: {encrypted.get('cipher')}")

    salt = urlsafe_b64decode(encrypted["salt"])
    nonce = urlsafe_b64decode(encrypted["nonce"])
    ciphertext = urlsafe_b64decode(encrypted["ciphertext"])
    params = encrypted.get("kdf_params", {"n": 2**16, "r": 8, "p": 1, "length": 32})

    kdf = Scrypt(salt=salt, length=params["length"], n=params["n"], r=params["r"], p=params["p"])
    key = kdf.derive(passphrase.encode("utf8"))

    aesgcm = AESGCM(key)
    try:
        plaintext_bytes = aesgcm.decrypt(nonce, ciphertext, None)
    except Exception as error:
        raise ValueError("Decryption failed — wrong passphrase or corrupted backup") from error

    return json.loads(plaintext_bytes.decode("utf8"))


# ---------------------------------------------------------------------------
# Secret scanner — find accidental key leakage
# ---------------------------------------------------------------------------

def scan_for_secrets(directory: Path, *, ignore_files: set[str] | None = None) -> list[dict[str, Any]]:
    """Scan a directory for files containing secret-like content.

    Returns a list of findings: file path, line number, pattern matched.
    Skips known safe files (.env files are expected to have keys).
    """
    findings = []
    ignore = ignore_files or {
        ".env",  # expected to contain API key
        "wallet-backup-*.json",
        "wallet.json",  # contains wallet IDs but no secrets in our schema
        "halt",
    }

    # Skip ignored directories
    skip_dirs = {".git", ".ows", "node_modules", "__pycache__", ".venv", "venv"}

    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue

        # Skip if any parent matches a skip dir
        if any(part in skip_dirs for part in file_path.parts):
            continue

        # Skip ignored files
        rel = file_path.relative_to(directory)
        if any(file_path.match(pat) for pat in ignore):
            continue

        # Don't scan binaries
        if file_path.suffix in {".db", ".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz"}:
            continue

        try:
            content = file_path.read_text(encoding="utf8")
        except (UnicodeDecodeError, PermissionError):
            continue

        for line_num, line in enumerate(content.splitlines(), 1):
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append({
                        "file": str(rel),
                        "line": line_num,
                        "pattern": pattern.pattern[:50],
                        "preview": sanitize_string(line)[:80],
                    })

    return findings


# ---------------------------------------------------------------------------
# Pre-flight security check
# ---------------------------------------------------------------------------

def preflight_security_check(agent_directory: Path) -> dict[str, Any]:
    """Run all security checks on an agent directory before going live.

    Returns a report with status, errors, and recommendations.
    """
    report = {
        "agent_directory": str(agent_directory),
        "checks": [],
        "errors": [],
        "warnings": [],
        "ok": True,
    }

    def add(name: str, status: str, message: str = "") -> None:
        report["checks"].append({"name": name, "status": status, "message": message})
        if status == "FAIL":
            report["errors"].append(f"{name}: {message}")
            report["ok"] = False
        elif status == "WARN":
            report["warnings"].append(f"{name}: {message}")

    # 1. Wallet exists
    wallet_path = agent_directory / "wallet.json"
    if wallet_path.exists():
        add("wallet.exists", "OK", str(wallet_path))
    else:
        add("wallet.exists", "FAIL", "No wallet.json found")
        return report

    # 2. Wallet is real OWS (not simulated)
    wallet = json.loads(wallet_path.read_text(encoding="utf8"))
    if wallet.get("provider") == "ows":
        add("wallet.provider", "OK", "real OWS wallet")
    else:
        add("wallet.provider", "FAIL", f"provider={wallet.get('provider')} (need 'ows' for live mode)")

    # 3. .env exists with API key
    env_path = agent_directory / ".env"
    if env_path.exists():
        add(".env.exists", "OK", str(env_path))
        # Check perms
        st = env_path.stat()
        if st.st_mode & 0o077:
            add(".env.perms", "WARN", f"permissions {oct(st.st_mode & 0o777)} (should be 0600)")
        else:
            add(".env.perms", "OK", "0600")
    else:
        add(".env.exists", "WARN", "No .env file (API key may be in environment)")

    # 4. .gitignore protects secrets
    gitignore_path = agent_directory / ".gitignore"
    if gitignore_path.exists():
        gitignore = gitignore_path.read_text(encoding="utf8")
        protected = {".env", ".ows", "wallet-backup"}
        missing = [p for p in protected if p not in gitignore]
        if missing:
            add(".gitignore.coverage", "WARN", f"missing: {missing}")
        else:
            add(".gitignore.coverage", "OK", "all secrets covered")
    else:
        add(".gitignore.exists", "WARN", "No .gitignore found")

    # 5. Vault permissions
    vault_path = agent_directory / ".ows"
    if vault_path.exists():
        st = vault_path.stat()
        if st.st_mode & 0o077:
            add(".ows.perms", "WARN", f"vault permissions {oct(st.st_mode & 0o777)} (should be 0700)")
        else:
            add(".ows.perms", "OK", "0700")

    # 6. Halt file present (sign that someone thought about kill switch)
    halt_path = agent_directory / "halt"
    if halt_path.exists():
        add("halt.active", "WARN", "Kill switch is ACTIVE — clear with 'forge resume' if intentional")

    # 7. Secret scanner
    findings = scan_for_secrets(agent_directory)
    if findings:
        for f in findings[:5]:
            add(
                f"secret.{f['file']}:{f['line']}",
                "FAIL",
                f"possible secret leak: {f['preview']}",
            )
    else:
        add("secret.scan", "OK", "no secrets found in non-ignored files")

    # 8. Audit log exists
    audit_path = agent_directory / "x402_audit.jsonl"
    if audit_path.exists():
        add("audit.exists", "OK", str(audit_path))
    else:
        add("audit.exists", "OK", "no audit log yet (no calls made)")

    return report

"""Tests for security hardening utilities."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from aether_forge.security_hardening import (
    decrypt_backup,
    encrypt_backup,
    harden_agent_directory,
    lock_down_directory,
    lock_down_file,
    preflight_security_check,
    sanitize_dict,
    sanitize_string,
    scan_for_secrets,
)


def _has_cryptography() -> bool:
    try:
        import cryptography  # noqa
        return True
    except ImportError:
        return False


requires_crypto = pytest.mark.skipif(not _has_cryptography(), reason="cryptography package not installed")


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------
#
# !! IMPORTANT — DO NOT REPLACE THE TEST MNEMONIC BELOW WITH A REAL ONE !!
#
# The mnemonic ``abandon abandon abandon abandon abandon abandon abandon
# abandon abandon abandon abandon about`` is the canonical BIP-39 test vector
# published in the BIP-39 specification. It derives publicly-documented
# addresses that every crypto library uses for unit testing. Funding any
# wallet derived from this phrase is reckless — assume it is drained
# immediately by every BIP-39 test scanner running on Ethereum.
#
# If you need a mnemonic for local testing of a NEW wallet flow (e.g.,
# manual end-to-end on Base Sepolia), generate one in your own dev
# environment and never commit it. The .gitignore already excludes .env,
# .ows/ vaults, and wallet-backup-*.json for this reason.
#
# Past incident: a real funded mnemonic was accidentally committed here
# 2026-04-15. The wallet was drained, repo history was nuked, and we
# moved to this canonical test vector. See SECURITY.md for the report
# process if you spot another leak.

def test_sanitize_string_redacts_mnemonic() -> None:
    text = "my mnemonic is abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about"
    result = sanitize_string(text)
    assert "abandon abandon abandon" not in result
    assert "[REDACTED]" in result


def test_sanitize_string_redacts_ows_api_key() -> None:
    text = "OWS_API_KEY=ows_key_e88dc0e4f52cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdc"
    result = sanitize_string(text)
    assert "ows_key_e88dc0e4" not in result
    assert "[REDACTED]" in result


def test_sanitize_string_redacts_hex_private_key() -> None:
    text = "private key: 0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
    result = sanitize_string(text)
    assert "0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890" not in result


def test_sanitize_dict_redacts_secret_fields() -> None:
    data = {
        "wallet_id": "test",
        "mnemonic": "abandon abandon abandon abandon",
        "private_key": "0x123",
        "addresses": {"evm": "0xabc"},
        "nested": {"api_key": "secret"},
    }
    result = sanitize_dict(data)
    assert result["mnemonic"] == "[REDACTED]"
    assert result["private_key"] == "[REDACTED]"
    assert result["addresses"]["evm"] == "0xabc"  # Address is fine
    assert result["nested"]["api_key"] == "[REDACTED]"
    assert result["wallet_id"] == "test"


def test_sanitize_dict_handles_lists() -> None:
    data = {"events": [{"mnemonic": "secret"}, {"normal": "ok"}]}
    result = sanitize_dict(data)
    assert result["events"][0]["mnemonic"] == "[REDACTED]"
    assert result["events"][1]["normal"] == "ok"


# ---------------------------------------------------------------------------
# File permissions
# ---------------------------------------------------------------------------

def test_lock_down_file(tmp_path: Path) -> None:
    file_path = tmp_path / "secret.txt"
    file_path.write_text("secret data")
    file_path.chmod(0o644)

    lock_down_file(file_path)
    mode = file_path.stat().st_mode & 0o777
    assert mode == 0o600


def test_lock_down_directory(tmp_path: Path) -> None:
    dir_path = tmp_path / ".vault"
    dir_path.mkdir()
    inner = dir_path / "wallet.json"
    inner.write_text("{}")
    inner.chmod(0o644)

    lock_down_directory(dir_path)
    dir_mode = dir_path.stat().st_mode & 0o777
    file_mode = inner.stat().st_mode & 0o777
    assert dir_mode == 0o700
    assert file_mode == 0o600


def test_harden_agent_directory(tmp_path: Path) -> None:
    # Set up agent dir with sensitive files
    (tmp_path / ".env").write_text("OWS_API_KEY=ows_key_x")
    (tmp_path / "wallet.json").write_text("{}")
    (tmp_path / ".ows").mkdir()
    (tmp_path / ".ows" / "wallets.json").write_text("[]")
    (tmp_path / "wallet-backup-20260410.json").write_text("{}")

    # Set wide perms first
    for f in [".env", "wallet.json", "wallet-backup-20260410.json"]:
        (tmp_path / f).chmod(0o644)

    report = harden_agent_directory(tmp_path)

    assert (tmp_path / ".env").stat().st_mode & 0o077 == 0
    assert (tmp_path / "wallet.json").stat().st_mode & 0o077 == 0
    assert (tmp_path / ".ows").stat().st_mode & 0o077 == 0
    assert len(report["locked_files"]) >= 3
    assert ".ows" in str(report["locked_dirs"][0]) if report["locked_dirs"] else False


# ---------------------------------------------------------------------------
# Encryption
# ---------------------------------------------------------------------------

@requires_crypto
def test_encrypt_decrypt_roundtrip() -> None:
    plaintext = {
        "wallet_id": "test-wallet",
        "wallet_name": "test",
        "secret": "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about",
        "addresses": {"evm": "0xabc"},
    }
    passphrase = "strong-passphrase-123"

    encrypted = encrypt_backup(plaintext, passphrase)
    assert encrypted["cipher"] == "AES-256-GCM"
    assert "secret" not in json.dumps(encrypted)  # Mnemonic must be in ciphertext only

    decrypted = decrypt_backup(encrypted, passphrase)
    assert decrypted == plaintext


@requires_crypto
def test_encrypt_rejects_short_passphrase() -> None:
    with pytest.raises(ValueError, match="at least 8"):
        encrypt_backup({"x": 1}, "short")


@requires_crypto
def test_decrypt_wrong_passphrase_fails() -> None:
    encrypted = encrypt_backup({"x": 1}, "correct-passphrase")
    with pytest.raises(ValueError, match="Decryption failed"):
        decrypt_backup(encrypted, "wrong-passphrase")


@requires_crypto
def test_encrypted_backup_metadata_safe() -> None:
    plaintext = {
        "wallet_id": "abc",
        "wallet_name": "test",
        "secret": "secret-mnemonic-here",
        "addresses": {"evm": "0xabc"},
    }
    encrypted = encrypt_backup(plaintext, "passphrase-123")
    # Metadata should not contain secret
    assert "secret-mnemonic-here" not in json.dumps(encrypted["metadata"])
    # But should have public info
    assert encrypted["metadata"]["wallet_id"] == "abc"
    assert encrypted["metadata"]["addresses"]["evm"] == "0xabc"


# ---------------------------------------------------------------------------
# Secret scanner
# ---------------------------------------------------------------------------

def test_scan_finds_mnemonic_in_file(tmp_path: Path) -> None:
    bad_file = tmp_path / "leaked.py"
    bad_file.write_text(
        "MNEMONIC = 'abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about'\n"
    )
    findings = scan_for_secrets(tmp_path)
    assert len(findings) > 0
    assert "leaked.py" in findings[0]["file"]


def test_scan_finds_api_key(tmp_path: Path) -> None:
    bad_file = tmp_path / "config.json"
    bad_file.write_text('{"key": "ows_key_e88dc0e4f52cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdc"}')
    findings = scan_for_secrets(tmp_path)
    assert any("config.json" in f["file"] for f in findings)


def test_scan_skips_env_file(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("OWS_API_KEY=ows_key_e88dc0e4f52cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdc")
    findings = scan_for_secrets(tmp_path)
    # .env is in default ignore list
    assert not any(".env" in f["file"] for f in findings)


def test_scan_skips_binary_files(tmp_path: Path) -> None:
    db = tmp_path / "memory.db"
    db.write_bytes(b"\x00\x01\x02SQLITE format 3\x00")
    findings = scan_for_secrets(tmp_path)
    assert len(findings) == 0


# ---------------------------------------------------------------------------
# Pre-flight check
# ---------------------------------------------------------------------------

def test_preflight_no_wallet_fails(tmp_path: Path) -> None:
    report = preflight_security_check(tmp_path)
    assert not report["ok"]
    assert any("wallet.exists" in c["name"] for c in report["checks"])


def test_preflight_simulated_wallet_fails(tmp_path: Path) -> None:
    (tmp_path / "wallet.json").write_text(json.dumps({"provider": "simulated"}))
    report = preflight_security_check(tmp_path)
    assert not report["ok"]


def test_preflight_full_setup_passes(tmp_path: Path) -> None:
    # Set up a fully secure agent dir
    (tmp_path / "wallet.json").write_text(json.dumps({
        "provider": "ows",
        "addresses": {"evm": "0xabc"},
    }))
    env_file = tmp_path / ".env"
    env_file.write_text("OWS_API_KEY=ows_key_e88dc0e4f52cdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdcdc")
    env_file.chmod(0o600)
    (tmp_path / ".gitignore").write_text(".env\n.ows\nwallet-backup\n")
    (tmp_path / ".ows").mkdir(mode=0o700)

    report = preflight_security_check(tmp_path)
    # The .env contains a key but is in the ignore list, so should pass
    assert report["ok"]


def test_preflight_detects_halt_file(tmp_path: Path) -> None:
    (tmp_path / "wallet.json").write_text(json.dumps({"provider": "ows", "addresses": {"evm": "0x1"}}))
    (tmp_path / "halt").write_text("kill")
    report = preflight_security_check(tmp_path)
    assert any("halt.active" in c["name"] for c in report["checks"])

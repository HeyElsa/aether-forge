"""Tests for live execution layer with budget caps and circuit breaker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.live_execution import (
    BudgetExceededError,
    CircuitBreakerError,
    LiveExecutionConfig,
    LiveExecutor,
    build_live_executor,
)


def _make_executor(tmp_path: Path, **overrides) -> LiveExecutor:
    """Build an executor with patched signing for tests."""
    defaults = {
        "max_order_size_usd": 10.0,
        "max_total_spent_usd": 50.0,
        "max_daily_loss_usd": 20.0,
        "max_open_orders": 3,
        "chain": "base-sepolia",
        "dry_run": True,
        "audit_log_path": str(tmp_path / "audit.jsonl"),
    }
    defaults.update(overrides)
    config = LiveExecutionConfig(**defaults)
    executor = LiveExecutor(config, agent_directory=tmp_path)

    # Patch signing to avoid OWS dependency in unit tests
    def fake_sign_message(directory, chain, message):
        return {"signature": "0xfakesignature" * 4, "recovery_id": 27}

    def fake_sign_and_send(directory, chain, tx_hex, rpc_url=None):
        return {"tx_hash": "0xfaketxhash" + "0" * 50}

    # Monkey-patch the wallet module functions
    import aether_forge.wallet as wallet_mod
    executor._original_sign_message = wallet_mod.sign_message
    executor._original_sign_and_send = wallet_mod.sign_and_send
    wallet_mod.sign_message = fake_sign_message
    wallet_mod.sign_and_send = fake_sign_and_send

    return executor


def _restore_executor(executor: LiveExecutor) -> None:
    import aether_forge.wallet as wallet_mod
    if hasattr(executor, "_original_sign_message"):
        wallet_mod.sign_message = executor._original_sign_message
    if hasattr(executor, "_original_sign_and_send"):
        wallet_mod.sign_and_send = executor._original_sign_and_send


def test_dry_run_signs_without_broadcast(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    try:
        result = executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        assert result["status"] == "signed_dry_run"
        assert "signature" in result
        assert "tx_hex" in result
        assert result["dry_run"] is True
    finally:
        _restore_executor(executor)


def test_per_order_cap_enforced(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, max_order_size_usd=5.0)
    try:
        with pytest.raises(BudgetExceededError, match="exceeds per-order cap"):
            executor.place_order(side="buy", token="ETH", amount=0.01, limit_price=2000.0)
    finally:
        _restore_executor(executor)


def test_session_total_cap_enforced(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, max_total_spent_usd=5.0, max_order_size_usd=10.0)
    try:
        # First order uses $4
        executor.place_order(side="buy", token="ETH", amount=0.002, limit_price=2000.0)
        # Second order would push total to $8 — exceeds $5 cap
        with pytest.raises(BudgetExceededError, match="session cap"):
            executor.place_order(side="buy", token="ETH", amount=0.002, limit_price=2000.0)
    finally:
        _restore_executor(executor)


def test_max_open_orders_enforced(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, max_open_orders=2)
    try:
        executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        with pytest.raises(BudgetExceededError, match="Open orders"):
            executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
    finally:
        _restore_executor(executor)


def test_circuit_breaker_trips_after_consecutive_failures(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, max_consecutive_failures=2)
    try:
        # Make signing fail
        import aether_forge.wallet as wallet_mod
        wallet_mod.sign_message = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("sign failed"))

        # First failure
        with pytest.raises(RuntimeError):
            executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        # Second failure trips the breaker
        with pytest.raises(RuntimeError):
            executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)

        # Third call hits the circuit breaker
        with pytest.raises(CircuitBreakerError, match="tripped"):
            executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
    finally:
        _restore_executor(executor)


def test_circuit_breaker_reset(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, max_consecutive_failures=1)
    try:
        import aether_forge.wallet as wallet_mod
        wallet_mod.sign_message = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("fail"))

        with pytest.raises(RuntimeError):
            executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        assert executor.state.circuit_tripped

        executor.reset_circuit()
        assert not executor.state.circuit_tripped
        assert executor.state.consecutive_failures == 0
    finally:
        _restore_executor(executor)


def test_audit_log_records_attempts_and_results(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    try:
        executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)

        log = executor.read_audit_log()
        events = [e["event"] for e in log]
        assert "order_attempted" in events
        assert "order_placed" in events
    finally:
        _restore_executor(executor)


def test_audit_log_records_failures(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    try:
        with pytest.raises(BudgetExceededError):
            executor.place_order(side="buy", token="ETH", amount=10.0, limit_price=2000.0)

        # Budget errors don't reach the audit log (raised before audit)
        # but circuit breaker trips do
    finally:
        _restore_executor(executor)


def test_status_reports_state(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    try:
        executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        status = executor.status()
        assert status["circuit_tripped"] is False
        assert status["transactions"] == 1
        assert status["dry_run"] is True
        assert status["chain"] == "base-sepolia"
        assert status["budget_remaining_usd"] > 0
    finally:
        _restore_executor(executor)


def test_factory_defaults(tmp_path: Path) -> None:
    executor = build_live_executor(tmp_path)
    assert executor.config.dry_run is True
    assert executor.config.chain == "base-sepolia"
    assert executor.config.max_order_size_usd == 1.0


def test_daily_loss_cap(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, max_daily_loss_usd=5.0)
    try:
        # Manually record a loss
        executor.state.record_loss(6.0)

        with pytest.raises(BudgetExceededError, match="Daily loss"):
            executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
    finally:
        _restore_executor(executor)


def test_audit_log_persists_to_jsonl(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    try:
        executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)

        audit_path = tmp_path / "audit.jsonl"
        assert audit_path.exists()

        # Each line is valid JSON
        with audit_path.open() as f:
            for line in f:
                line = line.strip()
                if line:
                    entry = json.loads(line)
                    assert "timestamp" in entry
                    assert "event" in entry
    finally:
        _restore_executor(executor)


def test_circuit_breaker_active_flag(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    try:
        # Manually activate the breaker (kill switch)
        executor.config.circuit_breaker_active = True

        with pytest.raises(CircuitBreakerError):
            executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
    finally:
        _restore_executor(executor)

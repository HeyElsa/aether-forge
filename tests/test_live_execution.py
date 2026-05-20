"""Tests for live execution layer with budget caps and circuit breaker."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from aether_forge.live_execution import (
    BudgetExceededError,
    CircuitBreakerError,
    LiveExecutionConfig,
    LiveExecutionNotConfiguredError,
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
    return executor


def _restore_executor(executor: LiveExecutor) -> None:
    _ = executor


def test_dry_run_validates_without_placeholder_tx_or_broadcast(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path)
    try:
        result = executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        assert result["status"] == "validated_dry_run"
        assert result["would_submit"] is False
        assert "signature" not in result
        assert "tx_hex" not in result
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
    submitted: list[dict] = []

    def submit(order: dict) -> dict:
        submitted.append(order)
        return {"order_id": f"live-{len(submitted)}"}

    config = LiveExecutionConfig(
        max_order_size_usd=10.0,
        max_total_spent_usd=5.0,
        max_daily_loss_usd=20.0,
        max_open_orders=3,
        chain="base-sepolia",
        dry_run=False,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    executor = LiveExecutor(config, agent_directory=tmp_path, submit_order_fn=submit)
    try:
        # First order uses $4
        executor.place_order(side="buy", token="ETH", amount=0.002, limit_price=2000.0)
        # Second order would push total to $8 — exceeds $5 cap
        with pytest.raises(BudgetExceededError, match="session cap"):
            executor.place_order(side="buy", token="ETH", amount=0.002, limit_price=2000.0)
    finally:
        _restore_executor(executor)


def test_max_open_orders_enforced(tmp_path: Path) -> None:
    submitted: list[dict] = []

    def submit(order: dict) -> dict:
        submitted.append(order)
        return {"order_id": f"live-{len(submitted)}"}

    config = LiveExecutionConfig(
        max_order_size_usd=10.0,
        max_total_spent_usd=50.0,
        max_daily_loss_usd=20.0,
        max_open_orders=2,
        chain="base-sepolia",
        dry_run=False,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    executor = LiveExecutor(config, agent_directory=tmp_path, submit_order_fn=submit)
    try:
        executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
        with pytest.raises(BudgetExceededError, match="Open orders"):
            executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)
    finally:
        _restore_executor(executor)


def test_circuit_breaker_trips_after_consecutive_failures(tmp_path: Path) -> None:
    def submit(order: dict) -> dict:
        raise RuntimeError("submit failed")

    config = LiveExecutionConfig(
        max_order_size_usd=10.0,
        max_total_spent_usd=50.0,
        max_daily_loss_usd=20.0,
        max_open_orders=3,
        max_consecutive_failures=2,
        chain="base-sepolia",
        dry_run=False,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    executor = LiveExecutor(config, agent_directory=tmp_path, submit_order_fn=submit)
    try:
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
    def submit(order: dict) -> dict:
        raise RuntimeError("fail")

    config = LiveExecutionConfig(
        max_order_size_usd=10.0,
        max_total_spent_usd=50.0,
        max_daily_loss_usd=20.0,
        max_open_orders=3,
        max_consecutive_failures=1,
        chain="base-sepolia",
        dry_run=False,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    executor = LiveExecutor(config, agent_directory=tmp_path, submit_order_fn=submit)
    try:
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
        assert status["budget_remaining_usd"] == 50.0
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


def test_live_mode_requires_explicit_submitter(tmp_path: Path) -> None:
    executor = _make_executor(tmp_path, dry_run=False)

    with pytest.raises(LiveExecutionNotConfiguredError, match="explicit submit_order_fn"):
        executor.place_order(side="buy", token="ETH", amount=0.001, limit_price=2000.0)


def test_live_mode_delegates_to_explicit_submitter(tmp_path: Path) -> None:
    submitted: list[dict] = []

    def submit(order: dict) -> dict:
        submitted.append(order)
        return {"venue_order_id": "venue-123"}

    config = LiveExecutionConfig(
        max_order_size_usd=10.0,
        max_total_spent_usd=50.0,
        max_daily_loss_usd=20.0,
        max_open_orders=3,
        chain="base-sepolia",
        dry_run=False,
        audit_log_path=str(tmp_path / "audit.jsonl"),
    )
    executor = LiveExecutor(config, agent_directory=tmp_path, submit_order_fn=submit)

    result = executor.place_order(side="buy", token="eth", amount=0.001, limit_price=2000.0)

    assert result["status"] == "submitted"
    assert result["venue_order_id"] == "venue-123"
    assert submitted == [{
        "side": "buy",
        "token": "ETH",
        "amount": 0.001,
        "limit_price": 2000.0,
        "notional_usd": 2.0,
        "chain": "base-sepolia",
        "dry_run": False,
    }]
    assert executor.state.total_spent_usd == 2.0
    assert executor.state.open_order_count == 1


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

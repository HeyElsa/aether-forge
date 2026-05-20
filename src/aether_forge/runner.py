"""Governed agent runner for Aether Forge.

Provides a continuous execution loop that repeatedly runs the
planner → policy → execute → ledger cycle on a configurable schedule,
persisting state between ticks.
"""

from __future__ import annotations

import json
import logging
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .memory import InMemoryMemoryStore, MemoryRecord
from .observability import (
    CompositeEventSink,
    EventSink,
    LoggingEventSink,
    ObservabilityEvent,
    emit_observability_event,
)
from .planner import HeuristicPlanner
from .policy import NativePolicyGate, PolicyDecision
from .runtime import (
    RuntimeSession,
    SessionStatus,
    load_artifact_bundle,
    write_session_replay_json,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RunnerConfig:
    """Configuration for the agent runner."""

    interval_seconds: float = 30.0
    max_ticks: int = 0  # 0 = unlimited
    max_steps_per_tick: int = 20
    environment: str = "sandbox"
    persist_memory: bool = True
    persist_replays: bool = True
    replay_directory: str | None = None
    memory_db_path: str | None = None
    auto_approve: bool = False  # Only for sandbox/paper
    # Deployment options
    health_port: int = 0  # 0 = disabled, >0 = start HTTP health server on this port
    json_log_file: str | None = None  # Path for structured JSON log output
    pid_file: str | None = None  # Write PID to this file for daemon management
    crash_recovery: bool = True  # Resume from last replay on crash
    # Autoresearch / self-improvement
    enable_autoresearch: bool = False  # Enable runtime self-evaluation
    eval_interval_ticks: int = 6  # Evaluate performance every N ticks
    # Knowledge layer
    enable_knowledge: bool = False  # Enable MemPalace long-term knowledge
    # A2A server — expose this agent's capabilities to other agents
    a2a_port: int = 0  # 0 = disabled, >0 = start A2A server on this port
    # Reliability — per-tick timeout (0 = no timeout). Prevents hung LLM calls
    # from stalling the runtime indefinitely.
    tick_timeout_seconds: float = 120.0
    # Circuit breaker — pause for cooldown if N consecutive ticks fail.
    circuit_breaker_threshold: int = 5
    circuit_breaker_cooldown_seconds: float = 60.0


@dataclass(slots=True)
class TickResult:
    """Result of a single agent tick."""

    tick_number: int
    timestamp: str
    session_status: str
    steps_executed: int
    observations: list[dict[str, Any]] = field(default_factory=list)
    pending_approvals: list[str] = field(default_factory=list)
    working_set_keys: list[str] = field(default_factory=list)


class AgentRunner:
    """Governed continuous agent execution loop.

    Each 'tick' creates a RuntimeSession, loads previous state from memory,
    runs the planner → policy → execute → ledger cycle, then persists
    results back to memory and disk.

    Usage::

        runner = AgentRunner(
            artifact_directory="/path/to/agent",
            config=RunnerConfig(interval_seconds=30, environment="sandbox"),
        )
        runner.run()  # Blocks until interrupted or max_ticks reached

    Or programmatically::

        runner = AgentRunner(...)
        for tick_result in runner.tick_generator():
            print(f"Tick {tick_result.tick_number}: {tick_result.session_status}")
            if some_condition:
                break
    """

    def __init__(
        self,
        artifact_directory: str | Path,
        *,
        config: RunnerConfig | None = None,
        planner_factory: Callable | None = None,
        execution_router_factory: Callable | None = None,
        memory_store: Any = None,
        event_sink: EventSink | None = None,
    ) -> None:
        self.artifact_directory = Path(artifact_directory).resolve()
        self.config = config or RunnerConfig()
        self.artifacts = load_artifact_bundle(self.artifact_directory)
        self._planner_factory = planner_factory or HeuristicPlanner
        self._execution_router_factory = execution_router_factory
        self._event_sink: EventSink | None = event_sink
        self._tick_count = 0  # Total ticks (including recovered)
        self._ticks_this_run = 0  # Ticks in current invocation
        self._running = False
        # Bounded tick history — prevents unbounded memory growth in long-running
        # agents. Only the most recent 200 ticks are kept in memory; older ticks
        # are persisted to replay files on disk.
        # (Flagged as MEDIUM by performance audit — 250MB+ after 7-day run.)
        from collections import deque
        self._tick_history: deque[TickResult] = deque(maxlen=200)

        # Working set persists across ticks
        self._working_set: dict[str, Any] = {}

        # Memory store — use provided, or build from config
        if memory_store is not None:
            self._memory_store = memory_store
        elif self.config.memory_db_path:
            from .storage import SqliteMemoryStore
            self._memory_store = SqliteMemoryStore(self.config.memory_db_path)
        elif self.config.persist_memory:
            from .storage import SqliteMemoryStore
            self._memory_store = SqliteMemoryStore(self.artifact_directory / "memory.db")
        else:
            self._memory_store = InMemoryMemoryStore()

        # Replay output
        if self.config.replay_directory:
            self._replay_dir = Path(self.config.replay_directory)
        elif self.config.persist_replays:
            self._replay_dir = self.artifact_directory / "replays"
        else:
            self._replay_dir = None
        if self._replay_dir:
            self._replay_dir.mkdir(parents=True, exist_ok=True)

        # Execution router
        if self._execution_router_factory is None:
            from .crypto import MockCryptoExecutionRouter
            self._execution_router_factory = MockCryptoExecutionRouter

        # Autoresearch — self-evaluation and improvement proposals
        self._autoresearch = None
        if self.config.enable_autoresearch:
            from .evolution import RuntimeAutoresearch
            strategy_path = self.artifact_directory / "strategy.json"
            # Use the planner model as the research model (same LLM)
            research_model = None
            try:
                planner_instance = planner_factory()
                if hasattr(planner_instance, "model"):
                    research_model = planner_instance.model
            except Exception:
                pass
            self._autoresearch = RuntimeAutoresearch(
                strategy_path,
                research_model=research_model,
                eval_interval=self.config.eval_interval_ticks,
            )
            logger.info("Autoresearch enabled: eval every %d ticks, strategy at %s", self.config.eval_interval_ticks, strategy_path)

        # Knowledge layer (MemPalace)
        self._knowledge = None
        if self.config.enable_knowledge:
            try:
                from .knowledge import KnowledgeStore
                knowledge_path = self.artifact_directory / "knowledge"
                agent_name = self.artifacts.agent_spec.get("metadata", {}).get("name", "agent")
                self._knowledge = KnowledgeStore(knowledge_path, wing=agent_name.lower().replace(" ", "-"))
                if self._knowledge.available:
                    logger.info("Knowledge layer enabled: %s", knowledge_path)
                else:
                    self._knowledge = None
            except Exception as error:
                logger.warning("Knowledge layer failed to initialize: %s", error)

        # Health server
        self._health_server = None
        self._agent_status: dict[str, Any] = {
            "status": "initialized",
            "environment": self.config.environment,
            "artifact_set": self.artifacts.agent_spec.get("artifactSetId", "?"),
            "ticks_completed": 0,
            "last_tick": None,
            "started_at": None,
        }

        # A2A server — expose this agent's capabilities to other agents
        self._a2a_server = None
        self._a2a_task_queue: list[dict[str, Any]] = []
        if self.config.a2a_port > 0:
            self._start_a2a_server(self.config.a2a_port)

        # JSON log handler
        self._json_log_handler = None
        if self.config.json_log_file:
            self._setup_json_logging(self.config.json_log_file)
            self._event_sink = CompositeEventSink.from_sinks(
                self._event_sink,
                LoggingEventSink(),
            )

        # Crash recovery — load last tick count from replays
        if self.config.crash_recovery and self._replay_dir and self._replay_dir.exists():
            existing = sorted(self._replay_dir.glob("tick_*.json"))
            if existing:
                self._tick_count = len(existing)
                logger.info("Crash recovery: found %d previous replays, resuming from tick %d", len(existing), self._tick_count + 1)

        logger.info(
            "AgentRunner initialized: artifact_set=%s environment=%s interval=%.0fs",
            self.artifacts.agent_spec.get("artifactSetId", "?"),
            self.config.environment,
            self.config.interval_seconds,
        )

    def run(self) -> list[TickResult]:
        """Run the agent loop until interrupted or max_ticks reached.

        Blocks the calling thread. Handles SIGINT/SIGTERM gracefully.
        Starts health server if configured. Writes PID file if configured.
        """
        self._running = True
        self._agent_status["status"] = "running"
        self._agent_status["started_at"] = datetime.now(UTC).isoformat()
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)

        def _stop(signum, frame):
            logger.info("Received signal %s, stopping after current tick", signum)
            self._running = False
            self._agent_status["status"] = "stopping"

        signal.signal(signal.SIGINT, _stop)
        signal.signal(signal.SIGTERM, _stop)

        # Start health server if configured
        if self.config.health_port > 0:
            self._start_health_server(self.config.health_port)

        # Write PID file
        if self.config.pid_file:
            self._write_pid_file(self.config.pid_file)

        try:
            self._print_banner()
            for tick_result in self.tick_generator():
                self._print_tick(tick_result)
                self._agent_status["ticks_completed"] = self._tick_count
                self._agent_status["last_tick"] = tick_result.timestamp
                self._log_tick_json(tick_result)
                if not self._running:
                    break
                if tick_result.session_status == "failed":
                    logger.warning("Agent session failed on tick %d, continuing", tick_result.tick_number)
                    # Don't stop — continuous agents recover from individual tick failures
                # Circuit breaker — if N consecutive ticks failed, cool down
                if self._check_circuit_breaker():
                    cooldown = self.config.circuit_breaker_cooldown_seconds
                    logger.warning(
                        "Circuit breaker tripped: %d consecutive failures. Cooling down for %.0fs",
                        self.config.circuit_breaker_threshold, cooldown,
                    )
                    self._agent_status["status"] = "circuit_breaker_cooldown"
                    time.sleep(cooldown)
                    self._agent_status["status"] = "running"
                if self._running and (self.config.max_ticks == 0 or self._ticks_this_run < self.config.max_ticks):
                    self._sleep_interruptible(self.config.interval_seconds)
        finally:
            self._agent_status["status"] = "stopped"
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)
            self._stop_health_server()
            self._stop_a2a_server()
            self._cleanup_pid_file()
            self._print_summary()

        return self._tick_history

    def tick_generator(self):
        """Yield TickResults one at a time. Caller controls scheduling.

        Tick timeout is enforced inside individual blocking calls (LLM, HTTP)
        rather than wrapping the whole tick in a thread, since SQLite memory
        is bound to a single thread. See ``config.tick_timeout_seconds``.
        """
        self._running = True
        while self._running:
            if self.config.max_ticks > 0 and self._ticks_this_run >= self.config.max_ticks:
                break
            yield self.tick()

    def tick(self, scenario_inputs: dict[str, Any] | None = None) -> TickResult:
        """Execute a single agent tick.

        ``scenario_inputs`` are copied into the ``RuntimeSession`` state for
        this tick only. They are the supported programmatic entry point for
        webhook payloads, queue messages, cron context, and other request-
        scoped inputs.
        """
        self._tick_count += 1
        self._ticks_this_run += 1
        tick_num = self._tick_count
        timestamp = datetime.now(UTC).isoformat()

        logger.info("Tick %d started at %s", tick_num, timestamp)
        self._emit_event(
            "runner.tick.started",
            tick=tick_num,
            message=f"Tick {tick_num} started.",
            details={"maxStepsPerTick": self.config.max_steps_per_tick},
        )

        # Build session for this tick
        planner = self._planner_factory()
        router = self._execution_router_factory()

        # When auto_approve is on, use a permissive policy gate that
        # auto-approves side-effecting capabilities in sandbox/paper.
        policy_gate = None
        if self.config.auto_approve and self.config.environment in ("sandbox", "paper"):
            policy_gate = _AutoApproveGate.from_policy_bundle(self.artifacts.policy_bundle)

        session = RuntimeSession(
            artifacts=self.artifacts,
            environment=self.config.environment,
            planner=planner,
            execution_router=router,
            policy_gate=policy_gate,
            scenario_inputs=scenario_inputs,
            memory_store=self._memory_store,
            event_sink=self._event_sink,
            tick_number=tick_num,
        )

        # Inject previous working set
        session.working_set = dict(self._working_set)

        # Run the governed loop
        status = session.run(max_steps=self.config.max_steps_per_tick)

        # Auto-approve in sandbox/paper if configured — retry until no more holds
        if self.config.auto_approve and self.config.environment in ("sandbox", "paper"):
            retries = 0
            while status == SessionStatus.HOLD and retries < 5:
                # Handle pending approvals
                if session.pending_approvals:
                    for approval in list(session.pending_approvals):
                        session.approve_pending(approval.request_id)
                # Handle report-gap holds — clear the gap and resume
                elif session.session_state.get("reported_gap"):
                    logger.debug("Auto-clearing reported gap in sandbox: %s", session.session_state["reported_gap"])
                    session.session_state["reported_gap"] = None
                    session.status = SessionStatus.RUNNING
                else:
                    break
                status = session.run(max_steps=self.config.max_steps_per_tick)
                retries += 1

        # Treat paused (max-steps exhaustion) or hold as complete for continuous agents
        if status in (SessionStatus.PAUSED, SessionStatus.HOLD):
            status = SessionStatus.COMPLETE
            session.status = SessionStatus.COMPLETE

        # Persist working set for next tick
        self._working_set.update(session.working_set)

        # Write tick memory summary
        if self.config.persist_memory:
            self._persist_tick_memory(session, tick_num)

        # Write replay
        if self._replay_dir:
            replay_path = self._replay_dir / f"tick_{tick_num:04d}.json"
            write_session_replay_json(session, replay_path)

        # Autoresearch — feed self-evaluator, may produce improvement proposal
        if self._autoresearch:
            # Extract balance from working set if available
            portfolio = session.working_set.get("elsa-get-portfolio", session.working_set.get("elsa-get-balances", {}))
            balance = portfolio.get("cash_usd", portfolio.get("balance_usd", self.config.initial_balance_usd if hasattr(self.config, "initial_balance_usd") else 10_000.0))
            trades = [
                entry.execution_result.output if hasattr(entry.execution_result, "output") else (entry.execution_result or {}).get("output", {})
                for entry in session.step_ledger
                if entry.proposal.capability_id and "order" in entry.proposal.capability_id
                and entry.execution_result
            ]
            proposal = self._autoresearch.on_tick_complete(float(balance), trades)
            if proposal:
                self._agent_status["pending_proposal"] = proposal.proposal_id

        # Knowledge layer — record long-term knowledge from this tick
        if self._knowledge:
            try:
                prices = {}
                orders_for_kg = []
                for entry in session.step_ledger:
                    er = entry.execution_result
                    out = er.output if hasattr(er, "output") else (er or {}).get("output", {})
                    if isinstance(out, dict):
                        if out.get("price_usd"):
                            prices[out.get("token", "?")] = out["price_usd"]
                        if out.get("order_id") and out.get("status") == "filled":
                            orders_for_kg.append(out)
                self._knowledge.record_tick_knowledge(tick_num, prices=prices, orders=orders_for_kg)
            except Exception as error:
                logger.debug("Knowledge recording failed: %s", error)

        result = TickResult(
            tick_number=tick_num,
            timestamp=timestamp,
            session_status=status.value,
            steps_executed=len(session.step_ledger),
            observations=[
                {"type": obs.get("type"), "description": obs.get("description")}
                for obs in session.observations
            ],
            pending_approvals=[a.request_id for a in session.pending_approvals],
            working_set_keys=list(session.working_set.keys()),
        )
        self._tick_history.append(result)
        logger.info("Tick %d complete: status=%s steps=%d", tick_num, status.value, len(session.step_ledger))
        self._emit_event(
            "runner.tick.failed" if status == SessionStatus.FAILED else "runner.tick.completed",
            severity="error" if status == SessionStatus.FAILED else "info",
            tick=tick_num,
            message=f"Tick {tick_num} {status.value}.",
            details={
                "status": status.value,
                "steps": len(session.step_ledger),
                "pendingApprovals": len(session.pending_approvals),
            },
        )
        return result

    def stop(self) -> None:
        """Signal the runner to stop after the current tick."""
        self._running = False

    def _persist_tick_memory(self, session: RuntimeSession, tick_num: int) -> None:
        """Write a summary memory record for this tick."""
        try:
            record = MemoryRecord(
                memory_id=f"mem_tick_{tick_num}_{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
                memory_type="decision-history",
                scope="session",
                environment=self.config.environment,
                content={
                    "tick": tick_num,
                    "status": session.status.value,
                    "steps": len(session.step_ledger),
                    "working_set_keys": list(session.working_set.keys()),
                    "observations_count": len(session.observations),
                },
                summary=f"Tick {tick_num}: {session.status.value} with {len(session.step_ledger)} steps",
                source="agent-runner",
                confidence=1.0,
                sensitivity="internal",
            )
            self._memory_store.write(record)
            self._emit_event(
                "memory.write",
                tick=tick_num,
                message="Tick summary memory written.",
                details={"memoryId": record.memory_id, "source": "agent-runner"},
            )
        except Exception as error:
            logger.warning("Failed to persist tick memory: %s", error)
            self._emit_event(
                "memory.write_failed",
                severity="warning",
                tick=tick_num,
                message="Failed to persist tick memory.",
                details={"error": repr(error), "source": "agent-runner"},
            )

    def _sleep_interruptible(self, seconds: float) -> None:
        """Sleep in small increments so SIGINT is responsive."""
        end = time.monotonic() + seconds
        while self._running and time.monotonic() < end:
            time.sleep(min(0.5, end - time.monotonic()))

    def _print_banner(self) -> None:
        name = self.artifacts.agent_spec.get("metadata", {}).get("name", "Agent")
        env = self.config.environment
        interval = self.config.interval_seconds
        print(f"\n  {name}")
        print(f"  Environment: {env} | Interval: {interval}s | Ctrl+C to stop\n")

    def _print_tick(self, result: TickResult) -> None:
        status_icon = {"complete": "ok", "hold": "hold", "failed": "FAIL", "running": "..."}.get(result.session_status, "?")
        print(f"  [{status_icon:>4}] Tick {result.tick_number}: {result.session_status} ({result.steps_executed} steps)", end="")
        if result.pending_approvals:
            print(f" — {len(result.pending_approvals)} pending approval(s)", end="")
        print()

    def _print_summary(self) -> None:
        total = len(self._tick_history)
        if total == 0:
            return
        statuses = {}
        for t in self._tick_history:
            statuses[t.session_status] = statuses.get(t.session_status, 0) + 1
        status_str = ", ".join(f"{k}={v}" for k, v in sorted(statuses.items()))
        print(f"\n  {total} ticks completed: {status_str}")

    # ------------------------------------------------------------------
    # Health server (lightweight HTTP on a background thread)
    # ------------------------------------------------------------------

    def _start_a2a_server(self, port: int) -> None:
        """Start the A2A server so other agents can send tasks to this agent."""
        try:
            from .a2a_server import A2AServer, build_agent_card

            card = build_agent_card(
                self.artifacts.agent_spec,
                self.artifacts.capability_manifest,
                port=port,
            )

            def _a2a_task_handler(task: dict[str, Any]) -> dict[str, Any]:
                """Queue incoming A2A tasks for the planner on the next tick."""
                self._a2a_task_queue.append(task)
                return {
                    "state": "completed",
                    "artifacts": [{
                        "parts": [{
                            "type": "text",
                            "text": json.dumps({
                                "queued": True,
                                "queue_position": len(self._a2a_task_queue),
                                "agent": card.get("name", "unknown"),
                                "message": "Task received and queued for next tick.",
                            }),
                        }],
                    }],
                }

            self._a2a_server = A2AServer(
                port=port,
                agent_card=card,
                task_handler=_a2a_task_handler,
            )
            self._a2a_server.start()
            logger.info("A2A server started on port %d", port)
        except Exception as error:
            logger.warning("Failed to start A2A server on port %d: %s", port, error)

    def _stop_a2a_server(self) -> None:
        if self._a2a_server is not None:
            self._a2a_server.stop()
            self._a2a_server = None
            logger.info("A2A server stopped")

    def _start_health_server(self, port: int) -> None:
        """Start a background HTTP server for health, status, ticks, and metrics.

        Endpoints:
            /health    — liveness: is the process responsive?
            /ready     — readiness: is the agent in a healthy state to do work?
                          (returns 503 if planner has failed N consecutive ticks
                          or kill switch is active)
            /status    — current agent state (status, ticks, errors)
            /ticks     — last 20 tick summaries
            /metrics   — Prometheus text format (tick count, errors, latency)
        """
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        runner_ref = self

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                try:
                    self._handle()
                except Exception as error:
                    try:
                        self.send_response(500)
                        self.send_header("Content-Type", "application/json")
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": str(error)}).encode())
                    except Exception:
                        pass

            def _handle(self):
                path = self.path.split("?")[0]
                if path == "/health":
                    # Liveness — process responsive
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"alive": True}).encode())
                elif path == "/ready":
                    # Readiness — DEEP check
                    ready, reason = runner_ref._compute_readiness()
                    self.send_response(200 if ready else 503)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps({"ready": ready, "reason": reason}).encode())
                elif path == "/status":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(runner_ref._agent_status).encode())
                elif path == "/ticks":
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    ticks = [
                        {"tick": t.tick_number, "status": t.session_status, "steps": t.steps_executed, "time": t.timestamp}
                        for t in runner_ref._tick_history[-20:]
                    ]
                    self.wfile.write(json.dumps(ticks).encode())
                elif path == "/metrics":
                    # Prometheus text exposition format
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.end_headers()
                    self.wfile.write(runner_ref._prometheus_metrics().encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress default access logs

        try:
            server = HTTPServer(("127.0.0.1", port), HealthHandler)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._health_server = server
            logger.info("Health server started on port %d", port)
        except OSError as error:
            logger.warning("Failed to start health server on port %d: %s", port, error)

    def _stop_health_server(self) -> None:
        if self._health_server:
            self._health_server.shutdown()
            self._health_server = None
            logger.info("Health server stopped")

    # ------------------------------------------------------------------
    # Health, readiness, metrics
    # ------------------------------------------------------------------

    def _check_circuit_breaker(self) -> bool:
        """True if last N ticks all failed and cooldown should trigger."""
        n = self.config.circuit_breaker_threshold
        if n <= 0:
            return False
        recent = list(self._tick_history)[-n:]
        return len(recent) >= n and all(
            t.session_status not in ("complete", "ok") for t in recent
        )

    def _compute_readiness(self) -> tuple[bool, str]:
        """Deep readiness check. Returns (ready, reason).

        NOT ready if:
        - Kill switch active (halt file present)
        - Last 5 consecutive ticks all failed
        - Agent has been started but no tick has run yet (warming up)
        """
        # Halt file
        halt_path = self.artifact_directory / "halt"
        if halt_path.exists():
            return (False, "kill switch active")

        # Consecutive failures
        recent = list(self._tick_history)[-5:]
        if len(recent) >= 5 and all(
            t.session_status not in ("complete", "ok") for t in recent
        ):
            return (False, f"last 5 ticks failed (last status: {recent[-1].session_status})")

        # Warming up (started but no tick yet)
        if self._agent_status.get("status") == "running" and self._tick_count == 0:
            return (False, "warming up — no tick completed yet")

        return (True, "ok")

    def _prometheus_metrics(self) -> str:
        """Render runner state as Prometheus text exposition format."""
        lines = []
        try:
            artifact = self.artifacts.agent_spec.get("metadata", {}).get("artifactSetId", "unknown")
        except Exception:
            artifact = "unknown"
        env = self.config.environment
        labels = f'{{agent="{artifact}",env="{env}"}}'

        # Tick counters
        total = len(self._tick_history)
        ok = sum(1 for t in self._tick_history if t.session_status in ("complete", "ok"))
        failed = total - ok
        lines.append("# HELP aether_ticks_total Total ticks completed (success + failure)")
        lines.append("# TYPE aether_ticks_total counter")
        lines.append(f"aether_ticks_total{labels} {self._tick_count}")
        lines.append("# HELP aether_ticks_failed_total Tick failures")
        lines.append("# TYPE aether_ticks_failed_total counter")
        lines.append(f"aether_ticks_failed_total{labels} {failed}")

        # Steps per tick (recent average)
        if self._tick_history:
            avg_steps = sum(t.steps_executed for t in self._tick_history) / total
            lines.append("# HELP aether_steps_per_tick_avg Average steps per recent tick")
            lines.append("# TYPE aether_steps_per_tick_avg gauge")
            lines.append(f"aether_steps_per_tick_avg{labels} {avg_steps:.2f}")

        # Status
        status = self._agent_status.get("status", "unknown")
        lines.append("# HELP aether_agent_running 1 if agent is running, 0 otherwise")
        lines.append("# TYPE aether_agent_running gauge")
        lines.append(f"aether_agent_running{labels} {1 if status == 'running' else 0}")

        # Readiness
        ready, _ = self._compute_readiness()
        lines.append("# HELP aether_agent_ready 1 if agent is ready to do work")
        lines.append("# TYPE aether_agent_ready gauge")
        lines.append(f"aether_agent_ready{labels} {1 if ready else 0}")

        # Pending approvals
        pending = len(self._agent_status.get("pending_approvals", []) or [])
        lines.append("# HELP aether_pending_approvals Steps waiting for human approval")
        lines.append("# TYPE aether_pending_approvals gauge")
        lines.append(f"aether_pending_approvals{labels} {pending}")

        return "\n".join(lines) + "\n"

    # ------------------------------------------------------------------
    # JSON structured logging
    # ------------------------------------------------------------------

    def _setup_json_logging(self, log_path: str) -> None:
        """Add a JSON file handler to the root logger.

        All log records are passed through ``sanitize_string`` so that any
        accidentally-emitted mnemonic, API key, or signature is redacted
        before it touches disk.
        """
        from .security_hardening import sanitize_dict, sanitize_string

        path = Path(log_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        class JsonFormatter(logging.Formatter):
            def format(self, record):
                entry = {
                    "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
                    "level": record.levelname,
                    "logger": record.name,
                    "message": sanitize_string(record.getMessage()),
                }
                if record.exc_info and record.exc_info[0]:
                    entry["exception"] = sanitize_string(self.formatException(record.exc_info))
                event_payload = getattr(record, "aether_event", None)
                if isinstance(event_payload, dict):
                    entry["aetherEvent"] = sanitize_dict(event_payload)
                return json.dumps(entry)

        # Use RotatingFileHandler to prevent unbounded log growth in
        # long-running agents (flagged by performance audit — 170MB+ after 7 days).
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(
            str(path),
            maxBytes=50 * 1024 * 1024,  # 50 MB per file
            backupCount=3,               # keep 3 rotated copies
        )
        handler.setFormatter(JsonFormatter())
        handler.setLevel(logging.DEBUG)
        # Lock the log file down on creation — only owner may read
        try:
            from .security_hardening import lock_down_file
            lock_down_file(path)
        except Exception:
            pass
        logging.getLogger().addHandler(handler)
        self._json_log_handler = handler
        logger.info("JSON logging to %s", path)

    def _log_tick_json(self, result: TickResult) -> None:
        """Write a structured tick summary to the JSON log."""
        if not self.config.json_log_file:
            return
        entry = {
            "event": "tick_complete",
            "tick": result.tick_number,
            "status": result.session_status,
            "steps": result.steps_executed,
            "timestamp": result.timestamp,
            "pending_approvals": len(result.pending_approvals),
        }
        logger.info("Tick %d: %s", result.tick_number, json.dumps(entry))

    def _emit_event(
        self,
        kind: str,
        *,
        severity: str = "info",
        tick: int | None = None,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        emit_observability_event(
            self._event_sink,
            ObservabilityEvent(
                kind=kind,
                artifact_set_id=self.artifacts.agent_spec.get("artifactSetId"),
                environment=self.config.environment,
                tick=tick,
                severity=severity,
                message=message,
                details=details or {},
            ),
        )

    # ------------------------------------------------------------------
    # PID file management
    # ------------------------------------------------------------------

    def _write_pid_file(self, pid_path: str) -> None:
        import os
        path = Path(pid_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(os.getpid()), encoding="utf8")
        logger.info("PID %d written to %s", os.getpid(), path)

    def _cleanup_pid_file(self) -> None:
        if self.config.pid_file:
            path = Path(self.config.pid_file)
            if path.exists():
                path.unlink()
                logger.debug("PID file removed: %s", path)


class _AutoApproveGate(NativePolicyGate):
    """Policy gate that auto-approves side-effecting capabilities.

    Used by the runner in sandbox/paper when --auto-approve is set.
    All other policy checks (environment, notional limits, staleness) still apply.
    """

    def evaluate_action(
        self,
        capability: dict[str, Any],
        credential_handles: list[dict[str, Any]],
        environment: str,
        action_payload: dict[str, Any],
    ) -> PolicyDecision:
        # Inject a synthetic approval token so the base gate doesn't hold
        patched_payload = {**action_payload, "approval_token": "auto-approve-sandbox"}
        return super().evaluate_action(capability, credential_handles, environment, patched_payload)

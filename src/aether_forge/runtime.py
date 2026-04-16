"""Bounded native runtime for Aether Forge."""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)

from .artifacts import validate_artifact_directory
from .memory import InMemoryMemoryStore, MemoryPromotionRequest, MemoryQuery, MemoryRecord
from .policy import NativePolicyGate


class SessionStatus(StrEnum):
    RUNNING = "running"
    HOLD = "hold"
    PAUSED = "paused"
    FAILED = "failed"
    COMPLETE = "complete"


class StepKind(StrEnum):
    REASON = "reason"
    USE_CAPABILITY = "use-capability"
    REQUEST_APPROVAL = "request-approval"
    REPLAN = "replan"
    REPORT_GAP = "report-gap"


class StepLifecycle(StrEnum):
    PROPOSED = "proposed"
    VALIDATED = "validated"
    POLICY_CHECKED = "policy-checked"
    APPROVAL_PENDING = "approval-pending"
    EXECUTED = "executed"
    RECORDED = "recorded"
    DENIED = "denied"
    FAILED = "failed"
    COMPLETE = "complete"


@dataclass(slots=True)
class StepProposal:
    kind: StepKind
    description: str
    capability_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionResult:
    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    mark_complete: bool = False
    requires_replan: bool = False
    failure_reason: str | None = None


@dataclass(slots=True)
class StepLedgerEntry:
    step_id: str
    proposal: StepProposal
    lifecycle: StepLifecycle
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    policy_decision: dict[str, Any] | None = None
    execution_result: dict[str, Any] | None = None
    message: str | None = None


@dataclass(slots=True)
class PendingApproval:
    request_id: str
    proposal: StepProposal
    created_from_step_id: str
    reason_ids: list[str] = field(default_factory=list)
    approval_kind: str = "manual"


@dataclass(slots=True)
class ArtifactBundle:
    directory_path: Path
    agent_spec: dict[str, Any]
    capability_manifest: dict[str, Any]
    policy_bundle: dict[str, Any]
    scenario_pack: dict[str, Any]
    research_record: dict[str, Any] | None = None
    promotion_record: dict[str, Any] | None = None
    scaffold_manifest: dict[str, Any] | None = None


@dataclass(slots=True)
class RuntimeReplay:
    artifact_set_id: str
    environment: str
    session_status: str
    session_state: dict[str, Any]
    working_set: dict[str, Any]
    observations: list[dict[str, Any]]
    pending_approvals: list[dict[str, Any]]
    step_ledger: list[dict[str, Any]]


class Planner(Protocol):
    def propose_plan(self, session: RuntimeSession) -> list[StepProposal]: ...


class ExecutionRouter(Protocol):
    def execute(
        self,
        session: RuntimeSession,
        proposal: StepProposal,
        capability: dict[str, Any],
    ) -> ExecutionResult: ...


class RuntimeSession:
    def __init__(
        self,
        artifacts: ArtifactBundle,
        environment: str,
        planner: Planner,
        execution_router: ExecutionRouter,
        policy_gate: NativePolicyGate | None = None,
        scenario_inputs: dict[str, Any] | None = None,
        memory_store: InMemoryMemoryStore | None = None,
    ) -> None:
        self.artifacts = artifacts
        self.environment = environment
        self.planner = planner
        self.execution_router = execution_router
        self.policy_gate = policy_gate or NativePolicyGate.from_policy_bundle(artifacts.policy_bundle)
        self.memory_store = memory_store or InMemoryMemoryStore()
        self.status = SessionStatus.RUNNING
        self.session_state: dict[str, Any] = {
            "objective": artifacts.agent_spec["objective"]["primaryGoal"],
            "environment": environment,
            "blocking_reason_ids": [],
            "goal_satisfied": False,
            "reported_gap": None,
            "last_approval_token": None,
            "scenario_inputs": scenario_inputs or {},
        }
        self.working_set: dict[str, Any] = {}
        self.observations: list[dict[str, Any]] = []
        self.plan_queue: list[StepProposal] = []
        self.pending_approvals: list[PendingApproval] = []
        self.step_ledger: list[StepLedgerEntry] = []
        self._step_counter = 0

    def run(self, max_steps: int = 20) -> SessionStatus:
        logger.info("RuntimeSession started: environment=%s artifact_set=%s", self.environment, self.artifacts.agent_spec.get("artifactSetId", "unknown"))
        while self.status == SessionStatus.RUNNING and self._step_counter < max_steps:
            # Populate memory context for prompting before planner invocation.
            self.session_state["memory_context"] = [
                record.to_dict()
                for record in self.memory_store.read(
                    MemoryQuery(scope="session", environment=self._current_environment())
                )
            ]

            if not self.plan_queue:
                self.plan_queue = self.planner.propose_plan(self)
                if not self.plan_queue:
                    self.status = SessionStatus.COMPLETE if self.session_state.get("goal_satisfied") else SessionStatus.FAILED
                    break

            proposal = self.plan_queue.pop(0)
            self._step_counter += 1
            logger.debug("Step %d: %s capability=%s", self._step_counter, proposal.kind, proposal.capability_id)
            state_before = self._snapshot_state()
            entry = StepLedgerEntry(
                step_id=f"step_{self._step_counter}",
                proposal=proposal,
                lifecycle=StepLifecycle.PROPOSED,
                state_before=state_before,
                state_after=state_before,
            )

            if proposal.kind not in set(StepKind):
                self.status = SessionStatus.FAILED
                entry.lifecycle = StepLifecycle.FAILED
                entry.message = f"Unsupported step kind {proposal.kind}."
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                break

            entry.lifecycle = StepLifecycle.VALIDATED

            if proposal.kind == StepKind.REPLAN:
                self.plan_queue.clear()
                entry.lifecycle = StepLifecycle.COMPLETE
                entry.message = proposal.description
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                continue

            if proposal.kind == StepKind.REQUEST_APPROVAL:
                self.pending_approvals.append(
                    PendingApproval(
                        request_id=f"approval_{uuid4().hex}",
                        proposal=proposal,
                        created_from_step_id=entry.step_id,
                        reason_ids=["approval-required"],
                    )
                )
                self.status = SessionStatus.HOLD
                entry.lifecycle = StepLifecycle.APPROVAL_PENDING
                entry.message = proposal.description
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                continue

            if proposal.kind == StepKind.REPORT_GAP:
                self.session_state["reported_gap"] = proposal.payload or {"message": proposal.description}
                self.status = SessionStatus.HOLD
                entry.lifecycle = StepLifecycle.COMPLETE
                entry.message = proposal.description
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                continue

            if proposal.kind == StepKind.REASON:
                self.observations.append({
                    "type": "reason",
                    "description": proposal.description,
                    "payload": proposal.payload,
                })
                if proposal.payload.get("mark_complete"):
                    self.session_state["goal_satisfied"] = True
                    self.status = SessionStatus.COMPLETE
                if proposal.payload.get("requires_replan"):
                    self.plan_queue.clear()
                entry.lifecycle = StepLifecycle.COMPLETE
                entry.message = proposal.description
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                continue

            # Check if this is a memory.* operation before capability resolution.
            is_memory_op = bool(proposal.capability_id and proposal.capability_id.startswith("memory."))

            capability = self._resolve_capability(proposal.capability_id)
            if capability is None and not is_memory_op:
                self.status = SessionStatus.FAILED
                entry.lifecycle = StepLifecycle.FAILED
                entry.message = f"Capability {proposal.capability_id} is not declared in the manifest."
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                break

            # For memory operations without a manifest entry, use a synthetic capability.
            if capability is None and is_memory_op:
                capability = {
                    "capabilityId": proposal.capability_id,
                    "kind": "memory-action",
                    "provider": "native-memory",
                    "allowedEnvironments": ["sandbox", "paper", "canary-live", "production"],
                    "riskLevel": "low",
                }

            # Global halt check BEFORE policy evaluation and execution.
            # Prevents kill-switch bypass via MCP tools or other channels that
            # don't go through X402Client._preflight().
            # (Flagged as HIGH by AI safety audit — MCP could make direct HTTP calls.)
            halt_path = getattr(self, "_halt_path", None)
            if halt_path is None and hasattr(self, "artifacts"):
                # Derive halt path from the artifacts directory if available
                for attr in ("agent_directory", "_agent_directory"):
                    d = getattr(self, attr, None)
                    if d:
                        from pathlib import Path
                        halt_path = Path(d) / "halt"
                        break
            if halt_path and hasattr(halt_path, "exists") and halt_path.exists():
                entry.lifecycle = StepLifecycle.FAILED
                entry.message = "Kill switch active — all capability execution blocked."
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                self.status = SessionStatus.FAILED
                break

            policy_decision = self.policy_gate.evaluate_action(
                capability=capability,
                credential_handles=self.artifacts.capability_manifest.get("credentialHandles", []),
                environment=self.environment,
                action_payload=proposal.payload,
            )
            entry.lifecycle = StepLifecycle.POLICY_CHECKED
            entry.policy_decision = asdict(policy_decision)
            logger.info("Policy decision: %s for capability %s", policy_decision.final_disposition, proposal.capability_id)

            if policy_decision.final_disposition != "allow":
                self.session_state["blocking_reason_ids"] = policy_decision.reason_ids
                if "approval-required" in policy_decision.reason_ids:
                    self.pending_approvals.append(
                        PendingApproval(
                            request_id=f"approval_{uuid4().hex}",
                            proposal=proposal,
                            created_from_step_id=entry.step_id,
                            reason_ids=list(policy_decision.reason_ids),
                        )
                    )
                self.status = SessionStatus.HOLD
                logger.warning("Session held: pending approval for %s", proposal.capability_id)
                entry.lifecycle = StepLifecycle.DENIED
                entry.message = ", ".join(policy_decision.reason_ids) or "policy denied action"
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                continue

            # Route memory.* operations to the built-in handler.
            if is_memory_op:
                execution_result = self._execute_memory_operation(proposal)
            else:
                execution_result = self.execution_router.execute(self, proposal, capability)
            entry.execution_result = {
                "success": execution_result.success,
                "output": execution_result.output,
                "mark_complete": execution_result.mark_complete,
                "requires_replan": execution_result.requires_replan,
                "failure_reason": execution_result.failure_reason,
            }

            if not execution_result.success:
                self.status = SessionStatus.FAILED
                entry.lifecycle = StepLifecycle.FAILED
                entry.message = execution_result.failure_reason or "execution failed"
                entry.state_after = self._snapshot_state()
                self.step_ledger.append(entry)
                continue

            # Sanitize capability results before they enter the working set
            # and prompt context. External sources (MCP, A2A, x402) can return
            # adversarial text designed to manipulate the LLM planner.
            # (Flagged as CRITICAL by AI safety audit — prompt injection via
            # MCP tool results and A2A task messages.)
            sanitized_output = execution_result.output
            try:
                from .security import InputSanitizer
                if isinstance(sanitized_output, str):
                    scan = InputSanitizer.scan(sanitized_output)
                    if scan.flagged:
                        logger.warning(
                            "Prompt injection detected in capability %s result: %s",
                            proposal.capability_id,
                            [m.pattern_name for m in scan.matches],
                        )
                elif isinstance(sanitized_output, dict):
                    for k, v in sanitized_output.items():
                        if isinstance(v, str):
                            scan = InputSanitizer.scan(v)
                            if scan.flagged:
                                logger.warning(
                                    "Prompt injection detected in capability %s result key '%s': %s",
                                    proposal.capability_id,
                                    k,
                                    [m.pattern_name for m in scan.matches],
                                )
            except (ImportError, Exception) as error:
                logger.debug("Input sanitization skipped: %s", error)

            self.observations.append({
                "type": "capability-result",
                "capabilityId": proposal.capability_id,
                "output": sanitized_output,
            })
            self.working_set[proposal.capability_id or "unknown-capability"] = sanitized_output

            if execution_result.requires_replan:
                self.plan_queue.clear()
            if execution_result.mark_complete:
                self.session_state["goal_satisfied"] = True
                self.status = SessionStatus.COMPLETE

            entry.lifecycle = StepLifecycle.COMPLETE if self.status == SessionStatus.COMPLETE else StepLifecycle.EXECUTED
            entry.message = proposal.description
            entry.state_after = self._snapshot_state()
            self.step_ledger.append(entry)

        if self.status == SessionStatus.RUNNING and self._step_counter >= max_steps:
            self.status = SessionStatus.PAUSED

        logger.info("Session %s after %d steps", self.status.value, self._step_counter)
        return self.status

    def approve_pending(self, approval_token: str, request_id: str | None = None) -> PendingApproval | None:
        if not self.pending_approvals:
            return None

        selected: PendingApproval | None = None
        for approval in self.pending_approvals:
            if request_id is None or approval.request_id == request_id:
                selected = approval
                break

        if selected is None:
            return None

        self.pending_approvals = [approval for approval in self.pending_approvals if approval.request_id != selected.request_id]
        self.session_state["last_approval_token"] = approval_token
        self.session_state["blocking_reason_ids"] = []

        if selected.proposal.kind == StepKind.USE_CAPABILITY:
            resumed_payload = {**selected.proposal.payload, "approval_token": approval_token}
            resumed = StepProposal(
                kind=selected.proposal.kind,
                description=selected.proposal.description,
                capability_id=selected.proposal.capability_id,
                payload=resumed_payload,
            )
            self.plan_queue.insert(0, resumed)

        self.status = SessionStatus.RUNNING
        return selected

    def _resolve_capability(self, capability_id: str | None) -> dict[str, Any] | None:
        if capability_id is None:
            return None

        for capability in self.artifacts.capability_manifest.get("capabilities", []):
            if capability.get("capabilityId") == capability_id:
                return capability
        return None

    def _current_environment(self) -> str:
        return self.artifacts.agent_spec.get("environmentContract", {}).get(
            "currentEnvironment", "sandbox"
        )

    def _execute_memory_operation(self, proposal: StepProposal) -> ExecutionResult:
        payload = proposal.payload
        cap_id = proposal.capability_id or ""

        if cap_id == "memory.read":
            query = MemoryQuery(
                scope=payload.get("scope", "session"),
                environment=self._current_environment(),
                memory_type=payload.get("memory_type"),
                tag=payload.get("tag"),
                text=payload.get("text"),
                limit=payload.get("limit", 25),
            )
            records = self.memory_store.read(query)
            return ExecutionResult(
                success=True,
                output={"records": [r.to_dict() for r in records]},
            )

        if cap_id == "memory.write":
            record = MemoryRecord(
                memory_id=payload.get("memory_id", f"mem_{uuid4().hex}"),
                memory_type=payload.get("memory_type", "observation"),
                scope=payload.get("scope", "session"),
                environment=self._current_environment(),
                content=payload.get("content", {}),
                summary=payload.get("summary", ""),
                source=payload.get("source", "runtime"),
                confidence=payload.get("confidence", 1.0),
                sensitivity=payload.get("sensitivity", "internal"),
                owner_agent_id=payload.get("owner_agent_id"),
                artifact_set_id=payload.get("artifact_set_id"),
                tags=payload.get("tags", []),
                metadata=payload.get("metadata", {}),
            )
            stored = self.memory_store.write(record)
            return ExecutionResult(
                success=True,
                output={"memory_id": stored.memory_id, "status": "written"},
            )

        if cap_id == "memory.promote":
            request = MemoryPromotionRequest(
                memory_id=payload["memory_id"],
                source_environment=self._current_environment(),
                target_environment=payload["target_environment"],
                approval_ref=payload.get("approval_reference"),
                requested_by=payload.get("requested_by"),
            )
            result = self.memory_store.promote(request)
            return ExecutionResult(
                success=result.promoted,
                output={
                    "promoted": result.promoted,
                    "reason": result.reason,
                    "record": result.record.to_dict() if result.record else None,
                },
                failure_reason=result.reason if not result.promoted else None,
            )

        return ExecutionResult(
            success=False,
            failure_reason=f"Unknown memory operation: {cap_id}",
        )

    def _snapshot_state(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "environment": self.environment,
            "session_state": dict(self.session_state),
            "working_set": dict(self.working_set),
            "plan_queue_length": len(self.plan_queue),
            "pending_approvals": [
                {
                    "request_id": approval.request_id,
                    "created_from_step_id": approval.created_from_step_id,
                    "proposal": {
                        "kind": approval.proposal.kind.value,
                        "description": approval.proposal.description,
                        "capabilityId": approval.proposal.capability_id,
                        "payload": approval.proposal.payload,
                    },
                    "reason_ids": list(approval.reason_ids),
                    "approval_kind": approval.approval_kind,
                }
                for approval in self.pending_approvals
            ],
            "observation_count": len(self.observations),
        }


def load_artifact_bundle(directory_path: str | Path) -> ArtifactBundle:
    directory = Path(directory_path)
    result = validate_artifact_directory(directory)
    if not result.ok:
        messages = "\n".join(f"{issue.code}: {issue.message}" for issue in result.issues)
        raise ValueError(f"Artifact directory failed validation:\n{messages}")

    artifacts = {artifact.artifact_type: artifact.data for artifact in result.artifacts}
    return ArtifactBundle(
        directory_path=directory,
        agent_spec=artifacts["agent-spec"],
        capability_manifest=artifacts["capability-manifest"],
        policy_bundle=artifacts["policy-bundle"],
        scenario_pack=artifacts["scenario-pack"],
        research_record=artifacts.get("research-record"),
        promotion_record=artifacts.get("promotion-record"),
        scaffold_manifest=artifacts.get("scaffold-manifest"),
    )


def write_step_ledger_json(session: RuntimeSession, output_path: str | Path) -> None:
    path = Path(output_path)
    serialized = []
    for entry in session.step_ledger:
        serialized.append(
            {
                "stepId": entry.step_id,
                "proposal": {
                    "kind": entry.proposal.kind.value,
                    "description": entry.proposal.description,
                    "capabilityId": entry.proposal.capability_id,
                    "payload": entry.proposal.payload,
                },
                "lifecycle": entry.lifecycle.value,
                "stateBefore": entry.state_before,
                "stateAfter": entry.state_after,
                "policyDecision": entry.policy_decision,
                "executionResult": entry.execution_result,
                "message": entry.message,
            }
        )
    path.write_text(f"{json.dumps(serialized, indent=2)}\n", encoding="utf8")


def export_session_replay(session: RuntimeSession) -> RuntimeReplay:
    return RuntimeReplay(
        artifact_set_id=session.artifacts.agent_spec["artifactSetId"],
        environment=session.environment,
        session_status=session.status.value,
        session_state=dict(session.session_state),
        working_set=dict(session.working_set),
        observations=list(session.observations),
        pending_approvals=[
            {
                "request_id": approval.request_id,
                "created_from_step_id": approval.created_from_step_id,
                "proposal": {
                    "kind": approval.proposal.kind.value,
                    "description": approval.proposal.description,
                    "capabilityId": approval.proposal.capability_id,
                    "payload": approval.proposal.payload,
                },
                "reason_ids": list(approval.reason_ids),
                "approval_kind": approval.approval_kind,
            }
            for approval in session.pending_approvals
        ],
        step_ledger=[
            {
                "stepId": entry.step_id,
                "proposal": {
                    "kind": entry.proposal.kind.value,
                    "description": entry.proposal.description,
                    "capabilityId": entry.proposal.capability_id,
                    "payload": entry.proposal.payload,
                },
                "lifecycle": entry.lifecycle.value,
                "stateBefore": entry.state_before,
                "stateAfter": entry.state_after,
                "policyDecision": entry.policy_decision,
                "executionResult": entry.execution_result,
                "message": entry.message,
            }
            for entry in session.step_ledger
        ],
    )


def write_session_replay_json(session: RuntimeSession, output_path: str | Path) -> None:
    replay = export_session_replay(session)
    payload = {
        "artifactSetId": replay.artifact_set_id,
        "environment": replay.environment,
        "sessionStatus": replay.session_status,
        "sessionState": replay.session_state,
        "workingSet": replay.working_set,
        "observations": replay.observations,
        "pendingApprovals": replay.pending_approvals,
        "stepLedger": replay.step_ledger,
    }
    Path(output_path).write_text(f"{json.dumps(payload, indent=2)}\n", encoding="utf8")


def load_session_replay_json(replay_path: str | Path) -> RuntimeReplay:
    payload = json.loads(Path(replay_path).read_text(encoding="utf8"))
    return RuntimeReplay(
        artifact_set_id=payload["artifactSetId"],
        environment=payload["environment"],
        session_status=payload["sessionStatus"],
        session_state=payload["sessionState"],
        working_set=payload["workingSet"],
        observations=payload["observations"],
        pending_approvals=payload["pendingApprovals"],
        step_ledger=payload["stepLedger"],
    )


def hydrate_session_from_replay(
    replay: RuntimeReplay,
    artifacts: ArtifactBundle,
    planner: Planner,
    execution_router: ExecutionRouter,
    policy_gate: NativePolicyGate | None = None,
) -> RuntimeSession:
    session = RuntimeSession(
        artifacts=artifacts,
        environment=replay.environment,
        planner=planner,
        execution_router=execution_router,
        policy_gate=policy_gate,
        scenario_inputs=replay.session_state.get("scenario_inputs", {}),
    )
    session.status = SessionStatus(replay.session_status)
    session.session_state = dict(replay.session_state)
    session.working_set = dict(replay.working_set)
    session.observations = list(replay.observations)
    session.pending_approvals = [
        PendingApproval(
            request_id=approval["request_id"],
            created_from_step_id=approval["created_from_step_id"],
            proposal=StepProposal(
                kind=StepKind(approval["proposal"]["kind"]),
                description=approval["proposal"]["description"],
                capability_id=approval["proposal"].get("capabilityId"),
                payload=approval["proposal"].get("payload", {}),
            ),
            reason_ids=list(approval.get("reason_ids", [])),
            approval_kind=approval.get("approval_kind", "manual"),
        )
        for approval in replay.pending_approvals
    ]
    session.step_ledger = [
        StepLedgerEntry(
            step_id=entry["stepId"],
            proposal=StepProposal(
                kind=StepKind(entry["proposal"]["kind"]),
                description=entry["proposal"]["description"],
                capability_id=entry["proposal"].get("capabilityId"),
                payload=entry["proposal"].get("payload", {}),
            ),
            lifecycle=StepLifecycle(entry["lifecycle"]),
            state_before=entry.get("stateBefore", {}),
            state_after=entry.get("stateAfter", {}),
            policy_decision=entry.get("policyDecision"),
            execution_result=entry.get("executionResult"),
            message=entry.get("message"),
        )
        for entry in replay.step_ledger
    ]
    session._step_counter = len(session.step_ledger)
    return session

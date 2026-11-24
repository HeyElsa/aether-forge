"""Per-run reputation snapshots for Forge agents.

Every agent run produces an evidence-backed ``reputation-record.json`` next to
the other artifacts: a small, machine-readable account of what the runtime
actually observed — tick reliability, execution follow-through, approval
friction, and (when the agent trades) portfolio movement.

Two design rules keep the record honest:

1. **Only observed inputs are scored.** A component with no underlying data is
   reported as unobserved and removed from the weighting (weights renormalize),
   never scored "neutral" — an agent that never traded must not look like a
   break-even trader.
2. **The formula ships with the record.** Each snapshot embeds its component
   scores, weights, and input counts so a third party can recompute the number
   from the same run data.

This is the runtime half of agent reputation. Registry/on-chain publication
(ERC-8004 metadata, attestor-signed snapshots) can consume these records but
is intentionally out of scope here.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

RECORD_FILENAME = "reputation-record.json"
RECORD_KIND = "aether-forge/reputation-record"
RECORD_VERSION = "0.1.0"


@dataclass(slots=True)
class ReputationInputs:
    """Counts gathered from one runner invocation."""

    ticks_total: int = 0
    ticks_complete: int = 0
    ticks_failed: int = 0
    steps_executed_total: int = 0
    approvals_pending_total: int = 0
    # Trading observations (None = not observed this run)
    initial_balance_usd: float | None = None
    final_balance_usd: float | None = None

    @property
    def trading_observed(self) -> bool:
        return self.initial_balance_usd is not None and self.final_balance_usd is not None

    @property
    def realized_pnl_usd(self) -> float | None:
        if not self.trading_observed:
            return None
        return round(self.final_balance_usd - self.initial_balance_usd, 2)


@dataclass(slots=True)
class ReputationSnapshot:
    """One scored reputation snapshot for a single run."""

    score: float
    tier: str
    components: dict[str, dict[str, float]]
    unobserved: list[str]
    inputs: ReputationInputs
    computed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "tier": self.tier,
            "components": self.components,
            "unobserved": self.unobserved,
            "inputs": {
                "ticksTotal": self.inputs.ticks_total,
                "ticksComplete": self.inputs.ticks_complete,
                "ticksFailed": self.inputs.ticks_failed,
                "stepsExecutedTotal": self.inputs.steps_executed_total,
                "approvalsPendingTotal": self.inputs.approvals_pending_total,
                "tradingObserved": self.inputs.trading_observed,
                "initialBalanceUsd": self.inputs.initial_balance_usd,
                "finalBalanceUsd": self.inputs.final_balance_usd,
                "realizedPnlUsd": self.inputs.realized_pnl_usd,
            },
            "computedAt": self.computed_at,
        }


class ReputationScorer(Protocol):
    """Anything that can turn run observations into a reputation snapshot."""

    def score(self, inputs: ReputationInputs) -> ReputationSnapshot:  # pragma: no cover - protocol
        ...


class DefaultReputationScorer:
    """Transparent weighted scorer over observed run behavior.

    Components (0-100 each):

    - ``reliability``    — completed ticks / total ticks. Weight 0.5.
    - ``follow_through`` — executed steps / (executed + pending-approval
      steps): how much of what the agent proposed actually ran inside policy.
      Weight 0.5.

    Realized PnL is *reported* in the snapshot but deliberately not folded
    into the v0 score: in sandbox/paper runs it reflects mock market data,
    and scoring it would reward noise. A live-trading scorer can subclass and
    override :meth:`score`.
    """

    WEIGHTS = {
        "reliability": 0.5,
        "follow_through": 0.5,
    }

    TIERS = ((80.0, "strong"), (50.0, "developing"), (0.0, "weak"))

    def score(self, inputs: ReputationInputs) -> ReputationSnapshot:
        components: dict[str, dict[str, float]] = {}
        unobserved: list[str] = []

        if inputs.ticks_total > 0:
            reliability = 100.0 * inputs.ticks_complete / inputs.ticks_total
            components["reliability"] = {
                "score": round(reliability, 2),
                "weight": self.WEIGHTS["reliability"],
            }
        else:
            unobserved.append("reliability")

        proposed = inputs.steps_executed_total + inputs.approvals_pending_total
        if proposed > 0:
            follow_through = 100.0 * inputs.steps_executed_total / proposed
            components["follow_through"] = {
                "score": round(follow_through, 2),
                "weight": self.WEIGHTS["follow_through"],
            }
        else:
            unobserved.append("follow_through")

        if not inputs.trading_observed:
            unobserved.append("trading")

        total_weight = sum(c["weight"] for c in components.values())
        if total_weight > 0:
            score = sum(c["score"] * c["weight"] for c in components.values()) / total_weight
        else:
            score = 0.0

        tier = next(name for threshold, name in self.TIERS if score >= threshold)
        return ReputationSnapshot(
            score=round(score, 2),
            tier=tier,
            components=components,
            unobserved=unobserved,
            inputs=inputs,
        )


def collect_inputs_from_run(
    tick_history: Any,
    working_set: dict[str, Any] | None = None,
    *,
    initial_balance_usd: float | None = None,
) -> ReputationInputs:
    """Build :class:`ReputationInputs` from runner state.

    ``tick_history`` is an iterable of ``TickResult``-shaped objects.
    ``working_set`` is the runner's persistent working set; portfolio data is
    read from the same keys the runner itself uses for status reporting.
    """
    inputs = ReputationInputs()
    for tick in tick_history or []:
        inputs.ticks_total += 1
        status = getattr(tick, "session_status", "")
        if status == "complete":
            inputs.ticks_complete += 1
        elif status == "failed":
            inputs.ticks_failed += 1
        inputs.steps_executed_total += getattr(tick, "steps_executed", 0) or 0
        inputs.approvals_pending_total += len(getattr(tick, "pending_approvals", []) or [])

    portfolio: dict[str, Any] = {}
    if working_set:
        portfolio = working_set.get(
            "elsa-get-portfolio", working_set.get("elsa-get-balances", {})
        ) or {}
    balance = portfolio.get("cash_usd", portfolio.get("balance_usd"))
    if balance is not None and initial_balance_usd is not None:
        inputs.initial_balance_usd = float(initial_balance_usd)
        inputs.final_balance_usd = float(balance)

    return inputs


def build_reputation_record(
    snapshot: ReputationSnapshot,
    *,
    artifact_set_id: str | None,
    agent_name: str | None,
    environment: str | None,
) -> dict[str, Any]:
    """Wrap a snapshot in the artifact envelope written to disk."""
    return {
        "kind": RECORD_KIND,
        "version": RECORD_VERSION,
        "artifactSetId": artifact_set_id,
        "agentName": agent_name,
        "environment": environment,
        "snapshot": snapshot.to_dict(),
        "scorer": type(DefaultReputationScorer()).__name__,
    }


def write_reputation_record(record: dict[str, Any], artifact_directory: str | Path) -> Path:
    """Persist the record as ``reputation-record.json`` in the artifact dir."""
    path = Path(artifact_directory) / RECORD_FILENAME
    path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf8")
    return path

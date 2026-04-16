"""Runtime self-evaluation and autoresearch for Aether Forge agents.

Enables agents to measure their own performance, detect underperformance,
propose strategy mutations, evaluate them, and present improvement
proposals to the user for approval.

This is the Karpathy autoresearch pattern applied at runtime:
  baseline → hypothesis → evaluate → keep/discard → iterate

The agent CANNOT weaken its own evaluation criteria or remove safety
constraints. All proposals go through the governance pipeline.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Strategy artifact — structured, mutable, versioned
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class StrategyArtifact:
    """Structured trading strategy that the agent can reason about and mutate.

    Unlike the agent-spec (which is the contract), the strategy artifact
    contains tunable parameters that change based on market conditions.
    """

    version: int = 1
    parameters: dict[str, Any] = field(default_factory=lambda: {
        "spread_pct": 1.0,
        "position_size_pct": 1.0,  # % of balance per trade
        "max_open_orders": 4,
        "momentum_threshold": 0.5,
        "volatility_multiplier": 1.0,  # widen spread in high vol
        "rebalance_interval_ticks": 6,
        "tokens": ["ETH"],
    })
    entry_rules: list[dict[str, str]] = field(default_factory=lambda: [
        {"condition": "momentum.trend == 'bearish' AND change_last_candle_pct < -0.3", "action": "buy"},
        {"condition": "momentum.trend == 'bullish' AND change_last_candle_pct > 0.3", "action": "sell"},
    ])
    success_metrics: dict[str, float] = field(default_factory=lambda: {
        "min_win_rate": 0.40,
        "max_drawdown_pct": 10.0,
        "min_profit_per_tick": 0.0,
    })
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "parameters": dict(self.parameters),
            "entry_rules": list(self.entry_rules),
            "success_metrics": dict(self.success_metrics),
            "history": list(self.history),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StrategyArtifact:
        return cls(
            version=data.get("version", 1),
            parameters=data.get("parameters", {}),
            entry_rules=data.get("entry_rules", []),
            success_metrics=data.get("success_metrics", {}),
            history=data.get("history", []),
        )

    @classmethod
    def load(cls, path: Path) -> StrategyArtifact:
        if path.exists():
            return cls.from_dict(json.loads(path.read_text(encoding="utf8")))
        return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf8")
        # Lock down strategy file — a compromised MCP server with filesystem access
        # could modify it to change the agent's behavior without an audit trail.
        # (Flagged as MEDIUM by AI safety audit.)
        try:
            path.chmod(0o600)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Self-evaluation — compute performance from trade history
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PerformanceReport:
    """Measured performance over a window of ticks."""

    window_ticks: int = 0
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    total_pnl_usd: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_pnl_per_tick: float = 0.0
    current_balance_usd: float = 0.0
    initial_balance_usd: float = 0.0
    observations: list[str] = field(default_factory=list)
    meets_criteria: bool = True
    failing_metrics: list[str] = field(default_factory=list)


class SelfEvaluator:
    """Evaluates agent performance against strategy success metrics."""

    def __init__(self, strategy: StrategyArtifact) -> None:
        self.strategy = strategy
        self._balance_history: list[float] = []
        self._trade_results: list[dict[str, Any]] = []

    def record_tick(self, balance_usd: float, trades: list[dict[str, Any]] | None = None) -> None:
        """Record a tick's result for evaluation."""
        self._balance_history.append(balance_usd)
        if trades:
            self._trade_results.extend(trades)

    def evaluate(self, initial_balance: float = 10_000.0) -> PerformanceReport:
        """Compute performance metrics and check against success criteria."""
        report = PerformanceReport(
            window_ticks=len(self._balance_history),
            initial_balance_usd=initial_balance,
            current_balance_usd=self._balance_history[-1] if self._balance_history else initial_balance,
        )

        # Trade analysis
        report.total_trades = len(self._trade_results)
        for trade in self._trade_results:
            pnl = trade.get("pnl_usd", 0)
            if pnl > 0:
                report.winning_trades += 1
            elif pnl < 0:
                report.losing_trades += 1

        if report.total_trades > 0:
            report.win_rate = report.winning_trades / report.total_trades

        # P&L
        report.total_pnl_usd = report.current_balance_usd - initial_balance
        report.avg_pnl_per_tick = report.total_pnl_usd / max(report.window_ticks, 1)

        # Drawdown
        if len(self._balance_history) >= 2:
            peak = self._balance_history[0]
            max_dd = 0.0
            for bal in self._balance_history:
                peak = max(peak, bal)
                dd = (peak - bal) / peak * 100 if peak > 0 else 0
                max_dd = max(max_dd, dd)
            report.max_drawdown_pct = round(max_dd, 3)

        # Check against criteria
        metrics = self.strategy.success_metrics
        report.meets_criteria = True
        report.failing_metrics = []

        if report.total_trades >= 4:  # Need minimum trades to evaluate
            if report.win_rate < metrics.get("min_win_rate", 0):
                report.failing_metrics.append(f"win_rate {report.win_rate:.2f} < {metrics['min_win_rate']}")
                report.meets_criteria = False

        if report.max_drawdown_pct > metrics.get("max_drawdown_pct", 100):
            report.failing_metrics.append(f"drawdown {report.max_drawdown_pct:.1f}% > {metrics['max_drawdown_pct']}%")
            report.meets_criteria = False

        if report.window_ticks >= 3:
            if report.avg_pnl_per_tick < metrics.get("min_profit_per_tick", -float("inf")):
                report.failing_metrics.append(f"avg_pnl_per_tick ${report.avg_pnl_per_tick:.2f} < ${metrics['min_profit_per_tick']}")
                report.meets_criteria = False

        # Observations
        if report.total_trades == 0 and report.window_ticks >= 3:
            report.observations.append("No trades placed in {report.window_ticks} ticks — strategy may be too conservative")
        if report.max_drawdown_pct > 5:
            report.observations.append(f"Drawdown of {report.max_drawdown_pct:.1f}% — consider tightening risk")

        return report


# ---------------------------------------------------------------------------
# Improvement proposals — structured, reviewable, governed
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class ImprovementProposal:
    """A proposed strategy mutation with rationale and evidence."""

    proposal_id: str = ""
    timestamp: str = ""
    hypothesis: str = ""
    mutations: dict[str, Any] = field(default_factory=dict)
    rationale: str = ""
    performance_before: dict[str, Any] = field(default_factory=dict)
    expected_improvement: str = ""
    status: str = "proposed"  # proposed | accepted | rejected | expired
    user_feedback: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "timestamp": self.timestamp,
            "hypothesis": self.hypothesis,
            "mutations": self.mutations,
            "rationale": self.rationale,
            "performance_before": self.performance_before,
            "expected_improvement": self.expected_improvement,
            "status": self.status,
            "user_feedback": self.user_feedback,
        }


# ---------------------------------------------------------------------------
# Runtime autoresearch — the self-improvement loop
# ---------------------------------------------------------------------------

class ResearchModel(Protocol):
    """LLM that proposes strategy improvements."""
    def complete(self, prompt: str) -> str: ...


class RuntimeAutoresearch:
    """Karpathy-style autoresearch loop running at agent runtime.

    Every ``eval_interval`` ticks:
    1. Self-evaluate current performance
    2. If underperforming, ask the LLM to propose a mutation
    3. Present the proposal to the user (don't auto-apply)
    4. User accepts → update strategy.json, increment version
    5. User rejects → discard, log in history

    The agent CANNOT:
    - Lower its own success criteria
    - Remove safety constraints
    - Auto-apply changes without user review (in v1)
    """

    def __init__(
        self,
        strategy_path: Path,
        *,
        research_model: ResearchModel | None = None,
        eval_interval: int = 6,  # Evaluate every N ticks
    ) -> None:
        self.strategy_path = strategy_path
        self.strategy = StrategyArtifact.load(strategy_path)
        self.evaluator = SelfEvaluator(self.strategy)
        self.research_model = research_model
        self.eval_interval = eval_interval
        self._proposals: list[ImprovementProposal] = []
        self._tick_since_eval = 0

    def on_tick_complete(self, balance_usd: float, trades: list[dict[str, Any]] | None = None) -> ImprovementProposal | None:
        """Called after each tick. Returns a proposal if improvement is needed."""
        self.evaluator.record_tick(balance_usd, trades)
        self._tick_since_eval += 1

        if self._tick_since_eval < self.eval_interval:
            return None

        self._tick_since_eval = 0
        report = self.evaluator.evaluate(self.strategy.parameters.get("initial_balance_usd", 10_000.0))

        logger.info(
            "Self-eval: ticks=%d trades=%d win_rate=%.2f pnl=$%.2f drawdown=%.1f%% meets_criteria=%s",
            report.window_ticks, report.total_trades, report.win_rate,
            report.total_pnl_usd, report.max_drawdown_pct, report.meets_criteria,
        )

        if report.meets_criteria:
            return None

        # Underperforming — propose improvement
        if self.research_model is None:
            logger.info("No research model configured — skipping autoresearch proposal")
            return None

        proposal = self._propose_improvement(report)
        if proposal:
            self._proposals.append(proposal)
            self._print_proposal(proposal)
        return proposal

    def accept_proposal(self, proposal_id: str) -> bool:
        """User accepts a proposal — apply mutations to strategy."""
        for proposal in self._proposals:
            if proposal.proposal_id == proposal_id and proposal.status == "proposed":
                # Validate: can't weaken success metrics
                if self._weakens_criteria(proposal.mutations):
                    proposal.status = "rejected"
                    proposal.user_feedback = "Rejected: would weaken success criteria"
                    logger.warning("Proposal %s rejected: weakens success criteria", proposal_id)
                    return False

                # Apply mutations
                for key, value in proposal.mutations.items():
                    if key in self.strategy.parameters:
                        self.strategy.parameters[key] = value
                    elif key in ("entry_rules",):
                        self.strategy.entry_rules = value

                self.strategy.version += 1
                self.strategy.history.append({
                    "version": self.strategy.version,
                    "proposal_id": proposal_id,
                    "mutations": proposal.mutations,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                self.strategy.save(self.strategy_path)
                proposal.status = "accepted"
                logger.info("Proposal %s accepted — strategy v%d saved", proposal_id, self.strategy.version)
                return True
        return False

    def reject_proposal(self, proposal_id: str, feedback: str = "") -> bool:
        """User rejects a proposal."""
        for proposal in self._proposals:
            if proposal.proposal_id == proposal_id and proposal.status == "proposed":
                proposal.status = "rejected"
                proposal.user_feedback = feedback
                logger.info("Proposal %s rejected: %s", proposal_id, feedback)
                return True
        return False

    @property
    def pending_proposals(self) -> list[ImprovementProposal]:
        return [p for p in self._proposals if p.status == "proposed"]

    @property
    def current_strategy(self) -> StrategyArtifact:
        return self.strategy

    def _propose_improvement(self, report: PerformanceReport) -> ImprovementProposal | None:
        """Ask the LLM to propose a strategy mutation."""
        prompt = self._build_research_prompt(report)
        try:
            raw = self.research_model.complete(prompt)
            # Strip code fences
            clean = raw.strip()
            if clean.startswith("```"):
                lines = clean.split("\n")
                clean = "\n".join(lines[1:])
                if clean.rstrip().endswith("```"):
                    clean = clean.rstrip()[:-3]

            data = json.loads(clean)
            return ImprovementProposal(
                proposal_id=f"prop_{uuid4().hex[:8]}",
                timestamp=datetime.now(UTC).isoformat(),
                hypothesis=data.get("hypothesis", ""),
                mutations=data.get("mutations", {}),
                rationale=data.get("rationale", ""),
                performance_before={
                    "win_rate": report.win_rate,
                    "total_pnl_usd": report.total_pnl_usd,
                    "max_drawdown_pct": report.max_drawdown_pct,
                    "failing_metrics": report.failing_metrics,
                },
                expected_improvement=data.get("expected_improvement", ""),
            )
        except Exception as error:
            logger.warning("Autoresearch proposal failed: %s", error)
            return None

    def _build_research_prompt(self, report: PerformanceReport) -> str:
        return (
            "You are analyzing a trading agent's strategy performance.\n\n"
            f"Current strategy (v{self.strategy.version}):\n"
            f"  Parameters: {json.dumps(self.strategy.parameters, indent=2)}\n"
            f"  Entry rules: {json.dumps(self.strategy.entry_rules, indent=2)}\n"
            f"  Success metrics: {json.dumps(self.strategy.success_metrics, indent=2)}\n\n"
            f"Performance report ({report.window_ticks} ticks):\n"
            f"  Total trades: {report.total_trades}\n"
            f"  Win rate: {report.win_rate:.2f}\n"
            f"  P&L: ${report.total_pnl_usd:+.2f}\n"
            f"  Max drawdown: {report.max_drawdown_pct:.1f}%\n"
            f"  Avg P&L per tick: ${report.avg_pnl_per_tick:+.2f}\n"
            f"  Failing metrics: {report.failing_metrics}\n"
            f"  Observations: {report.observations}\n\n"
            "Propose ONE mutation to improve performance. Return JSON only:\n"
            "{\n"
            '  "hypothesis": "what you expect to change and why",\n'
            '  "mutations": {"parameter_name": new_value, ...},\n'
            '  "rationale": "evidence-based reasoning for this change",\n'
            '  "expected_improvement": "what metric should improve and by how much"\n'
            "}\n\n"
            "Rules:\n"
            "- Only mutate parameters listed in the current strategy\n"
            "- Do NOT lower success_metrics thresholds\n"
            "- Prefer small changes (one parameter at a time)\n"
            "- Base reasoning on the performance data, not guesses\n"
        )

    # Safety bounds for strategy parameters that the autoresearch loop
    # CANNOT exceed, regardless of what the LLM proposes. Prevents the
    # agent from weakening its own risk controls by mutating parameters
    # that aren't covered by the success_metrics checks.
    # (Flagged as HIGH by AI safety audit — LLM can propose high-risk params.)
    _PARAM_SAFETY_BOUNDS: dict[str, tuple[float | None, float | None]] = {
        "position_size_pct": (0.1, 25.0),      # min 0.1%, max 25% per trade
        "max_open_orders": (1, 10),             # at least 1, at most 10
        "stop_loss_pct": (0.5, 20.0),           # at least 0.5%, at most 20%
        "spread_pct": (0.01, 10.0),             # at least 0.01%, at most 10%
        "momentum_threshold": (0.01, 5.0),      # sane range
        "volatility_multiplier": (0.1, 5.0),    # sane range
    }

    def _weakens_criteria(self, mutations: dict[str, Any]) -> bool:
        """Check if proposed mutations would weaken success criteria or
        exceed safety bounds on strategy parameters."""
        for key, value in mutations.items():
            # Check success_metrics (existing logic)
            if key in self.strategy.success_metrics:
                current = self.strategy.success_metrics[key]
                # For min_* metrics, lowering is weakening
                if key.startswith("min_") and isinstance(value, (int, float)) and value < current:
                    return True
                # For max_* metrics, raising is weakening
                if key.startswith("max_") and isinstance(value, (int, float)) and value > current:
                    return True

            # Check parameter safety bounds (new — AI safety audit fix)
            if key in self._PARAM_SAFETY_BOUNDS and isinstance(value, (int, float)):
                lo, hi = self._PARAM_SAFETY_BOUNDS[key]
                if lo is not None and value < lo:
                    logger.warning("Proposal rejected: %s=%.4f below safety floor %.4f", key, value, lo)
                    return True
                if hi is not None and value > hi:
                    logger.warning("Proposal rejected: %s=%.4f above safety ceiling %.4f", key, value, hi)
                    return True

        return False

    def _print_proposal(self, proposal: ImprovementProposal) -> None:
        """Print a proposal for user review."""
        print(f"\n  {'='*60}")
        print(f"  IMPROVEMENT PROPOSAL [{proposal.proposal_id}]")
        print(f"  {'='*60}")
        print(f"  Hypothesis: {proposal.hypothesis}")
        print(f"  Rationale:  {proposal.rationale}")
        print("  Changes:")
        for key, value in proposal.mutations.items():
            current = self.strategy.parameters.get(key, "?")
            print(f"    {key}: {current} → {value}")
        print(f"  Expected: {proposal.expected_improvement}")
        print(f"  Performance: win_rate={proposal.performance_before.get('win_rate', 0):.2f} "
              f"pnl=${proposal.performance_before.get('total_pnl_usd', 0):+.2f} "
              f"drawdown={proposal.performance_before.get('max_drawdown_pct', 0):.1f}%")
        print(f"  Failing:  {proposal.performance_before.get('failing_metrics', [])}")
        print(f"\n  To accept: forge strategy accept {proposal.proposal_id}")
        print(f"  To reject: forge strategy reject {proposal.proposal_id}")
        print(f"  {'='*60}\n")

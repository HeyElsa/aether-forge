"""Slow-mode artifact generation with autoresearch loop for Aether Forge.

Slow mode generates an initial baseline (via fast mode), then runs an
iterative autoresearch loop that proposes improvements, evaluates them
against a fixed scenario pack, and keeps only measurably better candidates.
The loop produces a research record artifact documenting every iteration.
"""

from __future__ import annotations

import copy
import json
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

logger = logging.getLogger(__name__)

from .evals import ScenarioPackEvaluationSummary, evaluate_scenario_pack
from .generator import FastGenerateRequest, GeneratedArtifactSet, generate_fast_artifact_set


class ResearchModel(Protocol):
    """A model that can propose artifact improvements."""

    def complete(self, planning_prompt: str) -> str: ...


@dataclass(slots=True)
class SlowGenerateRequest:
    name: str
    idea: str
    output_directory: Path
    max_iterations: int = 5
    research_model: ResearchModel | None = None
    skills: list[str] | None = None


@dataclass(slots=True)
class IterationEntry:
    candidate_id: str
    parent_candidate_id: str | None
    hypothesis: str
    changed_surfaces: list[str]
    budget_consumed: dict[str, Any]
    evaluation_conditions: dict[str, Any]
    measured_outcomes: dict[str, Any]
    decision_status: str  # keep | discard | blocked | execution-failure
    decision_rationale: str


@dataclass(slots=True)
class SlowGenerateResult:
    artifact_set_id: str
    output_directory: Path
    domain: str
    generated_files: list[Path]
    scaffold_files: list[Path]
    iterations: list[IterationEntry]
    baseline_metrics: dict[str, Any]
    final_metrics: dict[str, Any]
    research_record_path: Path | None


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def _compute_metrics(summary: ScenarioPackEvaluationSummary) -> dict[str, Any]:
    total = summary.total_scenarios
    return {
        "total_scenarios": total,
        "matched_expectations": summary.matched_expectations,
        "match_rate": summary.matched_expectations / total if total else 0.0,
        "counts_by_stage": dict(summary.counts_by_stage),
        "meets_expectations": summary.meets_expectations,
    }


def _is_improvement(candidate: dict[str, Any], baseline: dict[str, Any]) -> bool:
    """A candidate is an improvement if it matches at least as many expectations
    and does not regress the pass count."""
    if candidate["matched_expectations"] < baseline["matched_expectations"]:
        return False
    cand_pass = candidate["counts_by_stage"].get("pass", 0)
    base_pass = baseline["counts_by_stage"].get("pass", 0)
    if cand_pass < base_pass:
        return False
    # Strictly better on at least one axis
    return (
        candidate["matched_expectations"] > baseline["matched_expectations"]
        or cand_pass > base_pass
    )


# ---------------------------------------------------------------------------
# Improvement proposal parsing
# ---------------------------------------------------------------------------

_IMPROVEMENT_PROMPT_TEMPLATE = """\
You are an agent specification researcher improving an Aether Forge artifact set.

## Current Agent Spec
{agent_spec_json}

## Current Evaluation Metrics
{metrics_json}

## Previous Iterations
{iteration_summary}

## Instructions
Propose ONE focused improvement to the agent specification artifacts.
Choose from these mutation surfaces:
- agent-spec: objective clarity, evaluation criteria, capability refs
- policy-bundle: tighten or relax rules, add safety constraints
- scenario-pack: add edge-case scenarios, improve expected outcomes
- capability-manifest: refine capability descriptions, effect semantics

Respond with JSON only:
{{
  "hypothesis": "one-line description of what you expect to improve",
  "target_artifact": "agent-spec.json|policy-bundle.json|scenario-pack.json|capability-manifest.json",
  "mutations": [
    {{"path": "dotted.path.to.field", "action": "set", "value": "..."}}
  ]
}}
"""


@dataclass(slots=True)
class _ImprovementProposal:
    hypothesis: str
    target_artifact: str
    mutations: list[dict[str, Any]]


def _parse_improvement(raw: str) -> _ImprovementProposal | None:
    """Parse the model's JSON response into a typed proposal."""
    try:
        # Strip markdown fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines)
        data = json.loads(text)
        return _ImprovementProposal(
            hypothesis=data["hypothesis"],
            target_artifact=data["target_artifact"],
            mutations=data.get("mutations", []),
        )
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _apply_mutations(artifact: dict[str, Any], mutations: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply a list of simple dot-path mutations to an artifact dict."""
    result = copy.deepcopy(artifact)
    for mutation in mutations:
        path_parts = mutation.get("path", "").split(".")
        action = mutation.get("action", "set")
        value = mutation.get("value")
        if not path_parts or not path_parts[0]:
            continue
        target = result
        for part in path_parts[:-1]:
            if isinstance(target, dict) and part in target:
                target = target[part]
            else:
                break
        else:
            key = path_parts[-1]
            if action == "set" and isinstance(target, dict):
                target[key] = value
            elif action == "add" and isinstance(target, dict):
                existing = target.get(key, [])
                if isinstance(existing, list):
                    target[key] = existing + ([value] if not isinstance(value, list) else value)
            elif action == "remove" and isinstance(target, dict):
                target.pop(key, None)
    return result


# ---------------------------------------------------------------------------
# Research record builder
# ---------------------------------------------------------------------------

def _build_research_record(
    artifact_set_id: str,
    title: str,
    idea: str,
    iterations: list[IterationEntry],
    baseline_metrics: dict[str, Any],
    final_metrics: dict[str, Any],
    scenario_pack_ref: dict[str, Any],
    stop_reason: str,
) -> dict[str, Any]:
    now = datetime.now(UTC).isoformat()
    return {
        "artifactType": "research-record",
        "schemaVersion": "1.0.0",
        "artifactId": f"research_{artifact_set_id}",
        "artifactVersion": "0.1.0",
        "artifactSetId": artifact_set_id,
        "title": f"{title} Research Record",
        "generator": {
            "name": "aether-forge",
            "version": "0.1.0",
            "inputDigest": f"sha256:{artifact_set_id}:slow-mode",
        },
        "compatibility": {
            "status": "backward-compatible",
            "previousArtifactVersion": None,
            "migrationRef": None,
        },
        "provenance": {
            "createdAt": now,
            "sourceMode": "slow",
        },
        "researchPlan": {
            "goal": f"Refine agent specification for: {idea[:200]}",
            "tracks": ["policy-defaults", "scenario-coverage", "capability-refinement"],
        },
        "evidenceLog": [
            {
                "source": "autoresearch-loop",
                "claim": f"Ran {len(iterations)} iterations; "
                         f"baseline match_rate={baseline_metrics.get('match_rate', 0):.2f}, "
                         f"final match_rate={final_metrics.get('match_rate', 0):.2f}.",
            }
        ],
        "findings": [
            {
                "summary": entry.hypothesis,
                "confidence": "medium" if entry.decision_status == "keep" else "low",
            }
            for entry in iterations
            if entry.candidate_id != "cand_baseline"
        ],
        "blockers": [
            {"description": entry.decision_rationale}
            for entry in iterations
            if entry.decision_status == "blocked"
        ],
        "activeComparisonContract": {
            "comparisonId": f"cmp_{artifact_set_id}",
            "evaluatorVersion": "prq-1.0.0",
            "policyThresholdsDigest": f"sha256:policy-thresholds-{artifact_set_id}",
            "scenarioPackRef": scenario_pack_ref,
            "normalizationRules": {"fixedBudget": "yes"},
            "allowedMutationSurfaces": [
                {"artifactType": "agent-spec", "pathPattern": "/objective/**"},
                {"artifactType": "policy-bundle", "pathPattern": "/rules/**"},
                {"artifactType": "scenario-pack", "pathPattern": "/scenarios/**"},
                {"artifactType": "capability-manifest", "pathPattern": "/capabilities/**"},
            ],
            "budgetRules": {"maxIterations": len(iterations)},
            "artifactSetId": artifact_set_id,
        },
        "iterationLedger": [
            {
                "candidateId": entry.candidate_id,
                "parentCandidateId": entry.parent_candidate_id,
                "hypothesis": entry.hypothesis,
                "changedSurfaces": entry.changed_surfaces,
                "budgetConsumed": entry.budget_consumed,
                "evaluationConditions": entry.evaluation_conditions,
                "measuredOutcomes": entry.measured_outcomes,
                "decisionStatus": entry.decision_status,
                "decisionRationale": entry.decision_rationale,
            }
            for entry in iterations
        ],
        "stopRationale": {
            "reason": stop_reason,
            "note": f"Completed {len(iterations)} iterations of autoresearch.",
        },
    }


# ---------------------------------------------------------------------------
# Core slow-mode generation
# ---------------------------------------------------------------------------

_ARTIFACT_FILES = ("agent-spec.json", "capability-manifest.json", "policy-bundle.json", "scenario-pack.json")
_MUTABLE_ARTIFACTS = {"agent-spec.json", "capability-manifest.json", "policy-bundle.json", "scenario-pack.json"}


def generate_slow_artifact_set(request: SlowGenerateRequest) -> SlowGenerateResult:
    """Generate an artifact set using the autoresearch loop.

    1. Generate baseline via fast mode
    2. Evaluate baseline scenarios
    3. Iterate: propose improvement → apply → evaluate → keep or discard
    4. Write research record
    """
    # ── Step 1: Baseline generation ──────────────────────────────────────
    fast_result = generate_fast_artifact_set(
        FastGenerateRequest(
            name=request.name,
            idea=request.idea,
            output_directory=request.output_directory,
            skills=request.skills,
        )
    )
    artifact_set_id = fast_result.artifact_set_id
    out_dir = request.output_directory

    # ── Step 2: Baseline evaluation ──────────────────────────────────────
    baseline_summary, _ = evaluate_scenario_pack(str(out_dir))
    baseline_metrics = _compute_metrics(baseline_summary)
    current_metrics = baseline_metrics

    iterations: list[IterationEntry] = []
    iterations.append(IterationEntry(
        candidate_id="cand_baseline",
        parent_candidate_id=None,
        hypothesis="Establish baseline artifact set from fast-mode generation.",
        changed_surfaces=["baseline-artifact-set"],
        budget_consumed={"iterations": 1},
        evaluation_conditions={"mode": "sandbox"},
        measured_outcomes=dict(baseline_metrics),
        decision_status="keep",
        decision_rationale="Established the baseline artifact package.",
    ))

    # ── Step 3: Autoresearch loop ────────────────────────────────────────
    model = request.research_model
    last_candidate_id = "cand_baseline"
    stop_reason = "budget-exhausted"

    if model is not None:
        for iteration_num in range(1, request.max_iterations + 1):
            logger.info("Autoresearch iteration %d: hypothesis=pending", iteration_num)
            # Load current artifacts
            current_artifacts = {}
            for fname in _ARTIFACT_FILES:
                fpath = out_dir / fname
                if fpath.exists():
                    current_artifacts[fname] = json.loads(fpath.read_text(encoding="utf8"))

            # Build prompt
            iteration_summary = "\n".join(
                f"- [{e.decision_status}] {e.hypothesis}" for e in iterations
            )
            prompt = _IMPROVEMENT_PROMPT_TEMPLATE.format(
                agent_spec_json=json.dumps(current_artifacts.get("agent-spec.json", {}), indent=2)[:2000],
                metrics_json=json.dumps(current_metrics, indent=2),
                iteration_summary=iteration_summary or "(none yet)",
            )

            # Ask model for improvement
            try:
                raw_response = model.complete(prompt)
            except Exception:
                iterations.append(IterationEntry(
                    candidate_id=f"cand_iter_{iteration_num}",
                    parent_candidate_id=last_candidate_id,
                    hypothesis="(model call failed)",
                    changed_surfaces=[],
                    budget_consumed={"iterations": 1},
                    evaluation_conditions={"mode": "sandbox"},
                    measured_outcomes={},
                    decision_status="execution-failure",
                    decision_rationale="Research model call failed.",
                ))
                continue

            proposal = _parse_improvement(raw_response)
            if proposal is None:
                iterations.append(IterationEntry(
                    candidate_id=f"cand_iter_{iteration_num}",
                    parent_candidate_id=last_candidate_id,
                    hypothesis="(unparseable model response)",
                    changed_surfaces=[],
                    budget_consumed={"iterations": 1},
                    evaluation_conditions={"mode": "sandbox"},
                    measured_outcomes={},
                    decision_status="execution-failure",
                    decision_rationale="Could not parse model response as improvement proposal.",
                ))
                continue

            candidate_id = f"cand_iter_{iteration_num}"

            # Apply mutations
            target = proposal.target_artifact
            if target not in _MUTABLE_ARTIFACTS or target not in current_artifacts:
                iterations.append(IterationEntry(
                    candidate_id=candidate_id,
                    parent_candidate_id=last_candidate_id,
                    hypothesis=proposal.hypothesis,
                    changed_surfaces=[target],
                    budget_consumed={"iterations": 1},
                    evaluation_conditions={"mode": "sandbox"},
                    measured_outcomes={},
                    decision_status="execution-failure",
                    decision_rationale=f"Target artifact '{target}' is not mutable or not found.",
                ))
                continue

            # Save backup, apply, write
            original_text = (out_dir / target).read_text(encoding="utf8")
            mutated = _apply_mutations(current_artifacts[target], proposal.mutations)
            (out_dir / target).write_text(json.dumps(mutated, indent=2) + "\n", encoding="utf8")

            # Evaluate candidate
            try:
                candidate_summary, _ = evaluate_scenario_pack(str(out_dir))
                candidate_metrics = _compute_metrics(candidate_summary)
            except Exception:
                # Restore original on eval failure
                (out_dir / target).write_text(original_text, encoding="utf8")
                iterations.append(IterationEntry(
                    candidate_id=candidate_id,
                    parent_candidate_id=last_candidate_id,
                    hypothesis=proposal.hypothesis,
                    changed_surfaces=[target],
                    budget_consumed={"iterations": 1},
                    evaluation_conditions={"mode": "sandbox"},
                    measured_outcomes={},
                    decision_status="execution-failure",
                    decision_rationale="Evaluation failed after applying mutations.",
                ))
                continue

            # Keep or discard
            if _is_improvement(candidate_metrics, current_metrics):
                logger.info("Iteration %d decision: %s", iteration_num, "keep")
                current_metrics = candidate_metrics
                last_candidate_id = candidate_id
                iterations.append(IterationEntry(
                    candidate_id=candidate_id,
                    parent_candidate_id=last_candidate_id,
                    hypothesis=proposal.hypothesis,
                    changed_surfaces=[target],
                    budget_consumed={"iterations": 1},
                    evaluation_conditions={"mode": "sandbox"},
                    measured_outcomes=dict(candidate_metrics),
                    decision_status="keep",
                    decision_rationale="Candidate measurably improved metrics.",
                ))
            else:
                logger.info("Iteration %d decision: %s", iteration_num, "discard")
                # Discard: restore original artifact
                (out_dir / target).write_text(original_text, encoding="utf8")
                iterations.append(IterationEntry(
                    candidate_id=candidate_id,
                    parent_candidate_id=last_candidate_id,
                    hypothesis=proposal.hypothesis,
                    changed_surfaces=[target],
                    budget_consumed={"iterations": 1},
                    evaluation_conditions={"mode": "sandbox"},
                    measured_outcomes=dict(candidate_metrics),
                    decision_status="discard",
                    decision_rationale="Candidate did not improve over current best.",
                ))

            # Check diminishing returns: if last 2 iterations were both discarded, stop
            recent = iterations[-2:]
            if len(recent) >= 2 and all(e.decision_status == "discard" for e in recent):
                stop_reason = "diminishing-returns"
                break
    else:
        stop_reason = "no-research-model"

    # ── Step 4: Write research record ────────────────────────────────────
    scenario_pack_path = out_dir / "scenario-pack.json"
    scenario_pack = json.loads(scenario_pack_path.read_text(encoding="utf8")) if scenario_pack_path.exists() else {}

    research_record = _build_research_record(
        artifact_set_id=artifact_set_id,
        title=request.name.strip(),
        idea=request.idea,
        iterations=iterations,
        baseline_metrics=baseline_metrics,
        final_metrics=current_metrics,
        scenario_pack_ref={
            "artifactType": "scenario-pack",
            "artifactId": scenario_pack.get("artifactId", "unknown"),
            "artifactVersion": scenario_pack.get("artifactVersion", "0.1.0"),
        },
        stop_reason=stop_reason,
    )

    research_record_path = out_dir / "research-record.json"
    research_record_path.write_text(json.dumps(research_record, indent=2) + "\n", encoding="utf8")

    return SlowGenerateResult(
        artifact_set_id=artifact_set_id,
        output_directory=out_dir,
        domain=fast_result.domain,
        generated_files=fast_result.generated_files + [research_record_path],
        scaffold_files=fast_result.scaffold_files,
        iterations=iterations,
        baseline_metrics=baseline_metrics,
        final_metrics=current_metrics,
        research_record_path=research_record_path,
    )

"""Small Python facade for common Aether Forge workflows."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .artifacts import ArtifactSetValidationResult, validate_artifact_directory
from .evals import ScenarioPackEvaluationSummary, evaluate_scenario_pack
from .generator import FastGenerateRequest, GeneratedArtifactSet, generate_fast_artifact_set
from .observability import EventSink
from .runner import AgentRunner, RunnerConfig, TickResult
from .runtime import Planner


@dataclass(frozen=True, slots=True)
class ForgeProject:
    """Handle for an Aether Forge agent artifact directory."""

    directory: Path
    generated_artifacts: GeneratedArtifactSet | None = None

    def validate(self) -> ArtifactSetValidationResult:
        """Validate the project's artifact set."""
        return validate_artifact_directory(self.directory)

    def eval_pack(
        self,
        *,
        environment_kind: str | None = None,
        planner_factory: Callable[[], Planner] | None = None,
        execution_router_factory: Callable[[], Any] | None = None,
        memory_store: Any = None,
    ) -> tuple[ScenarioPackEvaluationSummary, dict[str, Any]]:
        """Evaluate the project's scenario pack."""
        return evaluate_scenario_pack(
            self.directory,
            environment_kind=environment_kind,
            planner_factory=planner_factory,
            execution_router_factory=execution_router_factory,
            memory_store=memory_store,
        )

    def run(
        self,
        *,
        environment: str = "sandbox",
        max_ticks: int = 1,
        auto_approve: bool = True,
        planner_factory: Callable[[], Planner] | None = None,
        execution_router_factory: Callable[[], Any] | None = None,
        memory_store: Any = None,
        event_sink: EventSink | None = None,
        **runner_config: Any,
    ) -> list[TickResult]:
        """Run a bounded number of ticks and return their results."""
        if max_ticks < 1:
            raise ValueError("ForgeProject.run requires max_ticks >= 1")

        config_values = {
            "environment": environment,
            "max_ticks": max_ticks,
            "interval_seconds": 0.0,
            "auto_approve": auto_approve,
            **runner_config,
        }
        runner = AgentRunner(
            self.directory,
            config=RunnerConfig(**config_values),
            planner_factory=planner_factory,
            execution_router_factory=execution_router_factory,
            memory_store=memory_store,
            event_sink=event_sink,
        )
        return [runner.tick() for _ in range(max_ticks)]


class Forge:
    """Facade for common generation and runtime workflows."""

    @staticmethod
    def open(directory: str | Path) -> ForgeProject:
        """Open an existing generated agent directory."""
        return ForgeProject(directory=Path(directory).resolve())

    @staticmethod
    def generate_fast(
        *,
        name: str,
        idea: str,
        output: str | Path,
        planner: str = "heuristic",
        planner_model: str | None = None,
        planner_base_url: str | None = None,
        planner_api_key_env: str | None = None,
        skills: list[str] | None = None,
        create_wallet: bool = False,
        autonomous: bool = False,
        wallet_chain: str = "evm",
        strategy_file: str | None = None,
        deployment_profile: str = "local",
    ) -> ForgeProject:
        """Generate an agent with fast mode and return a project handle."""
        request = FastGenerateRequest(
            name=name,
            idea=idea,
            output_directory=Path(output),
            skills=skills,
            create_wallet=create_wallet,
            autonomous=autonomous,
            wallet_chain=wallet_chain,
            strategy_file=strategy_file,
            planner_mode=planner,
            planner_model=planner_model,
            planner_base_url=planner_base_url,
            planner_api_key_env=planner_api_key_env,
            planner_source="explicit",
            deployment_profile=deployment_profile,
        )
        generated = generate_fast_artifact_set(request)
        return ForgeProject(directory=generated.output_directory.resolve(), generated_artifacts=generated)

import { AbsoluteFill, Series } from "remotion";
import { BG, CodeBlock, ContentScene, OutroScene, TitleScene } from "../shared";

const Scene1Generate = () => (
  <ContentScene kicker="Programmatic" subtitle="Generate an agent from your own code">
    <CodeBlock
      filename="my_app.py"
      charsPerSecond={80}
      source={`from pathlib import Path
from aether_forge import generate_fast_artifact_set
from aether_forge.generator import FastGenerateRequest

generate_fast_artifact_set(FastGenerateRequest(
    name="BTC Trader",
    idea="buy BTC on momentum uptrends",
    output_directory=Path("./my-agent"),
))`}
    />
  </ContentScene>
);

const Scene2Protocols = () => (
  <ContentScene kicker="New in v0.20" subtitle="Five extension Protocols, all top-level">
    <CodeBlock
      filename="my_extension.py"
      charsPerSecond={70}
      source={`from aether_forge import (
    Planner,            # propose_plan(session) -> list[StepProposal]
    ExecutionRouter,    # execute(session, proposal, capability)
    PlanningModel,      # complete(prompt) -> str
    MemoryStore,        # read / write / promote
    DataSource,         # supports / fetch / subscribe
)`}
    />
  </ContentScene>
);

const Scene3RunSession = () => (
  <ContentScene kicker="Run a tick" subtitle="A RuntimeSession in 8 lines">
    <CodeBlock
      filename="my_app.py"
      charsPerSecond={75}
      source={`from aether_forge import (
    HeuristicPlanner, MockCryptoExecutionRouter, RuntimeSession,
)
from aether_forge.runtime import load_artifact_bundle

bundle = load_artifact_bundle("./my-agent")
session = RuntimeSession(artifacts=bundle, environment="sandbox",
                         planner=HeuristicPlanner(),
                         execution_router=MockCryptoExecutionRouter())
session.run(max_steps=10)`}
    />
  </ContentScene>
);

export const PythonSDK: React.FC = () => (
  <AbsoluteFill style={{ background: BG }}>
    <Series>
      <Series.Sequence durationInFrames={180} name="Title">
        <TitleScene
          titleLines={["PYTHON", "SDK"]}
          tagline="Run agents, build prompts, query memory, verify attestations — from your code"
        />
      </Series.Sequence>
      <Series.Sequence durationInFrames={330} name="Generate">
        <Scene1Generate />
      </Series.Sequence>
      <Series.Sequence durationInFrames={420} name="Protocols">
        <Scene2Protocols />
      </Series.Sequence>
      <Series.Sequence durationInFrames={420} name="RunSession">
        <Scene3RunSession />
      </Series.Sequence>
      <Series.Sequence durationInFrames={240} name="Outro">
        <OutroScene />
      </Series.Sequence>
    </Series>
  </AbsoluteFill>
);

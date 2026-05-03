import { AbsoluteFill, Series } from "remotion";
import {
  ACCENT,
  BG,
  CodeBlock,
  ContentScene,
  MUTED,
  monoFamily,
  OutroScene,
  STRING,
  TitleScene,
} from "../shared";

const Step1Protocols = () => (
  <ContentScene kicker="Step 1" subtitle="Import the extension Protocols">
    <CodeBlock
      filename="my_extension.py"
      charsPerSecond={50}
      source={`from aether_forge import (
    Planner,
    ExecutionRouter,
    PlanningModel,
    MemoryStore,
    DataSource,
)`}
    />
  </ContentScene>
);

const Step2DataSource = () => (
  <ContentScene kicker="Step 2" subtitle="Subclass DataSource — 15 lines">
    <CodeBlock
      filename="src/strategy/coinbase_source.py"
      charsPerSecond={95}
      source={`from aether_forge import DataSource, DataResult, DataSourceCost

class CoinbaseSpotSource(DataSource):
    def __init__(self):
        super().__init__("coinbase")

    def supports(self, capability):
        return "price" in capability

    def fetch(self, capability, **params):
        symbol = params.get("symbol", "BTC")
        # ... real Coinbase HTTP call ...
        return DataResult(source="coinbase", capability=capability,
                          data={"price_usd": 78438.19, "symbol": symbol},
                          cost=DataSourceCost(amount_usd=0.0, paid=False))`}
    />
  </ContentScene>
);

const Step3Plugin = () => (
  <ContentScene kicker="Step 3" subtitle="Publish via PyPI — no fork needed">
    <CodeBlock
      filename="pyproject.toml"
      charsPerSecond={70}
      source={`[project.entry-points."aether_forge.data_sources"]
coinbase = "my_pkg:CoinbaseSpotSource"

[project.entry-points."aether_forge.planners"]
grok = "my_pkg:build_grok_planner"`}
    />
    <div
      style={{
        fontFamily: monoFamily,
        fontSize: 26,
        color: MUTED,
        paddingLeft: 4,
      }}
    >
      <span style={{ color: STRING }}>$</span> pip install aether-forge-coinbase
      <br />
      <span style={{ color: STRING }}>$</span> forge run ./my-agent --planner-mode grok
    </div>
  </ContentScene>
);

export const ExtendingFramework: React.FC = () => (
  <AbsoluteFill style={{ background: BG }}>
    <Series>
      <Series.Sequence durationInFrames={180} name="Title">
        <TitleScene
          headline="Extending Aether Forge"
          tagline="Custom planners, data sources & memory stores — without forking"
        />
      </Series.Sequence>
      <Series.Sequence durationInFrames={300} name="Protocols">
        <Step1Protocols />
      </Series.Sequence>
      <Series.Sequence durationInFrames={450} name="DataSource">
        <Step2DataSource />
      </Series.Sequence>
      <Series.Sequence durationInFrames={300} name="Plugin">
        <Step3Plugin />
      </Series.Sequence>
      <Series.Sequence durationInFrames={270} name="Outro">
        <OutroScene
          closing={
            <>
              Build on top. <span style={{ color: ACCENT }}>Don't fork.</span>
            </>
          }
        />
      </Series.Sequence>
    </Series>
  </AbsoluteFill>
);

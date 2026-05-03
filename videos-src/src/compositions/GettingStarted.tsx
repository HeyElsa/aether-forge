import { AbsoluteFill, Series } from "remotion";
import {
  ACCENT,
  BG,
  CodeBlock,
  ContentScene,
  OutroScene,
  ShellOutput,
  SUCCESS,
  TitleScene,
} from "../shared";

const Step1Install = () => (
  <ContentScene kicker="Step 1" subtitle="Install">
    <CodeBlock
      filename="terminal"
      charsPerSecond={70}
      source={`pip install 'aether-forge[all] @ git+https://github.com/HeyElsa/aether-forge.git'`}
      fontSize={26}
    />
  </ContentScene>
);

const Step2Generate = () => (
  <ContentScene kicker="Step 2" subtitle="Generate an agent from an idea">
    <CodeBlock
      filename="terminal"
      charsPerSecond={75}
      source={`forge generate-fast \\
    --name "BTC Trend Buyer" \\
    --idea "buy BTC on confirmed momentum uptrends" \\
    --output ./my-agent`}
      fontSize={28}
    />
    <ShellOutput
      lines={[
        { text: "[planner] auto-detected: mode=ollama model=gemma4:latest", color: SUCCESS },
        { text: "[ok] Generated 5 artifacts + Dockerfile + Makefile + tests/", color: SUCCESS },
      ]}
    />
  </ContentScene>
);

const Step3DayOne = () => (
  <ContentScene kicker="Step 3" subtitle="Day-one: green tests, green eval — no LLM key needed">
    <ShellOutput
      lines={[
        { prompt: "$", text: "cd ./my-agent" },
        { prompt: "$", text: "make test" },
        { text: "tests/test_agent.py::test_artifacts_validate          PASSED  [ 50%]", color: SUCCESS },
        { text: "tests/test_agent.py::test_scenario_pack_meets_expectations PASSED  [100%]", color: SUCCESS },
        { text: "" },
        { prompt: "$", text: "make eval-pack" },
        { text: "Scenario pack: total=2 matched=2 pass=1 hold=1 fail=0", color: SUCCESS },
        { text: "" },
        { prompt: "$", text: "make doctor" },
        { text: "Healthy — 8/8 ok, 0 skipped, 0 failed", color: SUCCESS },
      ]}
      fontSize={24}
    />
  </ContentScene>
);

const Step4Run = () => (
  <ContentScene kicker="Step 4" subtitle="Run it in paper mode">
    <CodeBlock
      filename="terminal"
      charsPerSecond={80}
      source={`forge run ./my-agent --mode paper --auto-approve --interval 30`}
      fontSize={28}
    />
    <ShellOutput
      lines={[
        { text: "BTC Trend Buyer" },
        { text: "Environment: paper | Interval: 30s | Ctrl+C to stop" },
        { text: "" },
        { text: "[ok] Tick 1: complete (4 steps)", color: SUCCESS },
        { text: "[ok] Tick 2: complete (3 steps)", color: SUCCESS },
        { text: "[ok] Tick 3: complete (3 steps)", color: SUCCESS },
      ]}
    />
  </ContentScene>
);

export const GettingStarted: React.FC = () => (
  <AbsoluteFill style={{ background: BG }}>
    <Series>
      <Series.Sequence durationInFrames={180} name="Title">
        <TitleScene
          headline="Get Started"
          tagline="Idea to governed, testable agent in 90 seconds"
        />
      </Series.Sequence>
      <Series.Sequence durationInFrames={210} name="Install">
        <Step1Install />
      </Series.Sequence>
      <Series.Sequence durationInFrames={420} name="Generate">
        <Step2Generate />
      </Series.Sequence>
      <Series.Sequence durationInFrames={480} name="DayOne">
        <Step3DayOne />
      </Series.Sequence>
      <Series.Sequence durationInFrames={330} name="Run">
        <Step4Run />
      </Series.Sequence>
      <Series.Sequence durationInFrames={240} name="Outro">
        <OutroScene
          closing={
            <>
              Idea to running agent.{" "}
              <span style={{ color: ACCENT }}>&lt; 90 seconds.</span>
            </>
          }
        />
      </Series.Sequence>
    </Series>
  </AbsoluteFill>
);

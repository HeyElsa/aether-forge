import { AbsoluteFill, Series } from "remotion";
import { BG, CodeBlock, ContentScene, OutroScene, TitleScene } from "../shared";

// Three scenes mirroring the three usable layers of @aether-forge/sdk v0.1.0:
//   1. Install + generated types — what you get out of the box
//   2. Validators — ajv-backed Result objects + the throw-on-invalid helper
//   3. Cross-language parser — parsePlannerOutput conforming to the same spec
//      and shared fixtures as the Python reference at
//      docs/specs/planner-output.md.
//
// Matches the existing PythonSDK composition in length, kicker style, and
// scene cadence so the two end-to-end videos feel like a pair.

const Scene1InstallTypes = () => (
  <ContentScene
    kicker="Install"
    subtitle="Generated types for every Aether Forge schema"
  >
    <CodeBlock
      filename="src/agent.ts"
      charsPerSecond={80}
      source={`// npm install @aether-forge/sdk
import {
  AgentSpec,
  CapabilityManifest,
  PolicyBundle,
  MigrationContract,
  PlannerOutput,
  DelegatedSigner,
} from "@aether-forge/sdk";

// Single committed bundle. Same JSON schemas as the Python core.`}
    />
  </ContentScene>
);

const Scene2Validators = () => (
  <ContentScene
    kicker="Validate"
    subtitle="Ajv-backed Result types. Same contract as Python."
  >
    <CodeBlock
      filename="src/load.ts"
      charsPerSecond={75}
      source={`import {
  validateAgentSpec,
  validateArtifactBundle,
  assertValid,
} from "@aether-forge/sdk";

const result = validateAgentSpec(jsonFromDisk);
if (result.ok) {
  // result.value is narrowed to AgentSpec
} else {
  console.error(result.errors);
}

// Or throw-on-invalid:
const spec = assertValid(validateAgentSpec(jsonFromDisk));`}
    />
  </ContentScene>
);

const Scene3CrossLanguage = () => (
  <ContentScene
    kicker="Same parser as Python"
    subtitle="parsePlannerOutput conforms to docs/specs/planner-output.md"
  >
    <CodeBlock
      filename="src/plan.ts"
      charsPerSecond={70}
      source={`import { parsePlannerOutput, PlannerParseError } from "@aether-forge/sdk";

try {
  const plan = parsePlannerOutput(rawLlmResponse);
  // recovers fenced JSON, reasoning preambles, trailing prose,
  // balanced-brace scan with string-literal awareness.
} catch (error) {
  if (error instanceof PlannerParseError) {
    // fall back to a heuristic planner
  }
}

// 13 shared fixtures. Two reference implementations. One spec.`}
    />
  </ContentScene>
);

export const TypeScriptSDK: React.FC = () => (
  <AbsoluteFill style={{ background: BG }}>
    <Series>
      <Series.Sequence durationInFrames={180} name="Title">
        <TitleScene
          titleLines={["TYPESCRIPT", "SDK"]}
          tagline="Validators, types, and the cross-language planner-output parser — Aether Forge in your browser, Node, or edge runtime"
          // Use the canonical fontSize/letter-spacing pair (130 / 8) — the
          // same defaults the CLI and Python SDK titles use, so the weight-200
          // stroke renders crisply. TYPESCRIPT fits within the frame at this
          // size; the smaller titleFontSize=110 override used previously made
          // browser sub-pixel rounding thicken the weight-200 strokes.
        />
      </Series.Sequence>
      <Series.Sequence durationInFrames={330} name="InstallTypes">
        <Scene1InstallTypes />
      </Series.Sequence>
      <Series.Sequence durationInFrames={420} name="Validators">
        <Scene2Validators />
      </Series.Sequence>
      <Series.Sequence durationInFrames={420} name="CrossLanguage">
        <Scene3CrossLanguage />
      </Series.Sequence>
      <Series.Sequence durationInFrames={240} name="Outro">
        <OutroScene />
      </Series.Sequence>
    </Series>
  </AbsoluteFill>
);

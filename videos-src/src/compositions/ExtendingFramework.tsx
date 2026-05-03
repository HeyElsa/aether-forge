import {
  AbsoluteFill,
  Img,
  Series,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadJetBrainsMono } from "@remotion/google-fonts/JetBrainsMono";

const { fontFamily: interFamily } = loadInter("normal", {
  weights: ["400", "600", "700"],
  subsets: ["latin"],
});
const { fontFamily: monoFamily } = loadJetBrainsMono("normal", {
  weights: ["400", "500"],
  subsets: ["latin"],
});

// Aether Forge dark palette
const BG = "#0a0a0a";
const FG = "#f5f5f5";
const MUTED = "#9ca3af";
const ACCENT = "#ef4444"; // matches Elsa red
const KEYWORD = "#7dd3fc"; // light cyan for `from`, `import`, `class`, `def`
const STRING = "#86efac"; // light green for "strings"
const COMMENT = "#6b7280"; // gray for comments
const TYPENAME = "#fbbf24"; // amber for type names

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const fadeIn = (frame: number, fps: number, delay = 0, dur = 0.6) =>
  spring({
    frame: frame - delay,
    fps,
    durationInFrames: Math.round(dur * fps),
    config: { damping: 200 },
  });

const typewriter = (text: string, frame: number, fps: number, charsPerSecond = 60) => {
  const charsToShow = Math.floor((frame / fps) * charsPerSecond);
  return text.slice(0, Math.max(0, charsToShow));
};

// ---------------------------------------------------------------------------
// Tinted code line — colors keywords/strings/comments without a real lexer
// ---------------------------------------------------------------------------

const KEYWORDS = new Set([
  "from", "import", "class", "def", "return", "self", "True", "False",
  "None", "if", "in", "as", "with",
]);

const TypedLine: React.FC<{ text: string }> = ({ text }) => {
  // Split keeping delimiters so we can re-color tokens.
  const tokens = text.split(/(\s+|[(),:.\]\[]|"[^"]*")/g);
  return (
    <div style={{ whiteSpace: "pre" }}>
      {tokens.map((tok, i) => {
        if (!tok) return null;
        // Comment — entire run after a `#`
        if (tok.startsWith("#")) return <span key={i} style={{ color: COMMENT }}>{tok}</span>;
        if (tok.startsWith('"') && tok.endsWith('"')) return <span key={i} style={{ color: STRING }}>{tok}</span>;
        if (KEYWORDS.has(tok)) return <span key={i} style={{ color: KEYWORD, fontWeight: 500 }}>{tok}</span>;
        // Capitalized identifiers → type names (heuristic)
        if (/^[A-Z][A-Za-z0-9_]*$/.test(tok)) return <span key={i} style={{ color: TYPENAME }}>{tok}</span>;
        return <span key={i}>{tok}</span>;
      })}
    </div>
  );
};

const CodeBlock: React.FC<{
  source: string;
  charsPerSecond?: number;
  filename?: string;
}> = ({ source, charsPerSecond = 80, filename }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const visible = typewriter(source, frame, fps, charsPerSecond);
  const lines = visible.split("\n");
  return (
    <div
      style={{
        background: "#111111",
        border: "1px solid #1f2937",
        borderRadius: 14,
        padding: "32px 40px 36px",
        fontFamily: monoFamily,
        fontSize: 30,
        lineHeight: 1.55,
        color: FG,
        boxShadow: "0 18px 60px rgba(0,0,0,0.55)",
        minWidth: 900,
        maxWidth: 1500,
      }}
    >
      {filename && (
        <div
          style={{
            color: MUTED,
            fontSize: 20,
            marginBottom: 18,
            fontFamily: interFamily,
            letterSpacing: 0.3,
          }}
        >
          {filename}
        </div>
      )}
      {lines.map((line, i) => (
        <TypedLine key={i} text={line} />
      ))}
      {/* Blinking cursor while typing isn't done */}
      {visible.length < source.length && (
        <CursorBlink />
      )}
    </div>
  );
};

const CursorBlink: React.FC = () => {
  const frame = useCurrentFrame();
  const visible = Math.floor(frame / 15) % 2 === 0;
  return (
    <span style={{ opacity: visible ? 1 : 0, color: ACCENT }}>▌</span>
  );
};

// ---------------------------------------------------------------------------
// Scenes
// ---------------------------------------------------------------------------

const TitleScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t1 = fadeIn(frame, fps, 0, 0.7);
  const t2 = fadeIn(frame, fps, 0.4 * fps, 0.7);
  const accentBar = interpolate(frame, [0, fps * 0.6], [0, 220], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill
      style={{
        background: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 24,
      }}
    >
      <div style={{ height: 5, width: accentBar, background: ACCENT, borderRadius: 3 }} />
      <h1
        style={{
          color: FG,
          fontFamily: interFamily,
          fontWeight: 700,
          fontSize: 110,
          margin: 0,
          letterSpacing: -2,
          opacity: t1,
          transform: `translateY(${(1 - t1) * 20}px)`,
        }}
      >
        Extending Aether Forge
      </h1>
      <p
        style={{
          color: MUTED,
          fontFamily: interFamily,
          fontSize: 38,
          margin: 0,
          fontWeight: 400,
          opacity: t2,
          transform: `translateY(${(1 - t2) * 15}px)`,
        }}
      >
        Custom planners, data sources &amp; memory stores — without forking
      </p>
    </AbsoluteFill>
  );
};

const SceneCaption: React.FC<{ text: string; subtitle?: string }> = ({ text, subtitle }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const op = fadeIn(frame, fps, 0, 0.5);
  return (
    <div
      style={{
        color: FG,
        fontFamily: interFamily,
        opacity: op,
        transform: `translateY(${(1 - op) * 10}px)`,
      }}
    >
      <div
        style={{
          fontSize: 22,
          color: ACCENT,
          fontWeight: 600,
          letterSpacing: 3,
          textTransform: "uppercase",
          marginBottom: 14,
        }}
      >
        {text}
      </div>
      {subtitle && (
        <div style={{ fontSize: 44, fontWeight: 600, color: FG, lineHeight: 1.2 }}>
          {subtitle}
        </div>
      )}
    </div>
  );
};

const ProtocolsScene: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        background: BG,
        padding: "100px 120px",
        flexDirection: "column",
        gap: 50,
        justifyContent: "center",
      }}
    >
      <SceneCaption text="Step 1" subtitle="Import the extension Protocols" />
      <CodeBlock
        filename="my_extension.py"
        source={`from aether_forge import (
    Planner,
    ExecutionRouter,
    PlanningModel,
    MemoryStore,
    DataSource,
)`}
        charsPerSecond={50}
      />
    </AbsoluteFill>
  );
};

const DataSourceScene: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        background: BG,
        padding: "100px 120px",
        flexDirection: "column",
        gap: 50,
        justifyContent: "center",
      }}
    >
      <SceneCaption text="Step 2" subtitle="Subclass DataSource — 15 lines" />
      <CodeBlock
        filename="src/strategy/coinbase_source.py"
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
        charsPerSecond={95}
      />
    </AbsoluteFill>
  );
};

const PluginScene: React.FC = () => {
  return (
    <AbsoluteFill
      style={{
        background: BG,
        padding: "100px 120px",
        flexDirection: "column",
        gap: 50,
        justifyContent: "center",
      }}
    >
      <SceneCaption text="Step 3" subtitle="Publish via PyPI — no fork needed" />
      <CodeBlock
        filename="pyproject.toml"
        source={`[project.entry-points."aether_forge.data_sources"]
coinbase = "my_pkg:CoinbaseSpotSource"

[project.entry-points."aether_forge.planners"]
grok = "my_pkg:build_grok_planner"`}
        charsPerSecond={70}
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
    </AbsoluteFill>
  );
};

const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fade = fadeIn(frame, fps, 0, 0.6);
  const logoScale = spring({ frame: frame - 8, fps, config: { damping: 12, stiffness: 110 } });
  return (
    <AbsoluteFill
      style={{
        background: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 40,
      }}
    >
      <div
        style={{
          color: FG,
          fontFamily: interFamily,
          fontSize: 56,
          fontWeight: 600,
          opacity: fade,
        }}
      >
        Build on top.{" "}
        <span style={{ color: ACCENT }}>Don't fork.</span>
      </div>
      <div
        style={{
          opacity: fade,
          transform: `scale(${logoScale})`,
          display: "flex",
          alignItems: "center",
          gap: 16,
        }}
      >
        <span
          style={{
            color: MUTED,
            fontFamily: interFamily,
            fontSize: 28,
            fontWeight: 400,
          }}
        >
          by
        </span>
        <Img
          src={staticFile("elsa-logo.svg")}
          style={{ height: 56, filter: "brightness(0) invert(1)" }}
        />
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Composition
// ---------------------------------------------------------------------------

export const ExtendingFramework: React.FC = () => {
  return (
    <AbsoluteFill style={{ background: BG }}>
      <Series>
        <Series.Sequence durationInFrames={180} name="Title">
          <TitleScene />
        </Series.Sequence>
        <Series.Sequence durationInFrames={300} name="Protocols">
          <ProtocolsScene />
        </Series.Sequence>
        <Series.Sequence durationInFrames={450} name="DataSource">
          <DataSourceScene />
        </Series.Sequence>
        <Series.Sequence durationInFrames={300} name="Plugin">
          <PluginScene />
        </Series.Sequence>
        <Series.Sequence durationInFrames={270} name="Outro">
          <OutroScene />
        </Series.Sequence>
      </Series>
    </AbsoluteFill>
  );
};

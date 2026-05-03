/**
 * Shared scene primitives + style tokens for all Aether Forge videos.
 *
 * Compositions stay short: define a `<Series>` of scenes, each scene
 * composes the helpers below. New compositions can drop in alongside
 * existing ones in `src/Root.tsx`.
 */

import {
  AbsoluteFill,
  Img,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { loadFont as loadInter } from "@remotion/google-fonts/Inter";
import { loadFont as loadJetBrainsMono } from "@remotion/google-fonts/JetBrainsMono";

const { fontFamily: interFamilyLoaded } = loadInter("normal", {
  weights: ["400", "600", "700"],
  subsets: ["latin"],
});
const { fontFamily: monoFamilyLoaded } = loadJetBrainsMono("normal", {
  weights: ["400", "500"],
  subsets: ["latin"],
});

export const interFamily = interFamilyLoaded;
export const monoFamily = monoFamilyLoaded;

// ---------------------------------------------------------------------------
// Palette — shared across all compositions
// ---------------------------------------------------------------------------

export const BG = "#0a0a0a";
export const FG = "#f5f5f5";
export const MUTED = "#9ca3af";
export const ACCENT = "#ef4444"; // Elsa red
export const KEYWORD = "#7dd3fc";
export const STRING = "#86efac";
export const COMMENT = "#6b7280";
export const TYPENAME = "#fbbf24";
export const SUCCESS = "#86efac";

// ---------------------------------------------------------------------------
// Animation helpers
// ---------------------------------------------------------------------------

export const fadeIn = (frame: number, fps: number, delay = 0, dur = 0.6) =>
  spring({
    frame: frame - delay,
    fps,
    durationInFrames: Math.round(dur * fps),
    config: { damping: 200 },
  });

export const typewriter = (
  text: string,
  frame: number,
  fps: number,
  charsPerSecond = 80,
) => {
  const charsToShow = Math.floor((frame / fps) * charsPerSecond);
  return text.slice(0, Math.max(0, charsToShow));
};

// ---------------------------------------------------------------------------
// Code rendering — heuristic syntax tinting (no real lexer)
// ---------------------------------------------------------------------------

const KEYWORDS = new Set([
  "from", "import", "class", "def", "return", "self", "True", "False",
  "None", "if", "in", "as", "with", "for", "while", "yield", "lambda",
  "pass", "and", "or", "not", "is",
]);

export const TypedLine: React.FC<{ text: string }> = ({ text }) => {
  const tokens = text.split(/(\s+|[(),:.\]\[]|"[^"]*")/g);
  return (
    <div style={{ whiteSpace: "pre" }}>
      {tokens.map((tok, i) => {
        if (!tok) return null;
        if (tok.startsWith("#")) return <span key={i} style={{ color: COMMENT }}>{tok}</span>;
        if (tok.startsWith('"') && tok.endsWith('"')) return <span key={i} style={{ color: STRING }}>{tok}</span>;
        if (KEYWORDS.has(tok)) return <span key={i} style={{ color: KEYWORD, fontWeight: 500 }}>{tok}</span>;
        if (/^[A-Z][A-Za-z0-9_]*$/.test(tok)) return <span key={i} style={{ color: TYPENAME }}>{tok}</span>;
        return <span key={i}>{tok}</span>;
      })}
    </div>
  );
};

export const CursorBlink: React.FC = () => {
  const frame = useCurrentFrame();
  const visible = Math.floor(frame / 15) % 2 === 0;
  return <span style={{ opacity: visible ? 1 : 0, color: ACCENT }}>▌</span>;
};

export const CodeBlock: React.FC<{
  source: string;
  charsPerSecond?: number;
  filename?: string;
  language?: "python" | "toml" | "shell" | "json";
  fontSize?: number;
  maxWidth?: number;
}> = ({
  source,
  charsPerSecond = 80,
  filename,
  fontSize = 30,
  maxWidth = 1500,
}) => {
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
        fontSize,
        lineHeight: 1.55,
        color: FG,
        boxShadow: "0 18px 60px rgba(0,0,0,0.55)",
        minWidth: 900,
        maxWidth,
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
      {visible.length < source.length && <CursorBlink />}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Shell output block (no typewriter; appears all at once with fade)
// ---------------------------------------------------------------------------

export const ShellOutput: React.FC<{
  lines: { prompt?: string; text: string; color?: string }[];
  fontSize?: number;
}> = ({ lines, fontSize = 26 }) => {
  return (
    <div
      style={{
        fontFamily: monoFamily,
        fontSize,
        color: FG,
        lineHeight: 1.55,
        paddingLeft: 6,
      }}
    >
      {lines.map((l, i) => (
        <div key={i} style={{ whiteSpace: "pre", color: l.color || FG }}>
          {l.prompt && (
            <span style={{ color: STRING }}>{l.prompt} </span>
          )}
          {l.text}
        </div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Title scene — accent bar + headline + tagline
// ---------------------------------------------------------------------------

export const TitleScene: React.FC<{
  headline: string;
  tagline: string;
}> = ({ headline, tagline }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t1 = fadeIn(frame, fps, 0, 0.7);
  const t2 = fadeIn(frame, fps, 0.4 * fps, 0.7);
  const accentBar = interpolate(frame, [0, fps * 0.6], [0, 220], {
    extrapolateRight: "clamp",
  });
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
        {headline}
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
          maxWidth: 1500,
          textAlign: "center",
        }}
      >
        {tagline}
      </p>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Scene caption — small accent label + bigger title
// ---------------------------------------------------------------------------

export const SceneCaption: React.FC<{ kicker?: string; subtitle?: string }> = ({
  kicker,
  subtitle,
}) => {
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
      {kicker && (
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
          {kicker}
        </div>
      )}
      {subtitle && (
        <div style={{ fontSize: 44, fontWeight: 600, color: FG, lineHeight: 1.2 }}>
          {subtitle}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Generic content scene wrapper — caption + content
// ---------------------------------------------------------------------------

export const ContentScene: React.FC<{
  kicker?: string;
  subtitle?: string;
  children: React.ReactNode;
}> = ({ kicker, subtitle, children }) => {
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
      <SceneCaption kicker={kicker} subtitle={subtitle} />
      {children}
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Outro — closing line + "by Elsa logo"
// ---------------------------------------------------------------------------

export const OutroScene: React.FC<{
  closing: React.ReactNode;
}> = ({ closing }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const fade = fadeIn(frame, fps, 0, 0.6);
  const logoScale = spring({
    frame: frame - 8,
    fps,
    config: { damping: 12, stiffness: 110 },
  });
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
          textAlign: "center",
          maxWidth: 1500,
        }}
      >
        {closing}
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

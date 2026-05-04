/**
 * Shared scene primitives + style tokens for all Aether Forge videos.
 *
 * Style is canon-matched against the existing 27 videos in
 * docs-site/public/videos/ (e.g. 21-cli, 03-agent-generation, 00-hero):
 *
 *   - Pure black background. White / gray monochrome typography.
 *   - Title scene: knot logo at top + thin uppercase 2-line title with wide
 *     letter-spacing + small gray tagline. NO red accent bars.
 *   - Content scenes: small gray uppercase kicker (wide letter-spacing) +
 *     bold headline + content body.
 *   - Outro: knot + AETHER / FORGE wordmark + github URL pill +
 *     "Spec first. Real money. Production grade." + tiny "by [elsa-mark]".
 *     Identical across every video.
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
  // 200 / 300 = thin/light for the wordmark; 600/700 for bold headlines.
  weights: ["200", "300", "400", "600", "700"],
  subsets: ["latin"],
});
const { fontFamily: monoFamilyLoaded } = loadJetBrainsMono("normal", {
  weights: ["400", "500"],
  subsets: ["latin"],
});

export const interFamily = interFamilyLoaded;
export const monoFamily = monoFamilyLoaded;

// ---------------------------------------------------------------------------
// Palette — pure monochrome to match existing videos
// ---------------------------------------------------------------------------

export const BG = "#000000";
export const FG = "#f5f5f7"; // matches the white in logo.svg
export const MUTED = "#9ca3af"; // gray for taglines + kickers
export const COMMENT = "#6b7280";
export const KEYWORD = "#7dd3fc";
export const STRING = "#86efac";
export const TYPENAME = "#fbbf24";
export const SUCCESS = "#86efac";

// Reserved (not used in canonical scenes; kept so old props don't break).
export const ACCENT = MUTED;

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
// Code rendering
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
  return <span style={{ opacity: visible ? 1 : 0, color: FG }}>▌</span>;
};

export const CodeBlock: React.FC<{
  source: string;
  charsPerSecond?: number;
  filename?: string;
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
        background: "#0a0a0a",
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
// Shell output
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
          {l.prompt && <span style={{ color: STRING }}>{l.prompt} </span>}
          {l.text}
        </div>
      ))}
    </div>
  );
};

// ---------------------------------------------------------------------------
// Wordmark renderer — "AETHER FORGE", "GET STARTED", "PYTHON SDK"
// ---------------------------------------------------------------------------
// Two-line uppercase, very wide letter-spacing, thin (200) weight.
// Matches the existing 21-cli "THE FORGE / CLI" and 03-agent-generation
// "AGENT / GENERATION" titles exactly.
// ---------------------------------------------------------------------------

export const Wordmark: React.FC<{
  lines: string[];
  fontSize?: number;
  letterSpacing?: number;
  color?: string;
}> = ({ lines, fontSize = 130, letterSpacing = 8, color = FG }) => (
  <div
    style={{
      fontFamily: interFamily,
      fontWeight: 200,
      fontSize,
      letterSpacing,
      color,
      textTransform: "uppercase",
      lineHeight: 1.05,
      textAlign: "center",
    }}
  >
    {lines.map((l, i) => (
      <div key={i}>{l}</div>
    ))}
  </div>
);

// ---------------------------------------------------------------------------
// Title scene — knot logo + 2-line wordmark + tagline
// ---------------------------------------------------------------------------

export const TitleScene: React.FC<{
  /** 2-line uppercase title, e.g. ["GET", "STARTED"]. */
  titleLines: string[];
  /** Small gray subtitle below the wordmark. */
  tagline: string;
  /** Wordmark font size; slim down for longer titles. */
  titleFontSize?: number;
  /** Letter-spacing for the wordmark. */
  letterSpacing?: number;
}> = ({ titleLines, tagline, titleFontSize = 130, letterSpacing = 8 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const logoOp = fadeIn(frame, fps, 0, 0.6);
  const titleOp = fadeIn(frame, fps, 0.4 * fps, 0.6);
  const taglineOp = fadeIn(frame, fps, 0.8 * fps, 0.6);
  return (
    <AbsoluteFill
      style={{
        background: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 60,
      }}
    >
      <div
        style={{
          opacity: logoOp,
          transform: `translateY(${(1 - logoOp) * 12}px)`,
        }}
      >
        <Img
          src={staticFile("forge-logo.svg")}
          style={{ width: 140, height: 140 }}
        />
      </div>
      <div
        style={{
          opacity: titleOp,
          transform: `translateY(${(1 - titleOp) * 12}px)`,
        }}
      >
        <Wordmark
          lines={titleLines}
          fontSize={titleFontSize}
          letterSpacing={letterSpacing}
        />
      </div>
      <div
        style={{
          opacity: taglineOp,
          transform: `translateY(${(1 - taglineOp) * 8}px)`,
          color: MUTED,
          fontFamily: interFamily,
          fontSize: 32,
          fontWeight: 400,
          textAlign: "center",
          maxWidth: 1500,
        }}
      >
        {tagline}
      </div>
    </AbsoluteFill>
  );
};

// ---------------------------------------------------------------------------
// Scene caption — tiny gray uppercase kicker + bold headline
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
            color: MUTED,
            fontWeight: 600,
            letterSpacing: 4,
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
// Generic content scene — caption + content body
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
// Outro — canonical "AETHER FORGE" end card (identical across all videos)
// ---------------------------------------------------------------------------

export const OutroScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const logoOp = fadeIn(frame, fps, 0, 0.6);
  const wordmarkOp = fadeIn(frame, fps, 0.3 * fps, 0.6);
  const pillOp = fadeIn(frame, fps, 0.7 * fps, 0.6);
  const taglineOp = fadeIn(frame, fps, 1.0 * fps, 0.5);
  const byOp = fadeIn(frame, fps, 1.3 * fps, 0.5);
  return (
    <AbsoluteFill
      style={{
        background: BG,
        justifyContent: "center",
        alignItems: "center",
        flexDirection: "column",
        gap: 32,
      }}
    >
      <div style={{ opacity: logoOp }}>
        <Img
          src={staticFile("forge-logo.svg")}
          style={{ width: 110, height: 110 }}
        />
      </div>
      <div style={{ opacity: wordmarkOp, marginTop: 8 }}>
        <Wordmark lines={["AETHER", "FORGE"]} fontSize={108} letterSpacing={6} />
      </div>
      <div
        style={{
          opacity: pillOp,
          marginTop: 20,
          padding: "16px 32px",
          background: "#0a0a0a",
          border: "1px solid #1f2937",
          borderRadius: 14,
          fontFamily: monoFamily,
          fontSize: 30,
          color: FG,
          letterSpacing: 0.5,
        }}
      >
        github.com/HeyElsa/aether-forge
      </div>
      <div
        style={{
          opacity: taglineOp,
          color: MUTED,
          fontFamily: interFamily,
          fontSize: 26,
          fontWeight: 400,
          marginTop: 10,
        }}
      >
        Spec first. Real money. Production grade.
      </div>
      <div
        style={{
          opacity: byOp,
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginTop: 12,
        }}
      >
        <span
          style={{
            color: MUTED,
            fontFamily: interFamily,
            fontSize: 20,
          }}
        >
          by
        </span>
        <Img
          src={staticFile("elsa-mark.svg")}
          style={{ height: 28, width: "auto" }}
        />
      </div>
    </AbsoluteFill>
  );
};

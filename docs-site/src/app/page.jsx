import Link from "next/link";

function LogoBurst() {
  // Particle bursts emanating from the logo center.
  // Each "ring" is a group of N dots that travel outward at a unique angle,
  // fading in then out. Multiple rings stagger so the burst is continuous.
  const RINGS = 6;
  const DOTS_PER_RING = 14;
  const CYCLE = 5.5; // seconds per ring cycle
  const STAGGER = CYCLE / RINGS;

  // Center of the logo (in SVG viewBox coords)
  const cx = 200;
  const cy = 200;

  // Build dots for each ring
  const rings = Array.from({ length: RINGS }, (_, ringIdx) => {
    const delay = ringIdx * STAGGER;
    const distance = 110 + ringIdx * 18; // each ring travels a bit further
    const dots = Array.from({ length: DOTS_PER_RING }, (_, i) => {
      // Distribute angles evenly around the circle, with a per-ring rotation
      // so dots in different rings don't all line up
      const angle = (i / DOTS_PER_RING) * Math.PI * 2 + ringIdx * 0.42;
      const tx = Math.cos(angle) * distance;
      const ty = Math.sin(angle) * distance;
      // Slight per-dot variance for organic feel
      const sizeJitter = 0.85 + ((i * 7) % 5) * 0.06;
      return { tx, ty, sizeJitter, idx: i };
    });
    return { ringIdx, delay, dots };
  });

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 400 400"
      style={{
        position: "absolute",
        top: "50%",
        left: "50%",
        transform: "translate(-50%, -50%)",
        width: "min(80vw, 720px)",
        height: "min(80vw, 720px)",
        zIndex: 0,
        pointerEvents: "none",
      }}
    >
      <defs>
        <radialGradient id="dotFade" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="currentColor" stopOpacity="1" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </radialGradient>
      </defs>
      <g style={{ color: "var(--af-burst, #6a6a72)" }}>
        {rings.map(({ ringIdx, delay, dots }) =>
          dots.map(({ tx, ty, sizeJitter, idx }) => {
            const r = 1.8 * sizeJitter;
            const id = `r${ringIdx}-d${idx}`;
            return (
              <circle key={id} cx={cx} cy={cy} r={r} fill="currentColor" opacity="0">
                {/* Travel outward */}
                <animate
                  attributeName="cx"
                  values={`${cx};${cx + tx}`}
                  dur={`${CYCLE}s`}
                  begin={`${delay}s`}
                  repeatCount="indefinite"
                  calcMode="spline"
                  keySplines="0.16 1 0.3 1"
                />
                <animate
                  attributeName="cy"
                  values={`${cy};${cy + ty}`}
                  dur={`${CYCLE}s`}
                  begin={`${delay}s`}
                  repeatCount="indefinite"
                  calcMode="spline"
                  keySplines="0.16 1 0.3 1"
                />
                {/* Fade in fast, fade out slow */}
                <animate
                  attributeName="opacity"
                  values="0;0.55;0.4;0"
                  keyTimes="0;0.15;0.6;1"
                  dur={`${CYCLE}s`}
                  begin={`${delay}s`}
                  repeatCount="indefinite"
                />
                {/* Dot shrinks slightly as it travels */}
                <animate
                  attributeName="r"
                  values={`${r * 1.4};${r}`}
                  dur={`${CYCLE}s`}
                  begin={`${delay}s`}
                  repeatCount="indefinite"
                  calcMode="spline"
                  keySplines="0.4 0 0.6 1"
                />
              </circle>
            );
          }),
        )}
      </g>
      <style>{`
        @media (prefers-color-scheme: dark) {
          svg[aria-hidden] g { color: #4a4a52 !important; }
        }
        @media (prefers-reduced-motion: reduce) {
          svg[aria-hidden] animate { display: none; }
        }
      `}</style>
    </svg>
  );
}

export default function HomePage() {
  return (
    <div
      style={{
        position: "relative",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "80vh",
        padding: "2rem",
        textAlign: "center",
        overflow: "hidden",
      }}
    >
      <LogoBurst />
      <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", alignItems: "center", width: "100%" }}>
      <picture>
        <source srcSet="/logo.svg" media="(prefers-color-scheme: dark)" />
        <img src="/logo-dark.svg" alt="Aether Forge" width={120} height={120} style={{position: "relative", zIndex: 2}} />
      </picture>
      <h1
        style={{
          fontSize: "3rem",
          fontWeight: 800,
          letterSpacing: "0.06em",
          marginTop: "1.5rem",
        }}
      >
        AETHER FORGE
      </h1>
      <a
        href="https://heyelsa.ai"
        target="_blank"
        rel="noreferrer"
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
          marginTop: "0.75rem",
          fontSize: "0.85rem",
          opacity: 1,
          textDecoration: "none",
          transition: "opacity 0.15s",
        }}
      >
        by
        <picture>
          <source srcSet="/elsa-logo.svg" media="(prefers-color-scheme: dark)" />
          <img src="/elsa-logo-dark.svg" alt="HeyElsa" width={48} height={20} />
        </picture>
      </a>
      <p
        style={{
          fontSize: "1.25rem",
          maxWidth: 600,
          marginTop: "1rem",
          opacity: 0.7,
        }}
      >
        Spec-first agent builder framework. Idea to governed, testable,
        production-capable agent in one CLI.
      </p>
      <div
        style={{
          marginTop: "2.5rem",
          width: "100%",
          maxWidth: 720,
          aspectRatio: "16 / 9",
          background: "#0a0a0a",
          borderRadius: 16,
          overflow: "hidden",
          border: "1px solid #222",
        }}
      >
        <video
          src="/videos/00-hero.mp4"
          preload="metadata"
          autoPlay
          muted
          loop
          playsInline
          style={{ width: "100%", height: "100%", display: "block", objectFit: "cover" }}
        />
      </div>
      <div style={{ display: "flex", gap: "1rem", marginTop: "2rem" }}>
        <Link
          href="/docs"
          style={{
            padding: "0.75rem 2rem",
            background: "#0a84ff",
            color: "#fff",
            borderRadius: 8,
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          Get Started
        </Link>
        <a
          href="https://github.com/HeyElsa/aether-forge"
          target="_blank"
          rel="noreferrer"
          style={{
            padding: "0.75rem 2rem",
            border: "1px solid #333",
            borderRadius: 8,
            fontWeight: 600,
            textDecoration: "none",
          }}
        >
          GitHub
        </a>
      </div>
      <div
        style={{
          marginTop: "3rem",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: "1.5rem",
          maxWidth: 800,
          width: "100%",
        }}
      >
        {[
          ["LLM-Driven", "Auto-detect Ollama, Claude, GPT, Gemini, OpenRouter"],
          ["Real Wallets", "OWS across 9 chains with encrypted backups"],
          ["A2A Protocol", "Agent-to-agent tasks via Google's open standard"],
          ["x402 Payments", "Agents send and receive USDC on Base"],
          ["MCP Tools", "Any Model Context Protocol server"],
          ["On-Chain ID", "ERC-8004 registry on Base mainnet"],
        ].map(([title, desc]) => (
          <div
            key={title}
            style={{
              padding: "1.25rem",
              border: "1px solid #222",
              borderRadius: 12,
              textAlign: "left",
            }}
          >
            <strong>{title}</strong>
            <p style={{ fontSize: "0.85rem", opacity: 0.6, marginTop: 4 }}>
              {desc}
            </p>
          </div>
        ))}
      </div>
      </div>
    </div>
  );
}

import Link from "next/link";

function WaveBackground() {
  // Generate 14 wave lines. Each line uses SMIL <animate> on its `d`
  // attribute to actually morph the wave shape over time (peaks shift
  // along the curve), producing organic flow rather than slide-translate.
  const lines = Array.from({ length: 14 }, (_, i) => {
    const baseY = 80 + i * 50;
    const amp = 12 + (i % 4) * 4;     // small amplitudes — 12 to 24px
    const dur = 22 + (i % 6) * 4;     // long durations — 22 to 42s
    const phase = (i * 1.7) % 6.28;   // distribute phase
    return { baseY, amp, dur, phase, idx: i };
  });

  // Build a list of d-frames per line by rotating the peak/trough
  // positions through the wave, creating a flowing-water effect.
  const buildPath = (baseY, amp, t) => {
    // 5 control points across the width, each oscillating with t
    const w = 1440;
    const segs = 6;
    const pts = [];
    for (let s = 0; s <= segs; s++) {
      const x = (s * w) / segs;
      const y = baseY + amp * Math.sin(t + (s * Math.PI) / 2);
      pts.push([x, y]);
    }
    // smooth quadratic bezier through control points
    let d = `M${pts[0][0]} ${pts[0][1].toFixed(2)}`;
    for (let s = 1; s < pts.length; s++) {
      const [x, y] = pts[s];
      const [px, py] = pts[s - 1];
      const cx = (px + x) / 2;
      const cy = (py + y) / 2;
      d += ` Q${px.toFixed(2)} ${py.toFixed(2)} ${cx.toFixed(2)} ${cy.toFixed(2)}`;
    }
    d += ` T${pts[segs][0]} ${pts[segs][1].toFixed(2)}`;
    return d;
  };

  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 1440 800"
      preserveAspectRatio="xMidYMid slice"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        zIndex: 0,
        pointerEvents: "none",
      }}
    >
      <defs>
        <linearGradient id="waveGrad" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stopColor="currentColor" stopOpacity="0" />
          <stop offset="50%" stopColor="currentColor" stopOpacity="1" />
          <stop offset="100%" stopColor="currentColor" stopOpacity="0" />
        </linearGradient>
      </defs>
      <g
        stroke="url(#waveGrad)"
        fill="none"
        strokeWidth="0.6"
        strokeLinecap="round"
        style={{ color: "var(--af-wave, #6a6a72)", opacity: 0.18 }}
      >
        {lines.map(({ baseY, amp, dur, phase, idx }) => {
          // 6 keyframes spread evenly across one full sine cycle
          const frames = Array.from({ length: 7 }, (_, k) =>
            buildPath(baseY, amp, phase + (k * 2 * Math.PI) / 6),
          );
          return (
            <path key={idx} d={frames[0]}>
              <animate
                attributeName="d"
                values={frames.join(";")}
                dur={`${dur}s`}
                repeatCount="indefinite"
                calcMode="spline"
                keySplines={frames.slice(1).map(() => "0.42 0 0.58 1").join(";")}
              />
            </path>
          );
        })}
      </g>
      <style>{`
        @media (prefers-color-scheme: dark) { svg[aria-hidden] g { color: #3a3a42 !important; opacity: 0.22 !important; } }
        @media (prefers-reduced-motion: reduce) { svg[aria-hidden] animate { display: none; } }
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
      <WaveBackground />
      <div style={{ position: "relative", zIndex: 1, display: "flex", flexDirection: "column", alignItems: "center", width: "100%" }}>
      <picture>
        <source srcSet="/logo.svg" media="(prefers-color-scheme: dark)" />
        <img src="/logo-dark.svg" alt="Aether Forge" width={120} height={120} />
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

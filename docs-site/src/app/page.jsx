import Link from "next/link";

export default function HomePage() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "80vh",
        padding: "2rem",
        textAlign: "center",
      }}
    >
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
  );
}

export default function ComingSoonPage() {
  return (
    <main className="soon">
      <div className="soon-glow" aria-hidden="true" />

      <div className="soon-body">
        <picture>
          <source srcSet="/logo.svg" media="(prefers-color-scheme: dark)" />
          <img
            className="soon-logo"
            src="/logo-dark.svg"
            alt=""
            width={88}
            height={88}
          />
        </picture>

        <p className="soon-wordmark">Aether Forge</p>

        <h1 className="soon-title">
          <span className="soon-v2">V2</span> is coming soon
        </h1>

        <p className="soon-lede">
          The next version of Aether Forge is on the way. This site will be
          back when it&rsquo;s ready.
        </p>

        <p className="soon-status">
          <span className="soon-dot" aria-hidden="true" />
          In the works
        </p>

        <a
          className="soon-link"
          href="https://github.com/HeyElsa/aether-forge"
          target="_blank"
          rel="noreferrer"
        >
          Follow along on GitHub
          <span aria-hidden="true"> &rarr;</span>
        </a>
      </div>

      <footer className="soon-footer">
        <span>{new Date().getFullYear()} Aether Forge</span>
        <span className="soon-sep" aria-hidden="true">
          |
        </span>
        <a
          className="soon-by"
          href="https://heyelsa.ai"
          target="_blank"
          rel="noreferrer"
        >
          by
          <picture>
            <source
              srcSet="/elsa-logo.svg"
              media="(prefers-color-scheme: dark)"
            />
            <img
              src="/elsa-logo-dark.svg"
              alt="HeyElsa"
              width={56}
              height={24}
            />
          </picture>
        </a>
      </footer>
    </main>
  );
}

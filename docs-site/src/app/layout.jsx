import { Footer, Layout, Navbar } from "nextra-theme-docs";
import { Head } from "nextra/components";
import { getPageMap } from "nextra/page-map";
import "nextra-theme-docs/style.css";

export const metadata = {
  title: {
    default: "Aether Forge",
    template: "%s | Aether Forge",
  },
  description:
    "Spec-first agent builder framework. Idea to governed, testable, production-capable agent in one CLI.",
};

export default async function RootLayout({ children }) {
  const pageMap = await getPageMap();

  return (
    <html lang="en" dir="ltr" suppressHydrationWarning>
      <Head faviconGlyph="A" />
      <body>
        <Layout
          navbar={
            <Navbar
              logo={
                <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <picture>
                    <source
                      srcSet="/logo.svg"
                      media="(prefers-color-scheme: dark)"
                    />
                    <img
                      src="/logo-dark.svg"
                      alt="Aether Forge"
                      width={28}
                      height={28}
                    />
                  </picture>
                  <b style={{ fontSize: 18, letterSpacing: "0.04em" }}>
                    AETHER FORGE
                  </b>
                </span>
              }
              projectLink="https://github.com/HeyElsa/aether-forge"
            />
          }
          footer={
            <Footer>
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 8,
                  flexWrap: "wrap",
                }}
              >
                <span>
                  {new Date().getFullYear()} Aether Forge
                </span>
                <span style={{ opacity: 0.4 }}>|</span>
                <a
                  href="https://heyelsa.ai"
                  target="_blank"
                  rel="noreferrer"
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    textDecoration: "none",
                    opacity: 1,
                  }}
                >
                  <span style={{ fontSize: 13 }}>by</span>
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
              </div>
            </Footer>
          }
          editLink="Edit this page on GitHub"
          docsRepositoryBase="https://github.com/HeyElsa/aether-forge/tree/main/docs-site"
          sidebar={{ defaultMenuCollapseLevel: 1 }}
          pageMap={pageMap}
        >
          {children}
        </Layout>
      </body>
    </html>
  );
}

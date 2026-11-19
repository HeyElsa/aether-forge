import nextra from "nextra";

const withNextra = nextra({
  defaultShowCopyCode: true,
  search: { codeblocks: false },
  contentDirBasePath: "/docs",
});

// Section folders have no index page; send their roots to the first page in
// each section's _meta.js so /docs/<section> does not 404.
const SECTION_LANDING = {
  features: "llm-planner",
  guides: "choose-your-path",
  reference: "install-matrix",
  examples: "delta-neutral-btc",
  help: "troubleshooting",
};

export default withNextra({
  reactStrictMode: true,
  async redirects() {
    return Object.entries(SECTION_LANDING).map(([section, page]) => ({
      source: `/docs/${section}`,
      destination: `/docs/${section}/${page}`,
      permanent: false,
    }));
  },
});

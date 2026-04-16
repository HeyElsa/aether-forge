import nextra from "nextra";

const withNextra = nextra({
  defaultShowCopyCode: true,
  search: { codeblocks: false },
  contentDirBasePath: "/docs",
});

export default withNextra({
  reactStrictMode: true,
});

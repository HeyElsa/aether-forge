import nextra from "nextra";

const withNextra = nextra({
  defaultShowCopyCode: true,
  search: { codeblocks: false },
  contentDirBasePath: "/docs",
});

export default withNextra({
  reactStrictMode: true,
  // The site is a V2 "coming soon" page for now. Send the old docs and media
  // URLs to it with temporary redirects so they can come back at the same paths.
  async redirects() {
    return ["/docs", "/docs/:path*", "/videos/:path*", "/video-posters/:path*"].map(
      (source) => ({ source, destination: "/", permanent: false })
    );
  },
});

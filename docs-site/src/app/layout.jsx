import "./globals.css";

export const metadata = {
  metadataBase: new URL("https://forge.heyelsa.ai"),
  title: "Aether Forge V2 — Coming soon",
  description:
    "Aether Forge V2 is on the way. The next version of the spec-first agent builder framework is being built now.",
  openGraph: {
    title: "Aether Forge V2 — Coming soon",
    description: "The next version of Aether Forge is being built now.",
    url: "/",
    siteName: "Aether Forge",
    type: "website",
  },
};

export const viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fafafa" },
    { media: "(prefers-color-scheme: dark)", color: "#08090c" },
  ],
};

export default function RootLayout({ children }) {
  return (
    <html lang="en" dir="ltr">
      <body>{children}</body>
    </html>
  );
}

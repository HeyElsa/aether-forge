import fs from "node:fs";
import path from "node:path";

const SITE_URL = "https://forge.heyelsa.ai";
const CONTENT_DIR = path.join(process.cwd(), "src/content");

function docRoutes(dir, prefix = "") {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    if (entry.isDirectory()) {
      return docRoutes(path.join(dir, entry.name), `${prefix}/${entry.name}`);
    }
    if (!entry.name.endsWith(".mdx")) return [];
    const name = entry.name.slice(0, -".mdx".length);
    return [name === "index" ? prefix : `${prefix}/${name}`];
  });
}

export default function sitemap() {
  const routes = ["", ...docRoutes(CONTENT_DIR).map((route) => `/docs${route}`)];
  return routes.map((route) => ({ url: `${SITE_URL}${route}` }));
}

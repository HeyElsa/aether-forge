const fs = require("node:fs");
const path = require("node:path");
const { normalizeRouteRegex } = require("next/dist/lib/load-custom-routes");
const { getNamedRouteRegex } = require("next/dist/shared/lib/router/utils/route-regex");
const { isDynamicRoute } = require("next/dist/shared/lib/router/utils");

const distDir = path.join(process.cwd(), ".next");
const routesManifestPath = path.join(distDir, "routes-manifest.json");
const appPathRoutesManifestPath = path.join(distDir, "app-path-routes-manifest.json");

function readJson(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function pageToRoute(page) {
  const routeRegex = getNamedRouteRegex(page, { prefixRouteKeys: true });
  return {
    page,
    regex: normalizeRouteRegex(routeRegex.re.source),
    routeKeys: routeRegex.routeKeys,
    namedRegex: routeRegex.namedRegex,
  };
}

function appPageToRoute(appPage) {
  if (!appPage.endsWith("/page")) {
    return null;
  }
  const route = appPage.slice(0, -"/page".length) || "/";
  if (route === "/_not-found") {
    return null;
  }
  return route;
}

const manifest = readJson(routesManifestPath, null);
if (!manifest) {
  throw new Error(`Missing ${routesManifestPath}; run next build before patching routes manifest.`);
}

const appPathRoutes = readJson(appPathRoutesManifestPath, {});
const appRoutes = Object.keys(appPathRoutes).map(appPageToRoute).filter(Boolean);

// Next 15.5 can emit an app-only routes manifest without these arrays. `next start`
// still expects them, so reconstruct the stable route records from app-paths.
manifest.pages404 ??= true;
manifest.dynamicRoutes ??= appRoutes.filter(isDynamicRoute).map(pageToRoute);
manifest.staticRoutes ??= appRoutes.filter((route) => !isDynamicRoute(route)).map(pageToRoute);
manifest.dataRoutes ??= [];
manifest.rewrites ??= { beforeFiles: [], afterFiles: [], fallback: [] };

if (Array.isArray(manifest.rewrites)) {
  manifest.rewrites = {
    beforeFiles: [],
    afterFiles: manifest.rewrites,
    fallback: [],
  };
}

manifest.rsc ??= {
  header: "RSC",
  varyHeader: "RSC, Next-Router-State-Tree, Next-Router-Prefetch, Next-Router-Segment-Prefetch",
  prefetchHeader: "Next-Router-Prefetch",
  didPostponeHeader: "x-nextjs-postponed",
  contentTypeHeader: "text/x-component",
  suffix: ".rsc",
  prefetchSuffix: ".prefetch.rsc",
  prefetchSegmentHeader: "Next-Router-Segment-Prefetch",
  prefetchSegmentSuffix: ".segment.rsc",
  prefetchSegmentDirSuffix: ".segments",
};

manifest.rewriteHeaders ??= {
  pathHeader: "x-nextjs-rewritten-path",
  queryHeader: "x-nextjs-rewritten-query",
};

fs.writeFileSync(routesManifestPath, JSON.stringify(manifest));

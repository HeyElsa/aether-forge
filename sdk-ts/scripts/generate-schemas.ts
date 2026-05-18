/**
 * Generate TypeScript types from every JSON schema under
 * ../src/aether_forge/schemas/. Emits a SINGLE bundle file at
 * src/schemas/generated/index.ts that exports one named type per schema
 * (e.g. AgentSpec, CapabilityManifest, MigrationContract). Single-file
 * output sidesteps the cross-schema $ref duplicate-export problem that
 * file-per-schema generation hits.
 *
 * The bundle is committed so npm consumers see types without needing this
 * script to run. CI verifies the committed output matches a fresh
 * regeneration via `git diff --exit-code`.
 *
 * Resolution strategy: every cross-schema $ref (URL pointing to
 * schemas.aether-forge.dev) is rewritten to an in-bundle JSON Pointer
 * `#/definitions/<TargetType>`. The bundle has a top-level `definitions`
 * object holding every schema by its PascalCase name, and a top-level
 * `oneOf` exists only to give jstt a starting node. Each named type is
 * exported individually at the top of the file.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..", "..");
const SCHEMAS_DIR = path.join(REPO_ROOT, "src", "aether_forge", "schemas");
const OUT_DIR = path.resolve(__dirname, "..", "src", "schemas", "generated");

interface SchemaFile {
  abs: string;
  rel: string;
  name: string;        // kebab-case file basename, e.g. "agent-spec"
  title: string;       // PascalCase type name, e.g. "AgentSpec"
  group: string;
  id: string;
}

function pascalCase(name: string): string {
  return name
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

async function discoverSchemas(): Promise<SchemaFile[]> {
  const results: SchemaFile[] = [];
  for (const group of ["artifacts", "common", "runtime"] as const) {
    const dir = path.join(SCHEMAS_DIR, group);
    const entries = await fs.readdir(dir);
    for (const entry of entries) {
      if (!entry.endsWith(".schema.json")) continue;
      const abs = path.join(dir, entry);
      const rel = path.join(group, entry);
      const data = JSON.parse(await fs.readFile(abs, "utf8"));
      if (typeof data.$id !== "string") {
        throw new Error(`schema ${rel} is missing required $id`);
      }
      const name = entry.replace(/\.schema\.json$/, "");
      results.push({
        abs,
        rel,
        name,
        title: pascalCase(name),
        group,
        id: data.$id,
      });
    }
  }
  results.sort((a, b) => a.rel.localeCompare(b.rel));
  return results;
}

/**
 * Rewrite cross-schema $refs into in-bundle JSON Pointers, AND rewrite
 * internal `#/$defs/*` and `#/definitions/*` refs to include the parent
 * type prefix (since the schema is being placed under
 * `#/definitions/<ParentTitle>`).
 */
function rewriteToInternalRefs(
  node: unknown,
  idToTitle: Map<string, string>,
  ownTitle: string,
): unknown {
  if (Array.isArray(node)) {
    return node.map((n) => rewriteToInternalRefs(n, idToTitle, ownTitle));
  }
  if (node !== null && typeof node === "object") {
    const obj = node as Record<string, unknown>;
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj)) {
      if (k === "$ref" && typeof v === "string") {
        // External: rewrite URL → in-bundle pointer to the sibling type.
        if (v.startsWith("https://schemas.aether-forge.dev/")) {
          const [base, fragment] = v.split("#");
          if (base !== undefined) {
            const title = idToTitle.get(base);
            if (title !== undefined) {
              out[k] = fragment
                ? `#/definitions/${title}${fragment}`
                : `#/definitions/${title}`;
              continue;
            }
          }
        }
        // Internal: rewrite `#/$defs/X` (and `#/definitions/X`) →
        // `#/definitions/<ownTitle>/$defs/X` so the pointer still
        // resolves once the schema is nested under the bundle root.
        if (v.startsWith("#/$defs/") || v.startsWith("#/definitions/")) {
          out[k] = `#/definitions/${ownTitle}${v.slice(1)}`;
          continue;
        }
      }
      // Strip $id and $schema inside nested schemas — only the bundle
      // root keeps them. Otherwise jstt emits a banner per nested $id.
      if (k === "$id" || k === "$schema") continue;
      out[k] = rewriteToInternalRefs(v, idToTitle, ownTitle);
    }
    return out;
  }
  return node;
}

async function main(): Promise<void> {
  await fs.mkdir(OUT_DIR, { recursive: true });
  const schemas = await discoverSchemas();
  const idToTitle = new Map<string, string>();
  for (const s of schemas) idToTitle.set(s.id, s.title);

  // Build the bundle: top-level definitions keyed by PascalCase title.
  const definitions: Record<string, unknown> = {};
  for (const s of schemas) {
    const raw = JSON.parse(await fs.readFile(s.abs, "utf8"));
    definitions[s.title] = rewriteToInternalRefs(raw, idToTitle, s.title);
  }

  // jstt only emits definition types that are reachable from the root.
  // Wire each definition to a root-level property of the same name so
  // every type gets emitted; the root interface itself is then trimmed
  // away as a post-process so the bundle exposes only the actual schemas.
  const properties: Record<string, unknown> = {};
  for (const s of schemas) {
    properties[s.title] = { $ref: `#/definitions/${s.title}` };
  }
  const bundle = {
    $schema: "https://json-schema.org/draft/2020-12/schema",
    title: "_AetherForgeSchemasRoot",
    type: "object",
    additionalProperties: false,
    properties,
    definitions,
  };

  let ts = await compile(bundle, "_AetherForgeSchemasRoot", {
    bannerComment:
      "/**\n * AUTOGENERATED bundle of every Aether Forge JSON schema.\n" +
      " * Source: src/aether_forge/schemas/{artifacts,common,runtime}/*.schema.json.\n" +
      " * Regenerate via `bun run generate:schemas`. DO NOT EDIT BY HAND.\n" +
      " * CI verifies the committed output matches a fresh regeneration.\n */",
    style: { semi: true, singleQuote: false },
    additionalProperties: true,
    declareExternallyReferenced: true,
  });

  // Strip the synthetic root interface — consumers should never see it.
  // The block is recognizable: `export interface _AetherForgeSchemasRoot { ... }`
  // followed by its body, ending with `}`.
  ts = ts.replace(
    /export interface _AetherForgeSchemasRoot \{[\s\S]*?^\}\n?/m,
    "",
  );

  await fs.writeFile(path.join(OUT_DIR, "index.ts"), ts, "utf8");
  console.log(`✓ Generated bundle: src/schemas/generated/index.ts`);
  console.log(`  Schemas included: ${schemas.length}`);
  for (const s of schemas) console.log(`    - ${s.title}  (from ${s.rel})`);
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});

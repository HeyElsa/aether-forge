/**
 * Language-agnostic planner-output parser. TypeScript reference implementation
 * of the spec at `docs/specs/planner-output.md`. Conformance with the Python
 * reference (`aether_forge.planner._extract_json`) is enforced by the shared
 * fixtures under `tests/fixtures/planner-outputs/` — both implementations
 * MUST produce identical results on every fixture.
 *
 * The recovery algorithm follows the spec §4 exactly:
 *   1. trim outer whitespace
 *   2. strip a single Markdown code-fence pair
 *   3. try JSON.parse on the cleaned string
 *   4. balanced-brace recovery (string-aware) for the longest top-level
 *      {…} or […] slice that parses
 *   5. raise PlannerParseError on miss
 */

import { PlannerParseError } from "../types/errors.js";

const FENCE_OPEN_RE = /^```[a-zA-Z0-9_-]*\s*\n?/;
const FENCE_CLOSE_RE = /\n?```\s*$/;

/**
 * Parse a raw planner response per `docs/specs/planner-output.md`.
 *
 * Returns the parsed value — typically `{ steps: PlannerStep[] }` or
 * `PlannerStep[]`, but bare JSON scalars (`null`, booleans, numbers, strings)
 * are also valid JSON and accepted; downstream code is responsible for shape
 * validation against `planner-output.schema.json`.
 *
 * Throws `PlannerParseError` if no JSON can be recovered.
 */
export function parsePlannerOutput(response: string): unknown {
  if (typeof response !== "string" || response.trim() === "") {
    throw new PlannerParseError("planner response was empty or non-string");
  }

  let clean = response.trim();
  clean = clean.replace(FENCE_OPEN_RE, "");
  clean = clean.replace(FENCE_CLOSE_RE, "").trim();

  try {
    return JSON.parse(clean);
  } catch {
    // fall through to balanced-brace recovery
  }

  const candidate = largestBalancedJson(clean);
  if (candidate !== null) {
    try {
      return JSON.parse(candidate);
    } catch {
      // fall through to failure
    }
  }

  throw new PlannerParseError(
    "could not recover JSON object or array from planner response",
  );
}

/**
 * Linear, string-aware scan for the longest contiguous `{…}` or `[…]` slice
 * whose braces close cleanly. Mirrors `aether_forge.planner._largest_balanced_json`
 * exactly. Brace-like characters inside JSON string literals do NOT contribute
 * to the brace stack — that's the rule that makes payloads with handlebars or
 * embedded JSON strings recover correctly.
 */
function largestBalancedJson(text: string): string | null {
  let best: [number, number] | null = null;
  type StackEntry = ["{" | "[", number];
  const stack: StackEntry[] = [];
  let inString = false;
  let escape = false;

  for (let i = 0; i < text.length; i++) {
    const ch = text[i] as string;
    if (inString) {
      if (escape) {
        escape = false;
      } else if (ch === "\\") {
        escape = true;
      } else if (ch === '"') {
        inString = false;
      }
      continue;
    }
    if (ch === '"') {
      inString = true;
      continue;
    }
    if (ch === "{" || ch === "[") {
      stack.push([ch, i]);
      continue;
    }
    if (ch === "}" || ch === "]") {
      const top = stack.pop();
      if (top === undefined) continue;
      const [opener, openerIndex] = top;
      const matches = (opener === "{" && ch === "}") || (opener === "[" && ch === "]");
      if (!matches) continue;
      if (stack.length === 0) {
        const span: [number, number] = [openerIndex, i + 1];
        if (best === null || span[1] - span[0] > best[1] - best[0]) {
          best = span;
        }
      }
    }
  }
  if (best === null) return null;
  return text.slice(best[0], best[1]);
}

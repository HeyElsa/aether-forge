/**
 * Cross-language conformance for the planner-output spec.
 *
 * Reads every fixture under `tests/fixtures/planner-outputs/` and runs it
 * through `parsePlannerOutput`. The Python counterpart at
 * `tests/test_planner_output_spec.py` runs the same fixtures through
 * `_extract_json`. Both implementations MUST produce identical results on
 * every fixture, or the spec at `docs/specs/planner-output.md` has drifted.
 *
 * CI runs both jobs as a gate on any schema or parser change. Adding a
 * fixture is a single-step change: drop a JSON file in
 * `tests/fixtures/planner-outputs/`.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import { parsePlannerOutput, PlannerParseError } from "../src/index.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURE_DIR = path.resolve(__dirname, "..", "..", "tests", "fixtures", "planner-outputs");

interface Fixture {
  description: string;
  input: string;
  expected:
    | { outcome: "parsed"; value: unknown }
    | { outcome: "parse-failure" };
}

async function loadFixtures(): Promise<Array<{ name: string; fixture: Fixture }>> {
  const entries = (await fs.readdir(FIXTURE_DIR))
    .filter((entry) => entry.endsWith(".json"))
    .sort();
  const fixtures: Array<{ name: string; fixture: Fixture }> = [];
  for (const entry of entries) {
    const data = JSON.parse(await fs.readFile(path.join(FIXTURE_DIR, entry), "utf8"));
    fixtures.push({ name: entry.replace(/\.json$/, ""), fixture: data as Fixture });
  }
  return fixtures;
}

const fixtures = await loadFixtures();
if (fixtures.length === 0) {
  throw new Error(
    `no fixtures found at ${FIXTURE_DIR} — did the discovery glob change?`,
  );
}

describe("cross-language conformance — planner-output spec", () => {
  test.each(fixtures.map(({ name, fixture }) => [name, fixture]))(
    "%s",
    (_name, fixture) => {
      const { input, expected } = fixture as Fixture;
      if (expected.outcome === "parsed") {
        expect(parsePlannerOutput(input)).toEqual(expected.value);
      } else {
        expect(() => parsePlannerOutput(input)).toThrow(PlannerParseError);
      }
    },
  );

  test("baseline fixture count (tripwire)", () => {
    // If the fixture suite shrinks unexpectedly, conformance becomes
    // meaningless. Pin the v0.23.0 baseline so a careless deletion is
    // caught immediately. Bump this number deliberately when adding cases.
    expect(fixtures.length).toBeGreaterThanOrEqual(13);
  });
});

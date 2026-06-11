/**
 * Cross-language conformance for reputation-record validation. Parametrizes
 * over the shared fixtures in `tests/fixtures/reputation-records/` — the same
 * files the Python suite (`tests/test_reputation_record_schema.py`) validates,
 * mirroring the planner-output conformance pattern.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import { validateReputationRecord } from "../src/index.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FIXTURES_DIR = path.resolve(
  __dirname,
  "..",
  "..",
  "tests",
  "fixtures",
  "reputation-records",
);

const VALID_FIXTURES = ["v0-runtime-record.json", "v1-extended-record.json"];
const INVALID_FIXTURES = ["invalid-score-out-of-range.json"];

async function readFixture(name: string): Promise<unknown> {
  return JSON.parse(await fs.readFile(path.join(FIXTURES_DIR, name), "utf8"));
}

describe("validateReputationRecord — shared fixtures", () => {
  for (const name of VALID_FIXTURES) {
    test(`${name} validates`, async () => {
      const result = validateReputationRecord(await readFixture(name));
      expect(result.ok, JSON.stringify(result.ok ? null : result.errors[0])).toBe(true);
    });
  }

  for (const name of INVALID_FIXTURES) {
    test(`${name} is rejected`, async () => {
      const result = validateReputationRecord(await readFixture(name));
      expect(result.ok).toBe(false);
    });
  }
});

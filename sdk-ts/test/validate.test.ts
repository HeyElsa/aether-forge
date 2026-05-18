/**
 * Tests for the ajv-backed validators. Loads real artifact bundles from
 * `examples/delta-neutral-btc/` and asserts the TS validators accept them.
 * This is also part of the cross-language conformance contract: any
 * artifact accepted by the Python `jsonschema` validator MUST be accepted
 * by the TS `ajv` validator and vice versa.
 */

import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, test } from "vitest";

import {
  assertValid,
  validateAgentSpec,
  validateAgentConfig,
  validateArtifactBundle,
  validateCapabilityManifest,
  validatePolicyBundle,
  validateScenarioPack,
  ValidationError,
} from "../src/index.js";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const EXAMPLE_DIR = path.resolve(__dirname, "..", "..", "examples", "delta-neutral-btc");

async function readJson(file: string): Promise<unknown> {
  return JSON.parse(await fs.readFile(path.join(EXAMPLE_DIR, file), "utf8"));
}

describe("validators — real example artifacts", () => {
  test("agent-spec validates", async () => {
    const result = validateAgentSpec(await readJson("agent-spec.json"));
    expect(result.ok, JSON.stringify(result.ok ? null : result.errors[0])).toBe(true);
  });

  test("capability-manifest validates", async () => {
    const result = validateCapabilityManifest(await readJson("capability-manifest.json"));
    expect(result.ok, JSON.stringify(result.ok ? null : result.errors[0])).toBe(true);
  });

  test("policy-bundle validates", async () => {
    const result = validatePolicyBundle(await readJson("policy-bundle.json"));
    expect(result.ok, JSON.stringify(result.ok ? null : result.errors[0])).toBe(true);
  });

  test("scenario-pack validates", async () => {
    const result = validateScenarioPack(await readJson("scenario-pack.json"));
    expect(result.ok, JSON.stringify(result.ok ? null : result.errors[0])).toBe(true);
  });

  test("validateArtifactBundle composes the four required artifacts", async () => {
    const result = validateArtifactBundle({
      agentSpec: await readJson("agent-spec.json"),
      capabilityManifest: await readJson("capability-manifest.json"),
      policyBundle: await readJson("policy-bundle.json"),
      scenarioPack: await readJson("scenario-pack.json"),
    });
    expect(result.ok).toBe(true);
  });
});

describe("validators — rejection cases", () => {
  test("agent-spec rejects missing required field", () => {
    const result = validateAgentSpec({} as unknown);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.length).toBeGreaterThan(0);
    }
  });

  test("assertValid throws ValidationError on invalid input", () => {
    expect(() => assertValid(validateAgentSpec({} as unknown))).toThrow(ValidationError);
  });
});

describe("validators — v0.22.0 schemas", () => {
  test("agent-config accepts a minimal deploymentProfile=local config", () => {
    const result = validateAgentConfig({
      deploymentProfile: "local",
      planner: { mode: "heuristic" },
      runtime: { cryptoRouter: "mock" },
    });
    expect(result.ok, JSON.stringify(result.ok ? null : result.errors[0])).toBe(true);
  });

  test("agent-config rejects an invalid deploymentProfile", () => {
    const result = validateAgentConfig({
      deploymentProfile: "prod",
      planner: { mode: "anthropic" },
    });
    expect(result.ok).toBe(false);
  });
});

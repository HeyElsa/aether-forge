/**
 * Tests for the parsePlannerOutput recovery algorithm, mirroring the Python
 * `tests/test_planner_parse_resilience.py` suite. The companion
 * `conformance.test.ts` runs every shared fixture under
 * `tests/fixtures/planner-outputs/` against the same parser to prove
 * parity with the Python reference implementation.
 */

import { describe, expect, test } from "vitest";

import { parsePlannerOutput, PlannerParseError } from "../src/index.js";

describe("parsePlannerOutput — happy paths", () => {
  test("clean JSON object", () => {
    expect(parsePlannerOutput('{"steps": []}')).toEqual({ steps: [] });
  });

  test("JSON fence with language tag", () => {
    const payload = "```json\n{\"steps\": [1, 2]}\n```";
    expect(parsePlannerOutput(payload)).toEqual({ steps: [1, 2] });
  });

  test("bare fence (no language tag)", () => {
    expect(parsePlannerOutput("```\n{\"steps\": []}\n```")).toEqual({ steps: [] });
  });

  test("top-level array", () => {
    expect(parsePlannerOutput('[{"kind": "reason", "description": "go"}]')).toEqual([
      { kind: "reason", description: "go" },
    ]);
  });

  test("bare scalars per RFC 8259", () => {
    expect(parsePlannerOutput("null")).toBeNull();
    expect(parsePlannerOutput("true")).toBe(true);
    expect(parsePlannerOutput("42")).toBe(42);
    expect(parsePlannerOutput('"just a string"')).toBe("just a string");
  });
});

describe("parsePlannerOutput — recovery from messy responses", () => {
  test("reasoning preamble + JSON", () => {
    const payload =
      "Let me think through this. Here is my plan: " +
      '{"steps": [{"kind": "reason", "description": "go"}]}';
    const result = parsePlannerOutput(payload) as { steps: { description: string }[] };
    expect(result.steps[0].description).toBe("go");
  });

  test("trailing prose after JSON", () => {
    const payload =
      '{"steps": [{"kind": "reason", "description": "go"}]}\n\nLet me know if you need anything else.';
    const result = parsePlannerOutput(payload) as { steps: { kind: string }[] };
    expect(result.steps[0].kind).toBe("reason");
  });

  test("preamble + fenced JSON + trailing prose", () => {
    const payload =
      "I'll need to read the basis first. Here's the plan:\n" +
      "```json\n" +
      '{"steps": [{"kind": "use-capability", "description": "Read basis.", "capabilityId": "cap-market-basis"}]}\n' +
      "```\n" +
      "Let me know if you want me to adjust.";
    const result = parsePlannerOutput(payload) as { steps: { capabilityId: string }[] };
    expect(result.steps[0].capabilityId).toBe("cap-market-basis");
  });

  test("braces inside JSON strings do not break balanced-brace scan", () => {
    const payload =
      "Note: {{handlebars}} are fine.\n" +
      '{"steps": [{"description": "use {{var}}"}]}';
    const result = parsePlannerOutput(payload) as { steps: { description: string }[] };
    expect(result.steps[0].description).toBe("use {{var}}");
  });
});

describe("parsePlannerOutput — failure cases", () => {
  test("plain refusal", () => {
    expect(() => parsePlannerOutput("I cannot help with that request.")).toThrow(
      PlannerParseError,
    );
  });

  test("truncated mid-object", () => {
    expect(() =>
      parsePlannerOutput('{"steps": [{"kind": "reason", "description": "tru'),
    ).toThrow(PlannerParseError);
  });

  test("empty string", () => {
    expect(() => parsePlannerOutput("")).toThrow(PlannerParseError);
  });

  test("whitespace only", () => {
    expect(() => parsePlannerOutput("   \n  ")).toThrow(PlannerParseError);
  });

  test("non-string input", () => {
    // Runtime check — the SDK is callable from untyped JS too.
    expect(() => parsePlannerOutput(null as unknown as string)).toThrow(PlannerParseError);
  });
});

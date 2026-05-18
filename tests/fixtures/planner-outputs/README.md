# Planner output conformance fixtures

Shared between Python (`tests/test_planner_output_spec.py`) and TypeScript (`sdk-ts/test/conformance.test.ts`). See `docs/specs/planner-output.md` §7.

Each `*.json` file has the shape:

```json
{
  "description": "human-readable summary",
  "input": "<raw planner response>",
  "expected": {
    "outcome": "parsed" | "parse-failure",
    "value": <parsed JSON value>      // only when outcome == "parsed"
  }
}
```

When `outcome` is `parsed`, both implementations MUST recover the listed `value` (compared with strict JSON equality). When `outcome` is `parse-failure`, both implementations MUST raise their respective `PlannerParseError`.

Adding a fixture is a two-step process:

1. Drop a new JSON file here.
2. Run the Python and TypeScript conformance tests; both MUST pass.

If a fixture exposes a real-world bug, the Python parser is the reference and the TypeScript implementation is brought into line.

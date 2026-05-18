# Aether Forge Planner Output Spec

**Status**: Normative
**Version**: 1.0.0 (introduced v0.23.0)
**Schema**: `src/aether_forge/schemas/runtime/planner-output.schema.json`
**Implementations**:
- Python: `aether_forge.planner._extract_json` + `PromptDrivenPlanner._parse_response`
- TypeScript: `@aether-forge/sdk` `parsePlannerOutput`

---

## 1. Purpose

This document is the cross-language contract for how an Aether Forge planner converts a raw LLM response into the typed step proposals the runtime executes. It exists because the Python parser had to grow real resilience (preamble stripping, balanced-brace recovery, code-fence tolerance) in v0.21.0, and the dev feedback that motivated this work asked for the resilience logic to be either embedded in the model client or published as a language-neutral spec.

The Python implementation IS the reference. A second implementation in the TypeScript SDK conforms to this spec and is exercised against the same shared fixtures as the Python one — see `tests/fixtures/planner-outputs/` and the conformance test on each side.

If you ship a third-party planner via the `aether_forge.planners` entry-point group (Python) or as a `@aether-forge/sdk`-compatible planner (TypeScript), implementing against this spec means downstream agents will treat your output identically to the built-in providers.

---

## 2. Input

A planner produces a single string response per tick. The string MAY contain:

- Pure JSON (no decoration)
- JSON inside a Markdown code fence (` ``` ` or ` ```json `)
- JSON preceded by reasoning prose ("Let me think about this. Here is my plan: {...}")
- JSON followed by commentary ("{...} let me know if you'd like adjustments")
- JSON with brace-like characters inside string literals
- Garbage (no recoverable JSON)
- Empty / whitespace-only output
- Mid-truncated JSON (provider truncated mid-object)

The recovery rules below define what a conforming parser MUST do with each case.

---

## 3. Output Shape

A conforming parser produces a value matching the JSON Schema at `planner-output.schema.json`. The shape is either:

```json
{ "steps": [ <step>, <step>, ... ] }
```

or a bare array:

```json
[ <step>, <step>, ... ]
```

Each `<step>` object MUST have:

- `kind` (string) — one of `reason`, `use-capability`, `request-approval`, `replan`, `report-gap`
- `description` (non-empty string)

A step MAY have:

- `capabilityId` (string) — REQUIRED when `kind` is `use-capability` or `request-approval`. The Python parser also accepts `capability_id` for legacy back-compat; new planners SHOULD emit `capabilityId`.
- `payload` (object) — step-specific arguments. For `reason` steps, `payload.mark_complete = true` advances the session.

---

## 4. Recovery Algorithm

A conforming parser MUST implement, in order:

### 4.1 Trim outer whitespace

Apply ordinary string `.strip()` before any other transform. Whitespace-only input is treated as an empty response (no recovery possible).

### 4.2 Strip a single Markdown code-fence pair

If the trimmed response begins with `` ``` `` optionally followed by a language tag and a newline (e.g. ` ```json `, ` ```python `, ` ``` `), remove that opening sequence. Then, if the result ends with an optional newline followed by `` ``` ``, remove that closing sequence. Only one fence pair is stripped at this stage; further fences are handled by step 4.4.

Regex form (for reference):

- Opening: `^```[a-zA-Z0-9_-]*\s*\n?`
- Closing: `\n?```\s*$`

### 4.3 Try `JSON.parse` on the cleaned string

If parsing succeeds, return the parsed value. This is the happy path.

### 4.4 Balanced-brace recovery

If parsing failed, scan the original cleaned string for the longest contiguous slice that:

- Opens with `{` or `[`
- Closes with the matching `}` or `]`
- Has balanced brace nesting (ignoring brace-like characters inside JSON string literals — see 4.4.1)

Pass that slice to `JSON.parse`. If it parses, return the value.

#### 4.4.1 String-aware scanning

While walking the text, a parser MUST track whether it is currently inside a JSON string literal. Inside a string, `{`, `}`, `[`, `]` do not affect the brace stack. A `\` escapes the next character. The string is exited on an unescaped `"`.

This rule lets payloads containing `{{handlebars}}` or `{"k": "v"}` strings recover cleanly even when the surrounding prose contains brace-like characters.

### 4.5 If 4.4 yields nothing parseable, raise a structured parse error

A conforming parser MUST emit a typed error (Python: `PlannerParseError`; TypeScript: `PlannerParseError`) so the runtime can record the failure event on the session ledger before falling back to a heuristic planner. Silent fallback is a contract violation.

---

## 5. Observability Contract

When a conforming parser raises a parse error, the surrounding planner MUST record a structured event on the runtime session before falling back. The event shape is:

```json
{
  "kind": "parse-failure" | "parse-exception" | "model-error" | "empty-plan",
  "detail": "<reason string or null>",
  "responsePreview": "<first 500 chars of the response or null>",
  "recordedAt": "<ISO-8601 timestamp>"
}
```

Discriminator semantics:

- `parse-failure` — `_extract_json` raised `PlannerParseError` (no recoverable JSON).
- `parse-exception` — some other exception was raised during parsing (e.g., the parsed value was not a list/dict). Distinct so operators can tell "garbage" from "unexpected shape."
- `model-error` — the LLM call itself raised (timeout, 5xx, etc.) — the parser never ran.
- `empty-plan` — parsing succeeded but produced zero actionable steps (e.g., `{"steps": []}`). Distinct from `parse-failure` so operators can tell "model returned nothing" from "model returned garbage."

The event is stored at `session.session_state["last_planner_parse_failure"]` (Python) and `session.sessionState.lastPlannerParseFailure` (TypeScript). Replay JSON files MUST preserve the event so post-hoc debugging is possible.

---

## 6. Retry Envelope (Provider Layer)

Distinct from the parser, the *provider client* layer handles transient HTTP failures from the LLM endpoint. A conforming provider client MUST retry on:

- Network errors (`URLError`, `TimeoutError`, equivalent)
- HTTP status codes in `{408, 425, 429, 500, 502, 503, 504}`

It MUST NOT retry on:

- HTTP `4xx` codes outside the set above (these indicate a client-side error that retry cannot fix)
- `PlannerParseError` raised after a successful HTTP response (that is the parser's job, not transport)

When retrying, a conforming client MUST honor the `Retry-After` header on 429 and 503 responses. Otherwise, it applies jittered exponential backoff. Defaults in the reference Python implementation: base `0.5s`, cap `8s`, ±20% jitter, 3 total attempts.

Provider clients MUST expose an opt-out (Python: `retry_attempts: int = 3`, set to `1` to disable; TypeScript: equivalent constructor field).

---

## 7. Conformance Fixtures

Shared fixtures live at `tests/fixtures/planner-outputs/`. Each file has the shape:

```json
{
  "description": "human-readable summary of the case",
  "input": "<raw planner response>",
  "expected": {
    "outcome": "parsed" | "parse-failure",
    "steps": [...]
  }
}
```

The Python conformance test at `tests/test_planner_output_spec.py` and the TypeScript conformance test at `sdk-ts/test/conformance.test.ts` MUST both pass against every fixture. CI runs both as a gate on schema changes.

Adding a new edge case is a two-step process:

1. Drop a new JSON file into `tests/fixtures/planner-outputs/`.
2. Confirm both tests pass.

If the fixture surfaces a real-world bug, the Python parser is the reference and the TypeScript implementation MUST be brought into line.

---

## 8. Versioning

This spec follows semantic versioning. v1.0.0 is the introduction.

- Patch bump (`1.0.x`): wording clarifications that do not change behavior.
- Minor bump (`1.x.0`): additive recovery rules (e.g., a new wrapping convention from a provider).
- Major bump (`x.0.0`): breaking change in the parse contract. Implementations MUST pin to a compatible major.

Major bumps are coordinated across both reference implementations and trigger a v0.x.0 PRD release.

---

## 9. Non-Goals

Explicitly out of scope for this spec:

- The *shape* of provider-native tool-use responses (Anthropic `tool_use` blocks, OpenAI `tool_calls`). Those are converted to the same step-list shape by `adapters/function_call.py` (Python) or the equivalent TS adapter; this spec covers the output of that conversion, not the wire format of the provider.
- The behavior of `HeuristicPlanner` — the heuristic is a runtime-side fallback, not a parser concern.
- Validation of `payload` arguments against capability `inputSchema` — that is the policy gate's responsibility, not the parser's.

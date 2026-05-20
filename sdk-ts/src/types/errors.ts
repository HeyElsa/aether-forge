/**
 * Aether Forge SDK error hierarchy. Public surface — every thrown error from
 * the SDK extends `AetherForgeError`, so consumers can `catch (error: unknown)`
 * with a single `instanceof` check.
 */

export class AetherForgeError extends Error {
  constructor(message: string, options?: { cause?: unknown }) {
    super(message, options);
    this.name = new.target.name;
    // Preserve prototype chain across the ES2015 class boundary so
    // `instanceof` works through bundler transformations.
    Object.setPrototypeOf(this, new.target.prototype);
  }
}

/**
 * Raised by `parsePlannerOutput` when no valid JSON object/array can be
 * recovered from a planner response. Mirrors the Python `PlannerParseError`
 * at `aether_forge.planner.PlannerParseError`. The conformance spec at
 * `docs/specs/planner-output.md` §4.5 requires both implementations raise
 * a typed error on this case rather than silently returning null/undefined.
 */
export class PlannerParseError extends AetherForgeError {}

/**
 * Raised by `validate*` helpers when an artifact does not match its schema.
 * Carries the underlying Ajv `errors` array so consumers can render
 * field-by-field feedback.
 */
export class ValidationError extends AetherForgeError {
  public readonly errors: ReadonlyArray<unknown>;
  constructor(message: string, errors: ReadonlyArray<unknown>) {
    super(message);
    this.errors = errors;
  }
}

/**
 * Raised when a TS consumer interacts with an artifact whose `schemaVersion`
 * is outside the range the installed `@aether-forge/sdk` declares it supports
 * (via `package.json:schemaCompat`). Pre-emptive — prevents subtle bugs from
 * silently parsing forward-incompatible artifacts.
 */
export class SchemaCompatError extends AetherForgeError {}

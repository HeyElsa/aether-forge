/**
 * Public surface of `@aether-forge/sdk` v0.1.0.
 *
 * Three layers:
 *   1. Generated types — TS interfaces for every JSON schema published at
 *      schemas.aether-forge.dev. Re-exported as a namespace-free flat surface.
 *   2. Validators — ajv-backed `validate*` functions returning Result objects,
 *      plus `assertValid` for the throw-on-invalid style.
 *   3. Protocol interfaces — Planner / ExecutionRouter / MemoryStore /
 *      DataSource / PlanningModel. Interface-only in v0.1.0 — runtime tick
 *      loop stays Python-side until cross-language adoption justifies a port.
 *
 * Also exports `parsePlannerOutput`, the language-agnostic implementation of
 * the spec at `docs/specs/planner-output.md`. Conforms identically to the
 * Python reference `aether_forge.planner._extract_json`.
 */

export const SCHEMA_VERSION = "0.23.0";
export const SCHEMA_BASE_URL = "https://schemas.aether-forge.dev";

// Generated types
export * from "./schemas/generated/index.js";

// Validators
export {
  validateAgentSpec,
  validateCapabilityManifest,
  validatePolicyBundle,
  validateScenarioPack,
  validateResearchRecord,
  validatePromotionRecord,
  validateMemoryRecord,
  validateScaffoldManifest,
  validateReputationRecord,
  validateMigrationContract,
  validatePlannerOutput,
  validateDelegatedSigner,
  validateAgentConfig,
  validateArtifactBundle,
  assertValid,
  type ValidationResult,
  type ArtifactBundleInput,
  type ArtifactBundleResult,
} from "./validate/index.js";

// Planner output parser
export { parsePlannerOutput } from "./planner/parse.js";

// Protocol interfaces (interface-only)
export type {
  StepKind,
  StepProposal,
  ExecutionResult,
  ArtifactBundle,
  RuntimeSession,
  Planner,
  PlanningModel,
  FunctionCallResponse,
  FunctionToolCall,
  ExecutionRouter,
  MemoryQuery,
  MemoryPromotionRequest,
  MemoryPromotionResult,
  MemoryStore,
  DataSource,
  DataResult,
  SigningIntent,
  DelegatedSigner,
} from "./types/protocols.js";

// Errors
export {
  AetherForgeError,
  PlannerParseError,
  ValidationError,
  SchemaCompatError,
} from "./types/errors.js";

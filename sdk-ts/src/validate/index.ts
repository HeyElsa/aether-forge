/**
 * Ajv-backed validators for every artifact / runtime / common schema
 * published at `https://schemas.aether-forge.dev/`. Schemas are bundled as
 * JSON imports so the SDK has zero filesystem dependency at runtime — works
 * in Node, browsers, and edge runtimes alike.
 *
 * Each validator returns either `{ ok: true, value }` (where `value` is the
 * input, narrowed to the target type) or `{ ok: false, errors }` carrying
 * the Ajv error array. Consumers who prefer the throw-on-invalid style can
 * use `assertValid<T>(result)` which raises `ValidationError`.
 */

import Ajv2020, { type ErrorObject, type ValidateFunction } from "ajv/dist/2020.js";
import addFormats from "ajv-formats";

import { ValidationError } from "../types/errors.js";

// Artifact schemas
import agentSpecSchema from "../../../src/aether_forge/schemas/artifacts/agent-spec.schema.json" with { type: "json" };
import capabilityManifestSchema from "../../../src/aether_forge/schemas/artifacts/capability-manifest.schema.json" with { type: "json" };
import policyBundleSchema from "../../../src/aether_forge/schemas/artifacts/policy-bundle.schema.json" with { type: "json" };
import scenarioPackSchema from "../../../src/aether_forge/schemas/artifacts/scenario-pack.schema.json" with { type: "json" };
import researchRecordSchema from "../../../src/aether_forge/schemas/artifacts/research-record.schema.json" with { type: "json" };
import promotionRecordSchema from "../../../src/aether_forge/schemas/artifacts/promotion-record.schema.json" with { type: "json" };
import memoryRecordSchema from "../../../src/aether_forge/schemas/artifacts/memory-record.schema.json" with { type: "json" };
import scaffoldManifestSchema from "../../../src/aether_forge/schemas/artifacts/scaffold-manifest.schema.json" with { type: "json" };

// Common schemas — referenced by artifact schemas via $id URLs, so they MUST
// be addSchema'd to the ajv instance up front for cross-refs to resolve.
import artifactEnvelopeSchema from "../../../src/aether_forge/schemas/common/artifact-envelope.schema.json" with { type: "json" };
import artifactRefSchema from "../../../src/aether_forge/schemas/common/artifact-ref.schema.json" with { type: "json" };
import compatibilitySchema from "../../../src/aether_forge/schemas/common/compatibility.schema.json" with { type: "json" };
import migrationContractSchema from "../../../src/aether_forge/schemas/common/migration-contract.schema.json" with { type: "json" };

// Runtime schemas
import activeComparisonContractSchema from "../../../src/aether_forge/schemas/runtime/active-comparison-contract.schema.json" with { type: "json" };
import agentConfigSchema from "../../../src/aether_forge/schemas/runtime/agent-config.schema.json" with { type: "json" };
import delegatedSignerSchema from "../../../src/aether_forge/schemas/runtime/delegated-signer.schema.json" with { type: "json" };
import plannerOutputSchema from "../../../src/aether_forge/schemas/runtime/planner-output.schema.json" with { type: "json" };
import plannerToolUseSchema from "../../../src/aether_forge/schemas/runtime/planner-tool-use.schema.json" with { type: "json" };
import policyDecisionRecordSchema from "../../../src/aether_forge/schemas/runtime/policy-decision-record.schema.json" with { type: "json" };
import runtimeStepLedgerEntrySchema from "../../../src/aether_forge/schemas/runtime/runtime-step-ledger-entry.schema.json" with { type: "json" };

import type {
  AgentSpec,
  CapabilityManifest,
  PolicyBundle,
  ScenarioPack,
  ResearchRecord,
  PromotionRecord,
  MemoryRecord,
  ScaffoldManifest,
  MigrationContract,
} from "../schemas/generated/index.js";

const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats.default ? addFormats.default(ajv) : (addFormats as unknown as (a: Ajv2020) => void)(ajv);

// Register every schema with the ajv instance up front so cross-schema
// `$ref` URLs (pointing at https://schemas.aether-forge.dev/...) resolve
// in-memory without network fetches. Each schema's own `$id` is the lookup
// key — the framework convention is that every published schema has one.
for (const schema of [
  artifactEnvelopeSchema,
  artifactRefSchema,
  compatibilitySchema,
  migrationContractSchema,
  activeComparisonContractSchema,
  agentConfigSchema,
  delegatedSignerSchema,
  plannerOutputSchema,
  plannerToolUseSchema,
  policyDecisionRecordSchema,
  runtimeStepLedgerEntrySchema,
  agentSpecSchema,
  capabilityManifestSchema,
  policyBundleSchema,
  scenarioPackSchema,
  researchRecordSchema,
  promotionRecordSchema,
  memoryRecordSchema,
  scaffoldManifestSchema,
] as Array<{ $id?: string }>) {
  if (schema.$id && !ajv.getSchema(schema.$id)) {
    ajv.addSchema(schema as object);
  }
}

export type ValidationResult<T> =
  | { readonly ok: true; readonly value: T }
  | { readonly ok: false; readonly errors: ReadonlyArray<ErrorObject> };

function buildValidator<T>(schema: unknown): (input: unknown) => ValidationResult<T> {
  const validate = ajv.compile(schema as object) as ValidateFunction;
  return (input: unknown): ValidationResult<T> => {
    if (validate(input)) {
      return { ok: true, value: input as T };
    }
    return { ok: false, errors: (validate.errors ?? []) as ReadonlyArray<ErrorObject> };
  };
}

export const validateAgentSpec = buildValidator<AgentSpec>(agentSpecSchema);
export const validateCapabilityManifest = buildValidator<CapabilityManifest>(capabilityManifestSchema);
export const validatePolicyBundle = buildValidator<PolicyBundle>(policyBundleSchema);
export const validateScenarioPack = buildValidator<ScenarioPack>(scenarioPackSchema);
export const validateResearchRecord = buildValidator<ResearchRecord>(researchRecordSchema);
export const validatePromotionRecord = buildValidator<PromotionRecord>(promotionRecordSchema);
export const validateMemoryRecord = buildValidator<MemoryRecord>(memoryRecordSchema);
export const validateScaffoldManifest = buildValidator<ScaffoldManifest>(scaffoldManifestSchema);
export const validateMigrationContract = buildValidator<MigrationContract>(migrationContractSchema);
export const validatePlannerOutput = buildValidator<unknown>(plannerOutputSchema);
export const validateDelegatedSigner = buildValidator<unknown>(delegatedSignerSchema);
export const validateAgentConfig = buildValidator<unknown>(agentConfigSchema);

/** Throws ValidationError if the result is not ok. Useful for code that
 * prefers exceptions over result types. */
export function assertValid<T>(result: ValidationResult<T>): T {
  if (!result.ok) {
    throw new ValidationError(
      `validation failed: ${result.errors.length} error(s) — first: ${JSON.stringify(result.errors[0])}`,
      result.errors,
    );
  }
  return result.value;
}

/**
 * Validate an entire artifact bundle (the five required artifacts a
 * generated agent ships with). Returns the first failure or all four
 * successes — mirrors `aether_forge.artifacts.validate_artifact_directory`.
 */
export interface ArtifactBundleInput {
  agentSpec: unknown;
  capabilityManifest: unknown;
  policyBundle: unknown;
  scenarioPack: unknown;
  scaffoldManifest?: unknown;
}

export interface ArtifactBundleResult {
  ok: boolean;
  results: Record<string, ValidationResult<unknown>>;
}

export function validateArtifactBundle(bundle: ArtifactBundleInput): ArtifactBundleResult {
  const results: Record<string, ValidationResult<unknown>> = {
    agentSpec: validateAgentSpec(bundle.agentSpec) as ValidationResult<unknown>,
    capabilityManifest: validateCapabilityManifest(bundle.capabilityManifest) as ValidationResult<unknown>,
    policyBundle: validatePolicyBundle(bundle.policyBundle) as ValidationResult<unknown>,
    scenarioPack: validateScenarioPack(bundle.scenarioPack) as ValidationResult<unknown>,
  };
  if (bundle.scaffoldManifest !== undefined) {
    results.scaffoldManifest = validateScaffoldManifest(bundle.scaffoldManifest) as ValidationResult<unknown>;
  }
  const ok = Object.values(results).every((r) => r.ok);
  return { ok, results };
}

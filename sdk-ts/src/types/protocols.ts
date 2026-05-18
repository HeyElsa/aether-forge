/**
 * Aether Forge extension protocols — TypeScript mirrors of the five Python
 * Protocols at:
 *   - `Planner`              → src/aether_forge/runtime.py:110
 *   - `ExecutionRouter`      → src/aether_forge/runtime.py:137
 *   - `MemoryStore`          → src/aether_forge/memory.py:139
 *   - `DataSource`           → src/aether_forge/data_layer.py:92
 *   - `PlanningModel`        → src/aether_forge/planner.py:17
 *
 * v0.23.0 ships these as INTERFACE-ONLY. There is no runtime implementation
 * of `RuntimeSession` / `AgentRunner` in TypeScript — the runtime tick loop
 * is the highest lockstep risk and deliberately stays Python-side until
 * cross-language usage data justifies porting. See plan §"What we deliberately
 * do not do" at ~/.claude/plans/friction-points-python-only-concurrent-lecun.md.
 *
 * Implementations of these interfaces can be plugged into the Python runtime
 * via `aether_forge.{planners,execution_routers,data_sources}` entry points
 * once a small Python adapter wrapper exists (future work).
 */

import type {
  AgentSpec,
  CapabilityManifest,
  PolicyBundle,
  ScenarioPack,
  MemoryRecord as MemoryRecordSchema,
} from "../schemas/generated/index.js";

// ---------------------------------------------------------------------------
// StepProposal — mirror of aether_forge.runtime.StepProposal
// ---------------------------------------------------------------------------

export type StepKind =
  | "reason"
  | "use-capability"
  | "request-approval"
  | "replan"
  | "report-gap";

export interface StepProposal {
  kind: StepKind;
  description: string;
  capabilityId?: string;
  payload?: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// ExecutionResult — mirror of aether_forge.runtime.ExecutionResult
// ---------------------------------------------------------------------------

export interface ExecutionResult {
  success: boolean;
  output?: Record<string, unknown>;
  markComplete?: boolean;
  requiresReplan?: boolean;
  failureReason?: string;
}

// ---------------------------------------------------------------------------
// RuntimeSession — interface-only snapshot for type-checking planners and
// routers. The Python tick loop owns construction and mutation.
// ---------------------------------------------------------------------------

export interface ArtifactBundle {
  agentSpec: AgentSpec;
  capabilityManifest: CapabilityManifest;
  policyBundle: PolicyBundle;
  scenarioPack: ScenarioPack;
}

/**
 * Read-only snapshot of a tick's runtime state. TypeScript implementations of
 * `Planner` / `ExecutionRouter` receive this; they MUST treat it as immutable
 * (mutations are invisible to the Python tick loop on the other side of an
 * eventual adapter boundary).
 */
export interface RuntimeSession {
  artifacts: ArtifactBundle;
  environment: "local" | "sandbox" | "paper" | "canary-live" | "production";
  workingSet: Record<string, unknown>;
  sessionState: Record<string, unknown>;
  observations: ReadonlyArray<Record<string, unknown>>;
}

// ---------------------------------------------------------------------------
// Planner / PlanningModel / ExecutionRouter / MemoryStore / DataSource
// ---------------------------------------------------------------------------

export interface Planner {
  /** Mirror of `Planner.propose_plan`. The runtime invokes this once per tick. */
  proposePlan(session: RuntimeSession): StepProposal[] | Promise<StepProposal[]>;
}

export interface PlanningModel {
  /** Mirror of `PlanningModel.complete`. Returns the raw model response string. */
  complete(planningPrompt: string): Promise<string> | string;
  /**
   * Optional provider-native tool-use path (v0.22.0+ FP-1 deepening). When
   * present and the planner has `toolMode: true`, the planner skips string
   * parsing entirely and uses this method. Tools are derived from the
   * capability manifest by `buildToolSchemaFromManifest`.
   */
  completeWithTools?(
    planningPrompt: string,
    tools: Array<Record<string, unknown>>,
  ): Promise<FunctionCallResponse> | FunctionCallResponse;
}

/**
 * Mirror of `aether_forge.adapters.function_call.FunctionCallResponse`.
 * Whether produced by the legacy string parser or the provider-native tool-use
 * path, downstream code consumes this shape via the translator.
 */
export interface FunctionCallResponse {
  reasoning?: string | null;
  toolCalls: FunctionToolCall[];
  finalMessage?: string | null;
  requiresApproval?: boolean;
}

export interface FunctionToolCall {
  name: string;
  arguments: Record<string, unknown>;
}

export interface ExecutionRouter {
  /** Mirror of `ExecutionRouter.execute`. */
  execute(
    session: RuntimeSession,
    proposal: StepProposal,
    capability: Record<string, unknown>,
  ): ExecutionResult | Promise<ExecutionResult>;
}

// ---------------------------------------------------------------------------
// MemoryStore — mirror of aether_forge.memory.MemoryStore
// ---------------------------------------------------------------------------

export type MemoryRecord = MemoryRecordSchema;

export interface MemoryQuery {
  scope?: string;
  environment?: string;
  memoryType?: string;
  sensitivityAtMost?: "public" | "internal" | "confidential" | "restricted";
  tag?: string;
  text?: string;
  limit?: number;
}

export interface MemoryPromotionRequest {
  memoryId: string;
  sourceEnvironment: string;
  targetEnvironment: string;
  approvalRef?: string;
  requestedBy?: string;
}

export interface MemoryPromotionResult {
  promoted: boolean;
  reason: string;
  record?: MemoryRecord;
}

export interface MemoryStore {
  read(query: MemoryQuery): MemoryRecord[] | Promise<MemoryRecord[]>;
  write(record: MemoryRecord): MemoryRecord | Promise<MemoryRecord>;
  promote(
    request: MemoryPromotionRequest,
  ): MemoryPromotionResult | Promise<MemoryPromotionResult>;
}

// ---------------------------------------------------------------------------
// DataSource — mirror of aether_forge.data_layer.DataSource (ABC)
// ---------------------------------------------------------------------------

export interface DataResult {
  capability: string;
  data: unknown;
  source: string;
  cost?: { kind: "free" | "x402" | "subscription" | "gas"; amount?: number };
  fetchedAt?: string;
}

export interface DataSource {
  supports(capability: string): boolean;
  fetch(capability: string, params?: Record<string, unknown>): Promise<DataResult> | DataResult;
}

// ---------------------------------------------------------------------------
// Wallet signing surface — mirror of aether_forge.crypto.signers.DelegatedSigner
// (v0.22.0). The TS surface lives in the x402 sub-package (sdk-ts/x402)
// scheduled for v0.1.1; the type is hoisted here so the planner protocols
// can reference SigningIntent if they ever need to.
// ---------------------------------------------------------------------------

export interface SigningIntent {
  chainId?: number;
  contractAddress?: string;
  spendUsd?: number;
  purpose: string;
}

export interface DelegatedSigner {
  signTypedData(
    typedData: Record<string, unknown>,
    options?: { intent?: SigningIntent },
  ): Promise<string> | string;
}

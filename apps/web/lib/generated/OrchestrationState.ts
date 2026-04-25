/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type Confidence = number;
/**
 * Request classifications produced by the small-tier classifier.
 *
 * Categories match Section 6's classifier prompt design, which supersedes
 * the summary in Section 5 §3. `chitchat`-style queries fall under
 * `out_of_scope` or `clarification` depending on whether a follow-up is
 * worth asking.
 */
export type Intent = "grounded_qa" | "extraction" | "tool_action" | "clarification" | "out_of_scope";
/**
 * Three-tier routing cascade — Section 19 Decision 4.
 */
export type ModelTier = "small" | "mid" | "frontier";
export type Workflow = string;
/**
 * State machine phases. Matches the lifecycle diagram in Section 5.
 */
export type OrchestratorPhase =
  | "RECEIVED"
  | "INPUT_GUARDRAILS"
  | "CLASSIFIED"
  | "RETRIEVED"
  | "ASSEMBLED"
  | "DISPATCHED"
  | "VALIDATED"
  | "OUTPUT_GUARDRAILS"
  | "SHAPED"
  | "COMPLETED"
  | "FAILED";
export type Attempt = number;
export type IdempotencyKey = string;
export type Model = string;
export type Provider = string;
export type Errors = string[];
export type CachePrefixTokens = number;
export type TemplateName = string;
export type TemplateVersion = number;
export type TotalTokensAssembled = number;
export type RequestId = string;
export type ChunksAfterRerank = number;
export type ChunksRetrieved = number;
export type QueryRewritten = string;
export type TopRelevanceScore = number;
export type Assembly = number | null;
export type Classification = number | null;
export type DispatchPending = number | null;
export type InputGuardrails = number | null;
export type OutputGuardrails = number | null;
export type Retrieval = number | null;
export type Total = number | null;
export type Validation = number | null;

export interface OrchestrationState {
  classification?: ClassificationResult | null;
  current_state: OrchestratorPhase;
  dispatch?: DispatchInfo | null;
  errors?: Errors;
  prompt?: PromptAssemblyInfo | null;
  request_id: RequestId;
  retrieval?: RetrievalSummary | null;
  timings_ms?: TimingsMs;
}
export interface ClassificationResult {
  confidence: Confidence;
  intent: Intent;
  model_tier: ModelTier;
  workflow: Workflow;
}
export interface DispatchInfo {
  attempt: Attempt;
  idempotency_key: IdempotencyKey;
  model: Model;
  provider: Provider;
}
export interface PromptAssemblyInfo {
  cache_prefix_tokens: CachePrefixTokens;
  template_name: TemplateName;
  template_version: TemplateVersion;
  total_tokens_assembled: TotalTokensAssembled;
}
export interface RetrievalSummary {
  chunks_after_rerank: ChunksAfterRerank;
  chunks_retrieved: ChunksRetrieved;
  query_rewritten: QueryRewritten;
  top_relevance_score: TopRelevanceScore;
}
/**
 * Per-stage timings in milliseconds. Nullable while the stage is pending.
 */
export interface TimingsMs {
  assembly?: Assembly;
  classification?: Classification;
  dispatch_pending?: DispatchPending;
  input_guardrails?: InputGuardrails;
  output_guardrails?: OutputGuardrails;
  retrieval?: Retrieval;
  total?: Total;
  validation?: Validation;
}

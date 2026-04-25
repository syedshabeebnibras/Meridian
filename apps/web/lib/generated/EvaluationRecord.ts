/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type EvalId = string;
export type EvaluationType = "offline_regression" | "online_sample" | "golden_run" | "safety_eval";
export type GoldenAnswer = string | null;
export type HumanLabel = string | null;
export type JudgeModel = string;
export type JudgePromptVersion = string;
export type LatencyMs = number;
export type ModelUsed = string;
export type PromptVersion = string;
export type RequestId = string;
export type CitationAccuracy = number | null;
export type Faithfulness = number | null;
export type Relevance = number | null;
export type ResponseCompleteness = number | null;
export type SafetyPass = boolean | null;
export type Timestamp = string;
export type TotalCostUsd = number;

export interface EvaluationRecord {
  eval_id: EvalId;
  eval_type: EvaluationType;
  golden_answer?: GoldenAnswer;
  human_label?: HumanLabel;
  judge_model: JudgeModel;
  judge_prompt_version: JudgePromptVersion;
  latency_ms: LatencyMs;
  model_used: ModelUsed;
  prompt_version: PromptVersion;
  request_id: RequestId;
  scores: EvaluationScores;
  timestamp: Timestamp;
  total_cost_usd: TotalCostUsd;
}
/**
 * Judge output. Individual judges may populate a subset of fields.
 */
export interface EvaluationScores {
  citation_accuracy?: CitationAccuracy;
  faithfulness?: Faithfulness;
  relevance?: Relevance;
  response_completeness?: ResponseCompleteness;
  safety_pass?: SafetyPass;
}

/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type ActivatedAt = string;
export type ActivatedBy = string;
export type CanaryPercentage = number;
export type Environment = string;
export type ActivationStatus = "active" | "canary" | "archived" | "draft";
export type Breakpoints = string[];
export type PrefixStable = boolean;
export type AvgLatencyMs = number;
export type FaithfulnessScore = number;
export type RegressionPassRate = number;
export type FewShotDataset = string | null;
export type MinModel = string;
/**
 * Three-tier routing cascade — Section 19 Decision 4.
 */
export type ModelTier = "small" | "mid" | "frontier";
export type Name = string;
export type Parameters = string[];
export type SchemaRef = string;
export type Template = string;
export type FewShot = number;
export type History = number;
export type Query = number;
export type Retrieval = number;
export type System = number;
export type TotalMax = number;
export type Version = number;

export interface PromptTemplate {
  activation: ActivationInfo;
  cache_control: CacheControl;
  eval_results?: EvalResults | null;
  few_shot_dataset?: FewShotDataset;
  min_model: MinModel;
  model_tier: ModelTier;
  name: Name;
  parameters: Parameters;
  schema_ref: SchemaRef;
  template: Template;
  token_budget: TokenBudget;
  version: Version;
}
export interface ActivationInfo {
  activated_at: ActivatedAt;
  activated_by: ActivatedBy;
  canary_percentage?: CanaryPercentage;
  environment: Environment;
  status: ActivationStatus;
}
/**
 * Provider-native cache breakpoints. Section 5 — three-layer cache.
 */
export interface CacheControl {
  breakpoints?: Breakpoints;
  prefix_stable?: PrefixStable;
}
/**
 * Rolling eval metrics attached to a template version.
 */
export interface EvalResults {
  avg_latency_ms: AvgLatencyMs;
  faithfulness_score: FaithfulnessScore;
  regression_pass_rate: RegressionPassRate;
}
/**
 * Slot-by-slot token caps enforced by the prompt assembler.
 */
export interface TokenBudget {
  few_shot: FewShot;
  history: History;
  query: Query;
  retrieval: Retrieval;
  system: System;
  total_max: TotalMax;
}

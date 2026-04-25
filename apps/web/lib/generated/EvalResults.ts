/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type AvgLatencyMs = number;
export type FaithfulnessScore = number;
export type RegressionPassRate = number;

/**
 * Rolling eval metrics attached to a template version.
 */
export interface EvalResults {
  avg_latency_ms: AvgLatencyMs;
  faithfulness_score: FaithfulnessScore;
  regression_pass_rate: RegressionPassRate;
}

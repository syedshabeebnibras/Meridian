/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type CitationAccuracy = number | null;
export type Faithfulness = number | null;
export type Relevance = number | null;
export type ResponseCompleteness = number | null;
export type SafetyPass = boolean | null;

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

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

export interface ClassificationResult {
  confidence: Confidence;
  intent: Intent;
  model_tier: ModelTier;
  workflow: Workflow;
}

/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type Assembly = number | null;
export type Classification = number | null;
export type DispatchPending = number | null;
export type InputGuardrails = number | null;
export type OutputGuardrails = number | null;
export type Retrieval = number | null;
export type Total = number | null;
export type Validation = number | null;

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

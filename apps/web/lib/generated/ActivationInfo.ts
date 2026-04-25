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

export interface ActivationInfo {
  activated_at: ActivatedAt;
  activated_by: ActivatedBy;
  canary_percentage?: CanaryPercentage;
  environment: Environment;
  status: ActivationStatus;
}

/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type Attempt = number;
export type IdempotencyKey = string;
export type Model = string;
export type Provider = string;

export interface DispatchInfo {
  attempt: Attempt;
  idempotency_key: IdempotencyKey;
  model: Model;
  provider: Provider;
}

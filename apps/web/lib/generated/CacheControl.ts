/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type Breakpoints = string[];
export type PrefixStable = boolean;

/**
 * Provider-native cache breakpoints. Section 5 — three-layer cache.
 */
export interface CacheControl {
  breakpoints?: Breakpoints;
  prefix_stable?: PrefixStable;
}

/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type FewShot = number;
export type History = number;
export type Query = number;
export type Retrieval = number;
export type System = number;
export type TotalMax = number;

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

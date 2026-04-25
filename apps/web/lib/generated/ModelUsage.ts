/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type CacheCreationInputTokens = number;
export type CacheReadInputTokens = number;
export type InputTokens = number;
export type OutputTokens = number;

export interface ModelUsage {
  cache_creation_input_tokens?: CacheCreationInputTokens;
  cache_read_input_tokens?: CacheReadInputTokens;
  input_tokens: InputTokens;
  output_tokens: OutputTokens;
}

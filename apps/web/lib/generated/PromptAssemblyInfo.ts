/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type CachePrefixTokens = number;
export type TemplateName = string;
export type TemplateVersion = number;
export type TotalTokensAssembled = number;

export interface PromptAssemblyInfo {
  cache_prefix_tokens: CachePrefixTokens;
  template_name: TemplateName;
  template_version: TemplateVersion;
  total_tokens_assembled: TotalTokensAssembled;
}

/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type ConfirmationMessage = string | null;
export type RequiresConfirmation = boolean;
export type ToolCallId = string;
export type ToolName = string;
export type NoInjectionDetected = boolean;
export type ParametersAllowlisted = boolean;
export type SchemaValid = boolean;

export interface ToolInvocation {
  confirmation_message?: ConfirmationMessage;
  parameters: Parameters;
  requires_confirmation?: RequiresConfirmation;
  tool_call_id: ToolCallId;
  tool_name: ToolName;
  validation: ToolValidation;
}
export interface Parameters {
  [k: string]: unknown;
}
/**
 * Pre-execution checks that must all pass before the call is dispatched.
 */
export interface ToolValidation {
  no_injection_detected: NoInjectionDetected;
  parameters_allowlisted: ParametersAllowlisted;
  schema_valid: SchemaValid;
}

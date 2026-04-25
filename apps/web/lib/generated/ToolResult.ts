/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type Error = string | null;
export type ExecutionTimeMs = number;
export type ToolResultStatus = "success" | "error" | "denied" | "timeout";
export type ToolCallId = string;
export type ToolName = string;

export interface ToolResult {
  error?: Error;
  execution_time_ms: ExecutionTimeMs;
  result?: Result;
  status: ToolResultStatus;
  tool_call_id: ToolCallId;
  tool_name: ToolName;
}
export interface Result {
  [k: string]: unknown;
}

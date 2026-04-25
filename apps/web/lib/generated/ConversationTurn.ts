/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type Content = string;
export type Role = "user" | "assistant";
export type Timestamp = string;

/**
 * One turn of prior conversation, surfaced to the orchestrator for in-session memory.
 */
export interface ConversationTurn {
  content: Content;
  role: Role;
  timestamp: Timestamp;
}

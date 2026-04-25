/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type MaxTokens = number;
export type Content = string;
export type Role = "system" | "user" | "assistant" | "tool";
export type Messages = _Message[];
export type Model = string;
export type Name = string;
export type Strict = boolean;
export type Type = "json_schema" | "text";
export type Temperature = number;

/**
 * Payload sent to the Model Gateway.
 */
export interface ModelRequest {
  max_tokens: MaxTokens;
  messages: Messages;
  metadata?: Metadata;
  model: Model;
  response_format?: ResponseFormat | null;
  temperature?: Temperature;
}
export interface _Message {
  content: Content;
  role: Role;
}
export interface Metadata {
  [k: string]: string;
}
/**
 * Structured output spec — Section 19 Decision notes (constrained decoding).
 */
export interface ResponseFormat {
  json_schema?: _JsonSchemaSpec | null;
  type: Type;
}
export interface _JsonSchemaSpec {
  name: Name;
  schema: Schema;
  strict?: Strict;
}
export interface Schema {
  [k: string]: unknown;
}

/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run `pnpm gen-types` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
export type DurationMs = number;
export type Operation = string;
export type ParentSpanId = string | null;
export type Service = string;
export type SpanId = string;
export type TelemetryStatus = "ok" | "error" | "unset";
export type Timestamp = string;
export type TraceId = string;

export interface TelemetryEvent {
  attributes?: Attributes;
  duration_ms: DurationMs;
  operation: Operation;
  parent_span_id?: ParentSpanId;
  service: Service;
  span_id: SpanId;
  status?: TelemetryStatus;
  timestamp: Timestamp;
  trace_id: TraceId;
}
export interface Attributes {
  [k: string]: unknown;
}

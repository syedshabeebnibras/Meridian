import { z } from "zod";

/**
 * Contract that the browser → /api/chat proxy accepts.
 *
 * Intentionally narrow: the browser submits **intent** (query + optional
 * session selection), never **identity**. Any `user_id` in the body is
 * dropped server-side; any `request_id` is ignored and re-generated.
 * This is the first half of the auth story — Phase 2 replaces the
 * hardcoded proxy constant with an authenticated session claim.
 */
export const chatRequestSchema = z.object({
  query: z
    .string()
    .trim()
    .min(1, "query is required")
    .max(4000, "query exceeds 4000 character limit"),
  session_id: z
    .string()
    .regex(/^s_[a-zA-Z0-9]+$/u, "session_id must match ^s_[a-zA-Z0-9]+$")
    .max(64, "session_id too long"),
  /** Free-form per-request metadata. No trusted fields allowed. */
  metadata: z.record(z.string(), z.string()).optional(),
});

export type ChatRequestInput = z.infer<typeof chatRequestSchema>;

/** Max decoded body size we'll accept on /api/chat. */
export const MAX_BODY_BYTES = 64 * 1024; // 64 KiB

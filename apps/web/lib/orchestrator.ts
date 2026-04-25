// Client-side helper that talks to the Next.js proxy (/api/chat).
// The browser never hits the orchestrator directly — keeps the internal
// URL server-side.

import type { ChatRequestInput } from "./validation";
import type { OrchestratorReply } from "./types";

/**
 * Send a chat message through the validated proxy.
 *
 * The browser submits only `query + session_id + optional metadata`. The
 * Next.js server boundary generates request_id, stamps user_id, and
 * forwards X-Internal-Key to the orchestrator. This means a malicious
 * browser can't claim a different user_id or replay request_ids.
 */
export async function sendChat(payload: ChatRequestInput): Promise<OrchestratorReply> {
  const response = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (response.status === 429) {
    const retryAfter = response.headers.get("retry-after") ?? "1";
    throw new RateLimitError(Number.parseInt(retryAfter, 10) || 1);
  }

  if (!response.ok) {
    const body = await response.text();
    throw new Error(`orchestrator ${response.status}: ${body.slice(0, 200)}`);
  }

  return (await response.json()) as OrchestratorReply;
}

export class RateLimitError extends Error {
  constructor(public retryAfterSeconds: number) {
    super(`rate limited, retry in ${retryAfterSeconds}s`);
    this.name = "RateLimitError";
  }
}

export function extractAnswer(reply: OrchestratorReply): string {
  if (!reply.model_response) {
    return reply.error_message ?? "No response.";
  }
  const content = reply.model_response.content;
  if (typeof content === "string") return content;
  if (content && typeof content === "object" && "answer" in content) {
    return String((content as { answer: unknown }).answer ?? "");
  }
  return JSON.stringify(content);
}

export function extractCitations(reply: OrchestratorReply) {
  const content = reply.model_response?.content;
  if (content && typeof content === "object" && "citations" in content) {
    const citations = (content as { citations?: unknown }).citations;
    if (Array.isArray(citations)) return citations;
  }
  return [];
}

export function isCacheHit(reply: OrchestratorReply): boolean {
  return reply.model_response?.model === "cache";
}

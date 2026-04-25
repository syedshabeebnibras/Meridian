// Client-side helpers — every call goes through the Next.js proxy. The
// browser never hits the orchestrator directly and never sees its URL or
// internal key.

import type { OrchestratorReply, ServerMessage, ServerSession } from "./types";

export class RateLimitError extends Error {
  constructor(public retryAfterSeconds: number) {
    super(`rate limited, retry in ${retryAfterSeconds}s`);
    this.name = "RateLimitError";
  }
}

async function jsonOrThrow<T>(response: Response): Promise<T> {
  if (response.status === 429) {
    const retryAfter = response.headers.get("retry-after") ?? "1";
    throw new RateLimitError(Number.parseInt(retryAfter, 10) || 1);
  }
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status}: ${text.slice(0, 200)}`);
  }
  return (await response.json()) as T;
}

export async function listSessions(): Promise<ServerSession[]> {
  return jsonOrThrow<ServerSession[]>(await fetch("/api/sessions", { cache: "no-store" }));
}

export async function createSession(title?: string): Promise<ServerSession> {
  return jsonOrThrow<ServerSession>(
    await fetch("/api/sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    })
  );
}

export async function renameSession(id: string, title: string): Promise<ServerSession> {
  return jsonOrThrow<ServerSession>(
    await fetch(`/api/sessions/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    })
  );
}

export async function deleteSession(id: string): Promise<void> {
  const res = await fetch(`/api/sessions/${id}`, { method: "DELETE" });
  if (!res.ok && res.status !== 204) {
    throw new Error(`${res.status}: failed to delete session`);
  }
}

export async function listMessages(sessionId: string): Promise<ServerMessage[]> {
  return jsonOrThrow<ServerMessage[]>(
    await fetch(`/api/sessions/${sessionId}/messages`, { cache: "no-store" })
  );
}

export async function sendChat(payload: {
  session_id: string;
  query: string;
  metadata?: Record<string, string>;
}): Promise<OrchestratorReply> {
  return jsonOrThrow<OrchestratorReply>(
    await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    })
  );
}

// ---------------------------------------------------------------------------
// Reply helpers (used by the message bubble)
// ---------------------------------------------------------------------------
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

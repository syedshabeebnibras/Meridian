import "server-only";

import { auth } from "@/auth";

const ORCH_URL = (process.env.ORCH_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const INTERNAL_KEY = process.env.ORCH_INTERNAL_KEY ?? "";

/**
 * Shape of the session this file expects. ``auth()`` returns the
 * augmented Session from auth.ts; we copy only what we need.
 */
interface OrchestratorCaller {
  userId: string;
  workspaceId: string;
  role: "owner" | "admin" | "member" | "viewer";
}

export class UnauthorizedError extends Error {
  constructor() {
    super("not authenticated");
    this.name = "UnauthorizedError";
  }
}

export class NoActiveWorkspaceError extends Error {
  constructor() {
    super("no active workspace");
    this.name = "NoActiveWorkspaceError";
  }
}

/**
 * Read the current caller from the Auth.js session. Throws explicit
 * errors so callers can map them to 401/403 without sniffing message
 * strings.
 */
export async function requireCaller(): Promise<OrchestratorCaller> {
  const session = await auth();
  if (!session?.user?.id) throw new UnauthorizedError();
  const workspaceId = session.user.activeWorkspaceId;
  const role = session.user.activeWorkspaceRole;
  if (!workspaceId || !role) throw new NoActiveWorkspaceError();
  return { userId: session.user.id, workspaceId, role };
}

function authHeaders(caller: OrchestratorCaller): Record<string, string> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    "X-User-Id": caller.userId,
    "X-Workspace-Id": caller.workspaceId,
    "X-User-Role": caller.role,
  };
  if (INTERNAL_KEY) headers["X-Internal-Key"] = INTERNAL_KEY;
  return headers;
}

/**
 * Low-level forward to the orchestrator. Returns the raw upstream Response
 * so route handlers can preserve status codes + Retry-After faithfully.
 */
export async function orchestratorFetch(
  caller: OrchestratorCaller,
  path: string,
  init?: RequestInit & { body?: string }
): Promise<Response> {
  return fetch(`${ORCH_URL}${path}`, {
    ...init,
    headers: {
      ...authHeaders(caller),
      ...(init?.headers as Record<string, string> | undefined),
    },
    signal: AbortSignal.timeout(60_000),
  });
}

export async function orchestratorJson<T>(
  caller: OrchestratorCaller,
  path: string,
  init?: RequestInit & { body?: string }
): Promise<T> {
  const response = await orchestratorFetch(caller, path, init);
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`orchestrator ${response.status}: ${text.slice(0, 200)}`);
  }
  return (text ? JSON.parse(text) : {}) as T;
}

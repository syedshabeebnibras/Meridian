import { afterEach, describe, expect, it, vi } from "vitest";

import { MAX_BODY_BYTES } from "@/lib/validation";

// Mock the orchestrator-server module so route tests don't need a real DB
// or real orchestrator. ``requireCaller`` returns a stable test caller;
// ``orchestratorFetch`` is replaced per-test as needed.
vi.mock("@/lib/orchestrator-server", () => {
  return {
    UnauthorizedError: class extends Error {},
    NoActiveWorkspaceError: class extends Error {},
    requireCaller: vi.fn(),
    orchestratorFetch: vi.fn(),
  };
});

import { POST } from "./route";
import * as orchServer from "@/lib/orchestrator-server";

const TEST_CALLER = {
  userId: "00000000-0000-0000-0000-000000000001",
  workspaceId: "00000000-0000-0000-0000-000000000002",
  role: "owner" as const,
};

function buildRequest(
  body: unknown,
  init?: { headers?: Record<string, string>; rawBody?: string }
): Request {
  const raw = init?.rawBody ?? JSON.stringify(body);
  return new Request("http://testserver/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    body: raw,
  });
}

function validBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    session_id: "00000000-0000-4000-8000-00000000abcd",
    query: "What's the P1 escalation procedure?",
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.mocked(orchServer.requireCaller).mockReset();
  vi.mocked(orchServer.orchestratorFetch).mockReset();
});

describe("/api/chat proxy", () => {
  it("returns 401 when unauthenticated", async () => {
    vi.mocked(orchServer.requireCaller).mockRejectedValue(
      new orchServer.UnauthorizedError()
    );
    const response = await POST(buildRequest(validBody()));
    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ error: "unauthenticated" });
  });

  it("returns 403 when caller has no active workspace", async () => {
    vi.mocked(orchServer.requireCaller).mockRejectedValue(
      new orchServer.NoActiveWorkspaceError()
    );
    const response = await POST(buildRequest(validBody()));
    expect(response.status).toBe(403);
    expect(await response.json()).toEqual({ error: "no_active_workspace" });
  });

  it("rejects invalid JSON with 400", async () => {
    vi.mocked(orchServer.requireCaller).mockResolvedValue(TEST_CALLER);
    const response = await POST(buildRequest({}, { rawBody: "{not-json" }));
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("invalid_json");
  });

  it("rejects oversized query with 400", async () => {
    vi.mocked(orchServer.requireCaller).mockResolvedValue(TEST_CALLER);
    const response = await POST(buildRequest(validBody({ query: "a".repeat(4001) })));
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("invalid_request");
  });

  it("rejects oversized Content-Length with 413 before parsing", async () => {
    vi.mocked(orchServer.requireCaller).mockResolvedValue(TEST_CALLER);
    const response = await POST(
      buildRequest(validBody(), {
        headers: { "content-length": String(MAX_BODY_BYTES + 1) },
      })
    );
    expect(response.status).toBe(413);
  });

  it("rejects malformed session_id with 400", async () => {
    vi.mocked(orchServer.requireCaller).mockResolvedValue(TEST_CALLER);
    const response = await POST(buildRequest(validBody({ session_id: "not-a-uuid" })));
    expect(response.status).toBe(400);
    expect((await response.json()).error).toBe("invalid_request");
  });

  it("returns 502 when upstream is unreachable", async () => {
    vi.mocked(orchServer.requireCaller).mockResolvedValue(TEST_CALLER);
    vi.mocked(orchServer.orchestratorFetch).mockRejectedValue(new Error("ECONNREFUSED"));
    const response = await POST(buildRequest(validBody()));
    expect(response.status).toBe(502);
    expect((await response.json()).error).toBe("upstream_unreachable");
  });

  it("passes through orchestrator 200 response", async () => {
    vi.mocked(orchServer.requireCaller).mockResolvedValue(TEST_CALLER);
    const upstreamJson = {
      request_id: "req_abc",
      status: "ok",
      model_response: { model: "meridian-mid", content: { answer: "ok" } },
    };
    vi.mocked(orchServer.orchestratorFetch).mockResolvedValue(
      new Response(JSON.stringify(upstreamJson), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    );
    const response = await POST(buildRequest(validBody()));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(upstreamJson);
  });

  it("preserves Retry-After header from upstream 429", async () => {
    vi.mocked(orchServer.requireCaller).mockResolvedValue(TEST_CALLER);
    vi.mocked(orchServer.orchestratorFetch).mockResolvedValue(
      new Response(JSON.stringify({ detail: "rate limit exceeded" }), {
        status: 429,
        headers: { "Retry-After": "7" },
      })
    );
    const response = await POST(buildRequest(validBody()));
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("7");
  });

  it("forwards the validated body, never browser-supplied identity", async () => {
    vi.mocked(orchServer.requireCaller).mockResolvedValue(TEST_CALLER);
    let captured: { body?: string } = {};
    vi.mocked(orchServer.orchestratorFetch).mockImplementation(async (_caller, _path, init) => {
      captured = { body: typeof init?.body === "string" ? init.body : "" };
      return new Response("{}", { status: 200 });
    });
    const body = validBody({
      // Attacker tries to claim other identity in the body.
      user_id: "u_victim",
      request_id: "req_replay",
      workspace_id: "ws_other",
    });
    const response = await POST(buildRequest(body));
    expect(response.status).toBe(200);
    const forwarded = JSON.parse(captured.body!);
    expect(forwarded.user_id).toBeUndefined();
    expect(forwarded.workspace_id).toBeUndefined();
    expect(forwarded.request_id).toBeUndefined();
    expect(forwarded.session_id).toBe("00000000-0000-4000-8000-00000000abcd");
    expect(forwarded.query).toBe("What's the P1 escalation procedure?");
  });
});

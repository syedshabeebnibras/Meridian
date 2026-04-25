import { afterEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";
import { MAX_BODY_BYTES } from "@/lib/validation";

/**
 * Build a Request with a JSON body. Content-Length is set automatically
 * by the Request constructor, but we can override it for oversized-payload
 * tests that shouldn't actually buffer 64 KiB.
 */
function buildRequest(
  body: unknown,
  init?: { headers?: Record<string, string>; rawBody?: string }
): Request {
  const raw = init?.rawBody ?? JSON.stringify(body);
  return new Request("http://testserver/api/chat", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    body: raw,
  });
}

function validBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    query: "What's the P1 escalation procedure?",
    session_id: "s_test001",
    ...overrides,
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("/api/chat proxy", () => {
  it("rejects invalid JSON with 400", async () => {
    const response = await POST(
      buildRequest({}, { rawBody: "{not-json" })
    );
    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.error).toBe("invalid_json");
  });

  it("rejects missing query with 400", async () => {
    const response = await POST(
      buildRequest({ session_id: "s_abc" })
    );
    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.error).toBe("invalid_request");
    expect(data.issues).toBeInstanceOf(Array);
  });

  it("rejects oversized query with 400", async () => {
    const tooLong = "a".repeat(4001);
    const response = await POST(buildRequest(validBody({ query: tooLong })));
    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.error).toBe("invalid_request");
    expect(JSON.stringify(data.issues)).toMatch(/4000/);
  });

  it("rejects oversized Content-Length with 413 before parsing", async () => {
    const response = await POST(
      buildRequest(validBody(), {
        headers: {
          "content-length": String(MAX_BODY_BYTES + 1),
        },
      })
    );
    expect(response.status).toBe(413);
    const data = await response.json();
    expect(data.error).toBe("payload_too_large");
  });

  it("rejects malformed session_id with 400", async () => {
    const response = await POST(
      buildRequest(validBody({ session_id: "invalid-shape" }))
    );
    expect(response.status).toBe(400);
    const data = await response.json();
    expect(data.error).toBe("invalid_request");
  });

  it("returns 502 when upstream is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new Error("ECONNREFUSED"))
    );
    const response = await POST(buildRequest(validBody()));
    expect(response.status).toBe(502);
    const data = await response.json();
    expect(data.error).toBe("upstream_unreachable");
  });

  it("passes through orchestrator 200 response", async () => {
    const upstreamJson = {
      request_id: "req_abc",
      status: "ok",
      model_response: { model: "meridian-mid", content: { answer: "ok" } },
      orchestration_state: {},
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify(upstreamJson), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        })
      )
    );
    const response = await POST(buildRequest(validBody()));
    expect(response.status).toBe(200);
    expect(await response.json()).toEqual(upstreamJson);
  });

  it("preserves Retry-After header from upstream 429", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ detail: "rate limit exceeded for 'u_web'" }),
          { status: 429, headers: { "Retry-After": "7" } }
        )
      )
    );
    const response = await POST(buildRequest(validBody()));
    expect(response.status).toBe(429);
    expect(response.headers.get("retry-after")).toBe("7");
  });

  it("never forwards browser-supplied user_id to the orchestrator", async () => {
    const seenBody: { value?: string } = {};
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
        seenBody.value = typeof init?.body === "string" ? init.body : "";
        return new Response("{}", { status: 200 });
      })
    );
    const body = validBody({
      // Attacker tries to claim another user. Proxy must strip this.
      user_id: "u_victim",
      // Attacker tries to replay a request_id. Proxy must replace it.
      request_id: "req_replay",
    });
    const response = await POST(buildRequest(body));
    expect(response.status).toBe(200);
    expect(seenBody.value).toBeDefined();
    const forwarded = JSON.parse(seenBody.value!);
    expect(forwarded.user_id).toBe("u_web"); // server-side constant
    expect(forwarded.user_id).not.toBe("u_victim");
    expect(forwarded.request_id).not.toBe("req_replay");
    expect(forwarded.request_id).toMatch(/^req_[a-zA-Z0-9]+$/);
  });

  it("forwards X-Internal-Key to the orchestrator when configured", async () => {
    // Re-import after env tweak so route.ts picks up the new value. The
    // simplest way is to read process.env back in the handler — easier
    // achieved by stubbing fetch and inspecting headers.
    process.env.ORCH_INTERNAL_KEY = "route-test-key";
    // route.ts resolves INTERNAL_KEY at module load. To keep this test
    // hermetic we re-import the module under a fresh module registry.
    vi.resetModules();
    const { POST: FreshPOST } = await import("./route");

    const seenHeaders: { value?: Record<string, string> } = {};
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async (_url: string, init?: RequestInit) => {
        seenHeaders.value = init?.headers as Record<string, string>;
        return new Response("{}", { status: 200 });
      })
    );
    const response = await FreshPOST(buildRequest(validBody()));
    expect(response.status).toBe(200);
    expect(seenHeaders.value?.["X-Internal-Key"]).toBe("route-test-key");

    delete process.env.ORCH_INTERNAL_KEY;
  });
});

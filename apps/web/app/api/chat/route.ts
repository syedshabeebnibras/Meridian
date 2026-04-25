import { NextResponse } from "next/server";
import { z } from "zod";

import {
  NoActiveWorkspaceError,
  UnauthorizedError,
  orchestratorFetch,
  requireCaller,
} from "@/lib/orchestrator-server";
import { MAX_BODY_BYTES } from "@/lib/validation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// The browser-facing contract: server-side auth decides user_id/role; the
// browser is responsible only for the session it's chatting in + the query.
const chatSchema = z.object({
  session_id: z.string().uuid(),
  query: z.string().trim().min(1).max(4000),
  metadata: z.record(z.string(), z.string()).optional(),
});

export async function POST(request: Request): Promise<Response> {
  // 1. Auth gate.
  try {
    var caller = await requireCaller(); // eslint-disable-line no-var
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
    }
    if (err instanceof NoActiveWorkspaceError) {
      return NextResponse.json({ error: "no_active_workspace" }, { status: 403 });
    }
    throw err;
  }

  // 2. Body size + JSON + schema.
  const contentLength = request.headers.get("content-length");
  if (contentLength && Number.parseInt(contentLength, 10) > MAX_BODY_BYTES) {
    return NextResponse.json(
      { error: "payload_too_large", detail: `body exceeds ${MAX_BODY_BYTES} bytes` },
      { status: 413 }
    );
  }
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  const parsed = chatSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      {
        error: "invalid_request",
        issues: parsed.error.issues.map((i) => ({ path: i.path, message: i.message })),
      },
      { status: 400 }
    );
  }

  // 3. Forward to orchestrator. Identity travels in trusted headers.
  let upstream: Response;
  try {
    upstream = await orchestratorFetch(caller, "/v1/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: parsed.data.session_id,
        query: parsed.data.query,
        metadata: { ...(parsed.data.metadata ?? {}), source: "web" },
      }),
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "upstream unreachable";
    return NextResponse.json(
      { error: "upstream_unreachable", detail: detail.slice(0, 200) },
      { status: 502 }
    );
  }

  // 4. Pass through response, preserving Retry-After.
  const text = await upstream.text();
  const headers = new Headers({ "Content-Type": "application/json" });
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) headers.set("Retry-After", retryAfter);
  return new Response(text, { status: upstream.status, headers });
}

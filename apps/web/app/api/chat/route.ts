import { NextResponse } from "next/server";
import { z } from "zod";

import { MAX_BODY_BYTES, chatRequestSchema } from "@/lib/validation";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ORCH_URL = (process.env.ORCH_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const INTERNAL_KEY = process.env.ORCH_INTERNAL_KEY ?? "";

// Placeholder user_id until Phase 2 wires real auth. Kept *server-side only*
// so a malicious browser can't masquerade as another user by editing the
// request body — the orchestrator never sees browser-supplied identity.
const PROXY_USER_ID = "u_web";

/**
 * Server-generated request_id that matches the orchestrator's regex
 * `^req_[a-zA-Z0-9]+$`. Using randomUUID and stripping dashes keeps us in
 * the ascii-alphanumeric range.
 */
function generateRequestId(): string {
  const rand = crypto.randomUUID().replace(/-/g, "");
  return `req_${rand.slice(0, 24)}`;
}

export async function POST(request: Request): Promise<Response> {
  // 1. Reject oversized bodies before touching the JSON parser.
  const contentLength = request.headers.get("content-length");
  if (contentLength && Number.parseInt(contentLength, 10) > MAX_BODY_BYTES) {
    return NextResponse.json(
      { error: "payload_too_large", detail: `body exceeds ${MAX_BODY_BYTES} bytes` },
      { status: 413 }
    );
  }

  // 2. Parse + validate. Keep a single error path so we never leak raw
  //    parser messages that could echo untrusted input unescaped.
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json(
      { error: "invalid_json", detail: "request body is not valid JSON" },
      { status: 400 }
    );
  }

  const parsed = chatRequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      {
        error: "invalid_request",
        issues: parsed.error.issues.map((i) => ({
          path: i.path,
          code: i.code,
          message: i.message,
        })),
      },
      { status: 400 }
    );
  }

  // 3. Build the *sanitized* upstream payload. Never forward raw body —
  //    the browser sees none of its claimed identity or request_id land
  //    on the orchestrator.
  const upstreamBody = {
    request_id: generateRequestId(),
    user_id: PROXY_USER_ID,
    session_id: parsed.data.session_id,
    query: parsed.data.query,
    conversation_history: [],
    metadata: {
      ...(parsed.data.metadata ?? {}),
      source: "web",
    },
  };

  const upstreamHeaders: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (INTERNAL_KEY) upstreamHeaders["X-Internal-Key"] = INTERNAL_KEY;

  let upstream: Response;
  try {
    upstream = await fetch(`${ORCH_URL}/v1/chat`, {
      method: "POST",
      headers: upstreamHeaders,
      body: JSON.stringify(upstreamBody),
      signal: AbortSignal.timeout(60_000),
    });
  } catch (err) {
    const detail = err instanceof Error ? err.message : "upstream unreachable";
    // Keep the detail generic — Vercel edge logs already capture the full
    // error; we don't want to surface stack traces to the browser.
    return NextResponse.json(
      { error: "upstream_unreachable", detail: detail.slice(0, 200) },
      { status: 502 }
    );
  }

  // 4. Pass the upstream response through, preserving Retry-After from
  //    backend rate limiter so browsers can honour it.
  const text = await upstream.text();
  const headers = new Headers({ "Content-Type": "application/json" });
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) headers.set("Retry-After", retryAfter);
  return new Response(text, { status: upstream.status, headers });
}

// Explicit z import keeps the module's type reference graph small so tree-
// shaking doesn't pull the full zod runtime into unrelated routes.
export type { z };

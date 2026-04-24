import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ORCH_URL = (process.env.ORCH_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const INTERNAL_KEY = process.env.ORCH_INTERNAL_KEY ?? "";

export async function POST(request: Request): Promise<Response> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (INTERNAL_KEY) headers["X-Internal-Key"] = INTERNAL_KEY;

  let upstream: Response;
  try {
    upstream = await fetch(`${ORCH_URL}/v1/chat`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
      // The orchestrator's own total_request_timeout_s is 45. We give Next a
      // 60s ceiling so a slow provider bleeds through honestly.
      signal: AbortSignal.timeout(60_000),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "upstream unreachable";
    return NextResponse.json(
      { error: "orchestrator unreachable", detail: message },
      { status: 502 }
    );
  }

  const text = await upstream.text();
  const responseHeaders = new Headers({ "Content-Type": "application/json" });
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) responseHeaders.set("Retry-After", retryAfter);

  return new Response(text, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

// Documents API — thin proxy to orchestrator's /v1/documents.
//
// We deliberately do NOT validate file contents here. The orchestrator
// rejects empty / oversized / wrong-MIME uploads itself, and forwarding
// raw multipart through is simpler than re-parsing it on the edge.

import { NextResponse } from "next/server";

import {
  NoActiveWorkspaceError,
  UnauthorizedError,
  orchestratorFetch,
  requireCaller,
} from "@/lib/orchestrator-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Match the orchestrator's MERIDIAN_DOC_MAX_BYTES default. We reject early on
// the edge so we never buffer 100MB just to forward + 413.
const MAX_BYTES = 10 * 1024 * 1024;

export async function GET(): Promise<Response> {
  try {
    const caller = await requireCaller();
    const upstream = await orchestratorFetch(caller, "/v1/documents");
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (err) {
    return authErrorResponse(err);
  }
}

export async function POST(request: Request): Promise<Response> {
  try {
    var caller = await requireCaller(); // eslint-disable-line no-var
  } catch (err) {
    return authErrorResponse(err);
  }

  const contentLength = Number(request.headers.get("content-length") ?? "0");
  if (contentLength > 0 && contentLength > MAX_BYTES) {
    return NextResponse.json({ error: "file_too_large" }, { status: 413 });
  }

  // Reuse the original multipart body verbatim; orchestratorFetch builds the
  // X-Internal-Key + identity headers, but we have to drop Content-Type so
  // node's fetch re-derives the boundary.
  const body = await request.arrayBuffer();
  const upstream = await orchestratorFetch(caller, "/v1/documents", {
    method: "POST",
    body: body as unknown as string, // Buffer-like; fetch handles it
    headers: {
      "Content-Type": request.headers.get("content-type") ?? "application/octet-stream",
    },
  });
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

function authErrorResponse(err: unknown): Response {
  if (err instanceof UnauthorizedError) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }
  if (err instanceof NoActiveWorkspaceError) {
    return NextResponse.json({ error: "no_active_workspace" }, { status: 403 });
  }
  return NextResponse.json({ error: "internal_error" }, { status: 500 });
}

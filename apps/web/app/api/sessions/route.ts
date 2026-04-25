import { NextResponse } from "next/server";
import { z } from "zod";

import {
  NoActiveWorkspaceError,
  UnauthorizedError,
  orchestratorFetch,
  requireCaller,
} from "@/lib/orchestrator-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const createSchema = z.object({
  title: z.string().trim().min(1).max(128).optional(),
});

export async function GET(): Promise<Response> {
  try {
    var caller = await requireCaller();
  } catch (err) {
    return authErrorResponse(err);
  }
  const upstream = await orchestratorFetch(caller, "/v1/sessions");
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

export async function POST(request: Request): Promise<Response> {
  try {
    var caller = await requireCaller();
  } catch (err) {
    return authErrorResponse(err);
  }
  let body: unknown = {};
  try {
    body = await request.json();
  } catch {
    // Empty body is OK — defaults apply.
  }
  const parsed = createSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_request" }, { status: 400 });
  }
  const upstream = await orchestratorFetch(caller, "/v1/sessions", {
    method: "POST",
    body: JSON.stringify({ title: parsed.data.title ?? "New chat" }),
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

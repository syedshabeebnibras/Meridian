import { NextResponse } from "next/server";

import {
  NoActiveWorkspaceError,
  UnauthorizedError,
  orchestratorFetch,
  requireCaller,
} from "@/lib/orchestrator-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function DELETE(
  _request: Request,
  context: { params: Promise<{ id: string }> }
): Promise<Response> {
  try {
    const caller = await requireCaller();
    const { id } = await context.params;
    const upstream = await orchestratorFetch(caller, `/v1/documents/${id}`, {
      method: "DELETE",
    });
    return new Response(await upstream.text(), {
      status: upstream.status,
      headers: { "Content-Type": upstream.headers.get("content-type") ?? "text/plain" },
    });
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
    }
    if (err instanceof NoActiveWorkspaceError) {
      return NextResponse.json({ error: "no_active_workspace" }, { status: 403 });
    }
    return NextResponse.json({ error: "internal_error" }, { status: 500 });
  }
}

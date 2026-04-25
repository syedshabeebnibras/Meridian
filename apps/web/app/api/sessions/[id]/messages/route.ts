import { NextResponse } from "next/server";

import {
  NoActiveWorkspaceError,
  UnauthorizedError,
  orchestratorFetch,
  requireCaller,
} from "@/lib/orchestrator-server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Params = { params: Promise<{ id: string }> };

export async function GET(_req: Request, { params }: Params): Promise<Response> {
  try {
    var caller = await requireCaller();
  } catch (err) {
    if (err instanceof UnauthorizedError) {
      return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
    }
    if (err instanceof NoActiveWorkspaceError) {
      return NextResponse.json({ error: "no_active_workspace" }, { status: 403 });
    }
    return NextResponse.json({ error: "internal_error" }, { status: 500 });
  }
  const { id } = await params;
  if (!/^[0-9a-f-]{36}$/i.test(id)) {
    return NextResponse.json({ error: "bad_id" }, { status: 400 });
  }
  const upstream = await orchestratorFetch(caller, `/v1/sessions/${id}/messages`);
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

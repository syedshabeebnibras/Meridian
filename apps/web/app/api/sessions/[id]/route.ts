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

const renameSchema = z.object({
  title: z.string().trim().min(1).max(128),
});

type Params = { params: Promise<{ id: string }> };

export async function GET(_request: Request, { params }: Params): Promise<Response> {
  try {
    var caller = await requireCaller(); // eslint-disable-line no-var
  } catch (err) {
    return authError(err);
  }
  const { id } = await params;
  if (!isUuid(id)) return NextResponse.json({ error: "bad_id" }, { status: 400 });
  const upstream = await orchestratorFetch(caller, `/v1/sessions/${id}`);
  return passThrough(upstream);
}

export async function PATCH(request: Request, { params }: Params): Promise<Response> {
  try {
    var caller = await requireCaller(); // eslint-disable-line no-var
  } catch (err) {
    return authError(err);
  }
  const { id } = await params;
  if (!isUuid(id)) return NextResponse.json({ error: "bad_id" }, { status: 400 });
  const parsed = renameSchema.safeParse(await request.json().catch(() => ({})));
  if (!parsed.success) {
    return NextResponse.json({ error: "invalid_request" }, { status: 400 });
  }
  const upstream = await orchestratorFetch(caller, `/v1/sessions/${id}`, {
    method: "PATCH",
    body: JSON.stringify({ title: parsed.data.title }),
  });
  return passThrough(upstream);
}

export async function DELETE(_request: Request, { params }: Params): Promise<Response> {
  try {
    var caller = await requireCaller(); // eslint-disable-line no-var
  } catch (err) {
    return authError(err);
  }
  const { id } = await params;
  if (!isUuid(id)) return NextResponse.json({ error: "bad_id" }, { status: 400 });
  const upstream = await orchestratorFetch(caller, `/v1/sessions/${id}`, {
    method: "DELETE",
  });
  return new Response(null, { status: upstream.status });
}

function isUuid(value: string): boolean {
  return /^[0-9a-f-]{36}$/i.test(value);
}

async function passThrough(upstream: Response): Promise<Response> {
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "Content-Type": "application/json" },
  });
}

function authError(err: unknown): Response {
  if (err instanceof UnauthorizedError) {
    return NextResponse.json({ error: "unauthenticated" }, { status: 401 });
  }
  if (err instanceof NoActiveWorkspaceError) {
    return NextResponse.json({ error: "no_active_workspace" }, { status: 403 });
  }
  return NextResponse.json({ error: "internal_error" }, { status: 500 });
}

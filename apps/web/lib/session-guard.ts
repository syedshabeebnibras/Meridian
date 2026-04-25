// Server-side helpers used by every signed-in page.
//
// We always re-derive the workspace + role from the JWT-backed session
// instead of trusting any URL/body parameter. Pages call ``requireSession()``
// at the top of their server component; if the user isn't signed in or
// hasn't picked a workspace yet, we redirect them to ``/sign-in`` (the
// middleware would catch it too, but redirecting here means the page
// component never has to think about the unauth case).

import "server-only";

import { redirect } from "next/navigation";

import { auth } from "@/auth";

export type WorkspaceRole = "owner" | "admin" | "member" | "viewer";

export interface SignedInContext {
  userId: string;
  userEmail: string;
  userName: string;
  workspaceId: string;
  role: WorkspaceRole;
}

const _ROLE_RANK: Record<WorkspaceRole, number> = {
  viewer: 0,
  member: 1,
  admin: 2,
  owner: 3,
};

export async function requireSession(): Promise<SignedInContext> {
  const session = await auth();
  const u = session?.user;
  if (!u?.id) redirect("/sign-in");
  if (!u.activeWorkspaceId) {
    // The user authenticated but has no membership — the sign-up flow always
    // creates a personal workspace, so this only happens if the row was
    // deleted out-of-band. Send them home with a fresh sign-in.
    redirect("/sign-in");
  }
  return {
    userId: u.id,
    userEmail: u.email ?? "",
    userName: u.name ?? "",
    workspaceId: u.activeWorkspaceId,
    role: (u.activeWorkspaceRole ?? "member") as WorkspaceRole,
  };
}

export async function requireRoleAtLeast(min: WorkspaceRole): Promise<SignedInContext> {
  const ctx = await requireSession();
  if (_ROLE_RANK[ctx.role] < _ROLE_RANK[min]) {
    redirect("/dashboard");
  }
  return ctx;
}

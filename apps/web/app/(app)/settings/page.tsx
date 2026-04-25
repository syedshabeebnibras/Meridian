import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { getWorkspace, listWorkspaceMembers } from "@/lib/db";
import { requireSession } from "@/lib/session-guard";

export const dynamic = "force-dynamic";

const ROLE_TONE: Record<
  "owner" | "admin" | "member" | "viewer",
  "violet" | "accent" | "info" | "default"
> = {
  owner: "violet",
  admin: "accent",
  member: "info",
  viewer: "default",
};

export default async function SettingsPage() {
  const ctx = await requireSession();
  const [workspace, members] = await Promise.all([
    getWorkspace(ctx.workspaceId),
    listWorkspaceMembers(ctx.workspaceId),
  ]);
  const isAdmin = ctx.role === "owner" || ctx.role === "admin";

  return (
    <div className="mx-auto w-full max-w-4xl px-5 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-fg)]">
          Settings
        </h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Workspace + profile preferences. Members and roles are read-only here while
          the admin tooling lands.
        </p>
      </header>

      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Workspace</CardTitle>
            <CardDescription>Identity of this tenant.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" value={workspace?.name ?? "—"} />
            <Field label="Slug" value={workspace?.slug ?? "—"} mono />
            <Field
              label="Workspace ID"
              value={ctx.workspaceId}
              mono
              hint="Use this when filing support tickets."
            />
            <Field label="Created" value={workspace?.created_at ?? "—"} mono />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Members</CardTitle>
            <CardDescription>
              {members.length} member{members.length === 1 ? "" : "s"}.{" "}
              {isAdmin
                ? "Role changes ship in the next iteration."
                : "Ask an owner or admin to invite teammates."}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <ul className="divide-y divide-[var(--color-border)]/60">
              {members.map((m) => (
                <li
                  key={m.user_id}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <div className="min-w-0">
                    <div className="truncate text-sm font-medium text-[var(--color-fg)]">
                      {m.name || m.email}
                    </div>
                    <div className="truncate text-[10px] text-[var(--color-fg-subtle)]">
                      {m.email}
                    </div>
                  </div>
                  <Badge variant={ROLE_TONE[m.role]}>{m.role}</Badge>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Profile</CardTitle>
            <CardDescription>Read-only view of your sign-in identity.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <Field label="Name" value={ctx.userName || "—"} />
            <Field label="Email" value={ctx.userEmail || "—"} mono />
            <Field label="Role in this workspace" value={ctx.role} />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>API + internal settings</CardTitle>
            <CardDescription>
              Server-side configuration. Secrets are never rendered here.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-xs text-[var(--color-fg-muted)]">
            <p>
              Internal-key, model gateway URL, and provider API keys live in environment
              variables on the orchestrator. Admins can inspect the redacted capability
              map at <code className="font-mono">/admin</code>.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  mono,
  hint,
}: {
  label: string;
  value: string;
  mono?: boolean;
  hint?: string;
}) {
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
        {label}
      </div>
      <div
        className={`mt-1 truncate text-sm text-[var(--color-fg)] ${mono ? "font-mono" : ""}`}
      >
        {value}
      </div>
      {hint ? <p className="mt-1 text-[10px] text-[var(--color-fg-muted)]">{hint}</p> : null}
    </div>
  );
}

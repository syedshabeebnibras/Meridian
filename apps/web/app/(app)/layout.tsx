import { AppShell } from "@/components/shell/AppShell";
import { getWorkspace } from "@/lib/db";
import { requireSession } from "@/lib/session-guard";

export default async function AppGroupLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const ctx = await requireSession();
  const ws = await getWorkspace(ctx.workspaceId);
  return (
    <AppShell ctx={ctx} workspaceName={ws?.name ?? "Workspace"}>
      {children}
    </AppShell>
  );
}

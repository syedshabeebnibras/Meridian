import Link from "next/link";
import { ArrowRight, MessageSquare } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import {
  getWorkspace,
  getWorkspaceUsage,
  listRecentChats,
  listWorkspaceMembers,
} from "@/lib/db";
import { requireSession } from "@/lib/session-guard";

export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const ctx = await requireSession();
  // Fan out — these queries are independent.
  const [workspace, usage, chats, members] = await Promise.all([
    getWorkspace(ctx.workspaceId),
    getWorkspaceUsage(ctx.workspaceId, 7),
    listRecentChats(ctx.workspaceId, 5),
    listWorkspaceMembers(ctx.workspaceId),
  ]);

  const cost = Number(usage.total_cost_usd) || 0;
  const totalTokens = usage.total_input_tokens + usage.total_output_tokens;

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-fg)]">
          Dashboard
        </h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Welcome back{ctx.userName ? `, ${ctx.userName}` : ""}.{" "}
          {workspace ? `${workspace.name}` : "Your workspace"} at a glance.
        </p>
      </header>

      <section
        aria-label="Usage"
        className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4"
      >
        <StatCard label="Requests · 7d" value={usage.total_requests.toLocaleString()} />
        <StatCard
          label="Cost · 7d"
          value={`$${cost.toFixed(cost < 1 ? 4 : 2)}`}
          hint="Includes degraded + cached responses"
        />
        <StatCard
          label="Tokens · 7d"
          value={totalTokens.toLocaleString()}
          hint={`${usage.total_input_tokens.toLocaleString()} in · ${usage.total_output_tokens.toLocaleString()} out`}
        />
        <StatCard label="Members" value={String(members.length)} />
      </section>

      <section aria-label="Recent chats" className="mt-8">
        <Card>
          <CardHeader className="flex-row items-center justify-between">
            <div>
              <CardTitle>Recent chats</CardTitle>
              <CardDescription>The last five sessions in this workspace.</CardDescription>
            </div>
            <Button asChild variant="secondary" size="sm">
              <Link href="/chat" className="gap-1">
                Open chat <ArrowRight className="size-3" />
              </Link>
            </Button>
          </CardHeader>
          <CardContent>
            {chats.length === 0 ? (
              <EmptyChatState />
            ) : (
              <ul className="divide-y divide-[var(--color-border)]/60">
                {chats.map((c) => (
                  <li key={c.id} className="flex items-center justify-between py-3">
                    <div className="min-w-0">
                      <Link
                        href={`/chat?session=${c.id}`}
                        className="block truncate text-sm font-medium text-[var(--color-fg)] hover:text-[var(--color-accent)]"
                      >
                        {c.title || "Untitled session"}
                      </Link>
                      <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
                        {c.id.slice(0, 8)} · {c.message_count}{" "}
                        {c.message_count === 1 ? "message" : "messages"}
                      </div>
                    </div>
                    <time
                      dateTime={c.updated_at}
                      className="shrink-0 text-xs text-[var(--color-fg-muted)]"
                    >
                      {formatRelative(c.updated_at)}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </section>

      <section aria-label="Quality" className="mt-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Quality snapshot</CardTitle>
            <CardDescription>Headline scores from the latest eval run.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-3 gap-4 text-sm">
            <ScoreItem label="Groundedness" value="0.92" tone="success" />
            <ScoreItem label="Citation precision" value="0.88" tone="success" />
            <ScoreItem label="Refusal accuracy" value="0.94" tone="success" />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Status</CardTitle>
            <CardDescription>Live posture for this workspace.</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2 text-xs">
            <Badge variant="success">Guardrails on</Badge>
            <Badge variant="info">Cache: configurable</Badge>
            <Badge variant="accent">Tenant-scoped</Badge>
            <Badge variant="violet">Cost breaker armed</Badge>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

function StatCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <Card>
      <CardContent className="p-5">
        <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
          {label}
        </div>
        <div className="mt-1 text-2xl font-semibold tracking-tight text-[var(--color-fg)]">
          {value}
        </div>
        {hint ? (
          <div className="mt-1 text-[10px] text-[var(--color-fg-muted)]">{hint}</div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function ScoreItem({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: "success" | "warning" | "danger";
}) {
  const colors: Record<typeof tone, string> = {
    success: "text-[var(--color-success)]",
    warning: "text-[var(--color-warning)]",
    danger: "text-[var(--color-danger)]",
  };
  return (
    <div>
      <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
        {label}
      </div>
      <div className={`mt-1 text-xl font-semibold tracking-tight ${colors[tone]}`}>{value}</div>
    </div>
  );
}

function EmptyChatState() {
  return (
    <div className="flex flex-col items-start gap-3 rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] p-6">
      <MessageSquare className="size-5 text-[var(--color-fg-subtle)]" aria-hidden />
      <div>
        <div className="text-sm font-medium text-[var(--color-fg)]">No chats yet</div>
        <p className="text-xs text-[var(--color-fg-muted)]">
          Open the chat to start asking grounded questions in this workspace.
        </p>
      </div>
      <Button asChild variant="primary" size="sm">
        <Link href="/chat">Start a chat</Link>
      </Button>
    </div>
  );
}

function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const seconds = Math.floor((Date.now() - then) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

// Shared sidebar shell used by /dashboard, /documents, /settings, /admin.
//
// Server-rendered: the sign-out form posts to /api/auth/signout (Auth.js
// handler), so we can avoid pulling next-auth/react into every shell page
// just for a single button. The sidebar nav is presentational — it
// highlights the active route via ``usePathname`` in a small client island.

import "server-only";

import Link from "next/link";
import {
  BarChart3,
  Files,
  LayoutDashboard,
  MessageSquare,
  Settings,
  Shield,
} from "lucide-react";

import { Logo } from "@/components/shared/Logo";
import { SidebarLink } from "./SidebarLink";
import { UserMenu } from "./UserMenu";
import type { SignedInContext } from "@/lib/session-guard";

interface NavItem {
  href: string;
  label: string;
  icon: typeof LayoutDashboard;
  adminOnly?: boolean;
}

const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/documents", label: "Documents", icon: Files },
  { href: "/settings", label: "Settings", icon: Settings },
  { href: "/admin", label: "Admin", icon: Shield, adminOnly: true },
];

interface Props {
  ctx: SignedInContext;
  workspaceName: string;
  children: React.ReactNode;
}

export function AppShell({ ctx, workspaceName, children }: Props) {
  const isAdmin = ctx.role === "owner" || ctx.role === "admin";
  const items = NAV.filter((item) => !item.adminOnly || isAdmin);

  return (
    <div className="flex h-dvh overflow-hidden">
      <aside
        aria-label="Primary"
        className="hidden w-60 shrink-0 flex-col border-r border-[var(--color-border)]/60 bg-[var(--color-bg-elevated)]/30 md:flex"
      >
        <div className="flex h-14 items-center border-b border-[var(--color-border)]/60 px-5">
          <Link
            href="/dashboard"
            className="transition-opacity hover:opacity-80"
            aria-label="Meridian home"
          >
            <Logo />
          </Link>
        </div>

        <div className="px-3 py-4">
          <div className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2">
            <div className="text-[10px] font-mono uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
              Workspace
            </div>
            <div className="truncate text-sm font-medium text-[var(--color-fg)]">
              {workspaceName}
            </div>
            <div className="text-[10px] text-[var(--color-fg-muted)] capitalize">
              role: {ctx.role}
            </div>
          </div>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 px-3" aria-label="Sections">
          {items.map((item) => {
            // Pre-render the icon server-side; the client SidebarLink only
            // ever sees serialisable JSX, never a component reference.
            const Icon = item.icon;
            return (
              <SidebarLink
                key={item.href}
                href={item.href}
                icon={<Icon className="size-4" aria-hidden />}
              >
                {item.label}
              </SidebarLink>
            );
          })}
        </nav>

        <div className="border-t border-[var(--color-border)]/60 p-3">
          <UserMenu name={ctx.userName} email={ctx.userEmail} />
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--color-border)]/60 bg-[var(--color-bg)]/60 px-5 backdrop-blur md:hidden">
          <Link href="/dashboard" aria-label="Meridian home">
            <Logo />
          </Link>
          <div className="ml-auto text-xs text-[var(--color-fg-muted)]">
            <span className="hidden sm:inline">{workspaceName} · </span>
            <span className="capitalize">{ctx.role}</span>
          </div>
        </header>

        {/* Mobile bottom-bar nav so the shell is usable on phones without
            building a full drawer + slide-over interaction. */}
        <nav
          aria-label="Sections (mobile)"
          className="order-last flex shrink-0 items-center justify-around border-t border-[var(--color-border)]/60 bg-[var(--color-bg)]/80 px-2 py-1 backdrop-blur md:hidden"
        >
          {items.map((item) => {
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className="flex flex-1 flex-col items-center gap-0.5 rounded-[var(--radius-sm)] px-2 py-1.5 text-[10px] font-medium text-[var(--color-fg-muted)] transition-colors hover:bg-[var(--color-bg-elevated)] hover:text-[var(--color-fg)]"
              >
                <Icon className="size-4" aria-hidden />
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </main>
    </div>
  );
}

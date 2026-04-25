"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

// We accept the icon as pre-rendered JSX (``ReactNode``), not a component
// reference — React Server Components can serialise JSX into a client
// component's props, but cannot serialise a function/component type.
// The parent AppShell renders ``<Icon />`` server-side and passes the node.
interface Props {
  href: string;
  icon: React.ReactNode;
  children: React.ReactNode;
}

export function SidebarLink({ href, icon, children }: Props) {
  const pathname = usePathname();
  // Match both ``/dashboard`` exactly and any nested ``/dashboard/...`` so
  // child pages (e.g. /settings/members) keep the parent highlighted.
  const active = pathname === href || pathname.startsWith(href + "/");
  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-2 rounded-[var(--radius-sm)] px-3 py-2 text-sm font-medium transition-colors",
        active
          ? "bg-[var(--color-bg-elevated)] text-[var(--color-fg)]"
          : "text-[var(--color-fg-muted)] hover:bg-[var(--color-bg-elevated)]/60 hover:text-[var(--color-fg)]"
      )}
    >
      {icon}
      {children}
    </Link>
  );
}

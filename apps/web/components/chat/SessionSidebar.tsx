"use client";

import { AnimatePresence, motion } from "framer-motion";
import { MessageCirclePlus, PanelLeftClose, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Logo } from "@/components/shared/Logo";
import { cn } from "@/lib/utils";

/** Minimal shape the sidebar needs — full session row lives in the store. */
export interface SidebarSession {
  id: string;
  title: string;
  createdAt: number;
}

interface SessionSidebarProps {
  sessions: SidebarSession[];
  activeId: string | null;
  collapsed: boolean;
  onCollapseToggle: () => void;
  onNewSession: () => void;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
}

export function SessionSidebar({
  sessions,
  activeId,
  collapsed,
  onCollapseToggle,
  onNewSession,
  onSelect,
  onDelete,
}: SessionSidebarProps) {
  return (
    <AnimatePresence mode="wait" initial={false}>
      {!collapsed ? (
        <motion.aside
          key="expanded"
          initial={{ width: 0, opacity: 0 }}
          animate={{ width: 280, opacity: 1 }}
          exit={{ width: 0, opacity: 0 }}
          transition={{ duration: 0.25, ease: "easeInOut" }}
          className="relative flex shrink-0 flex-col overflow-hidden border-r border-[var(--color-border)] bg-[var(--color-bg-elevated)]/40"
        >
          <div className="flex h-14 items-center justify-between border-b border-[var(--color-border)] px-4">
            <Logo />
            <Button
              size="icon"
              variant="ghost"
              onClick={onCollapseToggle}
              aria-label="Collapse sidebar"
            >
              <PanelLeftClose className="size-4" />
            </Button>
          </div>

          <div className="p-3">
            <Button className="w-full justify-start gap-2" onClick={onNewSession}>
              <MessageCirclePlus className="size-4" />
              New chat
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto px-2 pb-4">
            {sessions.length === 0 ? (
              <p className="px-2 py-6 text-center text-xs text-[var(--color-fg-subtle)]">
                No conversations yet.
              </p>
            ) : (
              <ul className="space-y-0.5">
                {sessions.map((session) => (
                  <li key={session.id}>
                    <button
                      onClick={() => onSelect(session.id)}
                      className={cn(
                        "group flex w-full items-center gap-2 rounded-[var(--radius-md)] px-2.5 py-2 text-left text-sm transition-colors",
                        session.id === activeId
                          ? "bg-[var(--color-bg-panel)] text-[var(--color-fg)]"
                          : "text-[var(--color-fg-muted)] hover:bg-[var(--color-bg-panel)]/60 hover:text-[var(--color-fg)]"
                      )}
                    >
                      <span className="flex-1 truncate">{session.title}</span>
                      <span
                        role="button"
                        tabIndex={0}
                        aria-label="Delete session"
                        onClick={(e) => {
                          e.stopPropagation();
                          onDelete(session.id);
                        }}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            e.stopPropagation();
                            onDelete(session.id);
                          }
                        }}
                        className="hidden rounded p-1 text-[var(--color-fg-subtle)] hover:bg-[var(--color-bg-subtle)] hover:text-[var(--color-danger)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/70 group-hover:inline-flex"
                      >
                        <Trash2 className="size-3.5" />
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="border-t border-[var(--color-border)] px-4 py-3 text-[10px] uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
            Meridian · dev
          </div>
        </motion.aside>
      ) : (
        <motion.div
          key="collapsed"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="flex w-14 shrink-0 flex-col items-center gap-2 border-r border-[var(--color-border)] bg-[var(--color-bg-elevated)]/40 py-3"
        >
          <Button
            size="icon"
            variant="ghost"
            onClick={onCollapseToggle}
            aria-label="Expand sidebar"
          >
            <Logo className="size-[22px]" />
          </Button>
          <div className="mt-1 h-px w-8 bg-[var(--color-border)]" />
          <Button
            size="icon"
            variant="ghost"
            onClick={onNewSession}
            aria-label="New chat"
          >
            <MessageCirclePlus className="size-4" />
          </Button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

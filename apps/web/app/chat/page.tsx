"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { signOut } from "next-auth/react";
import { ExternalLink, LogOut } from "lucide-react";

import { InputBar } from "@/components/chat/InputBar";
import { MessageList } from "@/components/chat/MessageList";
import { SessionSidebar } from "@/components/chat/SessionSidebar";
import { Button } from "@/components/ui/Button";
import { useChatStore } from "@/lib/store";

export default function ChatPage() {
  const sessions = useChatStore((s) => s.sessions);
  const order = useChatStore((s) => s.order);
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const sending = useChatStore((s) => s.sending);
  const error = useChatStore((s) => s.error);
  const messagesBySession = useChatStore((s) => s.messagesBySession);

  const loadSessions = useChatStore((s) => s.loadSessions);
  const newSession = useChatStore((s) => s.newSession);
  const setActive = useChatStore((s) => s.setActive);
  const removeSession = useChatStore((s) => s.removeSession);
  const send = useChatStore((s) => s.send);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [prefill, setPrefill] = useState<string | null>(null);

  useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  const orderedSessions = useMemo(
    () =>
      order
        .map((id) => sessions[id])
        .filter((s): s is NonNullable<typeof s> => !!s)
        .map((s) => ({
          id: s.id,
          title: s.title,
          createdAt: new Date(s.created_at).getTime(),
        })),
    [order, sessions]
  );

  const active = activeSessionId ? sessions[activeSessionId] : null;
  const messages = activeSessionId ? messagesBySession[activeSessionId] ?? [] : [];

  return (
    <div className="flex h-dvh overflow-hidden">
      <SessionSidebar
        sessions={orderedSessions}
        activeId={activeSessionId}
        collapsed={sidebarCollapsed}
        onCollapseToggle={() => setSidebarCollapsed((v) => !v)}
        onNewSession={() => {
          void newSession();
        }}
        onSelect={(id) => {
          void setActive(id);
        }}
        onDelete={(id) => {
          void removeSession(id);
        }}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-[var(--color-border)]/60 bg-[var(--color-bg)]/60 px-5 backdrop-blur">
          <div className="flex items-center gap-3 min-w-0">
            <h1 className="truncate text-sm font-medium text-[var(--color-fg)]">
              {active?.title ?? "New chat"}
            </h1>
            {active ? (
              <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
                {active.id.slice(0, 8)}
              </span>
            ) : null}
          </div>
          <div className="flex items-center gap-1">
            <Button asChild variant="ghost" size="sm">
              <Link href="/" className="gap-1">
                <ExternalLink className="size-3" /> Home
              </Link>
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                void signOut({ callbackUrl: "/" });
              }}
              className="gap-1"
            >
              <LogOut className="size-3" /> Sign out
            </Button>
          </div>
        </header>

        {error ? (
          <div className="border-b border-[color-mix(in_oklch,var(--color-danger)_30%,transparent)] bg-[color-mix(in_oklch,var(--color-danger)_10%,var(--color-bg))] px-5 py-2 text-xs text-[var(--color-danger)]">
            {error}
          </div>
        ) : null}

        <div className="flex-1 overflow-y-auto">
          <MessageList
            messages={messages}
            onPickPrompt={(prompt) => setPrefill(prompt)}
          />
        </div>

        <InputBar
          onSubmit={(value) => {
            void send(value);
          }}
          disabled={sending}
          prefill={prefill}
          onPrefillConsumed={() => setPrefill(null)}
        />
      </main>
    </div>
  );
}

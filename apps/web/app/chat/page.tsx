"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";

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
  const ensureActive = useChatStore((s) => s.ensureActive);
  const newSession = useChatStore((s) => s.newSession);
  const setActive = useChatStore((s) => s.setActive);
  const deleteSession = useChatStore((s) => s.deleteSession);
  const send = useChatStore((s) => s.send);

  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [prefill, setPrefill] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setHydrated(true);
    ensureActive();
  }, [ensureActive]);

  const orderedSessions = useMemo(
    () => order.map((id) => sessions[id]).filter((s): s is NonNullable<typeof s> => !!s),
    [order, sessions]
  );

  const active = activeSessionId ? sessions[activeSessionId] : null;

  if (!hydrated) {
    return (
      <div className="flex h-dvh items-center justify-center text-sm text-[var(--color-fg-muted)]">
        Loading…
      </div>
    );
  }

  return (
    <div className="flex h-dvh overflow-hidden">
      <SessionSidebar
        sessions={orderedSessions}
        activeId={activeSessionId}
        collapsed={sidebarCollapsed}
        onCollapseToggle={() => setSidebarCollapsed((v) => !v)}
        onNewSession={newSession}
        onSelect={setActive}
        onDelete={deleteSession}
      />

      <main className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-between gap-3 border-b border-[var(--color-border)]/60 bg-[var(--color-bg)]/60 px-5 backdrop-blur">
          <div className="flex items-center gap-3 min-w-0">
            <h1 className="truncate text-sm font-medium text-[var(--color-fg)]">
              {active?.title ?? "New chat"}
            </h1>
            {active ? (
              <span className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
                {active.id}
              </span>
            ) : null}
          </div>
          <Button asChild variant="ghost" size="sm">
            <Link href="/" className="gap-1">
              <ExternalLink className="size-3" /> Home
            </Link>
          </Button>
        </header>

        <div className="flex-1 overflow-y-auto">
          <MessageList
            messages={active?.messages ?? []}
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

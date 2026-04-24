"use client";

import { useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Sparkles } from "lucide-react";

import { MessageBubble } from "./MessageBubble";
import type { UIMessage } from "@/lib/types";

interface MessageListProps {
  messages: UIMessage[];
  onPickPrompt: (prompt: string) => void;
}

const SUGGESTIONS = [
  "What is the escalation procedure for a P1 outage?",
  "Summarize our on-call rotation policy.",
  "Refund order 7821 for jane@example.com — fraudulent charge.",
  "How do I rotate Postgres credentials in production?",
];

export function MessageList({ messages, onPickPrompt }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, messages[messages.length - 1]?.pending]);

  if (messages.length === 0) {
    return <EmptyState onPickPrompt={onPickPrompt} />;
  }

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6 px-5 pb-6 pt-10">
      <AnimatePresence initial={false}>
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
      </AnimatePresence>
      <div ref={bottomRef} />
    </div>
  );
}

function EmptyState({ onPickPrompt }: { onPickPrompt: (prompt: string) => void }) {
  return (
    <div className="mx-auto flex w-full max-w-2xl flex-col items-center gap-8 px-5 pb-6 pt-16 text-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.4 }}
        className="flex size-14 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)]"
      >
        <Sparkles className="size-6 text-[var(--color-accent)]" />
      </motion.div>

      <div className="space-y-2">
        <h2 className="text-balance text-2xl font-semibold tracking-tight">
          What can Meridian help you with?
        </h2>
        <p className="text-[var(--color-fg-muted)]">
          Ask a question, request an action, or pick a starter below.
        </p>
      </div>

      <div className="grid w-full gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((suggestion, i) => (
          <motion.button
            key={suggestion}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 + i * 0.04 }}
            onClick={() => onPickPrompt(suggestion)}
            className="group rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/50 p-4 text-left text-sm text-[var(--color-fg-muted)] transition-all hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-elevated)] hover:text-[var(--color-fg)]"
          >
            <span className="block text-pretty leading-relaxed">{suggestion}</span>
          </motion.button>
        ))}
      </div>
    </div>
  );
}

"use client";

import { motion } from "framer-motion";
import { AlertTriangle, Bot, User } from "lucide-react";

import { CitationList } from "./CitationList";
import { InsightPanel } from "./InsightPanel";
import { PipelineIndicator } from "./PipelineIndicator";
import { extractCitations } from "@/lib/orchestrator";
import type { UIMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

export function MessageBubble({ message }: { message: UIMessage }) {
  const isUser = message.role === "user";
  const citations = message.reply ? extractCitations(message.reply) : [];
  const hasError = !!message.error;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: "easeOut" }}
      className={cn(
        "group flex w-full gap-4",
        isUser ? "justify-end" : "justify-start"
      )}
    >
      {!isUser ? (
        <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
          <Bot className="size-4 text-[var(--color-accent)]" />
        </div>
      ) : null}

      <div
        className={cn(
          "flex max-w-[min(640px,85%)] flex-col",
          isUser ? "items-end" : "items-start"
        )}
      >
        <div
          className={cn(
            "relative rounded-[var(--radius-lg)] px-4 py-3 leading-relaxed",
            isUser
              ? "bg-gradient-to-br from-[var(--color-accent)] to-[color-mix(in_oklch,var(--color-violet)_70%,var(--color-accent))] text-[var(--color-accent-fg)] shadow-[0_12px_40px_-12px_color-mix(in_oklch,var(--color-accent)_40%,transparent)]"
              : hasError
                ? "border border-[color-mix(in_oklch,var(--color-danger)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-danger)_12%,var(--color-bg-elevated))] text-[var(--color-fg)]"
                : "border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/80 text-[var(--color-fg)] backdrop-blur-sm"
          )}
        >
          {message.pending ? (
            <PendingBubble />
          ) : hasError ? (
            <div className="flex items-start gap-2 text-sm">
              <AlertTriangle className="mt-0.5 size-4 shrink-0 text-[var(--color-danger)]" />
              <span>{message.error}</span>
            </div>
          ) : (
            <p className="whitespace-pre-wrap text-[15px]">{message.content}</p>
          )}
        </div>

        {!isUser && !message.pending && message.reply ? (
          <>
            <div className="w-full">
              <InsightPanel reply={message.reply} />
            </div>
            {citations.length > 0 ? (
              <div className="w-full">
                <CitationList citations={citations} />
              </div>
            ) : null}
          </>
        ) : null}
      </div>

      {isUser ? (
        <div className="mt-1 flex size-8 shrink-0 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)]">
          <User className="size-4 text-[var(--color-fg-muted)]" />
        </div>
      ) : null}
    </motion.div>
  );
}

function PendingBubble() {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <span className="flex gap-1">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="size-1.5 rounded-full bg-[var(--color-fg-muted)]"
              animate={{ opacity: [0.3, 1, 0.3] }}
              transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.15 }}
            />
          ))}
        </span>
        <span className="text-sm text-[var(--color-fg-muted)]">Thinking…</span>
      </div>
      <PipelineIndicator />
    </div>
  );
}

"use client";

import { motion } from "framer-motion";
import { Quote } from "lucide-react";

import type { Citation } from "@/lib/types";

export function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <div className="mt-3 space-y-2">
      {citations.map((citation, i) => (
        <motion.div
          key={`${citation.doc_index}-${i}`}
          initial={{ opacity: 0, x: -6 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.25, delay: 0.05 * i }}
          className="rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-panel)]/60 p-3 text-xs backdrop-blur-sm"
        >
          <div className="mb-1 flex items-center gap-2 text-[var(--color-fg-subtle)]">
            <Quote className="size-3" />
            <span className="font-mono text-[10px] uppercase tracking-wider">
              doc {citation.doc_index}
            </span>
            <span className="truncate text-[var(--color-fg-muted)]">{citation.source_title}</span>
          </div>
          <p className="line-clamp-3 text-[var(--color-fg-muted)] leading-relaxed">
            {citation.relevant_excerpt}
          </p>
        </motion.div>
      ))}
    </div>
  );
}

"use client";

import { motion } from "framer-motion";
import { Coins, Cpu, Gauge, Route, Zap } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { extractCitations, isCacheHit } from "@/lib/orchestrator";
import type { OrchestratorReply } from "@/lib/types";
import { cn, formatCost, formatLatency } from "@/lib/utils";

function intentVariant(intent: string | undefined) {
  switch (intent) {
    case "grounded_qa":
      return "accent" as const;
    case "tool_action":
      return "violet" as const;
    case "clarification":
      return "info" as const;
    case "out_of_scope":
      return "warning" as const;
    default:
      return "default" as const;
  }
}

function tierVariant(tier: string | undefined) {
  switch (tier) {
    case "frontier":
      return "violet" as const;
    case "mid":
      return "accent" as const;
    case "small":
      return "info" as const;
    default:
      return "default" as const;
  }
}

export function InsightPanel({ reply }: { reply: OrchestratorReply }) {
  const state = reply.orchestration_state;
  const cls = state.classification;
  const cacheHit = isCacheHit(reply);
  const citations = extractCitations(reply);
  const totalMs = state.timings_ms.total;

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: 0.05 }}
      className={cn(
        "mt-3 flex flex-wrap items-center gap-2 rounded-[var(--radius-lg)] border bg-[var(--color-bg-panel)]/50 px-3 py-2 text-xs backdrop-blur-sm",
        cacheHit
          ? "border-[color-mix(in_oklch,var(--color-success)_35%,var(--color-border))] shadow-[0_0_30px_-10px_var(--color-success)]"
          : "border-[var(--color-border)]"
      )}
    >
      {cacheHit ? (
        <Badge variant="success" className="gap-1">
          <Zap className="size-3" /> cache hit
        </Badge>
      ) : cls ? (
        <Badge variant={intentVariant(cls.intent)} className="gap-1">
          <Route className="size-3" />
          {cls.intent}
        </Badge>
      ) : null}

      {cls && !cacheHit ? (
        <Badge variant={tierVariant(cls.model_tier)} className="gap-1">
          <Cpu className="size-3" />
          {cls.model_tier}
        </Badge>
      ) : null}

      {state.retrieval ? (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[var(--color-fg-muted)]">
          <span className="text-[var(--color-fg-subtle)]">docs</span>
          <span className="text-[var(--color-fg)]">{state.retrieval.chunks_retrieved}</span>
        </span>
      ) : null}

      {citations.length > 0 ? (
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[var(--color-fg-muted)]">
          <span className="text-[var(--color-fg-subtle)]">cites</span>
          <span className="text-[var(--color-fg)]">{citations.length}</span>
        </span>
      ) : null}

      <div className="ml-auto flex items-center gap-3">
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[var(--color-fg-muted)]">
          <Gauge className="size-3 text-[var(--color-fg-subtle)]" />
          {formatLatency(totalMs)}
        </span>
        <span className="inline-flex items-center gap-1 font-mono text-[11px] text-[var(--color-fg-muted)]">
          <Coins className="size-3 text-[var(--color-fg-subtle)]" />
          {formatCost(reply.cost_usd)}
        </span>
      </div>
    </motion.div>
  );
}

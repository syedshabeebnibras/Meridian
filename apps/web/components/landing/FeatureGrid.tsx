"use client";

import {
  Activity,
  Brain,
  Gauge,
  type LucideIcon,
  Route,
  ShieldCheck,
  Zap,
} from "lucide-react";
import { motion } from "framer-motion";

import { Card, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";

interface Feature {
  icon: LucideIcon;
  title: string;
  body: string;
  accent: "accent" | "violet" | "info" | "success" | "warning" | "rose";
}

const features: Feature[] = [
  {
    icon: Route,
    title: "Deterministic routing",
    body: "10-phase state machine — classify → retrieve → assemble → dispatch → validate. Every request follows the same audit trail.",
    accent: "accent",
  },
  {
    icon: Brain,
    title: "Semantic response cache",
    body: "pgvector-backed, cosine ≥ 0.95. Partitioned by retrieved doc IDs so two tenants never share a cached answer.",
    accent: "violet",
  },
  {
    icon: ShieldCheck,
    title: "Input & output guardrails",
    body: "Injection detection, PII redaction, and faithfulness checks against retrieved documents. Hard-blocked or redacted, never silent.",
    accent: "success",
  },
  {
    icon: Gauge,
    title: "Cost circuit breaker",
    body: "When daily spend exceeds 150% of budget, frontier requests silently degrade to mid-tier models — users still get answers.",
    accent: "warning",
  },
  {
    icon: Zap,
    title: "Token-bucket rate limits",
    body: "Per-user burst of 30, sustained 1 req/s. Returns 429 + Retry-After before the orchestrator burns a classifier call.",
    accent: "info",
  },
  {
    icon: Activity,
    title: "Real observability",
    body: "Prometheus metrics, Langfuse traces, and end-to-end timing breakdown on every response. No black boxes.",
    accent: "rose",
  },
];

const accentClass: Record<Feature["accent"], string> = {
  accent: "text-[var(--color-accent)]",
  violet: "text-[var(--color-violet)]",
  info: "text-[var(--color-info)]",
  success: "text-[var(--color-success)]",
  warning: "text-[var(--color-warning)]",
  rose: "text-[var(--color-rose)]",
};

export function FeatureGrid() {
  return (
    <section className="relative mx-auto w-full max-w-6xl px-5 py-20">
      <div className="mb-12 flex flex-col items-center gap-3 text-center">
        <div className="font-mono text-[11px] uppercase tracking-[0.25em] text-[var(--color-accent)]">
          Capabilities
        </div>
        <h2 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
          Everything you'd build after the demo works.
        </h2>
        <p className="max-w-2xl text-pretty text-[var(--color-fg-muted)]">
          Meridian isn't a prompt with a UI. It's the orchestrator you'd put in production —
          with the invariants, instrumentation, and cost controls already wired in.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((feature, i) => (
          <motion.div
            key={feature.title}
            initial={{ opacity: 0, y: 16 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.35, delay: i * 0.04 }}
          >
            <Card className="group h-full transition-all hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-elevated)]/80">
              <CardHeader>
                <div
                  className={`mb-3 inline-flex size-9 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-panel)] ${accentClass[feature.accent]}`}
                >
                  <feature.icon className="size-4" />
                </div>
                <CardTitle className="text-base">{feature.title}</CardTitle>
                <CardDescription className="mt-1 text-sm">{feature.body}</CardDescription>
              </CardHeader>
            </Card>
          </motion.div>
        ))}
      </div>
    </section>
  );
}

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
import { cn } from "@/lib/utils";

type AccentKey = "accent" | "violet" | "info" | "success" | "warning" | "rose";

interface Feature {
  icon: LucideIcon;
  eyebrow: string;
  title: string;
  body: string;
  accent: AccentKey;
  featured?: boolean;
  visual: "rings" | "pulse" | "dots" | "bars" | "grid" | "radial";
}

const features: Feature[] = [
  {
    icon: Brain,
    eyebrow: "Semantic response cache",
    title: "Answers that pay for themselves.",
    body: "pgvector-backed, cosine ≥ 0.95. Partitioned by retrieved doc IDs so two tenants never share a cached answer. Repeat questions come back in milliseconds at $0.",
    accent: "violet",
    featured: true,
    visual: "rings",
  },
  {
    icon: Route,
    eyebrow: "Deterministic routing",
    title: "Same pipeline, every request.",
    body: "10-phase state machine — classify → retrieve → assemble → dispatch → validate. Every request follows the same audit trail.",
    accent: "accent",
    visual: "bars",
  },
  {
    icon: ShieldCheck,
    eyebrow: "Guardrails",
    title: "Never silent.",
    body: "Injection detection, PII redaction, and faithfulness checks against retrieved documents. Hard-blocked or redacted, never silent.",
    accent: "success",
    visual: "pulse",
  },
  {
    icon: Gauge,
    eyebrow: "Cost circuit breaker",
    title: "Graceful at 150%.",
    body: "When daily spend exceeds 150% of budget, frontier requests silently degrade to mid-tier models — users still get answers.",
    accent: "warning",
    visual: "radial",
  },
  {
    icon: Zap,
    eyebrow: "Rate limits",
    title: "Token-bucket, per user.",
    body: "Burst of 30, sustained 1 req/s. Returns 429 + Retry-After before the orchestrator burns a classifier call.",
    accent: "info",
    visual: "dots",
  },
  {
    icon: Activity,
    eyebrow: "Observability",
    title: "No black boxes.",
    body: "Prometheus metrics, Langfuse traces, and end-to-end timing breakdown on every response.",
    accent: "rose",
    visual: "grid",
  },
];

const accentVars: Record<AccentKey, string> = {
  accent: "var(--color-accent)",
  violet: "var(--color-violet)",
  info: "var(--color-info)",
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  rose: "var(--color-rose)",
};

const accentText: Record<AccentKey, string> = {
  accent: "text-[var(--color-accent)]",
  violet: "text-[var(--color-violet)]",
  info: "text-[var(--color-info)]",
  success: "text-[var(--color-success)]",
  warning: "text-[var(--color-warning)]",
  rose: "text-[var(--color-rose)]",
};

export function FeatureGrid() {
  return (
    <section className="relative mx-auto w-full max-w-6xl px-5 py-24">
      <div className="mb-14 flex flex-col items-center gap-3 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/50 px-3 py-1 font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-accent)] backdrop-blur">
          Capabilities
        </div>
        <h2 className="max-w-2xl text-balance text-3xl font-semibold tracking-[-0.02em] sm:text-4xl">
          Everything you&apos;d build after the demo works.
        </h2>
        <p className="max-w-2xl text-pretty text-[var(--color-fg-muted)]">
          Meridian isn&apos;t a prompt with a UI. It&apos;s the orchestrator you&apos;d put in
          production — with the invariants, instrumentation, and cost controls already
          wired in.
        </p>
      </div>

      <div className="grid auto-rows-[minmax(0,1fr)] gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((feature, i) => (
          <motion.div
            key={feature.title}
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, margin: "-80px" }}
            transition={{ duration: 0.4, delay: i * 0.05, ease: [0.22, 1, 0.36, 1] }}
            className={cn(feature.featured && "lg:col-span-2 lg:row-span-1")}
          >
            <FeatureCard feature={feature} />
          </motion.div>
        ))}
      </div>
    </section>
  );
}

function FeatureCard({ feature }: { feature: Feature }) {
  const accent = accentVars[feature.accent];

  return (
    <Card
      className={cn(
        "group relative h-full overflow-hidden transition-all duration-300",
        "hover:border-[var(--color-border-strong)] hover:bg-[var(--color-bg-elevated)]/80",
        feature.featured && "md:flex md:min-h-[260px] md:items-stretch"
      )}
      style={{ "--card-accent": accent } as React.CSSProperties}
    >
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-0 transition-opacity duration-500 group-hover:opacity-100"
        style={{
          background: `radial-gradient(600px circle at 30% 0%, color-mix(in oklch, ${accent} 18%, transparent), transparent 60%)`,
        }}
      />

      <CardHeader className={cn("relative z-10 flex-1", feature.featured && "md:p-8")}>
        <div
          className={cn(
            "mb-4 inline-flex size-10 items-center justify-center rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-panel)] shadow-inner",
            accentText[feature.accent]
          )}
        >
          <feature.icon className="size-[18px]" />
        </div>

        <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-fg-subtle)]">
          {feature.eyebrow}
        </div>
        <CardTitle
          className={cn(
            "text-[15px] font-semibold tracking-[-0.01em] text-[var(--color-fg)]",
            feature.featured && "md:text-2xl md:leading-tight"
          )}
        >
          {feature.title}
        </CardTitle>
        <CardDescription
          className={cn(
            "mt-2 text-[13px] leading-relaxed",
            feature.featured && "md:max-w-md md:text-[14px]"
          )}
        >
          {feature.body}
        </CardDescription>
      </CardHeader>

      <div
        className={cn(
          "pointer-events-none absolute right-4 top-4 z-0 hidden items-center justify-center opacity-70 sm:flex",
          feature.featured
            ? "md:relative md:right-0 md:top-0 md:size-56 md:shrink-0 md:self-center md:pr-8 md:opacity-100"
            : "size-20"
        )}
        aria-hidden
      >
        <FeatureVisual kind={feature.visual} accent={accent} featured={feature.featured} />
      </div>
    </Card>
  );
}

function FeatureVisual({
  kind,
  accent,
  featured,
}: {
  kind: Feature["visual"];
  accent: string;
  featured?: boolean;
}) {
  const size = featured ? 220 : 72;
  switch (kind) {
    case "rings":
      return (
        <svg width={size} height={size} viewBox="0 0 220 220" fill="none">
          <defs>
            <radialGradient id="ring-core" cx="50%" cy="50%">
              <stop offset="0%" stopColor={accent} stopOpacity="0.7" />
              <stop offset="100%" stopColor={accent} stopOpacity="0" />
            </radialGradient>
          </defs>
          <circle cx="110" cy="110" r="32" fill="url(#ring-core)" />
          {[55, 80, 105].map((r, i) => (
            <circle
              key={r}
              cx="110"
              cy="110"
              r={r}
              stroke={accent}
              strokeOpacity={0.45 - i * 0.12}
              strokeWidth="1"
              strokeDasharray={i === 2 ? "3 6" : undefined}
              fill="none"
            />
          ))}
        </svg>
      );
    case "pulse":
      return (
        <div className="relative flex size-full items-center justify-center">
          <span
            className="absolute size-5 rounded-full"
            style={{ backgroundColor: accent, opacity: 0.85 }}
          />
          <span
            className="absolute size-12 rounded-full animate-[pulse_2.4s_ease-in-out_infinite]"
            style={{
              background: `radial-gradient(circle, ${accent} 0%, transparent 70%)`,
              opacity: 0.4,
            }}
          />
        </div>
      );
    case "dots":
      return (
        <svg width={size} height={size} viewBox="0 0 72 72" fill="none">
          {[0, 1, 2, 3].flatMap((r) =>
            [0, 1, 2, 3].map((c) => (
              <circle
                key={`${r}-${c}`}
                cx={10 + c * 17}
                cy={10 + r * 17}
                r={1.6}
                fill={accent}
                opacity={0.3 + ((r + c) % 3) * 0.25}
              />
            ))
          )}
        </svg>
      );
    case "bars":
      return (
        <svg width={size} height={size} viewBox="0 0 72 72" fill="none">
          {[18, 34, 26, 48, 22, 38].map((h, i) => (
            <rect
              key={i}
              x={8 + i * 10}
              y={60 - h}
              width="5"
              height={h}
              rx="1.5"
              fill={accent}
              opacity={0.35 + (i % 3) * 0.2}
            />
          ))}
        </svg>
      );
    case "grid":
      return (
        <svg width={size} height={size} viewBox="0 0 72 72" fill="none">
          {[0, 1, 2, 3, 4].map((i) => (
            <line
              key={`h-${i}`}
              x1="4"
              x2="68"
              y1={12 + i * 12}
              y2={12 + i * 12}
              stroke={accent}
              strokeOpacity={0.25}
              strokeDasharray="2 4"
            />
          ))}
          <polyline
            points="4,48 20,30 36,40 52,18 68,26"
            stroke={accent}
            strokeWidth="1.6"
            fill="none"
          />
        </svg>
      );
    case "radial":
    default:
      return (
        <div
          className="size-full rounded-full blur-sm"
          style={{
            background: `conic-gradient(from 0deg, ${accent}, transparent 50%, ${accent})`,
            opacity: 0.45,
          }}
        />
      );
  }
}

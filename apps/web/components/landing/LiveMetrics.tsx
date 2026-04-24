"use client";

import { useEffect, useState } from "react";
import { Activity, DollarSign, Timer } from "lucide-react";
import { motion } from "framer-motion";

import { formatCost, formatLatency } from "@/lib/utils";

interface Snapshot {
  requests_total: number;
  cost_usd_total: number;
  avg_latency_seconds: number | null;
}

export function LiveMetrics() {
  const [snap, setSnap] = useState<Snapshot | null>(null);

  useEffect(() => {
    let active = true;
    const fetchSnap = async () => {
      try {
        const res = await fetch("/api/metrics", { cache: "no-store" });
        if (!res.ok) return;
        const data = (await res.json()) as Snapshot;
        if (active) setSnap(data);
      } catch {
        // swallow — landing still renders without metrics
      }
    };
    fetchSnap();
    const interval = setInterval(fetchSnap, 8000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, []);

  const avgMs =
    snap?.avg_latency_seconds != null ? Math.round(snap.avg_latency_seconds * 1000) : null;

  return (
    <section className="mx-auto w-full max-w-6xl px-5 pt-4 pb-2">
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true }}
        transition={{ duration: 0.5 }}
        className="grid gap-3 rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/60 p-2 backdrop-blur-sm sm:grid-cols-3"
      >
        <Metric
          icon={<Activity className="size-4 text-[var(--color-accent)]" />}
          label="Requests served"
          value={snap ? snap.requests_total.toLocaleString() : "—"}
        />
        <Metric
          icon={<Timer className="size-4 text-[var(--color-info)]" />}
          label="Avg latency"
          value={formatLatency(avgMs)}
        />
        <Metric
          icon={<DollarSign className="size-4 text-[var(--color-success)]" />}
          label="Total LLM cost"
          value={snap ? formatCost(snap.cost_usd_total) : "—"}
        />
      </motion.div>
    </section>
  );
}

function Metric({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center justify-between rounded-[var(--radius-lg)] bg-[var(--color-bg-panel)]/60 px-5 py-4">
      <div className="flex items-center gap-3">
        <div className="flex size-8 items-center justify-center rounded-full border border-[var(--color-border)] bg-[var(--color-bg)]">
          {icon}
        </div>
        <span className="text-xs uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
          {label}
        </span>
      </div>
      <span className="font-mono text-lg font-medium text-[var(--color-fg)]">{value}</span>
    </div>
  );
}

"use client";

import { motion } from "framer-motion";

const phases = [
  { label: "received", tier: "gate" },
  { label: "input guardrails", tier: "gate" },
  { label: "classified", tier: "route" },
  { label: "retrieved", tier: "route" },
  { label: "assembled", tier: "route" },
  { label: "dispatched", tier: "model" },
  { label: "validated", tier: "check" },
  { label: "output guardrails", tier: "gate" },
  { label: "shaped", tier: "check" },
  { label: "completed", tier: "done" },
];

const tierClass: Record<string, string> = {
  gate: "border-[color-mix(in_oklch,var(--color-warning)_35%,var(--color-border))] text-[var(--color-warning)]",
  route: "border-[color-mix(in_oklch,var(--color-accent)_35%,var(--color-border))] text-[var(--color-accent)]",
  model: "border-[color-mix(in_oklch,var(--color-violet)_35%,var(--color-border))] text-[var(--color-violet)]",
  check: "border-[color-mix(in_oklch,var(--color-info)_35%,var(--color-border))] text-[var(--color-info)]",
  done: "border-[color-mix(in_oklch,var(--color-success)_35%,var(--color-border))] text-[var(--color-success)]",
};

export function StateMachineViz() {
  return (
    <section className="relative mx-auto w-full max-w-6xl px-5 py-20">
      <div className="mb-10 flex flex-col items-center gap-3 text-center">
        <div className="font-mono text-[11px] uppercase tracking-[0.25em] text-[var(--color-violet)]">
          The pipeline
        </div>
        <h2 className="max-w-2xl text-balance text-3xl font-semibold tracking-tight sm:text-4xl">
          Every request, the same 10 deterministic phases.
        </h2>
        <p className="max-w-2xl text-[var(--color-fg-muted)]">
          Unrecoverable errors land in a typed <code className="rounded bg-[var(--color-bg-elevated)] px-1.5 py-0.5 font-mono text-xs text-[var(--color-fg)]">FAILED</code>{" "}
          state with a degraded reply — never a raw exception to the caller.
        </p>
      </div>

      <div className="rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/40 p-6 backdrop-blur-sm md:p-10">
        <ol className="flex flex-wrap items-center justify-center gap-2">
          {phases.map((phase, i) => (
            <motion.li
              key={phase.label}
              initial={{ opacity: 0, scale: 0.96 }}
              whileInView={{ opacity: 1, scale: 1 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ duration: 0.3, delay: i * 0.035 }}
              className="flex items-center gap-2"
            >
              <div
                className={`whitespace-nowrap rounded-full border bg-[var(--color-bg-panel)] px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider ${tierClass[phase.tier]}`}
              >
                {phase.label}
              </div>
              {i < phases.length - 1 ? (
                <span className="select-none text-[var(--color-fg-subtle)]">→</span>
              ) : null}
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}

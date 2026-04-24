"use client";

import { motion } from "framer-motion";

const phases = [
  "classify",
  "retrieve",
  "assemble",
  "dispatch",
  "validate",
];

export function PipelineIndicator() {
  return (
    <div className="mt-2 flex items-center gap-2 text-[11px] text-[var(--color-fg-subtle)]">
      {phases.map((phase, i) => (
        <motion.span
          key={phase}
          className="inline-flex items-center gap-2"
          initial={{ opacity: 0.3 }}
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{
            duration: 1.6,
            repeat: Infinity,
            delay: i * 0.25,
            ease: "easeInOut",
          }}
        >
          <span className="font-mono uppercase tracking-[0.15em]">{phase}</span>
          {i < phases.length - 1 ? <span className="text-[var(--color-fg-subtle)]/40">/</span> : null}
        </motion.span>
      ))}
    </div>
  );
}

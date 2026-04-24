"use client";

import Link from "next/link";
import { ArrowRight, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

import { Button } from "@/components/ui/Button";

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden">
      <div className="pointer-events-none absolute inset-0 dot-grid opacity-40" aria-hidden />
      <div className="pointer-events-none absolute -top-40 left-1/2 h-[500px] w-[700px] -translate-x-1/2 rounded-full bg-[color-mix(in_oklch,var(--color-accent)_20%,transparent)] blur-3xl" aria-hidden />

      <div className="relative mx-auto flex max-w-4xl flex-col items-center gap-7 px-5 pb-20 pt-24 text-center md:pt-32">
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/60 px-3 py-1 text-xs text-[var(--color-fg-muted)] backdrop-blur"
        >
          <Sparkles className="size-3 text-[var(--color-accent)]" />
          <span>Production-grade LLM orchestration</span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.05 }}
          className="text-balance text-4xl font-semibold leading-[1.05] tracking-tight text-gradient sm:text-5xl md:text-6xl"
        >
          Enterprise knowledge, answered with evidence.
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="max-w-2xl text-pretty text-base leading-relaxed text-[var(--color-fg-muted)] sm:text-lg"
        >
          A deterministic 10-phase state machine that routes every request through
          classification, retrieval, assembly, and validation — with semantic caching,
          cost circuit breakers, and full observability baked in.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="mt-2 flex flex-col items-center gap-3 sm:flex-row"
        >
          <Button asChild size="lg" className="group">
            <Link href="/chat">
              Start a conversation
              <ArrowRight className="size-4 transition-transform group-hover:translate-x-0.5" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="secondary">
            <a
              href="https://github.com/syedshabeebnibras/Meridian"
              target="_blank"
              rel="noreferrer"
            >
              View source
            </a>
          </Button>
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.35 }}
          className="mt-10 font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-fg-subtle)]"
        >
          Python · FastAPI · pgvector · LiteLLM · Langfuse · Next.js 15
        </motion.div>
      </div>
    </section>
  );
}

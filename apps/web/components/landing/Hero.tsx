"use client";

import Link from "next/link";
import { ArrowRight, ChevronRight, Sparkles } from "lucide-react";
import { motion } from "framer-motion";

import { Button } from "@/components/ui/Button";

const FADE_UP = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
};

export function Hero() {
  return (
    <section className="relative isolate overflow-hidden">
      <AuroraBackdrop />
      <div
        className="pointer-events-none absolute inset-0 dot-grid opacity-30"
        aria-hidden
      />

      <div className="relative mx-auto flex max-w-6xl flex-col items-center gap-8 px-5 pb-20 pt-20 text-center md:pt-28 lg:pb-28">
        <motion.div
          {...FADE_UP}
          transition={{ duration: 0.4 }}
        >
          <Link
            href="/chat"
            className="group inline-flex items-center gap-2 rounded-full border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/70 py-1 pl-1 pr-3 text-xs text-[var(--color-fg-muted)] backdrop-blur transition-colors hover:border-[var(--color-border-strong)] hover:text-[var(--color-fg)]"
          >
            <span className="inline-flex items-center gap-1.5 rounded-full bg-[color-mix(in_oklch,var(--color-accent)_20%,transparent)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-accent)]">
              <Sparkles className="size-3" />
              new
            </span>
            <span>Semantic cache ships — cosine ≥ 0.95</span>
            <ChevronRight className="size-3 transition-transform group-hover:translate-x-0.5" />
          </Link>
        </motion.div>

        <motion.h1
          {...FADE_UP}
          transition={{ duration: 0.5, delay: 0.05 }}
          className="max-w-3xl text-balance text-[2.5rem] font-semibold leading-[1.02] tracking-[-0.03em] text-gradient sm:text-5xl md:text-[4rem]"
        >
          Enterprise knowledge,
          <br className="hidden sm:block" />
          answered with evidence.
        </motion.h1>

        <motion.p
          {...FADE_UP}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="max-w-2xl text-pretty text-base leading-relaxed text-[var(--color-fg-muted)] sm:text-lg"
        >
          A deterministic 10-phase state machine that routes every request through
          classification, retrieval, assembly, and validation — with semantic caching,
          cost circuit breakers, and full observability baked in.
        </motion.p>

        <motion.div
          {...FADE_UP}
          transition={{ duration: 0.5, delay: 0.15 }}
          className="mt-1 flex flex-col items-center gap-3 sm:flex-row"
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

        <motion.ul
          {...FADE_UP}
          transition={{ duration: 0.5, delay: 0.2 }}
          className="mt-3 flex flex-wrap items-center justify-center gap-2 font-mono text-[11px] uppercase tracking-[0.14em] text-[var(--color-fg-subtle)]"
        >
          {[
            "10-phase pipeline",
            "206 passing tests",
            "cosine ≥ 0.95 cache",
          ].map((item, i) => (
            <li
              key={item}
              className="inline-flex items-center gap-2 rounded-full border border-[var(--color-border)]/80 bg-[var(--color-bg-elevated)]/40 px-3 py-1 backdrop-blur-sm"
            >
              <span className="size-1 rounded-full bg-[var(--color-accent)]/80" aria-hidden />
              {item}
            </li>
          ))}
        </motion.ul>

        <motion.div
          initial={{ opacity: 0, y: 24, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
          className="relative mt-10 hidden w-full max-w-3xl md:block"
        >
          <TerminalMock />
        </motion.div>

        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.6, delay: 0.45 }}
          className="mt-4 font-mono text-[11px] uppercase tracking-[0.2em] text-[var(--color-fg-subtle)]"
        >
          Python · FastAPI · pgvector · LiteLLM · Langfuse · Next.js 15
        </motion.div>
      </div>
    </section>
  );
}

/**
 * AuroraBackdrop — animated conic gradient blobs that drift slowly behind the
 * hero copy. Uses CSS-only `animation` (no JS timers) and respects
 * `prefers-reduced-motion` automatically because the `@media` query pauses the
 * keyframes. Layered gradients avoid any JS Framer costs while still feeling alive.
 */
function AuroraBackdrop() {
  return (
    <div className="pointer-events-none absolute inset-0 -z-10 overflow-hidden" aria-hidden>
      <div
        className="absolute left-1/2 top-[-20%] h-[560px] w-[780px] -translate-x-1/2 rounded-full opacity-60 blur-3xl"
        style={{
          background:
            "conic-gradient(from 210deg at 50% 50%, color-mix(in oklch, var(--color-accent) 35%, transparent), color-mix(in oklch, var(--color-violet) 30%, transparent), color-mix(in oklch, var(--color-accent) 20%, transparent))",
          animation: "aurora-drift 18s ease-in-out infinite alternate",
        }}
      />
      <div
        className="absolute right-[-10%] top-[40%] h-[420px] w-[520px] rounded-full opacity-40 blur-3xl"
        style={{
          background:
            "radial-gradient(circle at 30% 30%, color-mix(in oklch, var(--color-violet) 40%, transparent), transparent 65%)",
          animation: "aurora-drift 22s ease-in-out infinite alternate-reverse",
        }}
      />
      <style>
        {`
          @keyframes aurora-drift {
            0%   { transform: translate3d(-50%, 0, 0) rotate(0deg) scale(1); }
            100% { transform: translate3d(-50%, 2%, 0) rotate(6deg) scale(1.08); }
          }
          @media (prefers-reduced-motion: reduce) {
            [style*="aurora-drift"] { animation: none !important; }
          }
        `}
      </style>
    </div>
  );
}

/**
 * TerminalMock — a macOS-style window showing a real /v1/chat curl exchange.
 * Styled entirely with tokens + CSS; no images or external dependencies. The
 * content demonstrates product value (structured JSON reply with cost + tier)
 * without requiring a product screenshot.
 */
function TerminalMock() {
  return (
    <div className="group relative overflow-hidden rounded-[var(--radius-xl)] border border-[var(--color-border)] bg-[var(--color-bg-elevated)]/80 shadow-[0_30px_100px_-30px_color-mix(in_oklch,var(--color-accent)_40%,transparent)] backdrop-blur-md">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-[color-mix(in_oklch,var(--color-accent)_60%,transparent)] to-transparent"
      />
      <div className="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-bg-panel)]/60 px-4 py-2.5">
        <div className="flex items-center gap-1.5">
          <span className="size-3 rounded-full bg-[color-mix(in_oklch,var(--color-danger)_80%,var(--color-bg))]" />
          <span className="size-3 rounded-full bg-[color-mix(in_oklch,var(--color-warning)_80%,var(--color-bg))]" />
          <span className="size-3 rounded-full bg-[color-mix(in_oklch,var(--color-success)_80%,var(--color-bg))]" />
        </div>
        <span className="font-mono text-[11px] text-[var(--color-fg-subtle)]">
          zsh · meridian-orch
        </span>
        <span className="w-12" />
      </div>
      <pre className="overflow-x-auto px-5 py-4 text-left font-mono text-[12.5px] leading-relaxed">
        <code>
          <span className="text-[var(--color-fg-subtle)]">$</span>{" "}
          <span className="text-[var(--color-fg)]">curl</span>{" "}
          <span className="text-[var(--color-accent)]">-sX</span>{" "}
          <span className="text-[var(--color-fg)]">POST</span>{" "}
          <span className="text-[var(--color-success)]">
            https://meridian.dev/v1/chat
          </span>
          {"\n"}
          <span className="text-[var(--color-fg-muted)]">     -H</span>{" "}
          <span className="text-[var(--color-info)]">
            &apos;Content-Type: application/json&apos;
          </span>
          {"\n"}
          <span className="text-[var(--color-fg-muted)]">     -d</span>{" "}
          <span className="text-[var(--color-info)]">
            &apos;{"{"}&quot;query&quot;: &quot;P1 escalation procedure?&quot;{"}"}&apos;
          </span>
          {"\n\n"}
          <span className="text-[var(--color-fg-subtle)]">#</span>{" "}
          <span className="text-[var(--color-fg-subtle)]">response</span>
          {"\n"}
          <span className="text-[var(--color-fg)]">{"{"}</span>
          {"\n  "}
          <span className="text-[var(--color-violet)]">&quot;status&quot;</span>:{" "}
          <span className="text-[var(--color-success)]">&quot;ok&quot;</span>,
          {"\n  "}
          <span className="text-[var(--color-violet)]">&quot;model&quot;</span>:{" "}
          <span className="text-[var(--color-info)]">&quot;meridian-mid&quot;</span>,
          {"\n  "}
          <span className="text-[var(--color-violet)]">&quot;intent&quot;</span>:{" "}
          <span className="text-[var(--color-info)]">&quot;grounded_qa&quot;</span>,
          {"\n  "}
          <span className="text-[var(--color-violet)]">&quot;cost_usd&quot;</span>:{" "}
          <span className="text-[var(--color-accent)]">0.004236</span>,
          {"\n  "}
          <span className="text-[var(--color-violet)]">&quot;citations&quot;</span>:{" "}
          <span className="text-[var(--color-accent)]">2</span>,
          {"\n  "}
          <span className="text-[var(--color-violet)]">&quot;total_ms&quot;</span>:{" "}
          <span className="text-[var(--color-accent)]">1627</span>
          {"\n"}
          <span className="text-[var(--color-fg)]">{"}"}</span>
        </code>
      </pre>
    </div>
  );
}

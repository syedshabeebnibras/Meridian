import { FeatureGrid } from "@/components/landing/FeatureGrid";
import { Hero } from "@/components/landing/Hero";
import { LiveMetrics } from "@/components/landing/LiveMetrics";
import { StateMachineViz } from "@/components/landing/StateMachineViz";
import { Nav } from "@/components/shared/Nav";

export default async function LandingPage() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <LiveMetrics />
        <FeatureGrid />
        <StateMachineViz />
      </main>
      <footer className="border-t border-[var(--color-border)]/60 py-8">
        <div className="mx-auto flex max-w-6xl flex-col items-center justify-between gap-2 px-5 text-xs text-[var(--color-fg-subtle)] sm:flex-row">
          <span>Meridian — deterministic orchestration for enterprise LLMs.</span>
          <span className="font-mono">v0.1.0</span>
        </div>
      </footer>
    </>
  );
}

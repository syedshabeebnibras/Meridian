"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/Button";
import { signUpAction } from "@/app/(auth)/actions";

export default function SignUpPage() {
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-balance text-2xl font-semibold tracking-[-0.02em]">
          Create your workspace
        </h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          A personal workspace is created for you. You can invite teammates later.
        </p>
      </div>

      <form
        action={(formData) => {
          setError(null);
          startTransition(async () => {
            const result = await signUpAction(formData);
            if (result && !result.ok) setError(result.error);
          });
        }}
        className="space-y-4"
      >
        <label className="block space-y-1.5">
          <span className="text-xs font-medium uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
            Name
          </span>
          <input
            name="name"
            type="text"
            required
            autoComplete="name"
            minLength={1}
            maxLength={128}
            className="block w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-2.5 text-sm focus:border-[var(--color-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/70"
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-xs font-medium uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
            Email
          </span>
          <input
            name="email"
            type="email"
            required
            autoComplete="email"
            className="block w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-2.5 text-sm focus:border-[var(--color-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/70"
          />
        </label>
        <label className="block space-y-1.5">
          <span className="text-xs font-medium uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
            Password <span className="text-[var(--color-fg-subtle)]">(8+ chars)</span>
          </span>
          <input
            name="password"
            type="password"
            minLength={8}
            maxLength={256}
            required
            autoComplete="new-password"
            className="block w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-2.5 text-sm focus:border-[var(--color-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/70"
          />
        </label>

        {error ? (
          <p
            role="alert"
            className="rounded-[var(--radius-md)] border border-[color-mix(in_oklch,var(--color-danger)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-danger)_12%,var(--color-bg-elevated))] px-3 py-2 text-sm text-[var(--color-danger)]"
          >
            {error}
          </p>
        ) : null}

        <Button type="submit" size="lg" disabled={isPending} className="w-full">
          {isPending ? "Creating account…" : "Create account"}
        </Button>
      </form>

      <p className="text-center text-sm text-[var(--color-fg-muted)]">
        Already have an account?{" "}
        <Link
          href="/sign-in"
          className="font-medium text-[var(--color-accent)] hover:underline"
        >
          Sign in
        </Link>
      </p>
    </div>
  );
}

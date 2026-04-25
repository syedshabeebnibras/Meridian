"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

import { Button } from "@/components/ui/Button";
import { signInAction } from "@/app/(auth)/actions";

export default function SignInPage() {
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  return (
    <div className="space-y-6">
      <div className="space-y-1">
        <h1 className="text-balance text-2xl font-semibold tracking-[-0.02em]">
          Sign in to Meridian
        </h1>
        <p className="text-sm text-[var(--color-fg-muted)]">
          Continue with your email and password.
        </p>
      </div>

      <form
        action={(formData) => {
          setError(null);
          startTransition(async () => {
            const result = await signInAction(formData);
            if (result && !result.ok) setError(result.error);
          });
        }}
        className="space-y-4"
      >
        <FormField
          name="email"
          type="email"
          label="Email"
          autoComplete="email"
          required
        />
        <FormField
          name="password"
          type="password"
          label="Password"
          autoComplete="current-password"
          required
        />
        {error ? (
          <p
            role="alert"
            className="rounded-[var(--radius-md)] border border-[color-mix(in_oklch,var(--color-danger)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-danger)_12%,var(--color-bg-elevated))] px-3 py-2 text-sm text-[var(--color-danger)]"
          >
            {error}
          </p>
        ) : null}
        <Button type="submit" size="lg" disabled={isPending} className="w-full">
          {isPending ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <p className="text-center text-sm text-[var(--color-fg-muted)]">
        Don&apos;t have an account?{" "}
        <Link
          href="/sign-up"
          className="font-medium text-[var(--color-accent)] hover:underline"
        >
          Sign up
        </Link>
      </p>
    </div>
  );
}

function FormField({
  name,
  label,
  type = "text",
  ...rest
}: React.InputHTMLAttributes<HTMLInputElement> & { name: string; label: string }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-xs font-medium uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
        {label}
      </span>
      <input
        name={name}
        type={type}
        {...rest}
        className="block w-full rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg-elevated)] px-3 py-2.5 text-sm text-[var(--color-fg)] placeholder:text-[var(--color-fg-subtle)] focus:border-[var(--color-border-strong)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/70"
      />
    </label>
  );
}

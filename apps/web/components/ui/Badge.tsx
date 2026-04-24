import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
  {
    variants: {
      variant: {
        default:
          "border-[var(--color-border)] bg-[var(--color-bg-elevated)] text-[var(--color-fg-muted)]",
        accent:
          "border-[color-mix(in_oklch,var(--color-accent)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-accent)_15%,transparent)] text-[var(--color-accent)]",
        success:
          "border-[color-mix(in_oklch,var(--color-success)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-success)_15%,transparent)] text-[var(--color-success)]",
        warning:
          "border-[color-mix(in_oklch,var(--color-warning)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-warning)_15%,transparent)] text-[var(--color-warning)]",
        danger:
          "border-[color-mix(in_oklch,var(--color-danger)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-danger)_15%,transparent)] text-[var(--color-danger)]",
        violet:
          "border-[color-mix(in_oklch,var(--color-violet)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-violet)_15%,transparent)] text-[var(--color-violet)]",
        info:
          "border-[color-mix(in_oklch,var(--color-info)_40%,transparent)] bg-[color-mix(in_oklch,var(--color-info)_15%,transparent)] text-[var(--color-info)]",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant, ...props }, ref) => (
    <span ref={ref} className={cn(badgeVariants({ variant }), className)} {...props} />
  )
);
Badge.displayName = "Badge";

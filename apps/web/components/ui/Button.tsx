import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef } from "react";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap font-medium transition-all disabled:pointer-events-none disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-accent)]/70 focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)] active:scale-[0.98]",
  {
    variants: {
      variant: {
        primary:
          "bg-[var(--color-accent)] text-[var(--color-accent-fg)] hover:brightness-110 shadow-[0_10px_30px_-10px_color-mix(in_oklch,var(--color-accent)_40%,transparent)]",
        secondary:
          "bg-[var(--color-bg-elevated)] text-[var(--color-fg)] border border-[var(--color-border)] hover:bg-[var(--color-bg-panel)] hover:border-[var(--color-border-strong)]",
        ghost:
          "text-[var(--color-fg-muted)] hover:text-[var(--color-fg)] hover:bg-[var(--color-bg-elevated)]",
        danger:
          "bg-[color-mix(in_oklch,var(--color-danger)_20%,var(--color-bg-elevated))] text-[var(--color-danger)] border border-[color-mix(in_oklch,var(--color-danger)_30%,transparent)] hover:brightness-125",
        outline:
          "border border-[var(--color-border)] text-[var(--color-fg)] hover:bg-[var(--color-bg-elevated)] hover:border-[var(--color-border-strong)]",
      },
      size: {
        sm: "h-8 px-3 text-xs rounded-[var(--radius-sm)]",
        md: "h-10 px-4 text-sm rounded-[var(--radius-md)]",
        lg: "h-12 px-6 text-base rounded-[var(--radius-lg)]",
        icon: "h-9 w-9 rounded-[var(--radius-md)]",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size }), className)} ref={ref} {...props} />
    );
  }
);
Button.displayName = "Button";

export { buttonVariants };

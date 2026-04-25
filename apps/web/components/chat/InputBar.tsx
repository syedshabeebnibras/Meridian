"use client";

import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, Loader2, Mic, Paperclip } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface InputBarProps {
  onSubmit: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  prefill?: string | null;
  onPrefillConsumed?: () => void;
}

const MAX_CHARS = 4000;
const WARN_AT = 3500;

export function InputBar({
  onSubmit,
  disabled,
  placeholder = "Ask Meridian anything…",
  prefill,
  onPrefillConsumed,
}: InputBarProps) {
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (prefill != null) {
      // Prefill is an explicit external event from the prompt picker.
      // Syncing it into the controlled textarea is the intended effect.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setValue(prefill);
      onPrefillConsumed?.();
      textareaRef.current?.focus();
    }
  }, [prefill, onPrefillConsumed]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 220)}px`;
  }, [value]);

  const canSubmit = !disabled && value.trim().length > 0;
  const charCount = value.length;
  const charWarning = charCount >= WARN_AT;

  const submit = () => {
    if (!canSubmit) return;
    onSubmit(value);
    setValue("");
  };

  return (
    <div className="sticky bottom-0 z-10 border-t border-[var(--color-border)]/60 bg-[var(--color-bg)]/80 px-5 py-4 backdrop-blur-xl">
      <div className="mx-auto w-full max-w-3xl">
        <div className="relative">
          {/* Animated gradient ring — visible on focus. Uses a pseudo-layer via
              an extra div so the gradient doesn't clip the container's content. */}
          <div
            aria-hidden
            className={cn(
              "pointer-events-none absolute -inset-px rounded-[var(--radius-xl)] transition-opacity duration-300",
              focused ? "opacity-100" : "opacity-0"
            )}
            style={{
              background:
                "conic-gradient(from 180deg, var(--color-accent), var(--color-violet), var(--color-accent))",
              filter: "blur(6px)",
            }}
          />

          <div
            className={cn(
              "relative flex flex-col rounded-[var(--radius-xl)] border bg-[var(--color-bg-elevated)] transition-[border-color,box-shadow] duration-200",
              focused
                ? "border-[var(--color-border-strong)] shadow-[0_0_0_1px_color-mix(in_oklch,var(--color-accent)_35%,transparent),0_24px_60px_-28px_color-mix(in_oklch,var(--color-accent)_45%,transparent)]"
                : "border-[var(--color-border)]"
            )}
          >
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value.slice(0, MAX_CHARS))}
              onFocus={() => setFocused(true)}
              onBlur={() => setFocused(false)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submit();
                }
              }}
              rows={1}
              placeholder={placeholder}
              disabled={disabled}
              aria-label="Chat message"
              className="max-h-[220px] min-h-[64px] w-full resize-none bg-transparent px-5 pb-1 pt-4 text-[15px] leading-6 text-[var(--color-fg)] placeholder:text-[var(--color-fg-subtle)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
            />

            <div className="flex items-center justify-between gap-2 px-3 pb-2">
              <div className="flex items-center gap-1">
                <IconButton label="Attach file" disabled>
                  <Paperclip className="size-4" />
                </IconButton>
                <IconButton label="Voice message" disabled>
                  <Mic className="size-4" />
                </IconButton>
                <span
                  className={cn(
                    "ml-2 font-mono text-[11px] transition-colors",
                    charWarning
                      ? "text-[var(--color-warning)]"
                      : "text-[var(--color-fg-subtle)]"
                  )}
                  aria-live="polite"
                >
                  {charCount} / {MAX_CHARS}
                </span>
              </div>

              <div className="flex items-center gap-3">
                <span className="hidden font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)] sm:inline">
                  mid · ≤ 1.4k ctx
                </span>
                <motion.div
                  whileHover={canSubmit ? { scale: 1.05 } : {}}
                  whileTap={canSubmit ? { scale: 0.95 } : {}}
                  transition={{ type: "spring", stiffness: 400, damping: 20 }}
                >
                  <Button
                    type="button"
                    size="icon"
                    onClick={submit}
                    disabled={!canSubmit}
                    aria-label={disabled ? "Sending message" : "Send message"}
                    className="size-9 rounded-full"
                  >
                    <AnimatePresence mode="wait" initial={false}>
                      {disabled ? (
                        <motion.span
                          key="loading"
                          initial={{ opacity: 0, rotate: -90 }}
                          animate={{ opacity: 1, rotate: 0 }}
                          exit={{ opacity: 0, rotate: 90 }}
                          transition={{ duration: 0.2 }}
                        >
                          <Loader2 className="size-4 animate-spin" />
                        </motion.span>
                      ) : (
                        <motion.span
                          key="send"
                          initial={{ opacity: 0, y: 4 }}
                          animate={{ opacity: 1, y: 0 }}
                          exit={{ opacity: 0, y: -4 }}
                          transition={{ duration: 0.2 }}
                        >
                          <ArrowUp className="size-4" />
                        </motion.span>
                      )}
                    </AnimatePresence>
                  </Button>
                </motion.div>
              </div>
            </div>
          </div>
        </div>

        <div className="mx-auto mt-2 flex justify-between px-1 font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
          <span>
            <kbd className="rounded border border-[var(--color-border)] px-1 py-px">⏎</kbd> send
            {" · "}
            <kbd className="rounded border border-[var(--color-border)] px-1 py-px">⇧⏎</kbd>{" "}
            new line
          </span>
          <span className="hidden sm:inline">
            Meridian may produce grounded answers with citations.
          </span>
        </div>
      </div>
    </div>
  );
}

function IconButton({
  children,
  label,
  disabled,
}: {
  children: React.ReactNode;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      title={disabled ? `${label} (coming soon)` : label}
      className="inline-flex size-8 items-center justify-center rounded-full text-[var(--color-fg-subtle)] transition-colors hover:bg-[var(--color-bg-panel)] hover:text-[var(--color-fg-muted)] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
    >
      {children}
    </button>
  );
}

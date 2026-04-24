"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowUp, Loader2 } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/utils";

interface InputBarProps {
  onSubmit: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  prefill?: string | null;
  onPrefillConsumed?: () => void;
}

export function InputBar({
  onSubmit,
  disabled,
  placeholder = "Ask Meridian anything…",
  prefill,
  onPrefillConsumed,
}: InputBarProps) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (prefill != null) {
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

  const submit = () => {
    if (!canSubmit) return;
    onSubmit(value);
    setValue("");
  };

  return (
    <div className="sticky bottom-0 z-10 border-t border-[var(--color-border)]/60 bg-[var(--color-bg)]/80 px-5 py-4 backdrop-blur-xl">
      <div className="mx-auto flex w-full max-w-3xl items-end gap-2">
        <div
          className={cn(
            "relative flex w-full items-end rounded-[var(--radius-xl)] border bg-[var(--color-bg-elevated)] transition-all",
            value
              ? "border-[var(--color-border-strong)]"
              : "border-[var(--color-border)]"
          )}
        >
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                submit();
              }
            }}
            rows={1}
            placeholder={placeholder}
            disabled={disabled}
            className="max-h-[220px] min-h-[56px] flex-1 resize-none bg-transparent px-5 py-4 text-[15px] leading-6 text-[var(--color-fg)] placeholder:text-[var(--color-fg-subtle)] focus:outline-none disabled:cursor-not-allowed disabled:opacity-50"
          />
          <div className="p-2">
            <Button
              type="button"
              size="icon"
              onClick={submit}
              disabled={!canSubmit}
              aria-label="Send message"
              className="rounded-full"
            >
              {disabled ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <ArrowUp className="size-4" />
              )}
            </Button>
          </div>
        </div>
      </div>
      <div className="mx-auto mt-2 flex max-w-3xl justify-between px-1 font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
        <span>
          <kbd className="rounded border border-[var(--color-border)] px-1 py-px">⏎</kbd> send
          {" · "}
          <kbd className="rounded border border-[var(--color-border)] px-1 py-px">⇧⏎</kbd> new line
        </span>
        <span>Meridian may produce grounded answers with citations.</span>
      </div>
    </div>
  );
}

"use client";

import { useRouter } from "next/navigation";
import { useRef, useState, useTransition } from "react";
import { Upload } from "lucide-react";

import { Button } from "@/components/ui/Button";

const ACCEPTED = ".pdf,.txt,.md,application/pdf,text/plain,text/markdown";
const MAX_BYTES = 10 * 1024 * 1024;

export function UploadForm() {
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();
  const fileInput = useRef<HTMLInputElement>(null);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const form = event.currentTarget;
    const file = (form.elements.namedItem("file") as HTMLInputElement).files?.[0];
    if (!file) {
      setError("Pick a file first.");
      return;
    }
    if (file.size > MAX_BYTES) {
      setError("File is too large (10 MB max).");
      return;
    }

    const data = new FormData();
    data.append("file", file);
    data.append("title", file.name);

    const response = await fetch("/api/documents", {
      method: "POST",
      body: data,
    });
    if (!response.ok) {
      const text = await response.text();
      setError(text || `Upload failed (${response.status}).`);
      return;
    }

    if (fileInput.current) fileInput.current.value = "";
    // Server-rendered list re-fetches when we ask Next.js to refresh.
    startTransition(() => router.refresh());
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="flex flex-wrap items-center gap-3"
      aria-label="Upload document"
    >
      <input
        ref={fileInput}
        type="file"
        name="file"
        accept={ACCEPTED}
        required
        className="block w-full max-w-xs cursor-pointer rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-bg)] px-3 py-2 text-xs text-[var(--color-fg-muted)] file:mr-3 file:rounded-[var(--radius-sm)] file:border-0 file:bg-[var(--color-bg-elevated)] file:px-3 file:py-1.5 file:text-xs file:font-medium file:text-[var(--color-fg)] hover:file:bg-[var(--color-bg-panel)]"
      />
      <Button type="submit" variant="primary" size="sm" disabled={pending} className="gap-1">
        <Upload className="size-4" aria-hidden />
        {pending ? "Uploading…" : "Upload"}
      </Button>
      {error ? (
        <p role="alert" className="basis-full text-xs text-[var(--color-danger)]">
          {error}
        </p>
      ) : null}
    </form>
  );
}

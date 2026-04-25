import { FileText } from "lucide-react";

import { UploadForm } from "@/components/documents/UploadForm";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/Card";
import { listDocumentsSafe } from "@/lib/documents";
import { requireSession } from "@/lib/session-guard";

export const dynamic = "force-dynamic";

export default async function DocumentsPage() {
  const ctx = await requireSession();
  // ``listDocumentsSafe`` returns [] when the documents table doesn't exist
  // yet (Phase 6 ships the migration). The shell renders the same way either
  // way so this page becomes useful the moment ingestion lands.
  const docs = await listDocumentsSafe(ctx.workspaceId);

  return (
    <div className="mx-auto w-full max-w-6xl px-5 py-8">
      <header className="mb-8 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-[var(--color-fg)]">
            Documents
          </h1>
          <p className="text-sm text-[var(--color-fg-muted)]">
            Knowledge base for grounded answers. Tenant-scoped to this workspace.
          </p>
        </div>
        <UploadForm />
      </header>

      <Card>
        <CardHeader>
          <CardTitle>Indexed sources</CardTitle>
          <CardDescription>
            {docs.length === 0
              ? "Nothing indexed yet — upload to build your knowledge base."
              : `${docs.length} source${docs.length === 1 ? "" : "s"} indexed.`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {docs.length === 0 ? (
            <EmptyState />
          ) : (
            <ul className="divide-y divide-[var(--color-border)]/60">
              {docs.map((d) => (
                <li
                  key={d.id}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <FileText
                      className="size-4 shrink-0 text-[var(--color-fg-subtle)]"
                      aria-hidden
                    />
                    <div className="min-w-0">
                      <div className="truncate text-sm font-medium text-[var(--color-fg)]">
                        {d.title || d.id.slice(0, 8)}
                      </div>
                      <div className="font-mono text-[10px] uppercase tracking-[0.15em] text-[var(--color-fg-subtle)]">
                        {d.id.slice(0, 8)} · {d.chunk_count} chunk
                        {d.chunk_count === 1 ? "" : "s"}
                      </div>
                    </div>
                  </div>
                  <StatusBadge status={d.status} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-start gap-3 rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] bg-[var(--color-bg)] p-6">
      <FileText className="size-5 text-[var(--color-fg-subtle)]" aria-hidden />
      <div>
        <div className="text-sm font-medium text-[var(--color-fg)]">No documents yet</div>
        <p className="text-xs leading-relaxed text-[var(--color-fg-muted)]">
          Once ingestion is enabled, uploads will be chunked, embedded, and stored in
          pgvector — scoped to this workspace. Until then, retrieval falls back to the
          configured external RAG client.
        </p>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: "indexed" | "indexing" | "failed" }) {
  if (status === "indexed") return <Badge variant="success">Indexed</Badge>;
  if (status === "indexing") return <Badge variant="info">Indexing</Badge>;
  return <Badge variant="danger">Failed</Badge>;
}

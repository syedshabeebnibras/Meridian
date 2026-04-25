// Documents data access. The ``documents`` table is added by the Phase 6
// ingestion migration; until then we return [] so the UI can render the
// empty state without a 500.
//
// We pin ``in_memory: true`` after the first ENOENT so we don't hammer the
// server with the same failing query on every render — sticky null pattern.

import "server-only";

import { pool } from "@/lib/db";

export type DocumentStatus = "indexed" | "indexing" | "failed";

export interface DocumentRow {
  id: string;
  title: string;
  status: DocumentStatus;
  chunk_count: number;
  created_at: string;
}

let _documentsTableMissing = false;

export async function listDocumentsSafe(workspaceId: string): Promise<DocumentRow[]> {
  if (_documentsTableMissing) return [];
  try {
    const { rows } = await pool.query<DocumentRow>(
      `SELECT id::text, title, status, chunk_count, created_at::text
       FROM documents
       WHERE workspace_id = $1
       ORDER BY created_at DESC
       LIMIT 100`,
      [workspaceId]
    );
    return rows;
  } catch (err) {
    // Postgres ``42P01`` = undefined_table. Anything else (real query bug,
    // connectivity) we surface so it shows up in logs/Sentry.
    if (
      err &&
      typeof err === "object" &&
      "code" in err &&
      (err as { code?: string }).code === "42P01"
    ) {
      _documentsTableMissing = true;
      return [];
    }
    throw err;
  }
}

// Thin Postgres client for auth-time lookups + workspace reads.
// Schema ownership lives in the Python side (Alembic + SQLAlchemy) — this
// module is strictly *consume-only* for auth and session-list flows.

import "server-only";

import { Pool } from "pg";

const connectionString =
  process.env.DATABASE_URL_JS ??
  // Our Python DATABASE_URL uses the `postgresql+psycopg` scheme which
  // node-postgres doesn't understand. Strip the `+psycopg` suffix as a
  // convenience so a single env var works for both sides in dev.
  (process.env.DATABASE_URL
    ? process.env.DATABASE_URL.replace(/^postgresql\+psycopg:\/\//, "postgresql://")
    : undefined);

if (!connectionString && process.env.MERIDIAN_ENV === "production") {
  throw new Error("DATABASE_URL(_JS) is required in production");
}

declare global {
  // eslint-disable-next-line no-var
  var __meridian_pg__: Pool | undefined;
}

export const pool: Pool =
  globalThis.__meridian_pg__ ??
  new Pool({
    connectionString,
    // Keep the pool small — this process only handles auth + session reads.
    max: 4,
    idleTimeoutMillis: 30_000,
    // Conservative timeouts so a hung DB doesn't ruin the middleware chain.
    connectionTimeoutMillis: 4_000,
  });

if (process.env.NODE_ENV !== "production") {
  globalThis.__meridian_pg__ = pool;
}

export interface DbUser {
  id: string;
  email: string;
  name: string;
  password_hash: string | null;
}

export interface DbWorkspace {
  id: string;
  name: string;
  slug: string;
}

export interface DbMembership {
  workspace_id: string;
  workspace_name: string;
  workspace_slug: string;
  role: "owner" | "admin" | "member" | "viewer";
}

export async function findUserByEmail(email: string): Promise<DbUser | null> {
  const { rows } = await pool.query<DbUser>(
    `SELECT id::text, email, name, password_hash
     FROM users
     WHERE lower(email) = lower($1)
     LIMIT 1`,
    [email]
  );
  return rows[0] ?? null;
}

export async function findUserById(id: string): Promise<DbUser | null> {
  const { rows } = await pool.query<DbUser>(
    `SELECT id::text, email, name, password_hash
     FROM users WHERE id = $1`,
    [id]
  );
  return rows[0] ?? null;
}

export async function listMemberships(userId: string): Promise<DbMembership[]> {
  const { rows } = await pool.query<DbMembership>(
    `SELECT m.workspace_id::text AS workspace_id,
            w.name               AS workspace_name,
            w.slug               AS workspace_slug,
            m.role               AS role
     FROM memberships m
     JOIN workspaces w ON w.id = m.workspace_id
     WHERE m.user_id = $1 AND w.deleted_at IS NULL
     ORDER BY w.created_at`,
    [userId]
  );
  return rows;
}

// ---------------------------------------------------------------------------
// Workspace-scoped reads (Phase 5 product shell)
// ---------------------------------------------------------------------------
// All queries here MUST be parameterised by ``workspaceId``. The caller is
// responsible for resolving the workspace from the authenticated session
// before invoking — we never trust a client-supplied workspace_id.

export interface RecentChat {
  id: string;
  title: string;
  updated_at: string;
  message_count: number;
}

export async function listRecentChats(
  workspaceId: string,
  limit = 5
): Promise<RecentChat[]> {
  const { rows } = await pool.query<RecentChat>(
    `SELECT s.id::text, s.title, s.updated_at::text,
            (SELECT count(*) FROM chat_messages m WHERE m.session_id = s.id)::int AS message_count
     FROM chat_sessions s
     WHERE s.workspace_id = $1 AND s.deleted_at IS NULL
     ORDER BY s.updated_at DESC
     LIMIT $2`,
    [workspaceId, limit]
  );
  return rows;
}

export interface UsageWindow {
  total_requests: number;
  total_cost_usd: string;
  total_input_tokens: number;
  total_output_tokens: number;
}

export async function getWorkspaceUsage(
  workspaceId: string,
  windowDays = 7
): Promise<UsageWindow> {
  const { rows } = await pool.query<UsageWindow>(
    `SELECT count(*)::int                                    AS total_requests,
            coalesce(sum(cost_usd), 0)::text                 AS total_cost_usd,
            coalesce(sum(input_tokens), 0)::int              AS total_input_tokens,
            coalesce(sum(output_tokens), 0)::int             AS total_output_tokens
     FROM usage_records
     WHERE workspace_id = $1
       AND created_at >= now() - ($2 || ' days')::interval`,
    [workspaceId, String(windowDays)]
  );
  return (
    rows[0] ?? {
      total_requests: 0,
      total_cost_usd: "0",
      total_input_tokens: 0,
      total_output_tokens: 0,
    }
  );
}

export interface WorkspaceMember {
  user_id: string;
  email: string;
  name: string;
  role: "owner" | "admin" | "member" | "viewer";
  created_at: string;
}

export async function listWorkspaceMembers(
  workspaceId: string
): Promise<WorkspaceMember[]> {
  const { rows } = await pool.query<WorkspaceMember>(
    `SELECT u.id::text       AS user_id,
            u.email           AS email,
            u.name            AS name,
            m.role            AS role,
            m.created_at::text AS created_at
     FROM memberships m
     JOIN users u ON u.id = m.user_id
     WHERE m.workspace_id = $1
     ORDER BY
       CASE m.role
         WHEN 'owner'  THEN 0
         WHEN 'admin'  THEN 1
         WHEN 'member' THEN 2
         WHEN 'viewer' THEN 3
       END,
       u.email`,
    [workspaceId]
  );
  return rows;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  slug: string;
  created_at: string;
}

export async function getWorkspace(workspaceId: string): Promise<WorkspaceSummary | null> {
  const { rows } = await pool.query<WorkspaceSummary>(
    `SELECT id::text, name, slug, created_at::text
     FROM workspaces
     WHERE id = $1 AND deleted_at IS NULL`,
    [workspaceId]
  );
  return rows[0] ?? null;
}

/**
 * Transactionally create a user, a personal workspace, and the owner
 * membership. Called from the sign-up server action so the sign-up path
 * doesn't require hitting the Python side.
 */
export async function createUserAndPersonalWorkspace(params: {
  email: string;
  name: string;
  passwordHash: string;
}): Promise<{ userId: string; workspaceId: string; workspaceSlug: string }> {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    const userRes = await client.query<{ id: string }>(
      `INSERT INTO users (id, email, name, password_hash, created_at, updated_at)
       VALUES (gen_random_uuid(), lower($1), $2, $3, now(), now())
       RETURNING id::text`,
      [params.email, params.name, params.passwordHash]
    );
    const userId = userRes.rows[0].id;
    const slugBase = params.email.split("@")[0]!.replace(/[^a-z0-9-]/gi, "").toLowerCase().slice(0, 32);
    const slug = `${slugBase || "workspace"}-${userId.slice(0, 4)}`;
    const wsRes = await client.query<{ id: string; slug: string }>(
      `INSERT INTO workspaces (id, name, slug, owner_user_id, created_at)
       VALUES (gen_random_uuid(), $1, $2, $3, now())
       RETURNING id::text, slug`,
      [`${params.name}'s workspace`, slug, userId]
    );
    const workspaceId = wsRes.rows[0].id;
    const workspaceSlug = wsRes.rows[0].slug;
    await client.query(
      `INSERT INTO memberships (user_id, workspace_id, role, created_at)
       VALUES ($1, $2, 'owner', now())`,
      [userId, workspaceId]
    );
    await client.query("COMMIT");
    return { userId, workspaceId, workspaceSlug };
  } catch (err) {
    await client.query("ROLLBACK");
    throw err;
  } finally {
    client.release();
  }
}

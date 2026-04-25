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

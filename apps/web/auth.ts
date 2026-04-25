import NextAuth, { type DefaultSession } from "next-auth";
import Credentials from "next-auth/providers/credentials";
import { verify as verifyArgon2 } from "@node-rs/argon2";
import { z } from "zod";

import { authConfig } from "@/auth.config";
import { findUserByEmail, findUserById, listMemberships } from "@/lib/db";

/**
 * Types augment — we stash the active workspace + role on the JWT so the
 * middleware can inject them into the Next.js proxy call to the
 * orchestrator without an extra DB round-trip.
 */
declare module "next-auth" {
  interface Session {
    user: {
      id: string;
      email: string;
      name: string;
      activeWorkspaceId?: string;
      activeWorkspaceRole?: "owner" | "admin" | "member" | "viewer";
    } & DefaultSession["user"];
  }
  interface User {
    id?: string;
    activeWorkspaceId?: string;
    activeWorkspaceRole?: "owner" | "admin" | "member" | "viewer";
  }
}

// Auth.js v5 doesn't expose a `next-auth/jwt` module path the same way v4
// did — token shape augments through the JWT callback's local types.

const credentialsSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1).max(256),
});

export const { handlers, signIn, signOut, auth } = NextAuth({
  ...authConfig,
  // AUTH_SECRET is the v5 env var name. In production Auth.js refuses to
  // boot without it — which is the right fail-closed default.
  providers: [
    Credentials({
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(raw) {
        const parsed = credentialsSchema.safeParse(raw);
        if (!parsed.success) return null;

        const user = await findUserByEmail(parsed.data.email);
        if (!user || !user.password_hash) return null;

        const ok = await verifyArgon2(user.password_hash, parsed.data.password);
        if (!ok) return null;

        return {
          id: user.id,
          email: user.email,
          name: user.name,
        };
      },
    }),
  ],
  callbacks: {
    async jwt({ token, user, trigger, session }) {
      // On sign-in: stash id/email/name + eagerly resolve the first membership.
      if (user && user.id) {
        token.sub = user.id;
        token.email = user.email ?? undefined;
        token.name = user.name ?? undefined;
        const memberships = await listMemberships(user.id);
        if (memberships.length > 0) {
          token.activeWorkspaceId = memberships[0]!.workspace_id;
          token.activeWorkspaceRole = memberships[0]!.role;
        }
      }
      // Explicit workspace switch via useSession().update({activeWorkspaceId}).
      const sessionUser = (session as { user?: { activeWorkspaceId?: unknown } } | null)?.user;
      const requestedWs =
        typeof sessionUser?.activeWorkspaceId === "string"
          ? sessionUser.activeWorkspaceId
          : undefined;
      if (trigger === "update" && requestedWs) {
        token.activeWorkspaceId = requestedWs;
        if (token.sub) {
          const memberships = await listMemberships(token.sub);
          const match = memberships.find((m) => m.workspace_id === requestedWs);
          if (match) token.activeWorkspaceRole = match.role;
        }
      }
      return token;
    },
    async session({ session, token }) {
      if (token.sub) {
        const t = token as {
          sub: string;
          email?: string;
          name?: string;
          activeWorkspaceId?: string;
          activeWorkspaceRole?: "owner" | "admin" | "member" | "viewer";
        };
        session.user = {
          ...session.user,
          id: t.sub,
          email: t.email ?? session.user.email ?? "",
          name: t.name ?? session.user.name ?? "",
          activeWorkspaceId: t.activeWorkspaceId,
          activeWorkspaceRole: t.activeWorkspaceRole,
        };
      }
      return session;
    },
    // ``authorized`` is inherited from authConfig (edge-safe).
  },
});

/** Re-export for pages/routes that need to check membership ad-hoc. */
export { findUserById, listMemberships };

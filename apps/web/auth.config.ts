import type { NextAuthConfig } from "next-auth";

/**
 * Edge-safe slice of the auth config.
 *
 * The Next.js middleware runs in the Edge runtime, which can't load the
 * Node-native @node-rs/argon2 binding nor the pg client used by the
 * Credentials provider. This file exports ONLY the parts of the config
 * that work in both runtimes — pages, session strategy, and the
 * ``authorized`` callback the middleware reads.
 *
 * The full ``auth.ts`` extends this with Node-only providers + callbacks.
 */
export const authConfig: NextAuthConfig = {
  session: {
    strategy: "jwt",
    maxAge: 60 * 60 * 24 * 7, // 7 days
  },
  pages: {
    signIn: "/sign-in",
  },
  // Providers attached in auth.ts. Empty here so Edge bundling stays clean.
  providers: [],
  callbacks: {
    authorized({ auth, request }) {
      const pathname = request.nextUrl.pathname;
      // Public surfaces.
      if (
        pathname === "/" ||
        pathname.startsWith("/sign-in") ||
        pathname.startsWith("/sign-up") ||
        pathname.startsWith("/api/auth") ||
        pathname.startsWith("/api/metrics") ||
        pathname.startsWith("/_next") ||
        pathname === "/favicon.svg"
      ) {
        return true;
      }
      return !!auth?.user;
    },
  },
};

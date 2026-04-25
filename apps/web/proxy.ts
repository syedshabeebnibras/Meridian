import NextAuth from "next-auth";

import { authConfig } from "@/auth.config";

// Proxy runs in the Edge runtime — only the auth.config.ts slice
// (no DB, no argon2) is imported here. The full Auth.js setup lives in
// auth.ts and is used by route handlers + server components.
const { auth } = NextAuth(authConfig);

export default auth;

export const config = {
  matcher: [
    "/((?!_next/static|_next/image|favicon.svg|api/metrics|api/auth).*)",
  ],
};

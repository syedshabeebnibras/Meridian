import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appDir = path.dirname(fileURLToPath(import.meta.url));

// Security headers — Section N of the production hardening spec.
//
// HSTS is set by Vercel automatically. CSP is intentionally NOT set here
// yet: Auth.js issues inline scripts during the OAuth/Credentials flow,
// so a strict ``Content-Security-Policy`` needs per-page tuning + a
// nonce or hash strategy. Tracked separately; until then, every other
// header is locked down.
const SECURITY_HEADERS = [
  // Replaces the legacy X-Frame-Options DENY. ``frame-ancestors 'none'``
  // is the modern equivalent and supersedes XFO when both are set.
  { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
  // Belt-and-braces: legacy browsers still honour XFO.
  { key: "X-Frame-Options", value: "DENY" },
  // No MIME sniffing on assets we serve.
  { key: "X-Content-Type-Options", value: "nosniff" },
  // Send the Referer for same-origin nav, only the origin for cross-site.
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  // Disable powerful features the app never asks for.
  {
    key: "Permissions-Policy",
    value:
      "camera=(), microphone=(), geolocation=(), payment=(), usb=(), magnetometer=(), accelerometer=(), gyroscope=()",
  },
];

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  ...(process.env.VERCEL ? {} : { outputFileTracingRoot: path.join(appDir, "../..") }),
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion"],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: SECURITY_HEADERS,
      },
    ];
  },
};

export default config;

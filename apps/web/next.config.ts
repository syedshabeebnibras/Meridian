import type { NextConfig } from "next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const appDir = path.dirname(fileURLToPath(import.meta.url));

const config: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  outputFileTracingRoot: path.join(appDir, "../.."),
  experimental: {
    optimizePackageImports: ["lucide-react", "framer-motion"],
  },
};

export default config;

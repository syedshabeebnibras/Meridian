// Flat ESLint config for the Next.js 15 web app.

import nextConfig from "eslint-config-next";

const config = [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "lib/generated/**",
      "build/**",
      "next-env.d.ts",
    ],
  },
  ...nextConfig,
];

export default config;

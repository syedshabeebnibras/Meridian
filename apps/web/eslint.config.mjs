// Flat ESLint config for the Next.js 15 web app.

import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const nextConfigDir = path.dirname(require.resolve("eslint-config-next/package.json"));
const nextPlugin = require(path.join(nextConfigDir, "../@next/eslint-plugin-next"));

export default [
  {
    ignores: [
      ".next/**",
      "node_modules/**",
      "lib/generated/**",
      "build/**",
      "next-env.d.ts",
    ],
  },
  nextPlugin.flatConfig.recommended,
  nextPlugin.flatConfig.coreWebVitals,
];

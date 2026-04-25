// Flat ESLint config for the Next.js 15 web app.
//
// Next.js 16 deprecates ``next lint`` so we run ESLint directly. This is a
// minimal viable config — TypeScript compiler does the heavy lifting via
// ``pnpm typecheck``. Add rules here as the codebase grows.

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
];

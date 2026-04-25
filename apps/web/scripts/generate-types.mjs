#!/usr/bin/env node
/**
 * Generate TypeScript types from the orchestrator's JSON Schemas.
 *
 * Pipeline:
 *   1. Run ``uv run python scripts/export_schemas.py --out build/schemas``
 *      from the repo root to regenerate the schemas Python ships.
 *   2. For each ``*.schema.json`` under ``build/schemas/``, emit a TS file
 *      into ``apps/web/lib/generated/`` with a single named export.
 *   3. Write an ``index.ts`` barrel that re-exports every generated type.
 *
 * The output is committed. CI re-runs this script and fails on
 * ``git diff --exit-code`` so the frontend types can never silently drift
 * from the Python contracts.
 */

import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { compile } from "json-schema-to-typescript";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(__dirname, "../../..");
const SCHEMAS_DIR = join(REPO_ROOT, "build/schemas");
const GENERATED_DIR = resolve(__dirname, "../lib/generated");

// File header — keeping this stable matters because changing it would
// produce a noisy diff on every regeneration. Bump the version line if the
// generator's behaviour changes.
const HEADER = `/**
 * AUTO-GENERATED — do not edit by hand.
 *
 * Source: packages/contracts (Pydantic) → scripts/export_schemas.py →
 *         apps/web/scripts/generate-types.mjs.
 *
 * To regenerate run \`pnpm gen-types\` from apps/web. CI fails the build
 * if this file is out of sync with the Python contracts.
 */
`;

function regenerateSchemas() {
  console.log("[gen-types] regenerating JSON schemas via uv…");
  // execFileSync (not exec) — args go through the syscall as an argv array,
  // so no shell interpretation. The args are static; no user input.
  execFileSync(
    "uv",
    ["run", "python", "scripts/export_schemas.py", "--out", "build/schemas"],
    { cwd: REPO_ROOT, stdio: "inherit" }
  );
}

async function compileOne(schemaPath, outName) {
  const schema = JSON.parse(readFileSync(schemaPath, "utf-8"));
  const tsBody = await compile(schema, outName, {
    bannerComment: "",
    additionalProperties: false,
    style: { singleQuote: false, semi: true },
    // Inline ``$ref`` resolution against the same file. Pydantic's emitted
    // schemas use ``$defs`` for shared definitions; the lib follows them
    // automatically when ``cwd`` is the schema dir.
    cwd: dirname(schemaPath),
  });
  return HEADER + tsBody;
}

async function main() {
  regenerateSchemas();

  // Wipe the generated dir so deleted contracts don't leave stale .ts.
  rmSync(GENERATED_DIR, { recursive: true, force: true });
  mkdirSync(GENERATED_DIR, { recursive: true });

  const schemaFiles = readdirSync(SCHEMAS_DIR).filter((f) => f.endsWith(".schema.json"));
  schemaFiles.sort();
  const exportNames = [];
  for (const file of schemaFiles) {
    const name = file.replace(/\.schema\.json$/, "");
    const outFile = join(GENERATED_DIR, `${name}.ts`);
    const ts = await compileOne(join(SCHEMAS_DIR, file), name);
    writeFileSync(outFile, ts);
    exportNames.push(name);
    console.log(`[gen-types] wrote ${name}.ts`);
  }

  const barrel =
    HEADER +
    exportNames.map((n) => `export type { ${n} } from "./${n}";`).join("\n") +
    "\n";
  writeFileSync(join(GENERATED_DIR, "index.ts"), barrel);
  console.log(`[gen-types] wrote index.ts (${exportNames.length} exports)`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});

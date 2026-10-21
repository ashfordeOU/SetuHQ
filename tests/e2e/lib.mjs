// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Find the playwright package: next to the repository (npm install), on SETUHQ_PLAYWRIGHT, or in the global
// node_modules. It never downloads a browser; PLAYWRIGHT_BROWSERS_PATH picks an installed one.
import { createRequire } from "node:module";
import { execSync } from "node:child_process";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

export async function loadPlaywright() {
  const tries = [];
  if (process.env.SETUHQ_PLAYWRIGHT) tries.push(process.env.SETUHQ_PLAYWRIGHT);
  tries.push("playwright");
  try { tries.push(join(execSync("npm root -g", { encoding: "utf8" }).trim(), "playwright")); } catch (e) { /* no npm */ }
  const req = createRequire(import.meta.url);
  for (const t of tries) {
    try {
      const p = t.startsWith("/") ? await import(pathToFileURL(join(t, "index.mjs")).href) : req(t);
      return p.chromium ? p : p.default;
    } catch (e) { /* the next */ }
  }
  throw new Error("the playwright package was not found: npm install playwright, or set SETUHQ_PLAYWRIGHT to its folder");
}

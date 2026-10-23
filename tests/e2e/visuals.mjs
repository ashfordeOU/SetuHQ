// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The end-to-end test of the site's visual system (docs/SITE.md, "The visual system"), run by scripts/site_e2e.sh after
// tests/e2e/run.mjs:
//
//   node tests/e2e/visuals.mjs --site site [--browser chromium|webkit] [--report visuals-report.json] [--outputs DIR] [--only NAME]
//
// --outputs: the CLI outputs built by tests/e2e/build_outputs.py (scripts/site_e2e.sh builds them; without it
// checks/outputs.mjs builds its own). --only: run one module of checks/ (e.g. --only outputs).
//
// It runs every module in tests/e2e/checks/ (each exports a default async function given the helpers below), in name
// order: checks/system.mjs is the renderer, the motion budget, the honesty labels, the stages in light mode, layout
// shift and the header (phase 0); each later phase adds its own module there.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { serve } from "./server.mjs";
import { loadPlaywright } from "./lib.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const SITE = resolve(arg("site", "site"));
const BROWSER = arg("browser", "chromium");
const results = [];
let group = "";
function check(ok, what, detail = "") {
  results.push({ test: group, what, ok: !!ok, detail: ok ? "" : String(detail).slice(0, 400) });
  if (!ok) console.log(`  FAIL ${group}: ${what}${detail ? " (" + String(detail).slice(0, 300) + ")" : ""}`);
  return !!ok;
}
const setGroup = (g) => { group = `${g} [${BROWSER}]`; };

const pw = await loadPlaywright();
const server = await serve(SITE);
const BASE = `http://127.0.0.1:${server.address().port}`;
const browser = await pw[BROWSER].launch(BROWSER === "chromium" ? { args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] } : {});
const SIZES = { desktop: { width: 1440, height: 900 }, phone: { width: 390, height: 844 } };
async function context({ size = "desktop", theme = "dark", motion = "reduce", js = true, init = null } = {}) {
  const phone = size === "phone";
  const ctx = await browser.newContext({ viewport: SIZES[size], isMobile: phone && BROWSER === "chromium", hasTouch: phone, colorScheme: theme,
    reducedMotion: motion, javaScriptEnabled: js });
  await ctx.addInitScript((t) => { try { localStorage.setItem("setuhq-theme", t); } catch (e) { /* private */ } }, theme);
  if (init) await ctx.addInitScript(init);
  return ctx;
}
function watch(page) {
  const errs = [];
  page.on("console", (m) => { if (m.type() === "error") errs.push("console: " + m.text()); });
  page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
  return errs;
}
const ready = (page) => page.waitForFunction(() => document.documentElement.dataset.ready === "1", null, { timeout: 20000 });
const AXE = readFileSync(join(HERE, "vendor", "axe.min.js"), "utf8");
const D = JSON.parse(readFileSync(join(SITE, "assets", "data", readdirSync(join(SITE, "assets", "data")).find((f) => /^app-.*\.json$/.test(f))), "utf8"));
const helpers = { browser, BASE, SITE, BROWSER, D, check, setGroup, context, watch, ready, AXE, OUTPUTS: arg("outputs", ""),
  pages: JSON.parse(readFileSync(join(SITE, "assets", "pages.json"), "utf8")) };
const ONLY = arg("only", "");

for (const f of readdirSync(join(HERE, "checks")).filter((x) => x.endsWith(".mjs") && (!ONLY || x === ONLY + ".mjs")).sort()) {
  setGroup(f);
  try { await (await import(pathToFileURL(join(HERE, "checks", f)).href)).default(helpers); }
  catch (e) { check(false, `${f} ran to the end`, e.stack || e.message); }
}

await browser.close();
server.close();
const failed = results.filter((r) => !r.ok);
console.log(`\nvisuals (${BROWSER}): ${results.length} checks in ${new Set(results.map((r) => r.test)).size} groups; ${failed.length} failed`);
const report = arg("report");
if (report) writeFileSync(report, JSON.stringify({ browser: BROWSER, checks: results.length, failed: failed.length, failures: failed }, null, 1));
process.exit(failed.length ? 1 : 0);

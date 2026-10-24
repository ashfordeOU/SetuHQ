// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Phase 5, the CLI outputs that write HTML: `setuhq report`, `dashboard`, `docket`, `plate` and the search feed page of
// `setuhq discover`, built from the stored lead run (tests/e2e/build_outputs.py; scripts/site_e2e.sh passes --outputs).
// Each is opened served over HTTP and from disk: it makes no request to another site, logs no error, scrolls no page
// sideways on a phone, passes axe (no serious or critical violation) in both themes, and prints to PDF.
import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { serve } from "../server.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");
const OUTPUTS = ["report", "dashboard", "docket", "plate", "discover"];
// The case file's signal list is a listbox whose rows are filled by its script (as on the site: run.mjs KNOWN_AXE).
const KNOWN_AXE = [{ page: "docket", rule: "aria-required-children", target: "#rows" }];
const pyOf = () => process.env.PYTHON || (existsSync(join(ROOT, ".venv", "bin", "python")) ? join(ROOT, ".venv", "bin", "python") : "python3");

export default async function outputs(h) {
  const { check, setGroup, context, AXE } = h;
  let dir = h.OUTPUTS, own = false;
  if (!dir || !existsSync(join(dir, "report", "index.html"))) {
    dir = mkdtempSync(join(tmpdir(), "setuhq-outputs-")); own = true;
    execFileSync(pyOf(), [join(ROOT, "tests", "e2e", "build_outputs.py"), dir], { cwd: ROOT, stdio: "ignore" });
  }
  const server = await serve(dir);
  const BASE = `http://127.0.0.1:${server.address().port}`;
  try {
    for (const name of OUTPUTS) {
      setGroup(`outputs: ${name}`);
      check(existsSync(join(dir, name, "index.html")), `setuhq ${name} wrote its page`);
      for (const [size, theme, via] of [["desktop", "dark", "http"], ["desktop", "light", "http"], ["phone", "dark", "file"]]) {
        const ctx = await context({ size, theme });
        const page = await ctx.newPage();
        const errs = [], foreign = [];
        page.on("console", (m) => { if (m.type() === "error") errs.push("console: " + m.text()); });
        page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
        page.on("requestfailed", (r) => errs.push("failed: " + r.url()));
        page.on("request", (r) => { const u = r.url(); if (!u.startsWith(BASE) && !u.startsWith("file:") && !u.startsWith("data:") && !u.startsWith("blob:")) foreign.push(u); });
        const url = via === "file" ? pathToFileURL(join(dir, name, "index.html")).href : `${BASE}/${name}/`;
        await page.goto(url, { waitUntil: "load" }); await page.waitForTimeout(500);
        const tag = `${name} (${size}, ${theme}, ${via})`;
        check(foreign.length === 0, `${tag}: no request leaves the page's own folder`, foreign.slice(0, 3).join(" | "));
        check(errs.length === 0, `${tag}: no console error or failed request`, errs.slice(0, 3).join(" | "));
        const r = await page.evaluate(() => ({ wide: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          font: getComputedStyle(document.body).fontFamily, bg: getComputedStyle(document.body).backgroundColor,
          geist: document.fonts ? [...document.fonts].some((f) => /Geist/.test(f.family) && f.status === "loaded") : true }));
        check(r.wide <= 0, `${tag}: no sideways scroll`, r.wide);
        check(/Geist/.test(r.font), `${tag}: set in Geist (self-hosted)`, r.font);
        if (via === "http") check(r.geist, `${tag}: the Geist file beside the page loaded`);
        const want = theme === "light" ? "rgb(245, 245, 247)" : "rgb(4, 6, 11)";
        if (name !== "docket" && name !== "plate") check(r.bg === want, `${tag}: the page ground is the ${theme} token`, r.bg);
        if (via === "http") {
          await page.addScriptTag({ content: AXE });
          const v = await page.evaluate(async () => (await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }, resultTypes: ["violations"] }))
            .violations.filter((x) => x.impact === "serious" || x.impact === "critical").map((x) => ({ id: x.id, nodes: x.nodes.map((n) => n.target.join(" ")) })));
          const left = v.filter((x) => !KNOWN_AXE.some((k) => k.page === name && k.rule === x.id && x.nodes.every((n) => n.startsWith(k.target))));
          check(left.length === 0, `${tag}: axe, no serious or critical violation`, JSON.stringify(left).slice(0, 300));
        }
        if (size === "desktop" && theme === "light") {
          await page.emulateMedia({ media: "print" });
          const pdf = await page.pdf({ format: "A4", printBackground: true });
          check(pdf.length > 5000 && pdf.subarray(0, 5).toString() === "%PDF-", `${tag}: prints to PDF`, pdf.length);
          await page.emulateMedia({ media: "screen" });
        }
        await ctx.close();
      }
    }
    // Built from a checkout path over 120 characters deep, every printed path is long and absolute: still no page
    // scrolls sideways on a phone (long paths wrap).
    setGroup("outputs: a deep checkout path");
    const deep = mkdtempSync(join(tmpdir(), "setuhq-outputs-deep-"));
    try {
      execFileSync(pyOf(), [join(ROOT, "tests", "e2e", "build_outputs.py"), deep, "--deep"], { cwd: ROOT, stdio: "ignore" });
      const ctx = await context({ size: "phone", theme: "dark" });
      const page = await ctx.newPage();
      for (const name of OUTPUTS) {
        await page.goto(pathToFileURL(join(deep, name, "index.html")).href, { waitUntil: "load" }); await page.waitForTimeout(300);
        const r = await page.evaluate(() => ({ wide: document.documentElement.scrollWidth - document.documentElement.clientWidth, long: document.body.textContent.includes("a-deliberately-long") }));
        check(r.wide <= 0, `${name} built from a deep path: no sideways scroll on a phone`, JSON.stringify(r));
      }
      const plate = await (async () => { await page.goto(pathToFileURL(join(deep, "plate", "index.html")).href); return page.evaluate(() => document.querySelector("footer.colophon").textContent.includes("a-deliberately-long")); })();
      check(plate, "the deep path is printed (so the check above saw it)");
      await ctx.close();
    } finally { rmSync(deep, { recursive: true, force: true }); }
    // The report's blind PNG is the stored file, byte for byte (also in tests/test_report_style.py).
    setGroup("outputs: the report's blind image");
    const same = execFileSync("sh", ["-c", `for f in "${ROOT}"/runs/tess-pi-men-s1/subjects/*.png; do cmp -s "$f" "${dir}/report/assets/$(basename "$f")" || echo "$f"; done`]).toString().trim();
    check(same === "", "each blind-coded PNG in the report is the run's own file", same);
  } finally {
    server.close();
    if (own) rmSync(dir, { recursive: true, force: true });
  }
}

// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The renderer's stills: one image per planet look at 512 px and 160 px (WebP, quality 75), drawn by SetuRender on
// its Canvas2D path in Chromium (WebGL is switched off, so the pixels come from the CPU and do not depend on a GPU).
// They are what a page shows before (or without) JavaScript, under reduced motion, and on the deploy-time stubs.
//
//   node tools/render_stills.mjs            # write src/setuhq/data/stills/*.webp and stills.json
//   node tools/render_stills.mjs --check    # fail when the renderer's code or the look table changed since
//
// stills.json records each file's sha256, and the sha256 of the renderer's code (setuhq.renderer.render_js()) and of
// the look table (setuhq.looks.LOOKS) that drew them; the check compares hashes, not pixels, so it works on any
// machine. Needs the playwright package with Chromium (as tests/e2e does); PYTHON picks the interpreter.
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { loadPlaywright } from "../tests/e2e/lib.mjs";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const OUT = join(ROOT, "src", "setuhq", "data", "stills");
const PY = process.env.PYTHON || (existsSync(join(ROOT, ".venv", "bin", "python")) ? join(ROOT, ".venv", "bin", "python") : "python3");
const info = JSON.parse(execFileSync(PY, ["-m", "setuhq.renderer"], { cwd: ROOT, env: { ...process.env, PYTHONPATH: join(ROOT, "src") }, maxBuffer: 1 << 26 }).toString());
const sha = (b) => createHash("sha256").update(b).digest("hex");

if (process.argv.includes("--check")) {
  const f = join(OUT, "stills.json");
  const m = existsSync(f) ? JSON.parse(readFileSync(f, "utf8")) : {};
  const bad = [];
  if (m.render_js_sha256 !== info.js_sha256) bad.push("the renderer's code (setuhq.renderer.RENDER_JS_SRC)");
  if (m.looks_sha256 !== info.looks_sha256) bad.push("the look table (setuhq.looks.LOOKS)");
  for (const look of info.looks) for (const px of info.sizes) {
    const file = join(OUT, `${look}-${px}.webp`);
    if (!existsSync(file) || sha(readFileSync(file)) !== ((m.files || {})[look] || {})[px]) bad.push(`${look}-${px}.webp`);
  }
  if (bad.length) { console.error(`render_stills --check: stale since the stills were drawn: ${bad.join(", ")}. Run: node tools/render_stills.mjs`); process.exit(1); }
  console.log(`render_stills --check: ${info.looks.length} looks × ${info.sizes.length} sizes are current`);
  process.exit(0);
}

const { chromium } = await loadPlaywright();
const browser = await chromium.launch();
const ctx = await browser.newContext({ deviceScaleFactor: 1, reducedMotion: "reduce", viewport: { width: 600, height: 600 } });
// The Canvas2D path: no WebGL context is available to the page.
await ctx.addInitScript(() => { const g = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/.test(t) ? null : g.call(this, t, ...a); }; });
const page = await ctx.newPage();
await page.setContent(`<!doctype html><html><body style="margin:0;background:#000"><script>${info.js.replace(/<\/script/g, "<\\/script")}</script></body></html>`);
const path = await page.evaluate(() => window.SetuRender.path());
if (path !== "canvas2d") throw new Error(`expected the canvas2d path, got ${path}`);
mkdirSync(OUT, { recursive: true });
const files = {};
let total = 0;
for (const look of info.looks) {
  files[look] = {};
  for (const px of info.sizes) {
    const url = await page.evaluate(({ look, px, seed }) => {
      const cv = document.createElement("canvas"); cv.style.cssText = `width:${px}px;height:${px}px;display:block`;
      document.body.replaceChildren(cv);
      window.SetuRender.planet(cv, { look, seed, rotation: 0.6, t: 0, cpu_max: 256 });
      return cv.toDataURL("image/webp", 0.75);
    }, { look, px, seed: info.seed });
    const buf = Buffer.from(url.split(",")[1], "base64");
    if (!url.startsWith("data:image/webp")) throw new Error("this Chromium does not encode WebP");
    writeFileSync(join(OUT, `${look}-${px}.webp`), buf);
    files[look][px] = sha(buf);
    total += buf.length;
  }
}
await browser.close();
writeFileSync(join(OUT, "stills.json"), JSON.stringify({ note: "Drawn by tools/render_stills.mjs on SetuRender's Canvas2D path in Chromium; seed 1, rotation 0.6 rad, lit from the upper left.",
  render_js_sha256: info.js_sha256, looks_sha256: info.looks_sha256, seed: info.seed, sizes: info.sizes, files }, null, 1) + "\n");
console.log(`render_stills: ${info.looks.length} looks × ${info.sizes.length} sizes, ${total.toLocaleString("en-GB")} bytes in all, into ${OUT}`);

// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The renderer's stills: one image per planet look at 512 px and 160 px (WebP, quality 75), drawn by SetuRender on
// its Canvas2D path in Chromium (WebGL is switched off, so the pixels come from the CPU and do not depend on a GPU).
// They are what a page shows before (or without) JavaScript, under reduced motion, and on the deploy-time stubs.
//
//   node tools/render_stills.mjs            # write src/setuhq/data/stills/*.webp and stills.json
//   node tools/render_stills.mjs --check    # fail when the renderer's code or the look table changed since
//   node tools/render_stills.mjs --figure lineup   # the README's showcase line-up (docs/assets/readme/lineup/)
//
// --figure lineup draws the worked examples' known planets to one scale beside Earth, Neptune and Jupiter, as the
// site's line-up (V07) does, from tools/gen_readme_assets.py --lineup-spec (the catalogue's radii and each planet's
// look and seed), on the same Canvas2D path: a black stage, framed in the light ground for the light variant.
// lineup/LINEUP.json records the spec's and the renderer's hashes and each file's; gen_readme_assets --check reads it.
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

if (process.argv.includes("--figure")) {
  const which = process.argv[process.argv.indexOf("--figure") + 1];
  if (which !== "lineup") { console.error(`render_stills: no figure named ${which} (known: lineup)`); process.exit(2); }
  const spec = JSON.parse(execFileSync(PY, [join(ROOT, "tools", "gen_readme_assets.py"), "--lineup-spec"], { cwd: ROOT, maxBuffer: 1 << 24 }).toString());
  const b64 = (f) => readFileSync(f).toString("base64");
  const { chromium } = await loadPlaywright();
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ deviceScaleFactor: 1, reducedMotion: "reduce", viewport: { width: spec.width + 40, height: spec.height + 40 } });
  await ctx.addInitScript(() => { const g = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/.test(t) ? null : g.call(this, t, ...a); }; });
  const page = await ctx.newPage();
  const faces = `@font-face{font-family:"Geist";font-weight:300 700;src:url(data:font/woff2;base64,${b64(spec.fonts.sans)}) format("woff2")}`
    + `@font-face{font-family:"Geist Mono";font-weight:400 600;src:url(data:font/woff2;base64,${b64(spec.fonts.mono)}) format("woff2")}`
    + `@font-face{font-family:"Geist";font-weight:300 700;src:url(data:font/woff;base64,${b64(spec.fonts.symbols)}) format("woff");unicode-range:U+2295,U+2605,U+2609}`
    + `@font-face{font-family:"Geist Mono";font-weight:400 600;src:url(data:font/woff;base64,${b64(spec.fonts.symbols)}) format("woff");unicode-range:U+2295,U+2605,U+2609}`;
  await page.setContent(`<!doctype html><html><head><style>${faces}body{margin:0;background:#000;font-family:Geist}</style></head><body><span style="font:600 16px Geist">a⊕</span><span style="font:400 13px Geist">a</span><span style="font:14px 'Geist Mono'">a⊕</span><script>${info.js.replace(/<\/script/g, "<\\/script")}</script></body></html>`);
  await page.evaluate(() => document.fonts.ready);
  const path = await page.evaluate(() => window.SetuRender.path());
  if (path !== "canvas2d") throw new Error(`expected the canvas2d path, got ${path}`);
  mkdirSync(spec.out, { recursive: true });
  const files = {};
  for (const name of spec.files) {
    const light = name.includes("-light.");
    const url = await page.evaluate(({ spec, light }) => {
      const W = spec.width, H = spec.height, cv = document.createElement("canvas");
      cv.width = W; cv.height = H; cv.style.cssText = `width:${W}px;height:${H}px;display:block`;
      document.body.replaceChildren(cv);
      const c = cv.getContext("2d");
      // The stage: black in both themes (as on the site); the light variant sits it in the light ground.
      const f = light ? 20 : 0, r = light ? 22 : 0;
      c.fillStyle = light ? "#F5F5F7" : "#000"; c.fillRect(0, 0, W, H);
      c.fillStyle = "#000"; c.beginPath(); c.roundRect(f, f, W - 2 * f, H - 2 * f, r); c.fill();
      const ink = "#ECEFF5", dim = "#9AA3B5";
      // Text with ⊕ drawn as a small circled plus (the canvas does not take the symbol font's glyph at text size).
      const text = (t, x, y, px) => {
        const parts = t.split("⊕"), w = (q) => c.measureText(q).width, sym = px * 0.62, gapx = px * 0.08;
        const total = parts.reduce((a, q) => a + w(q), 0) + (parts.length - 1) * (sym + 2 * gapx);
        let at = c.textAlign === "center" ? x - total / 2 : c.textAlign === "right" ? x - total : x; const keep = c.textAlign; c.textAlign = "left";
        parts.forEach((q, i) => { c.fillText(q, at, y); at += w(q);
          if (i < parts.length - 1){ const r = sym / 2, cx = at + gapx + r, cy = y - px * 0.36; c.save(); c.strokeStyle = c.fillStyle; c.lineWidth = Math.max(1, px / 12);
            c.beginPath(); c.arc(cx, cy, r, 0, 7); c.moveTo(cx - r, cy); c.lineTo(cx + r, cy); c.moveTo(cx, cy - r); c.lineTo(cx, cy + r); c.stroke(); c.restore(); at += sym + 2 * gapx; } });
        c.textAlign = keep; };
      c.textBaseline = "alphabetic";
      c.font = "500 13px 'Geist Mono'"; c.fillStyle = dim; c.textAlign = "left";
      c.fillText("PLANETS TO ONE SCALE", f + 36, f + 46);
      c.font = "600 26px Geist"; c.fillStyle = ink; c.fillText("The worked examples' known planets, beside Earth, Neptune and Jupiter", f + 36, f + 82);
      c.font = "500 12px 'Geist Mono'"; c.fillStyle = dim; c.textAlign = "right"; c.fillText("ARTIST'S IMPRESSION", W - f - 36, f + 46);
      // One Earth radius is the same width all along the row; a small planet's slot is as wide as its label.
      const items = spec.items, gap = 22, avail = W - 2 * f - 72, minSlot = 104;
      let s = 10;
      for (let k = 0; k < 30; k++) {
        const fixed = items.filter((x) => 2 * x.rp_re * s < minSlot), free = items.filter((x) => 2 * x.rp_re * s >= minSlot);
        s = (avail - gap * (items.length - 1) - fixed.length * minSlot) / free.reduce((a, x) => a + 2 * x.rp_re, 0);
      }
      const base = H - f - 112;
      let x = f + 36;
      for (const it of items) {
        const R = it.rp_re * s, slot = Math.max(2 * R, minSlot), cx = x + slot / 2;
        window.SetuRender.drawPlanet2D(c, cx, base - R, R, it.look, true, { seed: it.seed, rotation: 0.6, sync: true, cpuMax: 256 });
        c.textAlign = "center"; c.font = `${it.ref ? 400 : 600} 16px Geist`; c.fillStyle = it.ref ? dim : ink; c.fillText(it.name, cx, base + 32);
        c.font = "400 14px 'Geist Mono'"; c.fillStyle = dim; text(it.label, cx, base + 54, 14);
        x += slot + gap;
      }
      c.textAlign = "left"; c.font = "400 13px Geist"; c.fillStyle = dim;
      text(`Radii: ${spec.source} (1 RJ = 11.209 R⊕). Grey names: the Solar System references. Each look is chosen from the measured radius and the computed irradiation; composition is not measured.`, f + 36, H - f - 30, 13);
      return cv.toDataURL("image/webp", 0.86);
    }, { spec, light });
    const buf = Buffer.from(url.split(",")[1], "base64");
    if (!url.startsWith("data:image/webp")) throw new Error("this Chromium does not encode WebP");
    writeFileSync(join(spec.out, name), buf);
    files[name] = sha(buf);
    console.log(`render_stills --figure lineup: ${buf.length.toLocaleString("en-GB")} bytes, ${join(spec.out, name)}`);
  }
  await browser.close();
  writeFileSync(join(spec.out, "LINEUP.json"), JSON.stringify({ note: "Drawn by tools/render_stills.mjs --figure lineup on SetuRender's Canvas2D path in Chromium, from tools/gen_readme_assets.py --lineup-spec.",
    spec_sha256: spec.spec_sha256, render_js_sha256: info.js_sha256, size: [spec.width, spec.height], source: spec.source, commit: spec.commit, alt: spec.alt, files }, null, 1) + "\n");
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

// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Screenshots of every page of a built site at 1440 x 900 and 390 x 844 (dark, and light with --light), as JPEG,
// plus index.html, a contact sheet. For looking at the site, not for the README (tools/capture_site_shots.mjs).
//   node tests/e2e/gallery.mjs --site site --out <dir> [--light] [--only /explore/,/docs/] [--full]
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { serve } from "./server.mjs";
import { loadPlaywright } from "./lib.mjs";

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const site = resolve(arg("site", "site")), out = resolve(arg("out", "gallery"));
const themes = process.argv.includes("--light") ? ["dark", "light"] : ["dark"];
const full = process.argv.includes("--full");
mkdirSync(out, { recursive: true });
let pages = JSON.parse(readFileSync(join(site, "assets", "pages.json"), "utf8"));
pages.push("/this-page-does-not-exist/");
if (arg("only")) pages = arg("only").split(",");
const { chromium } = await loadPlaywright();
const server = await serve(site);
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch();
const sizes = [{ name: "desktop", width: 1440, height: 900 }, { name: "phone", width: 390, height: 844, mobile: true }];
const shots = [];
for (const theme of themes) for (const size of sizes) {
  const ctx = await browser.newContext({ viewport: { width: size.width, height: size.height }, deviceScaleFactor: 1, isMobile: !!size.mobile,
    hasTouch: !!size.mobile, colorScheme: theme, reducedMotion: "reduce" });
  await ctx.addInitScript((t) => { try { localStorage.setItem("setuhq-theme", t); } catch (e) { /* private */ } }, theme);
  const page = await ctx.newPage();
  for (const p of pages) {
    await page.goto(base + p, { waitUntil: "networkidle" }).catch(() => {});
    await page.waitForFunction(() => document.documentElement.dataset.ready === "1" || document.title.includes("moved"), null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(400);
    const file = `${p.replace(/^\/|\/$/g, "").replace(/[^a-z0-9]+/gi, "_") || "home"}-${size.name}-${theme}.jpg`;
    const h = await page.evaluate(() => document.documentElement.scrollHeight);
    await page.screenshot({ path: join(out, file), type: "jpeg", quality: 55, fullPage: full,
      clip: full ? { x: 0, y: 0, width: size.width, height: Math.min(h, size.width < 500 ? 5200 : 3600) } : undefined });
    shots.push({ file, path: p, size: size.name, theme });
  }
  await ctx.close();
}
await browser.close();
server.close();
const rows = shots.map((s) => `<figure><a href="${s.file}"><img loading="lazy" src="${s.file}" alt="${s.path} at ${s.size} size, ${s.theme} theme"></a><figcaption>${s.path} · ${s.size} · ${s.theme}</figcaption></figure>`).join("\n");
writeFileSync(join(out, "index.html"), `<!doctype html><meta charset="utf-8"><title>SetuHQ site gallery</title>
<style>body{font:14px system-ui;background:#111;color:#eee;margin:16px}main{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(260px,1fr))}
figure{margin:0}img{width:100%;height:220px;object-fit:cover;object-position:top;border:1px solid #333;border-radius:6px;background:#000}figcaption{font-size:12px;color:#aaa;margin-top:4px}</style>
<h1>SetuHQ site gallery: ${shots.length} screenshots</h1><main>${rows}</main>`);
console.log(`gallery: ${shots.length} screenshots in ${out}`);

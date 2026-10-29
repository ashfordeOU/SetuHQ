// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The text the site's scripts draw, as messages (docs/TRANSLATING.md, "Page text"): opens every English page of a
// built site (and a sample of the deploy-time planet and star pages) in Chromium, lets the scripts draw, and runs the
// browser's own page-text walker (setuhq.i18n AUTO_JS) over the result. Every template it would look up is written to
// src/setuhq/locales/js-templates.json, which `tools/i18n.py extract` adds to en.arb with the prefix "js.".
// A block the server already writes on a main page (setuhq.i18n_auto, prefix "pg.") is left out.
//
//   node tools/i18n_harvest.mjs --site path/to/site-with-stubs [--out src/setuhq/locales/js-templates.json]
import { readFileSync, writeFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { loadPlaywright } from "../tests/e2e/lib.mjs";
import { serve } from "../tests/e2e/server.mjs";

const arg = (n, d) => { const i = process.argv.indexOf(n); return i > 0 ? process.argv[i + 1] : d; };
const SITE = arg("--site", "site"), OUT = arg("--out", "src/setuhq/locales/js-templates.json"), STUBS = +arg("--stubs", "24");
const I18N = JSON.parse(readFileSync(join(SITE, "assets/pages-i18n.json"), "utf8"));  // every /<lang>/ page
const LANGS = new Set(I18N.map(p => p.split("/")[1])), MAIN = new Set(I18N.map(p => p.replace(/^\/[^/]+/, "")));
let pages = JSON.parse(readFileSync(join(SITE, "assets/pages.json"), "utf8")).filter(p => !LANGS.has(p.split("/")[1]));
for (const kind of ["planets", "stars"]) {  // the deploy-time pages: a spread of them, not every one
  const dir = join(SITE, kind); if (!existsSync(dir)) continue;
  const all = readdirSync(dir).filter(d => existsSync(join(dir, d, "index.html"))).sort().map(d => `/${kind}/${d}/`).filter(p => !pages.includes(p));
  const step = Math.max(1, Math.floor(all.length / STUBS));
  pages = pages.concat(all.filter((_, i) => i % step === 0).slice(0, STUBS));
}
const pw = await loadPlaywright();
const server = await serve(SITE);
const BASE = `http://127.0.0.1:${server.address().port}`;
const browser = await pw.chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
// A reference (authors, journal, year) stays as published.
const CITE = /\bet al\.|\b(ApJL?|ApJS|A&amp;A|MNRAS|AJ|PASP|Nature|Science|ARA&amp;A|PSJ|RNAAS)\b \{n\d+\}/;
const found = {};
for (const vp of [{ width: 1440, height: 900 }]) {
  const ctx = await browser.newContext({ viewport: vp, reducedMotion: "reduce" });
  for (const path of pages) {
    const page = await ctx.newPage();
    try {
      const res = await page.goto(BASE + path, { waitUntil: "load", timeout: 30000 });
      const raw = res ? await res.text() : "";
      await page.evaluate(async () => { for (let y = 0; y < document.body.scrollHeight; y += 700){ scrollTo(0, y); await new Promise(r => setTimeout(r, 40)); } scrollTo(0, 0); });
      await page.waitForTimeout(800);
      const got = await page.evaluate(async () => {
        const SI = window.SetuI18n; if (!SI || !SI.conf.auto) return [];
        if (!SI.auto){ await new Promise((ok, no) => { const x = document.createElement("script"); x.src = SI.conf.auto; x.onload = ok; x.onerror = no; document.head.appendChild(x); }); }
        const h53 = SI.h53, out = new Map();
        SI.lang = "xx"; SI.cat = {}; SI.hash = (t, h) => { const id = h53(t); if (!out.has(id)) out.set(id, [t, h]); return id; };
        // Another view's markup rides hidden in the page (a /<lang>/ page opens other views from the server): not this page's text.
        for (const r of document.querySelectorAll('[id^="route-"]')) if (r.hidden || r.closest("[hidden]")) r.remove();
        for (const d of document.querySelectorAll("details")) d.open = true;
        await new Promise(r => setTimeout(r, 300));
        SI.auto(document);
        return [...out.entries()];
      });
      const main = MAIN.has(path);
      for (const [id, [t, h]] of got) {
        if (main && raw.includes(h) || t.length > 3000 || CITE.test(t)) continue;  // the server writes this one (pg.); a data dump; a reference
        const f = found[id] || (found[id] = { en: t, pages: [] });
        if (f.pages.length < 4 && !f.pages.includes(path)) f.pages.push(path);
      }
    } catch (e) { console.warn(`${path}: ${e.message}`); }
    await page.close();
  }
  await ctx.close();
}
await browser.close(); server.close();
const sorted = Object.fromEntries(Object.keys(found).sort().map(k => [k, found[k]]));
writeFileSync(OUT, JSON.stringify(sorted, null, 1) + "\n");
const chars = Object.values(found).reduce((s, f) => s + f.en.length, 0);
console.log(`${Object.keys(found).length} templates (${chars.toLocaleString("en")} characters) from ${pages.length} pages -> ${OUT}`);

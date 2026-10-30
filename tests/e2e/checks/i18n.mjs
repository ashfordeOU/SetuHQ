// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The languages (docs/TRANSLATING.md): a page under /<lang>/ is in its language with the note shown; the picker
// remembers a choice, and a page with one address (a catalogue stub, a dip) follows it in the browser; a first visit
// in another browser language gets a dismissible suggestion, never a redirect; no request leaves the site.
// Japanese and Chinese headings break only between phrases (the <wbr> of tools/i18n.py phrases, a space or a
// punctuation mark), never inside one, on every main page at phone and desktop width.
// SETUHQ_I18N_SHOTS=<dir> also saves the home page in Japanese, a Methods chapter in German, an evidence page in
// Chinese and a stub in Ukrainian there.
// Where a heading's lines break, as the text before each break (a line break at index i of the heading's text).
const BREAKS = () => {
  const out = [];
  for (const h of document.querySelectorAll("main h1, main h2, main h3, main h4, main .lead-h")) {
    if (!h.offsetParent || !h.querySelector("wbr")) continue;  // a heading with marked phrases (tools/i18n.py phrases)
    out.n = (out.n || 0) + 1;
    const marks = new Set(), chars = [];  // marks: indexes where a break is allowed
    const walk = n => { for (const c of n.childNodes) {
      if (c.nodeType === 3) { for (let i = 0; i < c.data.length; i++) chars.push([c, i]); }
      else if (c.nodeName === "WBR") marks.add(chars.length);
      else if (c.nodeType === 1 && getComputedStyle(c).display !== "none") walk(c);
    } };
    walk(h);
    const r = document.createRange(); let top = null;
    for (let i = 0; i < chars.length; i++) {
      const [n, o] = chars[i], ch = n.data[o];
      if (/\s/.test(ch)) continue;
      r.setStart(n, o); r.setEnd(n, o + 1); const b = r.getClientRects()[0]; if (!b) continue;
      if (top !== null && b.top > top + b.height / 2) {
        const prev = i > 0 ? chars[i - 1][0].data[chars[i - 1][1]] : "";
        const ok = marks.has(i) || /[\s、。，：；！？）」』・\-–—/]/.test(prev) || /[（「『(]/.test(ch);
        if (!ok) out.push(h.textContent.trim().slice(0, 60) + " | at " + JSON.stringify(chars.slice(Math.max(0, i - 3), i + 3).map(([n2, o2]) => n2.data[o2]).join("")));
      }
      top = b.top;
    }
  }
  return { bad: out, n: out.n || 0 };
};

export default async function ({ browser, BASE, check: ok }) {
  const base = BASE, check = (what, cond, detail = "") => ok(cond, what, detail);
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "en-GB" });
  const page = await ctx.newPage();
  const external = [];
  page.on("request", r => { if (!r.url().startsWith(base)) external.push(r.url()); });
  const errors = [];
  page.on("pageerror", e => errors.push(String(e)));

  // A translated page: its language, its note, its own canonical address and every alternate.
  await page.goto(base + "/de/explore/", { waitUntil: "networkidle" });
  check("de: <html lang>", await page.evaluate(() => document.documentElement.lang) === "de");
  check("de: canonical", (await page.getAttribute('link[rel="canonical"]', "href")).endsWith("/de/explore/"));
  check("de: 18 alternates", (await page.locator('link[rel="alternate"][hreflang]').count()) === 18);
  check("de: machine note shown", await page.locator(".sitefoot .mtnote").isVisible());
  check("de: nav in German", (await page.locator('.nav a[data-nav="explore"]').textContent()).trim() !== "Explore");
  check("de: links stay in German", (await page.getAttribute(".brand", "href")) === "/de/");
  // In-place navigation keeps the language in the address.
  await page.click('.subnav a[href="/de/explore/galaxy/"]');
  await page.waitForTimeout(400);
  check("de: in-place link keeps /de/", new URL(page.url()).pathname === "/de/explore/galaxy/");

  // The picker: choosing a language remembers it; a stub follows the choice.
  await page.goto(base + "/", { waitUntil: "networkidle" });
  check("en: no note", !(await page.locator(".sitefoot .mtnote").isVisible()));
  await page.click(".langpick > summary");
  check("picker: note visible", await page.locator(".langnote").isVisible());
  await page.click('.langmenu a[data-lang="uk"]');
  await page.waitForURL(u => new URL(u).pathname === "/uk/");
  check("picker: stored", await page.evaluate(() => { try { return localStorage.getItem("setuhq-lang"); } catch (e) { return null; } }) === "uk");
  const stub = await page.evaluate(async () => (await (await fetch("/assets/pages.json")).json()).length);
  check("pages.json readable", stub > 0);
  await page.goto(base + "/planets/kepler-22-b/", { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.documentElement.lang === "uk", null, { timeout: 8000 }).catch(() => {});
  check("stub: follows the stored choice", await page.evaluate(() => document.documentElement.lang) === "uk");
  check("stub: note shown", await page.locator(".sitefoot .mtnote").isVisible());

  // A first visit in another language: a suggestion, never a redirect.
  const ctx2 = await browser.newContext({ viewport: { width: 390, height: 844 }, locale: "ja-JP" });
  const p2 = await ctx2.newPage();
  await p2.goto(base + "/", { waitUntil: "networkidle" });
  check("first visit: no redirect", new URL(p2.url()).pathname === "/");
  await p2.waitForSelector(".langhint", { timeout: 8000 }).catch(() => {});
  check("first visit: suggestion offered", await p2.locator(".langhint").count() === 1);
  check("first visit: suggestion links to /ja/", (await p2.getAttribute(".langhint a", "href")) === "/ja/");
  await p2.click(".langhint button");
  check("first visit: dismissed", await p2.locator(".langhint").count() === 0);
  await p2.reload({ waitUntil: "networkidle" });
  check("first visit: stays dismissed", await p2.locator(".langhint").count() === 0);
  check("phone: no sideways scroll", await p2.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
  await ctx2.close();

  // CJK headings: phrase-aware line breaks on every main page, desktop and phone.
  const mains = await page.evaluate(async () => (await (await fetch("/assets/pages-i18n.json")).json()).filter(p => /^\/(ja|zh-Hans)\//.test(p)));
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const c4 = await browser.newContext({ viewport: vp }), p4 = await c4.newPage(), bad = [];
    let seen = 0;
    for (const url of mains) {
      await p4.goto(base + url, { waitUntil: "load" }); await p4.waitForTimeout(150);
      const r = await p4.evaluate(BREAKS); seen += r.n;
      for (const b of r.bad) bad.push(url + ": " + b);
    }
    check(`CJK headings break only between phrases (${vp.width}px, ${mains.length} pages, ${seen} headings)`, mains.length >= 60 && seen >= 100 && bad.length === 0, bad.slice(0, 4).join(" || "));
    await c4.close();
  }

  // The chapter cards in every language: a title wraps (never clipped) and the star's temperature is never cut.
  const langs = ["", ...new Set(mains.map(p => p.split("/")[1]))];
  const allLangs = [...new Set([...langs, ...(await page.evaluate(() => SetuI18n.conf.locales.filter(l => l !== "en")))])];
  for (const vp of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const c5 = await browser.newContext({ viewport: vp }), p5 = await c5.newPage(), bad = [];
    let cards = 0;
    for (const l of allLangs) {
      await p5.goto(base + (l ? "/" + l : "") + "/how-it-works/transits/", { waitUntil: "load" }); await p5.waitForTimeout(150);
      const r = await p5.evaluate(() => { const out = []; let n = 0;
        for (const a of document.querySelectorAll(".mxtoc a")) {
          n++; const box = a.getBoundingClientRect(), t = a.querySelector(".mxtoct"), tr = t.getBoundingClientRect();
          if (t.scrollWidth > t.clientWidth + 1 || tr.right > box.right + 1) out.push("title " + t.textContent.trim());
          const k = a.querySelector(".mxtocs > :last-child"), kr = k && k.getBoundingClientRect(), s = a.querySelector(".mxtocs").getBoundingClientRect();
          if (kr && (kr.right > s.right + 1 || kr.right > box.right + 1)) out.push("star line " + a.querySelector(".mxtocs").textContent.trim());
        }
        return { out, n }; });
      cards += r.n; for (const b of r.out) bad.push((l || "en") + ": " + b);
    }
    check(`chapter cards: titles wrap and temperatures show in every language (${vp.width}px, ${cards} cards)`, cards >= 17 * 15 && bad.length === 0, bad.slice(0, 4).join(" || "));
    await c5.close();
  }

  const shots = process.env.SETUHQ_I18N_SHOTS;
  if (shots) {
    const c3 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p3 = await c3.newPage();
    p3.on("request", r => { if (!r.url().startsWith(base)) external.push(r.url()); });
    for (const [url, file] of [["/ja/", "home-ja.png"], ["/de/", "home-de.png"], ["/de/how-it-works/transits/", "methods-de.png"],
      ["/zh-Hans/evidence/stellar/", "evidence-zh.png"]]) {
      await p3.goto(base + url, { waitUntil: "networkidle" }); await p3.waitForTimeout(800);
      await p3.screenshot({ path: shots + "/" + file });
    }
    await p3.evaluate(() => { try { localStorage.setItem("setuhq-lang", "uk"); } catch (e) {} });
    await p3.goto(base + "/planets/kepler-22-b/", { waitUntil: "networkidle" }); await p3.waitForTimeout(1200);
    await p3.screenshot({ path: shots + "/stub-uk.png" });
    await c3.close();
  }
  check("no request to another site", external.length === 0, external.slice(0, 3).join(", "));
  check("no script error", errors.length === 0, errors.slice(0, 3).join(" | "));
  await ctx.close();
}

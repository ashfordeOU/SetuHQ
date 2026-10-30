// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The languages (docs/TRANSLATING.md): a page under /<lang>/ is in its language with the note shown; the picker
// remembers a choice, and a page with one address (a catalogue stub, a dip) follows it in the browser; a first visit
// in another browser language gets a dismissible suggestion, never a redirect; no request leaves the site.
// SETUHQ_I18N_SHOTS=<dir> also saves the home page in Japanese and German and a stub in Ukrainian there.
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

  const shots = process.env.SETUHQ_I18N_SHOTS;
  if (shots) {
    const c3 = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    const p3 = await c3.newPage();
    p3.on("request", r => { if (!r.url().startsWith(base)) external.push(r.url()); });
    for (const [url, file] of [["/ja/", "home-ja.png"], ["/de/", "home-de.png"]]) {
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

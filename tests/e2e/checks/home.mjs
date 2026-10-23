// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Phase 1, the home page: every band at both sizes, the counters' numbers without JavaScript, the hero's first frame,
// its Pause button, the temperature strip's stored Teffs, labels on every stage, the tab order through the bands, and
// axe with motion on (phone, and the light theme).
const BANDS = [
  ["hero", "#route-overview header.launch .herostage"],
  ["gallery", "#route-overview #examples"],
  ["temperature strip", "#route-overview #band-tempstrip"],
  ["counters", "#route-overview #band-counters"],
  ["reference check", "#route-overview #band-refcheck"],
  ["what you can do here", "#route-overview #band-dohere"],
  ["what this page does not claim", "#route-overview #band-honest"],
];
// Bands drawn by other phases' modules: checked when their module has drawn them.
const PLACED = ["#band-lineup", "#band-fold", "#band-panel", "#band-sky"];
const LABELS = ["Artist's impression", "Model from stored values", "Real data, cited", "Illustration", "Speculative model"];

export default async function home(h) {
  const { BASE, D, check, setGroup, context, watch, ready, AXE } = h;

  // ---------------------------------------------------------------- the bands, at both sizes and in both themes
  setGroup("home bands");
  for (const size of ["desktop", "phone"]) {
    for (const theme of ["dark", "light"]) {
      const ctx = await context({ size, theme });
      const page = await ctx.newPage(); const errs = watch(page);
      await page.goto(BASE + "/"); await ready(page); await page.waitForTimeout(400);
      const r = await page.evaluate(([BANDS, PLACED, LABELS]) => {
        const vis = (e) => !!e && e.getClientRects().length > 0 && e.getBoundingClientRect().height > 8;
        const out = { missing: BANDS.filter(([, s]) => !vis(document.querySelector(s))).map(([n]) => n) };
        out.placedHidden = PLACED.filter((s) => document.querySelector(s) && !vis(document.querySelector(s)));
        const order = [...document.querySelectorAll("#route-overview header.launch, #route-overview #examples, #route-overview [id^=band-]")].map((e) => e.id || "hero");
        out.order = order;
        out.cards = [...document.querySelectorAll("#examples .excard")].length;
        out.toi236 = (() => { const a = document.querySelector("#ex-toi-236"); const card = a && a.closest(".excard"); return card ? { occ: card.textContent.includes("occulter not identified"), params: card.querySelector("[data-params]").dataset.params } : null; })();
        const stages = [...document.querySelectorAll("#route-overview .stage, #route-overview [data-render]")].filter(vis);
        out.stages = stages.length;
        out.unlabelled = stages.filter((s) => !LABELS.some((l) => s.textContent.includes(l))).map((s) => s.className);
        out.bg = stages.map((s) => getComputedStyle(s).backgroundColor).filter((c) => c !== "rgb(0, 0, 0)");
        const h1 = document.querySelector("#route-overview h1"), fig = document.querySelector(".herofig .rbox");
        const a = h1.getBoundingClientRect(), b = fig.getBoundingClientRect();
        out.copyAbove = innerWidth < 700 ? a.bottom <= b.top + 1 : true;  // the phone layout: the copy sits above the stage
        out.h1Colour = getComputedStyle(h1).color;
        out.wide = document.documentElement.scrollWidth - document.documentElement.clientWidth;
        return out;
      }, [BANDS, PLACED, LABELS]);
      const tag = `${size}, ${theme}`;
      check(r.missing.length === 0, `every band is on the page (${tag})`, r.missing.join(", "));
      check(r.placedHidden.length === 0, `the bands other modules draw are visible when drawn (${tag})`, r.placedHidden.join(", "));
      check(r.order[0] === "hero" && r.order[1] === "examples" && r.order[2] === "band-tempstrip" && r.order.indexOf("band-counters") < r.order.indexOf("band-refcheck") && r.order.at(-1) === "band-honest",
        `the bands come in the design's order (${tag})`, r.order.join(" "));
      check(r.cards === (D.showcase || []).length && r.cards === 5, `the gallery has one card per worked example (${tag})`, r.cards);
      check(r.toi236 && r.toi236.occ && !/"kind":"sil"/.test(r.toi236.params), `TOI-236 shows an unidentified occulter, no planet silhouette (${tag})`, JSON.stringify(r.toi236));
      check(r.stages > 5 && r.unlabelled.length === 0, `every stage on the home page carries one of the five labels (${tag})`, r.unlabelled.join(" | "));
      check(r.bg.length === 0, `every stage is black (${tag})`, r.bg.join(" "));
      check(r.copyAbove, `on a phone the heading sits above the stage (${tag})`);
      check(r.h1Colour === "rgb(236, 239, 245)", `the heading is stage ink on the black stage (${tag})`, r.h1Colour);
      check(r.wide <= 0, `no sideways scroll (${tag})`, r.wide);
      check(errs.length === 0, `no console errors (${tag})`, errs.join(" | "));
      await ctx.close();
    }
  }

  // ---------------------------------------------------------------- V10: the numbers are in the HTML
  setGroup("home counters without JavaScript");
  {
    const ctx = await context({ js: false });
    const page = await ctx.newPage();
    await page.goto(BASE + "/");
    const r = await page.evaluate(() => [...document.querySelectorAll("#band-counters .odo[data-odo]")].map((o) => ({ text: o.textContent.trim(), odo: o.dataset.odo, li: o.closest("li").textContent })));
    check(r.length >= 3 && r.every((x) => x.text === x.odo && /\d/.test(x.text)), "each counter's final number is in the page", JSON.stringify(r.slice(0, 4)));
    const rate = r.find((x) => x.odo.endsWith("%"));
    check(rate && /\d+ of \d+ \(\d+–\d+%\)/.test(rate.li), "the completeness counter shows k of n and its interval", rate && rate.li);
    const hero = await page.evaluate(() => { const i = document.querySelector(".herofig img.rstill"); return i && { alt: i.alt, w: i.getBoundingClientRect().width }; });
    check(hero && hero.w > 100 && /\d,\d{3} K/.test(hero.alt) && /depth [\d,]+ ppm/.test(hero.alt), "without JavaScript the hero shows its still with the star's Teff and the depth", JSON.stringify(hero));
    await ctx.close();
  }

  // ---------------------------------------------------------------- V09: the markers are the stored Teffs
  setGroup("home temperature strip");
  {
    const ctx = await context();
    const page = await ctx.newPage();
    await page.goto(BASE + "/"); await ready(page);
    const got = await page.evaluate(() => [...document.querySelectorAll("#band-tempstrip li[data-teff]")].map((l) => Number(l.dataset.teff)).sort((a, b) => a - b));
    const want = Object.values(D.run_ctx || {}).map((c) => c.star_params && c.star_params.teff).filter(Boolean).map(Math.round).concat([5772]).sort((a, b) => a - b);
    check(JSON.stringify(got) === JSON.stringify(want), "each marker's Teff is the run's stored Teff (and the Sun's)", `${got} vs ${want}`);
    await ctx.close();
  }

  // ---------------------------------------------------------------- V01: first frame, Pause, still under reduced motion
  setGroup("home hero");
  {
    const ctx = await context({ motion: "no-preference" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + "/");
    await page.waitForFunction(() => !!document.querySelector(".herofig canvas"), null, { timeout: 8000 }).catch(() => {});
    const t = await page.evaluate(() => { const nav = performance.getEntriesByType("navigation")[0]; return { now: performance.now(), load: nav ? nav.loadEventEnd || nav.domContentLoadedEventEnd : 0, has: !!document.querySelector(".herofig canvas") }; });
    check(t.has && t.now - Math.max(0, t.load) <= 1200, "the hero's canvas is drawn within 1.2 s of load", JSON.stringify(t));
    await ready(page); await page.waitForTimeout(600);
    const btn = page.locator("[data-hero-pause]");
    check(await btn.isVisible() && (await btn.getAttribute("aria-pressed")) === "false", "the Pause button shows, not pressed, with motion on");
    const f0 = await page.evaluate(() => window.SetuHero.frames); await page.waitForTimeout(500);
    const f1 = await page.evaluate(() => window.SetuHero.frames);
    check(f1 > f0, "the transit plays while on screen", `${f0} → ${f1}`);
    await btn.click(); await page.waitForTimeout(150);
    const p0 = await page.evaluate(() => window.SetuHero.frames); await page.waitForTimeout(500);
    const p1 = await page.evaluate(() => window.SetuHero.frames);
    check((await btn.getAttribute("aria-pressed")) === "true" && p1 === p0, "Pause sets aria-pressed and stops the frames", `${p0} → ${p1}`);
    await btn.click(); await page.waitForTimeout(500);
    check((await btn.getAttribute("aria-pressed")) === "false" && (await page.evaluate(() => window.SetuHero.frames)) > p1, "pressing it again plays");
    await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => true }); document.dispatchEvent(new Event("visibilitychange")); });
    await page.waitForTimeout(100);
    const h0 = await page.evaluate(() => window.SetuHero.frames); await page.waitForTimeout(500);
    check((await page.evaluate(() => window.SetuHero.frames)) === h0, "a hidden tab draws no hero frames");
    await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => false }); document.dispatchEvent(new Event("visibilitychange")); });
    await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight)); await page.waitForTimeout(400);
    const s0 = await page.evaluate(() => window.SetuHero.frames); await page.waitForTimeout(500);
    check((await page.evaluate(() => window.SetuHero.frames)) === s0, "scrolled out of view, the hero stops");
    const lbl = await page.evaluate(() => { const c = document.querySelector(".herofig canvas"); return c && c.getAttribute("aria-label"); });
    check(lbl && /\d,\d{3} K/.test(lbl) && /ppm/.test(lbl), "the hero canvas states the star's Teff and the depth", lbl);
    check(errs.length === 0, "no console errors (hero, motion on)", errs.join(" | "));
    await ctx.close();
  }
  {
    const ctx = await context({ motion: "reduce" });
    const page = await ctx.newPage();
    await page.goto(BASE + "/"); await ready(page); await page.waitForTimeout(800);
    const r = await page.evaluate(() => ({ frames: window.SetuHero.frames, run: document.querySelector(".herostage").dataset.run, pressed: document.querySelector("[data-hero-pause]").getAttribute("aria-pressed") }));
    check(r.frames === 0 && r.run === D.run.name && r.pressed === "true", "reduced motion: the lead run's designed still, no frames, Pause pressed", JSON.stringify(r));
    await ctx.close();
  }

  // ---------------------------------------------------------------- the keyboard reaches every control on the bands
  setGroup("home tab order");
  {
    const ctx = await context({ motion: "no-preference" });
    const page = await ctx.newPage();
    await page.goto(BASE + "/"); await ready(page); await page.waitForTimeout(300);
    const want = await page.evaluate(() => [...document.querySelectorAll("#route-overview a[href], #route-overview button")]
      .filter((e) => e.getClientRects().length && !e.closest("[hidden]") && !e.closest(".learncard, .learn, details:not([open])")).map((e, i) => { e.dataset.tabk = String(i); return i; }));
    const seen = new Set();
    for (let i = 0; i < 400 && seen.size < want.length; i++) {
      await page.keyboard.press("Tab");
      const k = await page.evaluate(() => document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.tabk : undefined);
      if (k !== undefined) seen.add(Number(k));
      if (await page.evaluate(() => !!document.activeElement && !!document.activeElement.closest("footer"))) break;
    }
    const missed = want.filter((i) => !seen.has(i));
    const names = await page.evaluate((m) => m.map((i) => { const e = document.querySelector(`[data-tabk="${i}"]`); return (e.textContent || "").trim().slice(0, 30); }), missed.slice(0, 5));
    check(missed.length === 0, `Tab reaches every link and button on the home page (${want.length})`, names.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- axe with motion on: phone (dark) and desktop (light)
  setGroup("home axe");
  for (const [size, theme] of [["phone", "dark"], ["desktop", "light"]]) {
    const ctx = await context({ size, theme, motion: "no-preference" });
    const page = await ctx.newPage();
    await page.goto(BASE + "/"); await ready(page); await page.waitForTimeout(3000);
    await page.addScriptTag({ content: AXE });
    const v = await page.evaluate(async () => (await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }, resultTypes: ["violations"] }))
      .violations.filter((x) => x.impact === "serious" || x.impact === "critical").map((x) => x.id + ": " + x.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(", ")));
    check(v.length === 0, `home (${size}, ${theme}): axe with motion on, no serious or critical violation`, v.join(" | "));
    await ctx.close();
  }
}

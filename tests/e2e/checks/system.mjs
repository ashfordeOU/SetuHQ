// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Phase 0, the visual system: the renderer's three paths, the animation budget, pausing when hidden or off screen,
// designed stills under reduced motion, labels on every picture, black stages in light mode, layout shift, the
// header that settles on the home page, and axe with motion on.
const PICS = "/docs/pictures/";
const LABELS = ["Artist's impression", "Model from stored values", "Real data, cited", "Illustration", "Speculative model"];

export default async function system(h) {
  const { BASE, BROWSER, D, check, setGroup, context, watch, ready, AXE } = h;
  const stats = (page) => page.evaluate(() => window.SetuRender && window.SetuRender.stats());
  const toGrid = async (page) => { await page.evaluate(() => document.querySelector(".lookgrid").scrollIntoView({ block: "start" })); await page.waitForTimeout(900); };
  const lead = (D.routes.dips || {})[D.routes.lead] || D.routes.lead;

  // ---------------------------------------------------------------- the three paths
  setGroup("renderer paths");
  {
    const ctx = await context({ motion: "no-preference" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + PICS); await ready(page); await page.waitForTimeout(800);
    const s = await stats(page);
    check(s && (s.path === "webgl" || (BROWSER !== "chromium" && s.path === "canvas2d")), `the path is webgl (${BROWSER})`, JSON.stringify(s));
    check(s && s.contexts <= 1, "one WebGL context for the page", s && s.contexts);
    check(await page.evaluate(() => document.documentElement.dataset.render) === s.path, "the page records its path");
    const up = await page.evaluate(() => [...document.querySelectorAll('[data-render="planet"]')].map((f) => ({ img: f.querySelector("img.rstill").hidden, cv: !!f.querySelector("canvas[role=img]") })));
    check(up.length === 18 && up.every((u) => u.img && u.cv), "every planet figure is upgraded: its canvas shown, its still hidden", JSON.stringify(up.slice(0, 3)));
    check(errs.length === 0, "no console errors (webgl)", errs.join(" | "));
    await ctx.close();
  }
  {
    const ctx = await context({ motion: "no-preference", init: () => { const g = HTMLCanvasElement.prototype.getContext; HTMLCanvasElement.prototype.getContext = function (t, ...a) { return /webgl/.test(t) ? null : g.call(this, t, ...a); }; } });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + PICS); await ready(page); await toGrid(page);
    const s = await stats(page);
    check(s && s.path === "canvas2d" && s.contexts === 0, "WebGL blocked: the canvas2d path", JSON.stringify(s));
    check(await page.evaluate(() => [...document.querySelectorAll('[data-render="planet"] canvas')].length === 18), "canvas2d draws every figure");
    check(errs.length === 0, "no console errors (canvas2d)", errs.join(" | "));
    await ctx.close();
  }
  {
    const ctx = await context({ js: false });
    const page = await ctx.newPage();
    for (const p of [PICS, "/"]) {
      await page.goto(BASE + p);
      const imgs = await page.evaluate(() => [...document.querySelectorAll("[data-render]")].map((f) => { const i = f.querySelector("img"); return { has: !!i, alt: i ? i.getAttribute("alt") : null, shown: i ? i.getBoundingClientRect().width > 0 || f.classList.contains("starfield") : false, kind: f.dataset.render }; }));
      check(imgs.length > 0 && imgs.every((i) => i.has && i.alt !== null && i.shown), `${p} without JavaScript: every [data-render] shows its still with alt text`, JSON.stringify(imgs.filter((i) => !(i.has && i.shown)).slice(0, 3)));
      check(imgs.filter((i) => i.kind !== "starfield").every((i) => i.alt.length > 20), `${p}: the stills' alt texts say what they show`);
    }
    await ctx.close();
  }

  // ---------------------------------------------------------------- the budget: at most 4 (2 on a phone), on screen only, paused when hidden
  setGroup("animation budget");
  for (const [size, cap] of [["desktop", 4], ["phone", 2]]) {
    const ctx = await context({ size, motion: "no-preference" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + "/"); await ready(page); await page.waitForTimeout(600);
    let s = await stats(page);
    check(s && s.animating <= cap, `home (${size}): at most ${cap} animating`, JSON.stringify(s));
    await page.goto(BASE + PICS); await ready(page); await toGrid(page);
    s = await stats(page);
    check(s.animating > 0 && s.animating <= cap, `${PICS} (${size}): the figures on screen animate, at most ${cap}`, JSON.stringify(s));
    if (size === "desktop") {
      const f0 = (await stats(page)).frames; await page.waitForTimeout(400);
      check((await stats(page)).frames > f0, "frames advance while visible");
      await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => true }); document.dispatchEvent(new Event("visibilitychange")); });
      await page.waitForTimeout(100);
      const f1 = (await stats(page)).frames; await page.waitForTimeout(500);
      check((await stats(page)).frames === f1, "a hidden page draws no frames", `${f1} → ${(await stats(page)).frames}`);
      await page.evaluate(() => { Object.defineProperty(document, "hidden", { configurable: true, get: () => false }); document.dispatchEvent(new Event("visibilitychange")); });
      await page.evaluate(() => window.scrollTo(0, 0)); await page.waitForTimeout(700);
      check((await stats(page)).animating === 0, "scrolled out of view, the figures stop", JSON.stringify(await stats(page)));
    }
    check(errs.length === 0, `no console errors (${size})`, errs.join(" | "));
    await ctx.close();
  }
  {
    const ctx = await context({ motion: "reduce" });
    const page = await ctx.newPage();
    await page.goto(BASE + PICS); await ready(page); await toGrid(page); await page.waitForTimeout(600);
    const s = await stats(page);
    check(s.frames === 0 && s.animating === 0 && s.stills >= 18, "reduced motion: each figure draws its still once, and no frame loop runs", JSON.stringify(s));
    check(await page.evaluate(() => !document.querySelector(".starfield canvas") && !document.querySelector(".starfield img").hidden), "reduced motion: the starfield is its static image");
    await ctx.close();
  }

  // ---------------------------------------------------------------- labels, numbers, black stages in light mode
  setGroup("labels and stages");
  for (const theme of ["dark", "light"]) {
    const ctx = await context({ theme });
    const page = await ctx.newPage(); const errs = watch(page);
    for (const p of [PICS, `/candidates/${lead}/`, "/planets/pi-men-c/", "/how-it-works/transits/"]) {
      await page.goto(BASE + p); await ready(page); await page.waitForTimeout(600);
      const r = await page.evaluate((LABELS) => {
        const stages = [...document.querySelectorAll('.route:not([hidden]) [data-render="planet"], .route:not([hidden]) [data-render="transit"], .route:not([hidden]) .stage')];
        const vis = (e) => e.getClientRects().length > 0;
        return {
          n: stages.filter(vis).length,
          unlabelled: stages.filter(vis).filter((s) => !LABELS.some((l) => s.textContent.includes(l))).map((s) => s.className + " " + (s.dataset.vis || s.dataset.render || "")),
          planetTags: [...document.querySelectorAll('[data-render="planet"] .stage-tag')].filter((t) => !(t.tagName === "A" && t.getAttribute("href") === "/docs/pictures/")).length,
          bg: stages.filter(vis).map((s) => getComputedStyle(s).backgroundColor).filter((c) => c !== "rgb(0, 0, 0)"),
          noDigit: [...document.querySelectorAll('.route:not([hidden]) [data-render] canvas[role="img"], .route:not([hidden]) #txsysfig canvas')].filter(vis).map((c) => c.getAttribute("aria-label") || "").filter((l) => !/\d/.test(l)),
        };
      }, LABELS);
      check(r.n > 0 && r.unlabelled.length === 0, `${p} (${theme}): every picture and stage carries one of the five labels`, r.unlabelled.slice(0, 3).join(" | "));
      check(r.planetTags === 0, `${p}: every planet tag links to ${PICS}`);
      check(r.bg.length === 0, `${p} (${theme}): every stage is black`, r.bg.slice(0, 3).join(" "));
      check(r.noDigit.length === 0, `${p}: every informative canvas states its numbers`, r.noDigit.slice(0, 2).join(" | "));
    }
    check(errs.length === 0, `no console errors (${theme})`, errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- layout shift, the header, axe with motion on
  setGroup("layout shift and header");
  {
    const ctx = await context({ motion: "no-preference" });
    const page = await ctx.newPage();
    for (const p of ["/", "/planets/pi-men-c/"]) {
      await page.goto(BASE + p); await ready(page); await page.waitForTimeout(1500);
      const cls = await page.evaluate(() => new Promise((res) => { let v = 0; new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) v += e.value; }).observe({ type: "layout-shift", buffered: true }); setTimeout(() => res(v), 300); }));
      check(cls <= 0.02, `${p}: cumulative layout shift at most 0.02`, cls.toFixed(4));
    }
    await page.goto(BASE + "/"); await ready(page);
    check(await page.evaluate(() => !document.querySelector(".topbar").classList.contains("settled")), "the home page's header is clear at the top");
    await page.mouse.wheel(0, 41); await page.waitForTimeout(300);
    if (await page.evaluate(() => window.scrollY) < 41) await page.evaluate(() => window.scrollTo(0, 41));
    await page.waitForTimeout(200);
    check(await page.evaluate(() => document.querySelector(".topbar").classList.contains("settled")), "after 41 px of scroll it settles (filled)");
    await page.goto(BASE + "/docs/"); await ready(page);
    check(await page.evaluate(() => document.querySelector(".topbar").classList.contains("settled")), "elsewhere it is always settled");
    for (const p of ["/", "/planets/pi-men-c/"]) {
      await page.goto(BASE + p); await ready(page); await page.waitForTimeout(3000);
      await page.addScriptTag({ content: AXE });
      const v = await page.evaluate(async () => (await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] }, resultTypes: ["violations"] }))
        .violations.filter((x) => x.impact === "serious" || x.impact === "critical").map((x) => x.id + ": " + x.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(", ")));
      check(v.length === 0, `${p}: axe with motion on, after 3 s, no serious or critical violation`, v.join(" | "));
    }
    await ctx.close();
  }
}

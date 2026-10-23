// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Phase 4: How it works, Evidence and Docs. The fold (V05) toggles with aria-pressed and is two still panels under
// reduced motion; every chapter's stages carry a label; the panel figure on /evidence/ lists every reviewer in the
// stored record; the benchmark's counters carry their intervals; the leaderboard's bars are the stored intervals to
// 1 px; /docs/pictures/ has one table row per look; the 404 page keeps its starfield and cards.
const LABELS = ["Artist's impression", "Model from stored values", "Real data, cited", "Illustration", "Speculative model"];

export default async function learn(h) {
  const { BASE, D, check, setGroup, context, watch, ready, pages } = h;
  const TR = "/how-it-works/transits/";

  // ---------------------------------------------------------------- V05: the fold
  setGroup("the fold (V05)");
  {
    const ctx = await context({ motion: "no-preference" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + TR); await ready(page);
    await page.evaluate(() => document.querySelector("figure.foldfig").scrollIntoView({ block: "center" }));
    await page.waitForFunction(() => document.querySelector("figure.foldfig").classList.contains("live"), null, { timeout: 8000 }).catch(() => {});
    check(await page.evaluate(() => document.querySelector("figure.foldfig").classList.contains("live")), "with motion, the still becomes the canvas near the viewport");
    const btn = page.locator("figure.foldfig .foldbtn");
    check(await btn.isVisible(), "the fold toggle is shown");
    await page.waitForTimeout(2600);  // the fold plays once on its own when it comes into view
    const a0 = await btn.getAttribute("aria-pressed");
    await btn.click(); await page.waitForTimeout(300);
    const a1 = await btn.getAttribute("aria-pressed");
    check(a0 !== a1 && ["true", "false"].includes(a1), "the toggle flips aria-pressed", `${a0} → ${a1}`);
    await btn.click(); await page.waitForTimeout(300);
    check(await btn.getAttribute("aria-pressed") === a0, "and flips it back");
    const label = await page.locator("figure.foldfig canvas").getAttribute("aria-label");
    check(/3,485 points/.test(label || "") && /6\.2680/.test(label || ""), "the canvas states its numbers", label);
    const inner = await page.evaluate(() => document.querySelector("figure.foldfig").textContent);
    check(inner.includes("Real data, cited") && inner.includes("runs/tess-pi-men-s1"), "it is labelled real data and names its run");
    check(errs.length === 0, "no console errors (fold, motion)", errs.join(" | "));
    await ctx.close();
  }
  {
    const ctx = await context({ motion: "reduce" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + TR); await ready(page);
    await page.evaluate(() => document.querySelector("figure.foldfig").scrollIntoView({ block: "center" }));
    await page.waitForTimeout(1200);
    const s = await page.evaluate(() => { const f = document.querySelector("figure.foldfig");
      return { live: f.classList.contains("live"), panels: [...f.querySelectorAll(".foldpanel svg")].filter((x) => x.getBoundingClientRect().width > 50).length,
        labels: [...f.querySelectorAll(".foldlbl")].map((x) => x.textContent), canvasShown: !f.querySelector(".foldlive").hidden }; });
    check(!s.live && !s.canvasShown && s.panels === 2, "reduced motion: the two-panel still, no canvas", JSON.stringify(s));
    check(s.labels.length === 2 && /Unfolded/.test(s.labels[0]) && /Folded/.test(s.labels[1]), "each panel has its own label", JSON.stringify(s.labels));
    const btn = page.locator("figure.foldfig .foldbtn");
    await btn.click(); await page.waitForTimeout(500);
    check(await btn.getAttribute("aria-pressed") === "true" && await page.evaluate(() => document.querySelector("figure.foldfig").classList.contains("live")),
      "reduced motion: the toggle shows the folded frame on request");
    check(errs.length === 0, "no console errors (fold, reduced motion)", errs.join(" | "));
    await ctx.close();
  }
  {
    const ctx = await context({ js: false });
    const page = await ctx.newPage();
    await page.goto(BASE + TR);
    const n = await page.evaluate(() => [...document.querySelectorAll("figure.foldfig .foldpanel svg[role=img]")].filter((x) => x.getBoundingClientRect().width > 50).length);
    check(n === 2, "without JavaScript the fold is its two panels");
    await ctx.close();
  }

  // ---------------------------------------------------------------- every chapter: stages labelled
  setGroup("chapters");
  {
    const ctx = await context();
    const page = await ctx.newPage(); const errs = watch(page);
    const chapters = pages.filter((p) => /^\/how-it-works\/[^/]+\/$/.test(p));
    check(chapters.length === 14, "14 chapter pages besides the overview", chapters.length);
    for (const p of ["/how-it-works/", ...chapters]) {
      await page.goto(BASE + p); await ready(page);
      const r = await page.evaluate((LABELS) => {
        const st = [...document.querySelectorAll(".route:not([hidden]) .stage")].filter((e) => e.getClientRects().length);
        return { n: st.length, bad: st.filter((s) => !LABELS.some((l) => s.textContent.includes(l))).map((s) => s.className + " " + (s.dataset.vis || "")),
          cards: document.querySelectorAll(".route:not([hidden]) .mxtoc a[data-ch]").length };
      }, LABELS);
      check((r.n > 0 || p.endsWith("/history/")) && r.bad.length === 0, `${p}: every stage carries one of the five labels (${r.n})`, r.bad.join(" | "));
      check(r.cards === 15, `${p}: the chapter cards`, r.cards);
    }
    check(errs.length === 0, "no console errors (chapters)", errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- Evidence
  setGroup("evidence");
  {
    const ctx = await context();
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + "/evidence/"); await ready(page);
    const names = (D.story.reviewers || []).map((r) => r.name);
    const r = await page.evaluate(() => {
      const ring = document.querySelector("#route-sentinels [data-viz=panelring], #route-sentinels .panelring");
      const fig = ring || document.querySelector("#senring");
      const svg = fig && fig.querySelector("svg[aria-label]");
      return { v06: !!ring, text: (fig ? fig.textContent : "") + " " + (svg ? svg.getAttribute("aria-label") : ""), bench: document.querySelector(".benchodo") ? document.querySelector(".benchodo").textContent : "" };
    });
    check(names.length > 0 && names.every((n) => r.text.includes(n)), `the panel figure (${r.v06 ? "V06, panel mode" : "the ring, until V06 is built"}) lists every stored reviewer`, names.filter((n) => !r.text.includes(n)).join(", "));
    check(/90 of 150 \(52–67%\)/.test(r.bench), "the benchmark's headline rate carries k of n and its interval", r.bench.slice(0, 200));
    check(await page.evaluate(() => document.body.textContent.split("Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic matched-filter detectors.").length - 1 >= 2), "the attribution line, word for word, at least twice");
    const plane = page.locator("#calplane svg.calplane");
    if (await plane.count()) {
      await plane.focus(); await page.keyboard.press("ArrowRight"); await page.waitForTimeout(100);
      check(/false-alarm rate/.test(await page.locator("#calread").textContent()), "the calibration plane answers on the arrow keys (S06)");
    }
    await page.goto(BASE + "/evidence/leaderboard/"); await ready(page);
    const bars = await page.evaluate(() => [...document.querySelectorAll("svg.lbbar")].map((s) => { const b = s.getBoundingClientRect(), iv = s.querySelector(".iv").getBoundingClientRect();
      const a = +s.dataset.a, z = +s.dataset.b, W = b.width; return { want0: W * (+s.dataset.lo - a) / (z - a), want1: W * (+s.dataset.hi - a) / (z - a), got0: iv.left - b.left, got1: iv.right - b.left, w: b.width }; }));
    const off = bars.filter((x) => x.w > 0 && (Math.abs(x.got0 - x.want0) > 1 || Math.abs(x.got1 - x.want1) > 1));
    check(bars.length > 10 && off.length === 0, `the leaderboard's ${bars.length} bars match the stored lo–hi to 1 px`, JSON.stringify(off.slice(0, 2)));
    check(await page.evaluate(() => /cannot show that the Probes read light curves better than catalogue metadata/.test(document.body.textContent)), "the metadata-floor note stays");
    await page.goto(BASE + "/evidence/runs/"); await ready(page);
    const discs = await page.evaluate(() => document.querySelectorAll("#route-runs .rundisc svg.stardisc").length);
    check(discs === (D.showcase || []).length, "a star disc for every example run", `${discs} of ${(D.showcase || []).length}`);
    check(errs.length === 0, "no console errors (evidence)", errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- Docs, the pictures, 404
  setGroup("docs");
  {
    const ctx = await context();
    const page = await ctx.newPage();
    await page.goto(BASE + "/docs/pictures/"); await ready(page);
    const r = await page.evaluate(() => ({ rows: [...document.querySelectorAll("table.looktable tr[data-look]")].map((t) => t.dataset.look),
      figs: [...document.querySelectorAll('.lookgrid [data-render="planet"]')].map((f) => JSON.parse(f.dataset.params).look) }));
    check(r.rows.length === 18 && JSON.stringify(r.rows) === JSON.stringify(r.figs), "/docs/pictures/: one table row per look, the LOOKS keys, as the 18 stills", JSON.stringify(r.rows));
    await page.goto(BASE + "/docs/"); await ready(page);
    check(await page.locator('#route-docs a[href="/docs/pictures/"]').count() > 0, "Docs links How the pictures are drawn");
    await page.goto(BASE + "/no-such-page/"); await ready(page);
    check(await page.evaluate(() => !!document.querySelector(".starfield") && document.querySelectorAll("#route-notfound .docard").length >= 5), "404: the starfield and the section cards");
    await ctx.close();
  }
}

// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The stellar pages: /evidence/stellar/ (the validation status of flares, pulsations and CHEOPS, two figures of
// real TESS data, the stars at their TIC Teff, ESA's terms), /docs/stellar/ and /docs/cheops-proposals/. Each status
// is shown with its count and never as "validated"; each figure is a black stage labelled "Real data, cited" with
// its source, in both themes, at both sizes and under reduced motion; no request leaves the site.
const STATUS = ["partly validated (5 of 8 checks pass)", "partly validated (7 of 9 checks pass)", "not validated (2 of 5 checks pass)"];
const DISCLAIMER = "SetuHQ is independent and is not affiliated with, endorsed by or operated on behalf of ESA, the CHEOPS mission or the CHEOPS Consortium";

export default async function stellar(h) {
  const { BASE, check, setGroup, context, watch, ready } = h;
  setGroup("stellar pages");
  for (const [size, theme, motion] of [["desktop", "dark", "reduce"], ["desktop", "light", "no-preference"], ["phone", "dark", "reduce"]]) {
    const ctx = await context({ size, theme, motion });
    const page = await ctx.newPage(); const errs = watch(page);
    const outside = [];
    page.on("request", (r) => { const u = new URL(r.url()); if (!["127.0.0.1", "localhost"].includes(u.hostname) && !u.protocol.startsWith("data")) outside.push(r.url()); });
    const tag = `${size}, ${theme}, motion ${motion}`;
    await page.goto(BASE + "/evidence/stellar/"); await ready(page);
    const r = await page.evaluate(() => {
      const sec = document.querySelector("#route-stellar");
      const figs = [...sec.querySelectorAll("figure.stfig")];
      return {
        text: sec.innerText,
        cards: [...sec.querySelectorAll(".stcard .stword")].map((x) => x.textContent),
        figs: figs.map((f) => ({ tag: f.querySelector(".stage-tag")?.textContent, bg: getComputedStyle(f).backgroundColor,
          alt: f.querySelector("svg[role=img]")?.getAttribute("aria-label") || "", src: f.querySelector(".stsrc")?.textContent || "" })),
        stars: [...sec.querySelectorAll('[data-render="star"]')].map((f) => ({ teff: JSON.parse(f.dataset.params).teff,
          tag: f.querySelector(".stage-tag")?.textContent, shown: !!(f.querySelector("canvas") || f.querySelector("img.rstill:not([hidden])")) })),
        current: document.querySelector('#subnav [aria-current="page"]')?.textContent || "",
        sideways: document.documentElement.scrollWidth - innerWidth,
      };
    });
    for (const s of STATUS) check(r.text.includes(s), `${tag}: the status "${s}" is shown`);
    check(JSON.stringify(r.cards) === JSON.stringify(["partly validated", "partly validated", "not validated"]), `${tag}: the three status cards`, JSON.stringify(r.cards));
    check(r.figs.length === 2 && r.figs.every((f) => f.tag === "Real data, cited" && f.bg === "rgb(0, 0, 0)"), `${tag}: two figures, each a black stage labelled Real data, cited`, JSON.stringify(r.figs.map((f) => [f.tag, f.bg])));
    check(r.figs.every((f) => /TESS sector \d+/.test(f.src) && /MAST/.test(f.src) && f.alt.length > 80), `${tag}: each figure names its source and states its numbers`);
    check(r.stars.length === 2 && r.stars[0].teff === 3286 && r.stars[1].teff > 7000 && r.stars.every((s) => s.tag === "Model from stored values" && s.shown),
      `${tag}: both stars drawn at their TIC Teff, labelled`, JSON.stringify(r.stars));
    check(r.text.includes(DISCLAIMER) && /Credit: ESA, \S/.test(await page.evaluate(() => document.querySelector("#route-stellar .stcheops").textContent)), `${tag}: the CHEOPS part carries the disclaimer and the credit lines`);
    check(r.current === "Stars", `${tag}: Evidence's sub-navigation marks Stars`, r.current);
    check(r.sideways <= 0, `${tag}: no sideways scroll`, r.sideways);
    for (const [path, h1, must] of [["/docs/stellar/", "Flares, pulsations and CHEOPS.", "ESA does not designate DACE"],
                                    ["/docs/cheops-proposals/", "Prepare a CHEOPS proposal.", "never logs in, submits, or automates any ESA system"]]) {
      await page.goto(BASE + path); await ready(page);
      const d = await page.evaluate(() => ({ h1: document.querySelector("main h1, #content h1")?.textContent, text: document.querySelector("#content").innerText,
        sideways: document.documentElement.scrollWidth - innerWidth }));
      check(d.h1 === h1 && d.text.includes(must) && d.text.includes(DISCLAIMER), `${tag}: ${path} has its heading, its limits and the disclaimer`, d.h1);
      check(d.sideways <= 0, `${tag}: ${path} has no sideways scroll`, d.sideways);
    }
    check(outside.length === 0, `${tag}: no request to another site`, outside.join(" "));
    check(errs.length === 0, `${tag}: no console errors`, errs.join(" | "));
    await ctx.close();
  }
  {
    // without JavaScript the figures are the same static SVG (they are their own still)
    const ctx = await context({ js: false });
    const page = await ctx.newPage();
    await page.goto(BASE + "/evidence/stellar/");
    const n = await page.evaluate(() => document.querySelectorAll("figure.stfig svg[role=img]").length);
    check(n === 2, "without JavaScript both figures are drawn", n);
    await ctx.close();
  }
}

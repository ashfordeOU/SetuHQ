// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Phase 2, Explore and the catalogue pages: the sky by year (its scrubber, "Transits only", the sky file fetched only
// where the map is), the timeline's crosshair, the planet pages' portraits for several looks (a stub's still before
// the app boots and its canvas after), a star page's orbits, the catalogue's temperature filter, and a phone scroll
// of the catalogue without long tasks.
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";

export default async function explore(h) {
  const { BASE, SITE, check, setGroup, context, watch, ready } = h;
  const cat = JSON.parse(readFileSync(join(SITE, "assets", "data", "catalogue.json"), "utf8"));
  const P = cat.planets, n = P.name.length;
  const slugOf = (name) => P.slug[P.name.indexOf(name)];

  // ---------------------------------------------------------------- the sky by year
  setGroup("explore: the sky by year");
  {
    const html = readFileSync(join(SITE, "explore", "index.html"), "utf8");
    check(html.length <= 160000, `/explore/ is at most 160,000 characters (${html.length.toLocaleString("en-GB")})`);
    const ctx = await context({ motion: "reduce" });
    const page = await ctx.newPage(); const errs = watch(page);
    const asked = [];
    page.on("request", (r) => { if (/\/assets\/data\/sky-[0-9a-f]+\.json$/.test(r.url())) asked.push(new URL(r.url()).pathname); });
    await page.goto(BASE + "/docs/"); await ready(page); await page.waitForTimeout(800);
    check(asked.length === 0, "a page without the sky map never asks for the sky file", asked.join(" "));
    await page.goto(BASE + "/explore/"); await ready(page);
    await page.waitForFunction(() => { const f = document.querySelector("#skyyears"); return f && f.querySelector("canvas"); }, null, { timeout: 15000 }).catch(() => {});
    check(asked.length === 1, "/explore/ fetches the sky file once", asked.join(" "));
    const sky = asked[0] ? statSync(join(SITE, asked[0])).size : 0;
    check(sky > 0 && sky <= 160000, `the sky file is at most 160,000 bytes (${sky.toLocaleString("en-GB")})`);
    const s0 = await page.evaluate(() => { const r = document.querySelector('#skyyears [data-sky="year"]'), p = document.querySelector('#skyyears [data-sky="play"]');
      return { vt: r.getAttribute("aria-valuetext"), shown: !r.closest("label").hidden, play: p.textContent, pressed: p.getAttribute("aria-pressed") }; });
    check(/^2026: 8,376 planets$/.test(s0.vt), "the scrubber's aria-valuetext names the year and the count", s0.vt);
    check(s0.shown && s0.play === "Play" && s0.pressed === "false", "under reduced motion the map holds the final year, with Play", JSON.stringify(s0));
    await page.focus('#skyyears [data-sky="year"]'); await page.keyboard.press("Home");
    const first = await page.evaluate(() => document.querySelector('#skyyears [data-sky="year"]').getAttribute("aria-valuetext"));
    await page.keyboard.press("End"); await page.keyboard.press("ArrowLeft");
    const prev = await page.evaluate(() => [document.querySelector('#skyyears [data-sky="year"]').getAttribute("aria-valuetext"), document.querySelector("#skyyears .skyyear").textContent]);
    check(/^19\d\d: \d+ planets?$/.test(first) && /^2025: [\d,]+ planets$/.test(prev[0]) && prev[1] === "2025", "the arrow keys move the year, and the readout follows", `${first} | ${prev}`);
    await page.click('#skyyears [data-sky="transit"]');
    const t = await page.evaluate(() => [document.querySelector('#skyyears [data-sky="transit"]').getAttribute("aria-pressed"), document.querySelector("#skyyears .skyread").textContent]);
    check(t[0] === "true" && /transits only/.test(t[1]) && !/radial velocity/.test(t[1]), '"Transits only" toggles, and only transits are counted', t.join(" | "));
    await page.click('#skyyears [data-sky="transit"]');
    check(await page.evaluate(() => document.querySelector('#skyyears [data-sky="transit"]').getAttribute("aria-pressed")) === "false", '"Transits only" toggles back');
    // The timeline answers on the arrow keys.
    await page.focus("#timeline .tlsvg"); await page.keyboard.press("ArrowRight"); await page.keyboard.press("ArrowRight");
    const tl = await page.evaluate(() => document.querySelector("#timeline .tlread").textContent);
    check(/^\d{4}: [\d,]+ planets?/.test(tl), "the timeline's crosshair reads a year and its count", tl);
    check(errs.length === 0, "no console errors on /explore/", errs.join(" | "));
    await ctx.close();
  }
  {
    const ctx = await context({ motion: "no-preference" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + "/explore/"); await ready(page);
    await page.waitForFunction(() => document.querySelector('#skyyears [data-sky="play"]').textContent === "Pause", null, { timeout: 15000 }).catch(() => {});
    const y0 = await page.evaluate(() => document.querySelector("#skyyears .skyyear").textContent);
    await page.waitForTimeout(1500);
    const y1 = await page.evaluate(() => document.querySelector("#skyyears .skyyear").textContent);
    check(Number(y1) > Number(y0), `with motion the years play (${y0} → ${y1})`);
    await page.click('#skyyears [data-sky="play"]');
    const a = await page.evaluate(() => document.querySelector("#skyyears .skyyear").textContent); await page.waitForTimeout(1200);
    const b = await page.evaluate(() => document.querySelector("#skyyears .skyyear").textContent);
    check(a === b && await page.evaluate(() => document.querySelector('#skyyears [data-sky="play"]').getAttribute("aria-pressed")) === "false", "Pause stops it", `${a} ${b}`);
    check(errs.length === 0, "no console errors with motion", errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- planet pages: the look, the tag, the caption
  setGroup("explore: planet pages");
  const massOnly = P.slug[[...Array(n).keys()].find((i) => !P.radius[i] && (P.mass[i] || P.msini[i]) && P.steff[i])];
  const nothing = P.slug[[...Array(n).keys()].find((i) => !P.radius[i] && !P.mass[i] && !P.msini[i])];
  const cases = [[slugOf("pi Men c"), "envelope-hot"], [slugOf("WASP-126 b"), "giant-hot"], [slugOf("TOI-270 b"), "rock-warm"], [massOnly, "mass"], [nothing, "none"]];
  {
    const ctx = await context({ motion: "reduce" });
    const page = await ctx.newPage(); const errs = watch(page);
    for (const [slug, want] of cases) {
      await page.goto(BASE + `/planets/${slug}/`); await ready(page); await page.waitForTimeout(700);
      const r = await page.evaluate(() => { const f = document.querySelector('.route:not([hidden]) #plhero [data-render="planet"]'), t = f && f.querySelector(".stage-tag");
        return { has: !!f, look: f ? JSON.parse(f.dataset.params).look : null, tag: t ? [t.tagName, t.getAttribute("href"), t.textContent] : null,
          cap: f ? f.querySelector("figcaption").textContent : "", none: (document.querySelector(".route:not([hidden]) .plnone") || {}).textContent || "",
          canvas: !!(f && f.querySelector("canvas[role=img]")) }; });
      if (want === "none") check(!r.has && r.none === "No radius or mass stored, so no planet is drawn.", `${slug}: no radius or mass, so no planet and the reason`, JSON.stringify(r));
      else {
        check(r.has && r.tag && r.tag[0] === "A" && r.tag[1] === "/docs/pictures/" && r.tag[2] === "Artist's impression", `${slug}: the portrait's tag links to /docs/pictures/`, JSON.stringify(r.tag));
        if (want === "mass") check(/Radius not measured: not to scale/.test(r.cap), `${slug}: a mass-only planet is drawn not to scale, and says so`, r.cap);
        else check(r.look === want && r.cap.startsWith(`Artist's impression · ${want.replace("-", ", ")}`) && /exoplanet\.eu/.test(r.cap), `${slug}: the ${want} look, its reasons and source`, `${r.look} ${r.cap.slice(0, 120)}`);
        check(r.canvas, `${slug}: the renderer drew it`);
        check(!/habitable/i.test(r.cap), `${slug}: no "habitable"`);
      }
    }
    check(errs.length === 0, "no console errors on planet pages", errs.join(" | "));
    await ctx.close();
  }
  // A deploy-time page: the still before the app boots (and without JavaScript), the canvas after.
  {
    const pre = new Set(JSON.parse(readFileSync(join(SITE, "assets", "pages.json"), "utf8")).map((p) => p.path || p));
    const pick = [...Array(n).keys()].filter((i) => P.radius[i] && P.steff[i] && !pre.has(`/planets/${P.slug[i]}/`));
    const slug = P.slug[pick[Math.floor(pick.length / 3)]];
    const nojs = await context({ js: false });
    const p1 = await nojs.newPage();
    await p1.goto(BASE + `/planets/${slug}/`);
    const still = await p1.evaluate(() => { const i = document.querySelector('[data-render="planet"] img.rstill'); return i && { w: i.getBoundingClientRect().width, alt: i.alt, src: i.getAttribute("src") }; });
    check(still && still.w > 0 && /^Artist's impression: /.test(still.alt) && /-512\.webp$/.test(still.src), `/planets/${slug}/ (deploy-time) shows its still before the app`, JSON.stringify(still));
    await nojs.close();
    const ctx = await context({ motion: "no-preference" });
    const p2 = await ctx.newPage(); const errs = watch(p2);
    await p2.goto(BASE + `/planets/${slug}/`); await ready(p2);
    await p2.waitForFunction(() => !!document.querySelector('#plhero [data-render="planet"] canvas[role=img]'), null, { timeout: 10000 }).catch(() => {});
    const up = await p2.evaluate(() => { const f = document.querySelector('#plhero [data-render="planet"]'); return f && { cv: !!f.querySelector("canvas[role=img]"), img: f.querySelector("img.rstill").hidden, btn: (f.querySelector("[data-spin]") || {}).textContent }; });
    check(up && up.cv && up.img, `/planets/${slug}/: after the app boots, the canvas replaces the still`, JSON.stringify(up));
    await p2.waitForFunction(() => { const b = document.querySelector("#plhero [data-spin]"); return b && !b.hidden; }, null, { timeout: 8000 }).catch(() => {});
    const b0 = await p2.evaluate(() => document.querySelector("#plhero [data-spin]").getAttribute("aria-pressed"));
    await p2.click("#plhero [data-spin]");
    const b1 = await p2.evaluate(() => document.querySelector("#plhero [data-spin]").getAttribute("aria-pressed"));
    check(b0 === "true" && b1 === "false", "the portrait turns with motion, and its Pause stops it", `${b0} → ${b1}`);
    check(errs.length === 0, "no console errors on a deploy-time planet page", errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- a star with two or more planets: the orbits
  setGroup("explore: star pages");
  for (const [path, size] of [["/stars/toi-270/", "desktop"], ["/stars/trappist-1/", "phone"]]) {
    const ctx = await context({ size, motion: "reduce" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + path); await ready(page); await page.waitForTimeout(700);
    const r = await page.evaluate(() => { const f = document.querySelector('.route:not([hidden]) #sthero [data-viz="orbits"]');
      return f && { cv: !!f.querySelector("canvas[role=img]"), label: f.querySelector("canvas") && f.querySelector("canvas").getAttribute("aria-label"), play: f.querySelector('[data-orb="play"]').textContent,
        rows: f.querySelectorAll("tbody tr").length, star: !!document.querySelector('#sthero [data-render="star"]'), thumbs: document.querySelectorAll("#stplanets img.plthumb").length }; });
    check(r && r.cv && /\d/.test(r.label) && r.rows >= 2, `${path} (${size}): the orbits of its planets, with their table`, JSON.stringify(r));
    check(r && r.play === "Play" && r.star && r.thumbs >= 2, `${path}: still under reduced motion (Play), its star, and its planets' pictures`, JSON.stringify(r));
    check(errs.length === 0, `no console errors on ${path}`, errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- the catalogue: the temperature filter, and a phone scroll
  setGroup("explore: the catalogue");
  {
    const ctx = await context({ motion: "reduce" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + "/catalogue/"); await ready(page);
    await page.waitForFunction(() => /Showing 8,376 of 8,376/.test(document.querySelector("#ctcount").textContent), null, { timeout: 15000 }).catch(() => {});
    const strip = await page.evaluate(() => !!document.querySelector('#route-catalogue [data-viz="tempstrip"][data-filter="1"]'));
    await page.evaluate(() => { document.querySelector("#route-catalogue .ctmore").open = true; });
    if (strip) await page.evaluate(() => { const i = document.querySelector('#route-catalogue [data-ts="lo"]'); i.value = "5000"; i.dispatchEvent(new Event("input", { bubbles: true })); });
    else await page.fill('#route-catalogue [data-rk="teff"][data-end="lo"]', "5000");
    await page.waitForFunction(() => !/Showing 8,376 of/.test(document.querySelector("#ctcount").textContent), null, { timeout: 5000 }).catch(() => {});
    const c = await page.evaluate(() => document.querySelector("#ctcount").textContent);
    check(/^Showing [\d,]+ of 8,376 planets$/.test(c) && !/Showing 8,376 of/.test(c), `the host-temperature filter (${strip ? "the strip's handles" : "the range boxes"}) changes the rows`, c);
    const dots = await page.evaluate(() => [document.querySelectorAll("#ctscroll .ctdot[style]").length, document.querySelectorAll("#ctscroll .ctrow").length]);
    check(dots[0] > 0 && dots[0] <= dots[1], "the Host column carries the star's colour", JSON.stringify(dots));
    check(errs.length === 0, "no console errors on the catalogue", errs.join(" | "));
    await ctx.close();
  }
  {
    const ctx = await context({ size: "phone", motion: "reduce" });
    const page = await ctx.newPage();
    await page.goto(BASE + "/catalogue/"); await ready(page);
    await page.waitForFunction(() => /Showing 8,376/.test(document.querySelector("#ctcount").textContent), null, { timeout: 15000 }).catch(() => {});
    await page.waitForTimeout(500);
    const long = await page.evaluate(async () => {
      const out = []; const po = new PerformanceObserver((l) => { for (const e of l.getEntries()) out.push(Math.round(e.duration)); }); po.observe({ type: "longtask" });
      const sc = document.querySelector("#ctscroll");
      for (let y = 0; y <= 4000; y += 100) { sc.scrollTop = y; await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))); }
      await new Promise((r) => setTimeout(r, 300)); po.disconnect(); return out;
    });
    check(long.length === 0, "scrolling the catalogue 4,000 px on a phone has no long task over 50 ms", long.join(", "));
    await ctx.close();
  }
}

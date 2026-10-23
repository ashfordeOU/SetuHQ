// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Phase 3, candidates, dips, case files and plates: the panel ring (V06) on every dip page with the stored marks,
// weights and status; no Sentinel on a Probes-only run; the multi-planet example's orbits inset; the run stars'
// discs; the radius ratios' silhouettes (never planet art); the feed timeline's crosshair; a case file that works
// with no network and from a file; and a plate printed on A4 in light.
import { join } from "node:path";
import { pathToFileURL } from "node:url";

export default async function candidates(h) {
  const { BASE, SITE, D, check, setGroup, context, watch, ready } = h;
  const SLUG = (id) => (D.routes.dips || {})[id] || id;
  const ALL = D.story.dips.concat(D.showcase_dips || []);
  const W = Object.fromEntries(((D.calibration || {}).points || []).map((p) => [p.id, p.weight]));
  const ctxOf = (d) => D.run_ctx[d.run] || {};

  // ---------------------------------------------------------------- V06 on every dip page
  setGroup("panel ring on every dip");
  {
    const ctx = await context({ size: "desktop", theme: "dark" });
    const page = await ctx.newPage(); const errs = watch(page);
    for (const d of ALL) {
      await page.goto(BASE + `/candidates/${SLUG(d.id)}/`); await ready(page);
      const r = await page.evaluate(() => {
        const box = document.querySelector("#route-transit #txscore .panelring");
        if (!box) return null;
        return {
          verdict: (box.querySelector("[data-verdict]") || {}).textContent || "",
          sen: box.querySelectorAll(".prnode.sen").length, prb: box.querySelectorAll(".prnode.prb").length,
          rows: [...box.querySelectorAll("tbody tr")].map((tr) => ({ id: tr.querySelector(".mono").textContent, cells: [...tr.querySelectorAll("td")].map((td) => td.textContent) })),
          text: box.innerText, label: box.querySelector("svg").getAttribute("aria-label") || "",
          stage: getComputedStyle(box.querySelector(".prfig")).backgroundColor,
          tag: (box.querySelector(".stage-tag") || {}).textContent,
        };
      });
      const id = SLUG(d.id), C = ctxOf(d);
      if (!check(r, `${id}: the panel ring is drawn`)) continue;
      check(r.verdict === D.dip_state[d.outcome][2], `${id}: its status is the dip's (${D.dip_state[d.outcome][2]})`, r.verdict);
      if (d.outcome === "rejected") check(!/candidate, unconfirmed/i.test(r.text + r.label), `${id} (rejected): the ring never calls it a candidate`);
      const lanes = d.lanes.filter((l) => l.role === "probe" || (l.role === "sentinel" && !C.probes_only));
      check(r.rows.length === lanes.length && lanes.every((l, i) => r.rows[i].id === l.id && r.rows[i].cells[2] === (l.counted ? "yes" : "no")),
        `${id}: the table's marks are the stored ones`, JSON.stringify(r.rows.map((x) => [x.id, x.cells[2]])));
      check(lanes.every((l, i) => r.rows[i] && r.rows[i].cells[3] === (W[l.id] === undefined || W[l.id] === null ? "not stored" : W[l.id].toFixed(2))),
        `${id}: each weight is the calibrated weight`);
      check(/\d/.test(r.label) && r.tag === "Real data, cited" && r.stage === "rgb(0, 0, 0)", `${id}: labelled, numbered, on a black stage`, `${r.tag} ${r.stage}`);
      if (C.probes_only) {
        check(r.sen === 0 && r.prb === 3 && r.text.includes(D.probes_only_label), `${id}: Probes only, no Sentinel node, and says so`, `${r.sen} sentinels`);
      } else {
        check(r.sen === 2 && r.prb === 3 && r.text.includes(D.attribution), `${id}: 3 Probes and 2 Sentinels, with the attribution`, `${r.prb} + ${r.sen}`);
      }
    }
    // Changing dip in place redraws the ring for the new dip (the page's script draws what Python drew).
    const first = D.story.dips[0], next = D.story.dips[1];
    await page.goto(BASE + `/candidates/${SLUG(first.id)}/`); await ready(page);
    const before = await page.evaluate(() => document.querySelector("#txscore .panelring").outerHTML);
    await page.click(`#txchips a[href$="/${SLUG(next.id)}/"]`); await page.waitForTimeout(400);
    const after = await page.evaluate(() => ({ h: document.querySelector("#txscore .panelring").outerHTML, v: document.querySelector("#txscore [data-verdict]").textContent }));
    check(after.h !== before && after.v === D.dip_state[next.outcome][2], "a dip changed in place gets its own ring");
    check(errs.length === 0, "no console errors on the dip pages", errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- reduced motion is the final still; with motion, it converges once
  setGroup("panel ring motion");
  {
    const lead = D.story.dips[0];
    const ctx = await context({ motion: "no-preference" });
    const page = await ctx.newPage();
    await page.goto(BASE + `/candidates/${SLUG(lead.id)}/`); await ready(page); await page.waitForTimeout(1500);
    const s = await page.evaluate(() => { const f = document.querySelector("#txscore .prfig"); return { pre: f.classList.contains("pr-pre"), off: getComputedStyle(f.querySelector(".prring")).strokeDashoffset }; });
    check(!s.pre && parseFloat(s.off) < 1, "with motion on, the ring has filled to the stored score once on screen", JSON.stringify(s));
    await ctx.close();
    const ctx2 = await context({ motion: "reduce" });
    const p2 = await ctx2.newPage();
    await p2.goto(BASE + `/candidates/${SLUG(lead.id)}/`); await ready(p2);
    check(await p2.evaluate(() => !document.querySelector("#txscore .prfig").classList.contains("pr-pre")), "reduced motion: the ring is its final still at once");
    await ctx2.close();
  }

  // ---------------------------------------------------------------- the multi-planet example: orbits inset (V08, drawn by viz.orbits)
  setGroup("orbits inset");
  {
    const multi = (D.showcase || []).find((c) => c.kind === "Multi-planet system");
    const ctx = await context();
    const page = await ctx.newPage();
    if (check(multi, "the showcase has a multi-planet example")) {
      const mine = ALL.filter((d) => d.run === multi.run), other = ALL.find((d) => d.run !== multi.run);
      await page.goto(BASE + `/candidates/${SLUG(mine[0].id)}/`); await ready(page);
      const has = await page.evaluate((run) => !!document.querySelector(`.txinset[data-run="${run}"]`), multi.run);
      if (has) {
        for (const d of mine) {
          await page.goto(BASE + `/candidates/${SLUG(d.id)}/`); await ready(page);
          check(await page.evaluate((run) => { const f = document.querySelector(`.txinset[data-run="${run}"]`); return f && !f.hidden && f.getBoundingClientRect().height > 0; }, multi.run), `${SLUG(d.id)}: the system's orbits are shown`);
        }
        await page.goto(BASE + `/candidates/${SLUG(other.id)}/`); await ready(page);
        check(await page.evaluate(() => [...document.querySelectorAll(".txinset")].every((f) => f.hidden)), `${SLUG(other.id)}: no other run's orbits`);
      } else {
        // viz.orbits (phase 2) is not built in this tree: the slot stays empty and the page leaves the band out.
        const viz = await page.evaluate(() => document.querySelectorAll(".txinset").length);
        check(viz === 0, `${multi.star}'s dips leave the orbits band out until viz.orbits draws it`);
      }
    }
    await ctx.close();
  }

  // ---------------------------------------------------------------- the star discs, the silhouettes and the timeline's crosshair
  setGroup("candidates, radius ratios");
  {
    const ctx = await context({ theme: "light" });
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + "/candidates/"); await ready(page);
    const discs = await page.evaluate(() => [...document.querySelectorAll(".rundips .rundiphead")].map((h) => (h.querySelector(".stardisc") || { getAttribute: () => "" }).getAttribute("aria-label") || ""));
    const want = (D.showcase || []).map((c) => Math.round(((D.run_ctx[c.run] || {}).star_params || {}).teff || 0));
    check(discs.length === want.length && discs.every((l, i) => !want[i] || l.includes(want[i].toLocaleString("en-GB") + " K")), "each run's group shows its star at its TIC Teff", discs.join(" | "));
    const tl = await page.$("#timeline svg");
    if (tl) {
      await tl.scrollIntoViewIfNeeded(); const b = await tl.boundingBox();
      await page.mouse.move(b.x + b.width * 0.5, b.y + b.height * 0.5); await page.waitForTimeout(150);
      const read = await page.evaluate(() => document.getElementById("tlread").textContent);
      check(/\d/.test(read) && read.includes(D_UNC(D)), "the feed timeline answers on hover", read);
      await tl.focus(); await page.keyboard.press("ArrowRight");
      check(/\d/.test(await page.evaluate(() => document.getElementById("tlread").textContent)), "and on the arrow keys");
    }
    await page.goto(BASE + "/candidates/radius-ratios/"); await ready(page);
    const rr = await page.evaluate(() => ({ figs: [...document.querySelectorAll("#planetcards .rrfig")].map((f) => f.getAttribute("aria-label")),
      art: document.querySelectorAll('#route-planets [data-render="planet"]').length, sil: document.querySelectorAll("#planetcards .rrsil circle").length }));
    check(rr.figs.length > 0 && rr.figs.length === rr.sil && rr.figs.every((l) => /Rp\/R★ \d\.\d{4}/.test(l) && /if it were a planet/.test(l)), "each ratio has its star and a silhouette at √depth", rr.figs.slice(0, 2).join(" | "));
    check(rr.art === 0, "no planet art on the radius ratios");
    // The case file's header shows the dip's own star.
    const d = D.showcase_dips.find((x) => (ctxOf(x).star_params || {}).teff);
    await page.goto(BASE + `/candidates/${SLUG(d.id)}/case-file/`); await ready(page);
    const star = await page.evaluate(() => [...document.querySelectorAll(".dipstar")].filter((s) => !s.hidden).map((s) => s.dataset.run));
    check(star.length >= 1 && star.every((r) => r === d.run), "the case file's header shows the dip's own star", star.join(","));
    check(errs.length === 0, "no console errors", errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- a case file with no network, and from a file
  setGroup("case file offline");
  {
    const ctx = await context();
    const page = await ctx.newPage(); const errs = watch(page);
    await page.goto(BASE + "/candidates/toi-270/case-file/", { waitUntil: "load" });
    await ctx.setOffline(true);
    await page.keyboard.press("j"); await page.waitForTimeout(300);
    const ok = await page.evaluate(() => ({ outcome: !!document.querySelector("#dtop .outcome"), strip: !!document.querySelector(".strip svg"), star: !!document.querySelector(".runstar .stardisc") }));
    check(ok.outcome && ok.strip && ok.star, "after load, offline: the case file still renders and moves between dips", JSON.stringify(ok));
    await ctx.setOffline(false);
    const reqs = [];
    page.on("request", (r) => { if (/^https?:/.test(r.url())) reqs.push(r.url()); });
    await page.goto(pathToFileURL(join(SITE, "candidates", "case-file", "index.html")).href, { waitUntil: "load" });
    await page.waitForTimeout(300);
    const f = await page.evaluate(() => ({ outcome: !!document.querySelector("#dtop .outcome"), font: getComputedStyle(document.body).fontFamily }));
    check(f.outcome && reqs.length === 0, "from a file: it renders and asks the network for nothing", reqs.slice(0, 3).join(" "));
    check(errs.filter((e) => !/ERR_INTERNET_DISCONNECTED|net::/.test(e)).length === 0, "no script errors", errs.join(" | "));
    await ctx.close();
  }

  // ---------------------------------------------------------------- a plate printed on A4, in light
  setGroup("plates print");
  {
    const ctx = await context({ theme: "dark" });
    const page = await ctx.newPage();
    await page.goto(BASE + "/evidence/plates/toi-270/", { waitUntil: "load" });
    const screen = await page.evaluate(() => ({ caps: document.querySelectorAll("p.caption b.fig").length, text: document.querySelector("header.mast").innerText, star: !!document.querySelector(".pstar .stardisc") }));
    await page.emulateMedia({ media: "print" });
    const print = await page.evaluate(() => ({ caps: document.querySelectorAll("p.caption b.fig").length, text: document.querySelector("header.mast").innerText,
      bg: getComputedStyle(document.body).backgroundColor, ink: getComputedStyle(document.body).color }));
    check(screen.star, "the plate is headed by its star's disc");
    check(print.caps === screen.caps && print.caps > 0 && print.text === screen.text, "printing keeps every caption and count", `${screen.caps} → ${print.caps}`);
    check(print.bg === "rgb(255, 255, 255)" && print.ink === "rgb(29, 29, 31)", "print is light: white paper and dark ink, even from the dark theme", `${print.bg} ${print.ink}`);
    let pdf = null;
    try { pdf = await page.pdf({ format: "A4", printBackground: true }); } catch (e) { pdf = null; }
    if (pdf) {
      const pages = (pdf.toString("latin1").match(/\/Type\s*\/Page[^s]/g) || []).length;
      check(pdf.length > 20000 && pages >= 2, `the plates print to an A4 PDF (${pages} pages)`, pdf.length);
    } else check(h.BROWSER !== "chromium", "page.pdf works in Chromium");
    await ctx.close();
  }
}

const D_UNC = (D) => D.unconfirmed;

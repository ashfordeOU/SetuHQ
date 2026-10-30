// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The v0.2 features: the journey strip and the light line on a dip page, Source / limits on every labelled figure and
// the first-visit hint (keyboard, Escape, kept once dismissed), the orbit and Galaxy camera buttons, /explore/tess-now/
// (its label, its date stamp, the scrubber by keyboard), /candidates/be-the-vetter/ (a call, the reveal, the local
// score; a rejected dip shows as rejected) and /editions/ (no prices, the address as text with a copy button). axe on
// each with the disclosures open; no request leaves the site.
const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];

export default async function features(h) {
  const { BASE, check, setGroup, context, watch, ready, AXE, BROWSER } = h;
  const axe = async (page) => { await page.addScriptTag({ content: AXE });
    return page.evaluate(async (tags) => (await window.axe.run(document, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations"] }))
      .violations.filter((x) => x.impact === "serious" || x.impact === "critical").map((x) => x.id + ": " + x.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(", ")), AXE_TAGS); };
  setGroup("v0.2 features");
  for (const [size, theme, motion] of [["desktop", "dark", "reduce"], ["desktop", "light", "no-preference"], ["phone", "dark", "reduce"]]) {
    const tag = `${size}, ${theme}, motion ${motion}`;
    const ctx = await context({ size, theme, motion });
    const page = await ctx.newPage(); const errs = watch(page), outside = [];
    page.on("request", (r) => { const u = new URL(r.url()); if (!["127.0.0.1", "localhost"].includes(u.hostname) && !u.protocol.startsWith("data")) outside.push(r.url()); });

    // a dip page: the journey strip and the light line
    await page.goto(BASE + "/candidates/toi-270/dip-1/"); await ready(page);
    const j = await page.evaluate(() => ({ steps: [...document.querySelectorAll("#txjourney .journey li")].map((li) => li.innerText),
      light: document.querySelector("#txlight")?.textContent || "" }));
    check(j.steps.length === 6 && j.steps[0].includes("Found by SetuHQ") && j.steps.every((s) => /as of \d{4}-\d\d-\d\d|no date/.test(s)), `${tag}: the dip's journey strip, six dated steps`, JSON.stringify(j.steps));
    check(/^The light in this dip left the star about [\d,]+ years ago \(distance [\d.]+ pc, .+\)\.$/.test(j.light), `${tag}: the light-travel line`, j.light);
    // the next dip in place: the strip follows
    await page.click('#txnav a[aria-label^="Next"]'); await page.waitForTimeout(400);
    check(await page.evaluate(() => document.querySelectorAll("#txjourney .journey li").length === 6), `${tag}: the strip follows an in-place dip change`);

    // a star page: Source / limits on every labelled stage, the hint, the orbit camera
    await page.goto(BASE + "/stars/toi-270/"); await ready(page); await page.waitForTimeout(300);
    const s = await page.evaluate(() => { const st = [...document.querySelectorAll("#route-star .stage")].filter((x) => x.querySelector(".stage-tag") && x.offsetWidth >= 200);
      return { n: st.length, with: st.filter((x) => x.querySelector("details.srclim summary")).length, hint: !!document.querySelector(".orbits .fxhint"),
        light: document.querySelector("#stlight")?.textContent || "" }; });
    check(s.n > 0 && s.with === s.n, `${tag}: every labelled figure has Source / limits`, JSON.stringify(s));
    check(/^The light from this star left it about [\d,]+ years ago/.test(s.light), `${tag}: the star's light line`, s.light);
    check(s.hint, `${tag}: the orbits show their first-visit hint`);
    const sum = page.locator(".orbits details.srclim summary").first();
    await sum.focus(); await page.keyboard.press("Enter");
    const opened = await page.evaluate(() => document.querySelector(".orbits details.srclim").open && /Source: .+/.test(document.querySelector(".orbits details.srclim").innerText));
    await page.keyboard.press("Escape");
    const closed = await page.evaluate(() => !document.querySelector(".orbits details.srclim").open && document.activeElement.tagName === "SUMMARY");
    check(opened && closed, `${tag}: Source / limits opens with Enter, names the source and closes with Escape`, JSON.stringify([opened, closed]));
    await page.evaluate(() => document.querySelectorAll("details.srclim").forEach((d) => { d.open = true; }));
    const v1 = await axe(page);
    check(v1.length === 0, `${tag}: axe on a star page with every Source / limits open`, v1.join(" | "));
    await page.evaluate(() => document.querySelectorAll("details.srclim").forEach((d) => { d.open = false; }));
    const cam = page.locator(".orbits .orbcam button[data-oc='1']").first();
    check(await page.evaluate(() => !document.querySelector(".orbits .orbcam").hidden), `${tag}: the orbit camera buttons are shown`);
    await cam.focus(); await page.keyboard.press("Enter");
    check(await cam.getAttribute("aria-pressed") === "true", `${tag}: a planet focus button works from the keyboard`);
    await page.locator(".orbits .orbcam button[data-oc='in']").first().click(); await page.locator(".orbits .orbcam button[data-oc='reset']").first().click();
    check(await page.locator(".orbits .orbcam button[data-oc='all']").first().getAttribute("aria-pressed") === "true", `${tag}: Reset returns to All`);
    await page.locator(".orbits .fxhint button").first().click();
    check(await page.evaluate(() => !document.querySelector(".fxhint") && document.activeElement.tagName === "SUMMARY"), `${tag}: the hint dismisses and focus stays on the figure`);
    await page.reload(); await ready(page); await page.waitForTimeout(300);
    check(await page.evaluate(() => !document.querySelector(".fxhint")), `${tag}: a dismissed hint stays dismissed`);

    // Where TESS is now
    await page.goto(BASE + "/explore/tess-now/"); await ready(page);
    const t0 = await page.evaluate(() => ({ text: document.querySelector("#route-tessnow").innerText, on: document.querySelectorAll(".tnsec.on").length,
      read: document.querySelector("#tnread").textContent, bg: getComputedStyle(document.querySelector("#tnow .stage")).backgroundColor,
      sideways: document.documentElement.scrollWidth - innerWidth }));
    check(t0.text.includes("Pointing from the published schedule, not live telemetry") && /Schedule saved on \d{4}-\d\d-\d\d/.test(t0.text), `${tag}: TESS now carries its label and date stamp`);
    check(t0.on === 1 && /^Sector \d+: /.test(t0.read) && t0.bg === "rgb(0, 0, 0)" && t0.sideways <= 0, `${tag}: one sector shown on a black stage`, JSON.stringify(t0));
    // Source / limits sits clear of the plotted map (on a phone, in a strip under it)
    const ov = await page.evaluate(() => { const a = document.querySelector("#tnow .srclim summary").getBoundingClientRect(), b = document.querySelector("#tnow svg.tnsvg").getBoundingClientRect();
      return { hit: a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top, a: [a.left, a.top, a.right, a.bottom].map(Math.round), b: [b.left, b.top, b.right, b.bottom].map(Math.round) }; });
    check(size !== "phone" || !ov.hit, `${tag}: Source / limits does not cover the TESS map at 390 px`, JSON.stringify(ov));
    await page.focus("#tnrange"); await page.keyboard.press("ArrowRight");
    const t1 = await page.evaluate(() => ({ read: document.querySelector("#tnread").textContent, vt: document.querySelector("#tnrange").getAttribute("aria-valuetext"), on: document.querySelectorAll(".tnsec.on").length }));
    check(t1.read !== t0.read && t1.vt === t1.read && t1.on === 1, `${tag}: the scrubber moves by keyboard and says the sector`, JSON.stringify(t1));
    const v2 = await axe(page);
    check(v2.length === 0, `${tag}: axe on TESS now`, v2.join(" | "));

    // Be the vetter
    await page.goto(BASE + "/candidates/be-the-vetter/"); await ready(page);
    const card = page.locator(".vtcard").first();
    await card.locator("button[data-vt='flagged']").click();
    const b = await page.evaluate(() => { const c = document.querySelector(".vtcard"); return { say: c.querySelector(".vtsay").textContent, open: c.querySelector(".vtreveal").open,
      score: document.querySelector("#vtscore").textContent, rej: [...document.querySelectorAll('.vtcard[data-out="rejected"] .vtreveal')].every((d) => d.textContent.includes("rejected by vetting")),
      note: document.querySelector("#route-vetter").innerText.includes("A learning exercise, not a contribution to the science") }; });
    check(/^You called it: flag\. The vetting: (pass|flag|reject)\.$/.test(b.say) && b.open && /of 1 dips/.test(b.score), `${tag}: a call reveals the stored decision and scores it`, JSON.stringify(b));
    check(b.rej && b.note, `${tag}: rejected dips show as rejected; the page says it is a learning exercise`);
    await page.reload(); await ready(page);
    check(await page.evaluate(() => document.querySelector(".vtcard button[data-vt='flagged']").getAttribute("aria-pressed") === "true"), `${tag}: the call is kept in this browser`);
    await page.click("#vtreset");
    const v3 = await axe(page);
    check(v3.length === 0, `${tag}: axe on Be the vetter`, v3.join(" | "));

    // Editions, with animations at a tenth of their speed (a slow runner): a view's entrance must never fade its text,
    // so axe reads full contrast whenever it runs.
    const slow = BROWSER === "chromium" ? await page.context().newCDPSession(page) : null;
    if (slow) { await slow.send("Animation.enable"); await slow.send("Animation.setPlaybackRate", { playbackRate: 0.1 }); }
    await page.goto(BASE + "/editions/"); await ready(page);
    const e = await page.evaluate(() => ({ text: document.querySelector("#route-editions").innerText, codes: [...document.querySelectorAll(".edaddr")].map((c) => c.textContent),
      copy: document.querySelectorAll("button[data-copy]").length, foot: !!document.querySelector('.sitefoot a[href="/editions/"]') }));
    check(!/[$€£]\s?\d/.test(e.text) && e.text.includes("There are no prices on this site"), `${tag}: no prices on Editions`);
    check(e.codes.length >= 3 && e.codes.every((c) => c === "contact@ashforde.org") && e.copy === e.codes.length && e.foot, `${tag}: the address as text with a copy button, linked from the footer`, JSON.stringify(e.codes));
    check(e.text.includes("in development") && e.text.includes("CC BY-NC 3.0 IGO"), `${tag}: Pro in development; the CHEOPS carve-out`);
    const v4 = await axe(page);
    check(v4.length === 0, `${tag}: axe on Editions`, v4.join(" | "));
    if (slow) { await slow.send("Animation.setPlaybackRate", { playbackRate: 1 }); await slow.detach(); }

    // the Galaxy camera buttons
    await page.goto(BASE + "/explore/galaxy/"); await ready(page);
    for (const k of ["in", "out", "star", "all", "reset"]) await page.locator(`#gxcam [data-gc='${k}']`).click();
    check(await page.locator("#gxcam button").count() === 5, `${tag}: the Galaxy camera buttons`);

    check(outside.length === 0, `${tag}: no request to another site`, outside.join(" "));
    check(errs.length === 0, `${tag}: no console errors`, errs.join(" | "));
    await ctx.close();
  }
  {
    // without JavaScript: the schedule's table and the vetter's reveal still work; no answer buttons
    const ctx = await context({ js: false });
    const page = await ctx.newPage();
    await page.goto(BASE + "/explore/tess-now/");
    check(await page.evaluate(() => document.querySelectorAll(".tnsec.on").length === 1 && document.querySelectorAll(".skytable tbody tr").length > 5), "without JavaScript TESS now shows the saved day's sector and the table");
    await page.goto(BASE + "/candidates/be-the-vetter/");
    check(await page.evaluate(() => document.querySelectorAll(".vtreveal").length > 0 && [...document.querySelectorAll(".vtpick")].every((x) => x.hidden)), "without JavaScript the vetter reveals, with no answer buttons");
    await ctx.close();
  }
  {
    // Source / limits never sits over its figure's caption (its text or its links), in English, Japanese and German
    for (const size of ["desktop", "phone"]) {
      const ctx = await context({ size });
      const page = await ctx.newPage(), bad = [];
      for (const url of ["/", "/ja/", "/de/", "/stars/toi-270/", "/ja/how-it-works/transits/", "/planets/kepler-22-b/", "/stars/kepler-22/"]) {
        await page.goto(BASE + url); await ready(page); await page.waitForTimeout(400);
        bad.push(...await page.evaluate((url) => [...document.querySelectorAll(".srclim>summary")].filter((s) => s.offsetWidth).flatMap((s) => {
          const a = s.getBoundingClientRect(), fig = s.closest("figure") || s.parentElement, cap = fig && fig.querySelector("figcaption");
          if (!cap) return [];
          const r = document.createRange(), hits = [];
          const w = document.createTreeWalker(cap, NodeFilter.SHOW_TEXT);
          for (let n = w.nextNode(); n; n = w.nextNode()) { r.selectNodeContents(n);
            for (const b of r.getClientRects()) if (b.width && a.left < b.right - 1 && a.right > b.left + 1 && a.top < b.bottom - 1 && a.bottom > b.top + 1) hits.push(n.data.trim().slice(0, 30)); }
          return hits.length ? [url + ": " + hits.slice(0, 2).join(" / ")] : [];
        }), url));
      }
      check(bad.length === 0, `${size}: Source / limits clear of every caption's text and links`, bad.slice(0, 4).join(" || "));
      await ctx.close();
    }
  }
}

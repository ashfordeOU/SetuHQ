// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// The end-to-end test of the built site, in Chromium, against a local server that serves site/ at the domain root
// as GitHub Pages does (tests/e2e/server.mjs). Run by scripts/site_e2e.sh:
//
//   node tests/e2e/run.mjs --site site [--quick] [--report e2e-report.json]
//
// Every page listed in site/assets/pages.json, at 1440 x 900 and 390 x 844, dark and light:
//   HTTP 200; no console error, page error or failed request; the app starts; no sideways overflow and nothing cut off at the right edge; the title,
//   description, canonical address and Open Graph image; every image has alt text; no old #/ link; one heading;
//   a reload of the address shows the same page; an axe-core scan with no serious or critical violation.
// Then: the top bar's links and sub-navigation (in place, by the History API), the phone menu (open, close, Escape,
// keyboard), the skip link and visible focus, the search overlay (/ and Ctrl+K, arrows, Enter, Escape), Back and
// Forward, every old address forwarding, the 404 page, a sample of the catalogue's planet and star pages (written
// by setuhq.stubs, as the deploy does), and a crawl of every internal link from the home page.
// --quick runs the page matrix on a sample (the home page and one page of each kind) instead of every page.
import { readFileSync, readdirSync, writeFileSync } from "node:fs";
import { join, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { serve } from "./server.mjs";
import { loadPlaywright } from "./lib.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : d; };
const SITE = resolve(arg("site", "site"));
const QUICK = process.argv.includes("--quick");
const SITE_URL = "https://setuhq.com";
const AXE = readFileSync(join(HERE, "vendor", "axe.min.js"), "utf8");

const results = [];
let current = "";
function check(ok, what, detail = "") {
  results.push({ test: current, what, ok: !!ok, detail: ok ? "" : String(detail).slice(0, 400) });
  if (!ok) console.log(`  FAIL ${current}: ${what}${detail ? " (" + String(detail).slice(0, 300) + ")" : ""}`);
  return !!ok;
}

const pages = JSON.parse(readFileSync(join(SITE, "assets", "pages.json"), "utf8"));
const dataFile = readdirSync(join(SITE, "assets", "data")).find((f) => /^app-.*\.json$/.test(f));
const D = JSON.parse(readFileSync(join(SITE, "assets", "data", dataFile), "utf8"));
const SLUG = (id) => D.routes.dips[id] || id;  // a dip's readable address, e.g. pi-men/dip-2
const LEAD = SLUG(D.routes.lead);
const IDS = D.dossier_ids;  // the stored ids, as the old addresses wrote them
const DIPS = IDS.map(SLUG);
const catalogue = JSON.parse(readFileSync(join(SITE, "assets", "data", "catalogue.json"), "utf8"));
const PLANET_SLUGS = new Set(catalogue.planets.slug);
const STAR_SLUGS = new Set(catalogue.stars.slugs);
// Their own pages, not the app's: every example run's case file, plates and report (the build lists them).
const STANDALONE = (() => { try { return JSON.parse(readFileSync(join(SITE, "assets", "standalone.json"), "utf8")); }
  catch (e) { return ["/candidates/case-file/", "/evidence/plates/", "/evidence/report/"]; } })();
const TECHNICAL = ["/docs/", "/evidence/runs/", ...STANDALONE.filter((p) => p.startsWith("/evidence/report/"))];  // pages that may quote a stored record verbatim
// One known axe finding, named here so it cannot hide another: on a phone the stand-alone case file's signal list
// (a listbox) makes each signal's header an accordion button, which ARIA does not allow inside a listbox. Fixing it
// means a tree pattern for that list; until then it is reported (as "known") rather than failed.
const KNOWN_AXE = STANDALONE.filter((p) => p.endsWith("/case-file/")).map((page) => ({ page, rule: "aria-required-children", target: "#rows" }));
// The deliberate sideways scrollers: what is inside them may run past the window, because they scroll. Anything else
// whose right edge passes the window is cut off (html and body hide sideways overflow), and fails (tests/e2e/clipped.js).
const SCROLLERS = [
  "div.tablewrap", "div.scroll",  // wide tables
  "pre",  // code on the Docs page
  "#exscatter.astable",  // the candidates' compact period table, on a phone
  "div.cthead",  // the catalogue table's header, scrolled with its body
  ".mxtoc ol",  // How it works: the chapter list, one row on a phone
].join(", ");
const CLIPPED = readFileSync(join(HERE, "clipped.js"), "utf8").replace("%SCROLLERS%", SCROLLERS);

const { chromium } = await loadPlaywright();
const server = await serve(SITE);
const BASE = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch({ args: ["--use-gl=swiftshader", "--enable-unsafe-swiftshader"] });
const SIZES = { desktop: { width: 1440, height: 900 }, phone: { width: 390, height: 844 } };

async function context(size, theme) {
  const phone = size === "phone";
  const ctx = await browser.newContext({ viewport: SIZES[size], isMobile: phone, hasTouch: phone, colorScheme: theme, reducedMotion: "reduce" });
  await ctx.addInitScript((t) => { try { localStorage.setItem("setuhq-theme", t); } catch (e) { /* private */ } }, theme);
  return ctx;
}

// A page with its errors collected: console errors, uncaught exceptions, failed requests and same-origin responses >= 400.
function watch(page) {
  const errs = [];
  page.on("console", (m) => { if (m.type() === "error") errs.push("console: " + m.text()); });
  page.on("pageerror", (e) => errs.push("pageerror: " + e.message));
  // A request the browser cancels because the page moved on (net::ERR_ABORTED) is not a failure of the site.
  page.on("requestfailed", (r) => { const why = (r.failure() || {}).errorText || ""; if (!r.url().startsWith("blob:") && !why.includes("ERR_ABORTED")) errs.push("requestfailed: " + r.url() + " " + why); });
  page.on("response", (r) => { if (r.url().startsWith(BASE) && r.status() >= 400 && r.request().resourceType() !== "document") errs.push(`response ${r.status()}: ${r.url()}`); });
  return errs;
}

async function ready(page) {
  await page.waitForFunction(() => document.documentElement.dataset.ready === "1", null, { timeout: 20000 });
}

// The visible logo image in a link home, its box and its link's box, and what is under the image's centre.
const LOGO_GEOMETRY = () => {
  const img = [...document.querySelectorAll('a[href="/"] img.brandlogo')].find((i) => {
    const r = i.getBoundingClientRect();
    return r.width > 0 && r.height > 0 && getComputedStyle(i).visibility !== "hidden";
  });
  if (!img) return null;
  const a = img.closest("a");
  a.scrollIntoView({ block: "center" });
  const r = img.getBoundingClientRect(), b = a.getBoundingClientRect();
  const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
  const box = (q) => [q.left, q.top, q.width, q.height].map((v) => Math.round(v)).join(",");
  return { inside: r.left >= b.left - 0.5 && r.right <= b.right + 0.5 && r.top >= b.top - 0.5 && r.bottom <= b.bottom + 0.5,
    hit: !!hit && a.contains(hit), img: box(r), link: box(b), at: hit ? hit.tagName + "." + hit.className : "nothing" };
};

async function pageFacts(page) {
  return page.evaluate(() => {
    const meta = (sel) => (document.querySelector(sel) || {}).content || (document.querySelector(sel) || {}).href || null;
    const vis = (el) => !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length) && getComputedStyle(el).visibility !== "hidden";
    const imgs = [...document.querySelectorAll("img")].filter((i) => !i.hasAttribute("alt")).map((i) => i.src);
    const hashLinks = [...document.querySelectorAll("a[href]")].filter((a) => a.getAttribute("href").startsWith("#/")).map((a) => a.getAttribute("href"));
    const h1s = [...document.querySelectorAll("h1")].filter(vis).map((h) => h.textContent.trim());
    // Sideways overflow: the page itself, and any element that sticks out past the right edge of the window.
    const over = document.documentElement.scrollWidth - window.innerWidth;
    return { title: document.title, description: meta('meta[name="description"]'), canonical: meta('link[rel="canonical"]'),
      ogImage: meta('meta[property="og:image"]'), ogTitle: meta('meta[property="og:title"]'), imgs, hashLinks, h1s, over,
      path: location.pathname + location.search };
  });
}

async function axe(page) {
  await page.addScriptTag({ content: AXE });
  return page.evaluate(async () => {
    const r = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      resultTypes: ["violations"] });
    return r.violations.filter((v) => v.impact === "serious" || v.impact === "critical")
      .map((v) => ({ id: v.id, impact: v.impact, nodes: v.nodes.slice(0, 3).map((n) => n.target.join(" ") + " :: " + (n.failureSummary || "").split("\n").slice(1, 2).join("")) }));
  });
}

// ---------------------------------------------------------------- every page, two sizes, two themes
let list = pages;
if (QUICK) {
  const kinds = new Map();
  for (const p of pages) { const k = p.split("/").slice(0, 2).join("/") + (p.split("/").length > 4 ? "/*" : ""); if (!kinds.has(k)) kinds.set(k, p); }
  list = [...kinds.values()];
}
const axeSummary = { pages: 0, serious: 0, critical: 0, known: 0, byRule: {} };
for (const size of ["desktop", "phone"]) for (const theme of ["dark", "light"]) {
  const ctx = await context(size, theme);
  const page = await ctx.newPage();
  for (const p of list) {
    current = `${p} @${size}/${theme}`;
    const errs = watch(page);
    let res;
    try { res = await page.goto(BASE + p, { waitUntil: "load" }); } catch (e) { check(false, "loads", e.message); page.removeAllListeners(); continue; }
    check(res && res.status() === 200, "HTTP 200", res && res.status());
    const app = !STANDALONE.includes(p);
    if (app) { try { await ready(page); check(true, "the app starts"); } catch (e) { check(false, "the app starts", e.message); } }
    await page.waitForTimeout(250);
    const f = await pageFacts(page);
    check(f.over <= 1, "no sideways overflow", `${f.over}px wider than the window`);
    const cut = await page.evaluate(CLIPPED);
    check(cut.length === 0, "nothing in the page is cut off at the right edge", cut.slice(0, 4).join(" | "));
    check(f.title && f.title.length > 3, "has a title", f.title);
    check(f.description && f.description.length > 20, "has a description", f.description);
    check(f.canonical === SITE_URL + p, "canonical is its own address", f.canonical);
    check(f.ogImage && f.ogImage.startsWith(SITE_URL + "/assets/brand/"), "og:image is the site's social card", f.ogImage);
    check(f.ogTitle, "has og:title");
    check(f.imgs.length === 0, "every image has alt text", f.imgs.join(" "));
    // The home link's logo: its drawing lies inside the link's box, and a click on its centre lands on the link.
    const logo = await page.evaluate(LOGO_GEOMETRY);
    if (app) check(!!logo, "the header shows the logo as the home link");
    if (logo) {
      check(logo.inside, "the logo lies inside its link's box", `img ${logo.img} link ${logo.link}`);
      check(logo.hit, "the logo's centre hits its link", logo.at);
    }
    check(f.hashLinks.length === 0, "no old #/ links", f.hashLinks.slice(0, 5).join(" "));
    // The project's old name stays out of what a visitor reads; only a quoted record keeps it ("then called exoplan").
    const old = await page.evaluate(() => (document.body.innerText.match(/.{0,30}\bexoplan\b.{0,20}/gi) || []).filter((m) => !/then called exoplan/i.test(m)));
    check(old.length === 0 || TECHNICAL.includes(p), "no old project name in the visible text", old.slice(0, 3).join(" | "));
    if (app) check(f.h1s.length === 1, "exactly one visible h1", JSON.stringify(f.h1s));
    if (app && size === "desktop") {
      const html = readFileSync(join(SITE, p, "index.html"), "utf8");
      const served = (html.match(/<title>([^<]*)<\/title>/) || [])[1].replace(/&amp;/g, "&").replace(/&#x27;/g, "'");
      check(f.title === served, "the app keeps the page's own title", `${f.title} vs ${served}`);
      // The page reads without JavaScript: its own view is in the HTML, with its heading.
      check(/<h1 [^>]*>[^<]{3,}/.test(html.slice(html.indexOf('id="content"'))), "the HTML has its heading without JavaScript");
    }
    if (size === "desktop" && theme === "dark") {
      await page.reload({ waitUntil: "load" });
      if (app) await ready(page).catch(() => {});
      const g = await pageFacts(page);
      check(g.path === f.path && JSON.stringify(g.h1s) === JSON.stringify(f.h1s), "a reload shows the same page", `${g.path} ${g.h1s}`);
    }
    if (size === "desktop" || theme === "dark") {  // axe: every page at desktop (both themes) and on a phone (dark)
      try {
        const all = await axe(page);
        const known = (x) => KNOWN_AXE.some((k) => k.page === p && k.rule === x.id && x.nodes.every((n) => n.startsWith(k.target + " ")));
        const v = all.filter((x) => !known(x));
        axeSummary.known += all.length - v.length;
        axeSummary.pages++;
        for (const x of v) { axeSummary[x.impact]++; axeSummary.byRule[x.id] = (axeSummary.byRule[x.id] || 0) + 1; }
        check(v.length === 0, "axe: no serious or critical violation", JSON.stringify(v));
      } catch (e) { check(false, "axe ran", e.message); }
    }
    check(errs.length === 0, "no console error, page error or failed request", errs.slice(0, 4).join(" | "));
    page.removeAllListeners();
  }
  await ctx.close();
}

// ---------------------------------------------------------------- the top bar, in place, with Back and Forward
{
  const ctx = await context("desktop", "dark");
  const page = await ctx.newPage();
  const errs = watch(page);
  current = "top bar (desktop)";
  await page.goto(BASE + "/"); await ready(page);
  await page.evaluate(() => { window.__same = 1; });
  const expect = { Explore: "/explore/", Candidates: "/candidates/", "How it works": "/how-it-works/", Evidence: "/evidence/", Docs: "/docs/" };
  for (const [label, path] of Object.entries(expect)) {
    await page.click(`.nav a:text-is("${label}")`);
    await page.waitForFunction((p) => location.pathname === p, path);
    const s = await page.evaluate(() => ({ same: window.__same, cur: (document.querySelector('.nav a[aria-current="page"]') || {}).textContent, h1: (document.querySelector(".route:not([hidden]) h1") || {}).textContent }));
    check(s.same === 1, `${label} opens in place (no reload)`);
    check(s.cur === label, `${label} is marked current`, s.cur);
    check(s.h1 && s.h1.length > 2, `${label} shows its heading`);
  }
  current = "sub-navigation, Back and Forward";
  await page.click('.nav a:text-is("Explore")');
  await page.waitForFunction(() => location.pathname === "/explore/");
  await page.click('#subnav a:text-is("Galaxy")');
  await page.waitForFunction(() => location.pathname === "/explore/galaxy/");
  check(await page.evaluate(() => document.title.startsWith("Galaxy")), "the title follows the page");
  check(await page.evaluate(() => !!document.querySelector('#crumbs:not([hidden]) a[href="/explore/"]')), "a deep page shows its breadcrumbs");
  await page.click('#subnav a:text-is("Catalogue")');
  await page.waitForFunction(() => location.pathname === "/catalogue/");
  await page.goBack(); await page.waitForFunction(() => location.pathname === "/explore/galaxy/");
  check(await page.evaluate(() => !document.getElementById("route-galaxy").hidden), "Back shows the Galaxy");
  await page.goBack(); await page.waitForFunction(() => location.pathname === "/explore/");
  check(await page.evaluate(() => !document.getElementById("route-sky").hidden && document.getElementById("crumbs").hidden), "Back again shows the sky map, without breadcrumbs");
  await page.goForward(); await page.waitForFunction(() => location.pathname === "/explore/galaxy/");
  check(await page.evaluate(() => !document.getElementById("route-galaxy").hidden), "Forward shows the Galaxy again");
  check(await page.evaluate(() => window.__same === 1), "all of it without a reload");
  // The logo goes home.
  current = "the logo";
  await page.goto(BASE + "/docs/"); await ready(page);
  await page.click(".topbar a.brand img.brandlogo.dk");
  await page.waitForFunction(() => location.pathname === "/");
  check(await page.evaluate(() => location.pathname === "/"), "clicking the logo goes to /");
  current = "a dip, its case file, Back";
  // A dip: its page, its case file, Back.
  await page.goto(BASE + "/candidates/"); await ready(page);
  await page.click('#subnav a:text-is("Dips")');
  await page.waitForFunction((d) => location.pathname === `/candidates/${d}/`, LEAD);
  await page.click("#txcase a");
  await page.waitForFunction((d) => location.pathname === `/candidates/${d}/case-file/`, LEAD);
  await page.goBack(); await page.waitForFunction((d) => location.pathname === `/candidates/${d}/`, LEAD);
  check(await page.evaluate(() => !document.getElementById("route-transit").hidden), "Back from a case file shows the dip");
  // No view state in the address after changing a view.
  await page.goto(BASE + "/catalogue/"); await ready(page);
  await page.fill("#ctq", "kepler").catch(() => {});
  await page.waitForTimeout(400);
  check(await page.evaluate(() => location.search === ""), "a filter does not write itself into the address", await page.evaluate(() => location.href));
  check(errs.length === 0, "no errors", errs.join(" | "));
  await ctx.close();
}

// ---------------------------------------------------------------- the phone menu and the keyboard
{
  const ctx = await context("phone", "dark");
  const page = await ctx.newPage();
  const errs = watch(page);
  current = "phone menu";
  await page.goto(BASE + "/"); await ready(page);
  check(await page.isHidden(".nav"), "the section links are in the menu on a phone");
  check(await page.isHidden("#menu"), "the menu starts closed");
  await page.click("#menubtn");
  check(await page.isVisible("#menu"), "the menu button opens it");
  check(await page.getAttribute("#menubtn", "aria-expanded") === "true", "aria-expanded follows");
  check(await page.evaluate(() => document.activeElement && document.activeElement.closest("#menu") !== null), "focus moves into the menu");
  const over = await page.evaluate(() => { const m = document.getElementById("menu").getBoundingClientRect(); return m.right - innerWidth; });
  check(over <= 1, "the menu fits the screen", over);
  await page.keyboard.press("Escape");
  check(await page.isHidden("#menu"), "Escape closes it");
  check(await page.evaluate(() => document.activeElement.id === "menubtn"), "focus returns to the menu button");
  await page.click("#menubtn");
  for (let i = 0; i < 40; i++) await page.keyboard.press("Tab");
  check(await page.evaluate(() => !!document.activeElement.closest("#menu, #menubtn")), "Tab stays inside the open menu");
  await page.click('#menu .msec > a:text-is("Candidates")');
  await page.waitForFunction(() => location.pathname === "/candidates/");
  check(await page.isHidden("#menu"), "following a link closes the menu");
  await page.click("#menubtn");
  await page.mouse.click(200, 800);
  check(await page.isHidden("#menu"), "a tap outside closes it");
  // Every label in the top bar is whole (nothing cut off) on a phone.
  const clipped = await page.evaluate(() => [...document.querySelectorAll(".topbar a, .topbar button, #subnav a")].filter((e) => e.offsetParent && e.scrollWidth > e.clientWidth + 1).map((e) => e.textContent));
  check(clipped.length === 0, "no clipped labels in the top bar or sub-navigation", clipped.join(", "));
  check(errs.length === 0, "no errors", errs.join(" | "));
  await ctx.close();
}
{
  const ctx = await context("desktop", "light");
  const page = await ctx.newPage();
  current = "keyboard and focus";
  await page.goto(BASE + "/explore/galaxy/"); await ready(page);
  await page.keyboard.press("Tab");
  check(await page.evaluate(() => document.activeElement.classList.contains("skip")), "the first Tab reaches the skip link");
  const skipTop = await page.evaluate(() => document.activeElement.getBoundingClientRect().top);
  check(skipTop >= 0, "the skip link shows when focused", skipTop);
  await page.keyboard.press("Enter");
  check(await page.evaluate(() => document.activeElement.id === "content"), "the skip link moves focus to the content");
  await page.goto(BASE + "/"); await ready(page);
  const seen = [];
  for (let i = 0; i < 8; i++) {
    await page.keyboard.press("Tab");
    seen.push(await page.evaluate(() => { const a = document.activeElement, s = getComputedStyle(a); return { t: (a.textContent || a.getAttribute("aria-label") || "").trim().slice(0, 30), outline: s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0 }; }));
  }
  check(seen.some((s) => s.t === "Explore"), "Tab reaches the section links", JSON.stringify(seen.map((s) => s.t)));
  check(seen.slice(1).every((s) => s.outline), "focus is visible on every top-bar control", JSON.stringify(seen));
  // Theme: the button changes the theme and names the next one.
  current = "theme control";
  const label0 = await page.getAttribute("[data-theme-toggle]", "aria-label");
  await page.click("[data-theme-toggle]");
  const t1 = await page.evaluate(() => document.documentElement.dataset.theme);
  check(t1 === "system", "light switches to system", t1);
  check((await page.getAttribute("[data-theme-toggle]", "aria-label")) !== label0, "its accessible name follows");
  check(!(await page.textContent("[data-theme-toggle]")).trim(), "no visible words in the theme button");
  await ctx.close();
}

// ---------------------------------------------------------------- the search overlay
{
  const ctx = await context("desktop", "dark");
  const page = await ctx.newPage();
  const errs = watch(page);
  current = "search overlay";
  await page.goto(BASE + "/docs/"); await ready(page);
  await page.keyboard.press("/");
  check(await page.evaluate(() => document.getElementById("gsearch").open), "/ opens it");
  check(await page.evaluate(() => document.activeElement.id === "gsq"), "the field has focus");
  await page.keyboard.type("pi Men");
  await page.waitForFunction(() => [...document.querySelectorAll("#gsresults [role=option]")].some((o) => o.textContent.includes("pi Men c")), null, { timeout: 15000 });
  check(true, "typing finds pi Men c");
  await page.keyboard.press("Escape");
  check(await page.evaluate(() => !document.getElementById("gsearch").open), "Escape closes it");
  await page.keyboard.press("Control+k");
  check(await page.evaluate(() => document.getElementById("gsearch").open), "Ctrl+K opens it");
  await page.keyboard.type("Galaxy");
  await page.waitForTimeout(200);
  await page.keyboard.press("Enter");
  await page.waitForFunction(() => location.pathname === "/explore/galaxy/");
  check(await page.evaluate(() => !document.getElementById("gsearch").open), "Enter opens the result and closes the overlay");
  await page.click("#gsearchbtn");
  check(await page.evaluate(() => document.getElementById("gsearch").open), "the search icon opens it");
  await page.keyboard.type("pi Men c");
  await page.waitForFunction(() => document.querySelectorAll("#gsresults [role=option]").length > 0);
  await page.keyboard.press("ArrowDown"); await page.keyboard.press("ArrowUp");
  const sel = await page.evaluate(() => (document.querySelector('#gsresults [aria-selected="true"]') || {}).textContent || "");
  check(sel.length > 0, "the arrow keys move the selection");
  await page.keyboard.press("Escape");
  check(errs.length === 0, "no errors", errs.join(" | "));
  await ctx.close();
}

// ---------------------------------------------------------------- old addresses
{
  const ctx = await context("desktop", "dark");
  const page = await ctx.newPage();
  current = "old addresses forward";
  const CH = D.routes.chapters;
  const map = [
    ["/app/", "/"], ["/app/#/", "/"], ["/app/#/overview", "/"], ["/app/#/overview?layout=kpis.L,discoveries.M,runs.M,top.L", "/"],
    ["/app/#/sky", "/explore/"], ["/app/#/galaxy", "/explore/galaxy/"], ["/app/#/galaxy?focus=pi%20Men", "/explore/galaxy/?focus=pi+Men"],
    ["/app/#/catalogue", "/catalogue/"], ["/app/#/catalogue?q=kepler", "/catalogue/?q=kepler"], ["/app/#/variables", "/catalogue/everything-that-dims/"],
    ["/app/#/mission", "/explore/mission-control/"], ["/app/#/transit", `/candidates/${LEAD}/`], [`/app/#/transit?dip=${IDS[0]}`, `/candidates/${DIPS[0]}/`],
    ["/app/#/explorer", "/candidates/"], ["/app/#/explorer?sort=depth&filter=new", "/candidates/?sort=depth&filter=new"],
    ["/app/#/candidates", `/candidates/${LEAD}/case-file/`], [`/app/#/candidates?dip=${IDS[1]}`, `/candidates/${DIPS[1]}/case-file/`],
    [`/app/#/candidates?dip=${IDS[1]}&section=ledger`, `/candidates/${DIPS[1]}/case-file/#ledger`],
    ["/app/#/planets", "/candidates/radius-ratios/"], ["/app/#/sentinels", "/evidence/"], ["/app/#/leaderboard", "/evidence/leaderboard/"],
    ["/app/#/runs", "/evidence/runs/"], ["/app/#/methods", "/how-it-works/"],
    ["/app/#/planet/pi-men-c", "/planets/pi-men-c/"], ["/app/#/star/pi-men", "/stars/pi-men/"],
    ["/app/#/discoveries", "/candidates/"], ["/app/#/feed", "/candidates/"], ["/app/#/panel", "/evidence/"], ["/app/#/home", "/explore/"],
    ["/app/#/cockpit", `/candidates/${LEAD}/`], ["/app/#/about", "/"], ["/app/#/no-such-section", "/"],
    ["/docket/", "/candidates/case-file/*"], [`/docket/#${IDS[2]}`, `/candidates/${DIPS[2]}/case-file/`],
    ["/plate/", "/evidence/plates/"], ["/report/", "/evidence/report/"], ["/dashboard/", "/candidates/"], ["/discoveries/", "/candidates/"],
    ["/app", "/"], ["/docket", "/candidates/case-file/*"],
  ];
  for (const ch of Object.keys(CH)) map.push([`/app/#/methods?ch=${ch}`, "/how-it-works/" + (CH[ch] ? CH[ch] + "/" : "")]);
  for (const [from, to] of map) {
    await page.goto("about:blank");
    await page.goto(BASE + from, { waitUntil: "load" });
    // "*": the page may add a hash of its own (the stand-alone case file names the dip it opens on).
    const same = (u) => to.endsWith("*") ? u.pathname === to.slice(0, -1) : u.pathname + u.search + u.hash === to;
    try { await page.waitForURL(same, { timeout: 8000 }); } catch (e) { /* checked below */ }
    const u = new URL(page.url());
    check(same(u), `${from} → ${to}`, u.pathname + u.search + u.hash);
  }
  // An old link inside the app (#/...) is followed to its new page too.
  await page.goto(BASE + "/explore/#/galaxy");
  await page.waitForURL((u) => u.pathname === "/explore/galaxy/", { timeout: 8000 }).catch(() => {});
  check(new URL(page.url()).pathname === "/explore/galaxy/", "/explore/#/galaxy → /explore/galaxy/", page.url());
  await ctx.close();
}

// ---------------------------------------------------------------- page not found
{
  const ctx = await context("phone", "light");
  const page = await ctx.newPage();
  current = "404";
  const res = await page.goto(BASE + "/this-page-does-not-exist/");
  check(res.status() === 404, "an unknown address is a 404", res.status());
  await ready(page);
  check((await page.textContent("h1")).includes("not here"), "the page says so");
  const links = await page.$$eval("#route-notfound a", (as) => as.map((a) => a.getAttribute("href")));
  for (const p of ["/", "/explore/", "/candidates/", "/how-it-works/", "/evidence/", "/docs/"]) check(links.includes(p), `it links to ${p}`);
  check(await page.evaluate(() => !document.querySelector('link[rel="canonical"]')) && await page.evaluate(() => (document.querySelector('meta[name="robots"]') || {}).content === "noindex"), "it is not indexed");
  // A dip address the run does not hold is a 404 that says so: never another dip in its place.
  const r3 = await page.goto(BASE + "/candidates/pi-men/dip-99/");
  check(r3.status() === 404, "an unknown dip address is a 404", r3.status());
  await ready(page);
  check(await page.evaluate(() => !document.getElementById("route-notfound").hidden && document.getElementById("route-transit").hidden), "an unknown dip shows the not-found page, not another dip");
  // A planet address the catalogue does not know is a 404 too.
  const r2 = await page.goto(BASE + "/planets/no-such-planet-b/");
  check(r2.status() === 404, "an unknown planet is a 404", r2.status());
  await ctx.close();
}

// ---------------------------------------------------------------- a dip's status follows its vetting outcome
{
  const ctx = await context("phone", "light");
  const page = await ctx.newPage();
  current = "dip status";
  const ALL = D.story.dips.concat(D.showcase_dips || []);  // every example run's dips
  for (const d of ALL) {
    await page.goto(BASE + `/candidates/${SLUG(d.id)}/`); await ready(page);
    const s = await page.evaluate(() => ({ text: document.getElementById("route-transit").innerText, tags: [...document.querySelectorAll("#route-transit .tag")].filter((t) => t.offsetParent).map((t) => t.textContent) }));
    if (d.outcome === "rejected") {
      check(!/candidate, unconfirmed/i.test(s.text) && !s.tags.includes("candidate"), `${SLUG(d.id)} (rejected) is never called a candidate`, s.text.match(/.{0,40}candidate.{0,20}/gi));
      check(/The dip, played back/.test(s.text) && !/The transit, played back/.test(s.text), `${SLUG(d.id)} (rejected) is a dip, not a transit`);
    }
  }
  await page.goto(BASE + "/candidates/"); await ready(page);
  const tags = await page.evaluate(() => [...document.querySelectorAll(".rundips li")].map((li) => [li.querySelector(".rundip").getAttribute("href"), li.querySelector(".tag").textContent]));
  for (const [href, tag] of tags) {
    const d = ALL.find((x) => `/candidates/${SLUG(x.id)}/` === href);
    check(d && tag === { passed: "candidate", flagged: "flagged", rejected: "rejected" }[d.outcome], `${href}: its tag follows its outcome`, `${tag} for ${d && d.outcome}`);
  }
  // The run's count, as every page must give it: "7 dips (5 candidates, 1 flagged, 1 rejected)".
  const k = (o) => D.story.dips.filter((d) => d.outcome === o).length, nd = D.story.dips.length;
  const runCount = `${nd} dips (` + [[k("passed"), "candidate", "candidates"], [k("flagged"), "flagged", "flagged"], [k("rejected"), "rejected", "rejected"]]
    .filter(([n]) => n).map(([n, one, many]) => `${n} ${n === 1 ? one : many}`).join(", ") + ")";
  // The plates: the run plate's line, and no count anywhere (text, SVG descriptions, labels) that calls every dip a candidate.
  await page.goto(BASE + "/evidence/plates/", { waitUntil: "load" });
  const pl = await page.evaluate(() => ({ text: document.body.innerText,
    svg: [...document.querySelectorAll("svg desc, svg title, [aria-label]")].map((e) => e.getAttribute("aria-label") || e.textContent).join(" | "),
    rows: [...document.querySelectorAll("p.caption b.fig")].map((b) => b.textContent) }));
  check(pl.text.includes(`· ${runCount} ·`), "the plates count the run's dips by status", runCount);
  check(!/\b\d+ candidates? (on|by) /.test(pl.text + pl.svg), "no plate count calls every dip a candidate", (pl.text + pl.svg).match(/.{0,30}\d+ candidates? (on|by) .{0,20}/g));
  const named = D.story.dips.map((d) => (D.dips[d.id] || {}).label).filter(Boolean).map((l) => l.replace(/ \([\d.]+ d\)$/, ""));
  check(named.every((l) => pl.rows.some((r) => r.includes(l + "."))), "each run dip's plate row leads with its name", pl.rows.slice(0, 3).join(" | "));
  // The case file's intro.
  await page.goto(BASE + `/candidates/${SLUG(D.story.dips[0].id)}/case-file/`); await ready(page);
  const intro = await page.evaluate(() => document.querySelector("#route-candidates header").textContent);
  check(/Each signal that passed vetting is a candidate, unconfirmed; a rejected or flagged one is named by its status\./.test(intro) && !/Every signal here is a candidate/.test(intro), "the case file's intro names what is a candidate", intro.slice(0, 200));
  await ctx.close();
}

// ---------------------------------------------------------------- the catalogue's planet and star pages (stubs)
{
  const ctx = await context("desktop", "dark");
  const page = await ctx.newPage();
  current = "catalogue pages";
  const errs = watch(page);
  const pick = (all, kind) => { const rest = [...all].filter((s) => !pages.includes(`/${kind}/${s}/`)).sort(); return [0, 0.25, 0.5, 0.75, 0.999].map((q) => rest[Math.floor(q * (rest.length - 1))]); };
  check(readdirSync(join(SITE, "planets")).length > 5000, "every catalogue planet has a page (run setuhq.stubs on the site first)", readdirSync(join(SITE, "planets")).length);
  for (const [kind, all, h] of [["planets", PLANET_SLUGS, "#h-planet"], ["stars", STAR_SLUGS, "#h-star"]]) {
    for (const slug of pick(all, kind)) {
      const p = `/${kind}/${slug}/`;
      const res = await page.goto(BASE + p, { waitUntil: "load" });
      check(res.status() === 200, `${p}: HTTP 200`, res.status());
      const html = readFileSync(join(SITE, p, "index.html"), "utf8");
      check(/<h1[^>]*>[^<]{2,}<\/h1>/.test(html), `${p}: its name is in the HTML without JavaScript`);
      try { await ready(page); } catch (e) { check(false, `${p}: the app starts`, e.message); continue; }
      await page.waitForFunction((sel) => { const e = document.querySelector(sel); return e && !/^(Planet|Star|.*not found)$/.test(e.textContent.trim()); }, h, { timeout: 15000 }).catch(() => {});
      const f = await pageFacts(page);
      check(f.canonical === SITE_URL + p, `${p}: canonical is its own address`, f.canonical);
      check(/· SetuHQ$/.test(f.title), `${p}: has its own title`, f.title);
      check(f.h1s.length === 1 && !/not found/i.test(f.h1s[0]), `${p}: the page is drawn, with one heading`, JSON.stringify(f.h1s));
      check(await page.evaluate(() => !!document.querySelector(".topbar .nav") && !!document.querySelector("footer")), `${p}: has the site's header and footer`);
      check(f.over <= 1, `${p}: no sideways overflow`, f.over);
      const cut = await page.evaluate(CLIPPED);
      check(cut.length === 0, `${p}: nothing cut off at the right edge`, cut.slice(0, 4).join(" | "));
    }
  }
  check(errs.length === 0, "no errors", errs.slice(0, 4).join(" | "));
  await ctx.close();
}

// ---------------------------------------------------------------- every internal link resolves (crawl from /)
{
  const ctx = await context("desktop", "dark");
  const page = await ctx.newPage();
  current = "internal links";
  const seen = new Set(["/"]), queue = ["/"], targets = new Map();
  while (queue.length) {
    const p = queue.shift();
    await page.goto(BASE + p, { waitUntil: "load" }).catch(() => {});
    if (!STANDALONE.includes(p) && pages.includes(p)) await ready(page).catch(() => {});
    const hrefs = await page.$$eval("a[href]", (as) => as.map((a) => a.href));
    for (const h of hrefs) {
      const u = new URL(h);
      if (u.origin !== BASE) continue;
      const key = u.pathname;
      if (!targets.has(key)) targets.set(key, p);
      if (pages.includes(key) && !seen.has(key)) { seen.add(key); queue.push(key); }
    }
  }
  let bad = [], stubs = 0;
  for (const [path, from] of targets) {
    if (pages.includes(path)) continue;
    if (/^\/(planets|stars)\//.test(path)) stubs++;  // a catalogue page written at deploy time: it must be served too
    const r = await page.request.get(BASE + path);
    if (r.status() !== 200) bad.push(`${path} (from ${from}): ${r.status()}`);
  }
  check(bad.length === 0, `every internal link resolves (${targets.size} addresses from ${seen.size} pages; ${stubs} of them catalogue pages written at deploy time)`, bad.slice(0, 10).join(" | "));
  check(seen.size >= pages.length * 0.9, "the crawl from / reaches the pages", `${seen.size} of ${pages.length}`);
  await ctx.close();
}

await browser.close();
server.close();
const failed = results.filter((r) => !r.ok);
const tests = new Set(results.map((r) => r.test));
console.log(`\ne2e: ${results.length} checks in ${tests.size} groups (${list.length} pages × 2 sizes × 2 themes${QUICK ? ", quick sample" : ""}); ${failed.length} failed`);
console.log(`axe-core 4.10.3: ${axeSummary.pages} scans, ${axeSummary.serious} serious and ${axeSummary.critical} critical violations, ${axeSummary.known} known (KNOWN_AXE)${Object.keys(axeSummary.byRule).length ? " " + JSON.stringify(axeSummary.byRule) : ""}`);
const report = arg("report");
if (report) writeFileSync(report, JSON.stringify({ checks: results.length, failed: failed.length, axe: axeSummary, failures: failed }, null, 1));
process.exit(failed.length ? 1 : 0);

// SPDX-License-Identifier: AGPL-3.0-only
// SPDX-FileCopyrightText: 2026 Ashforde OÜ
// Capture the README's app screenshots from the built site (site/, served at its root), light and dark.
//
// One rule for every shot, so the README's tiles line up:
//   * one window: 1440 x 900 CSS px at device scale 2, reduced motion on (the app then starts with
//     its intro animations off and every drawing at rest), the colour theme set before first paint;
//   * one frame: 1360 x 850 CSS px (16:10), the app's content column (x 40 to 1400, the 1280 px
//     column plus its 40 px gutters), starting 32 px above the shot's anchor element: the route's
//     section for a page (a shot may start closer, `above`, when the block before it is nearer), a Methods chapter's named stage (figure.mxstage) or the heading that introduces it, and never
//     above the end of the block before it (so no frame opens on a sliver of earlier text). The top bar and the page bar
//     (breadcrumbs, sub-navigation) are hidden, so no
//     frame carries navigation chrome, and nothing is cut by anything but the frame's bottom edge.
// Nothing is drawn or edited. tools/gen_readme_assets.py --import-shots <out> then scales every PNG
// to 1600 px wide, encodes it as WebP and writes docs/assets/readme/app/SHOTS.json.
//
// It also rasterises the social card (docs/assets/brand/setuhq-social-card.svg, every word already outlined)
// at 1200 x 630 px for link previews, which do not accept SVG; --import-shots copies it to
// docs/assets/brand/setuhq-social-card.png and records the SVG's sha256, so --check notices a stale PNG.
//
// Usage (from the repository root):
//   node tools/capture_site_shots.mjs --out <dir>      # serves site/ itself on a free port
//   python3 tools/gen_readme_assets.py --import-shots <dir>
//
// Needs Node.js 18+ and the `playwright` package with Chromium. It looks for playwright next to this
// script, then in the global node_modules (npm root -g); PLAYWRIGHT_BROWSERS_PATH picks the browser.
// It never downloads a browser.

import { createRequire } from "node:module";
import { createServer } from "node:http";
import { execSync } from "node:child_process";
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { join, extname, resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SITE = join(ROOT, "site");

function loadPlaywright() {
  const roots = [import.meta.url];
  try { roots.push(join(execSync("npm root -g", { encoding: "utf8" }).trim(), "/")); } catch (e) { /* no npm */ }
  for (const r of roots) {
    try { return createRequire(r)("playwright"); } catch (e) { /* try the next */ }
  }
  throw new Error("capture_site_shots: the playwright package was not found (npm i -g playwright, without installing browsers)");
}
const { chromium } = loadPlaywright();

const arg = (name, dflt) => {
  const i = process.argv.indexOf(`--${name}`);
  return i > 0 && process.argv[i + 1] ? process.argv[i + 1] : dflt;
};
const out = resolve(arg("out", "app-shots"));
mkdirSync(out, { recursive: true });

const VIEWPORT = { width: 1440, height: 900 };
const SCALE = 2;
const FRAME = { x: 40, width: 1360, height: 850, above: 32 };

// view, route (the page's address), anchor (the element the frame starts above), and the alt text:
// what the frame shows, stated from the app's own data.
const SHOTS = [
  { view: "mission", route: "/explore/mission-control/", anchor: "#route-mission",
    alt: "Mission Control: the catalogue line (8,376 planets and 5,684 stars from exoplanet.eu, fetched 2026-10-18; 8,049 planets placed; the run tess-pi-men-s1 with 7 dips; the feed's 28 entries) and six linked panes: the Galaxy with pi Men selected and its three planets, the sky position, the stored light curve with its dips, a catalogue slice, the system view and the Sentinel feed. Selecting a star in one pane selects it in every pane." },
  { view: "overview", route: "/", anchor: "#route-overview",
    alt: "Overview: the landing page, The sky, reviewed. SetuHQ searches any TESS star's public light curve for transits; a calibrated panel of Sentinels (AI reviewers) and Probes (deterministic detectors) marks the dips, and vetting explains every verdict; nothing is called a planet until it is one. Below, an artist's impression of a planet, labelled as one, and what you can do here." },
  // above: the gap to the "What you can do here" cards is narrower than the usual 32 px, so start closer.
  { view: "examples", route: "/", anchor: "#examples", above: 12,
    alt: "Worked examples on the home page: five cards, one per stored run on public TESS light curves, each with what kind of example it is, the star, a one-line summary, its dips counted by vetting outcome (a candidate stays unconfirmed; a rejected dip is not a candidate), its sector and panel, a line on what it did not recover where it missed something, and links to its case file, plates and run report. WASP-126, hot Jupiter: 8 dips (8 candidates), TESS sector 1, Probes only; TOI-270, multi-planet system: 7 dips (5 candidates, 2 flagged), TESS sector 5, Probes only, b not found and d with no period; HD 15337, small planets near the limit: 3 dips (2 candidates, 1 flagged), TESS sector 4, Probes only, 1 of b's 5 transits found and neither published period recovered; TOI-236, known false positive: 6 dips (6 rejected), TESS sector 2, Probes only; pi Men, reference check: 7 dips (5 candidates, 1 flagged, 1 rejected), TESS sector 1, Probes and Sentinels." },
  { view: "galaxy", route: "/explore/galaxy/", anchor: "#route-galaxy",
    alt: "Galaxy: every known exoplanet, around the Sun. 8,049 planets around 5,433 stars placed where exoplanet.eu lists them, in 3D galactic coordinates, with distance rings in light-years, a radar and a heads-up readout of the planets near the aim. The app states that it maps these planets and did not find them." },
  { view: "catalogue", route: "/catalogue/", anchor: "#route-catalogue",
    alt: "Catalogue: all 8,376 exoplanet.eu records in a sortable, filterable table with text search and CSV export, each row linking to the planet's own page." },
  { view: "planet", route: "/planets/pi-men-c/", anchor: "#route-planet",
    alt: "A planet page, pi Men c (transit, discovered 2018, super-Earth): the star and planet drawn to scale from stored values (orbit not to scale), the transit light curve from stored values with SetuHQ's own stored points, and the stored parameters from exoplanet.eu with their bounds." },
  { view: "transit", route: "/candidates/pi-men/dip-2/", anchor: "#route-transit",
    alt: "Transit case for the dip at BTJD 1331.77 on pi Men c: 241 ppm, 2.46 hours, SNR 16.0, a candidate, unconfirmed. The seven dips of the run as tabs, the transit played back from stored values, the panel score of 1.00 with the reason (its period matches pi Men c: a known planet recovered, not a discovery) and each reviewer's stored marks, Probes and Sentinels." },
  { view: "methods-rv", route: "/how-it-works/radial-velocity/", anchor: '#mx-rv figure[data-vis="wobble"]', heading: true,
    alt: "Methods, chapter 4 of 15, Radial velocity: 51 Peg b and its star orbiting their shared centre of mass, with the radial-velocity curve (K = 56.7 m/s from m sin i; stored 55.77 m/s) and the star's spectral lines shifting; labelled a model from stored values, the star's motion exaggerated 1,000 times." },
  { view: "methods-atmospheres", route: "/how-it-works/atmospheres/", anchor: '#mx-spectroscopy figure[data-vis="jwst"]', heading: true,
    alt: "Methods, chapter 11 of 15, Reading atmospheres: A real spectrum, WASP-39 b with JWST. The NIRSpec PRISM transmission spectrum (Carter et al. 2024, CC BY 4.0), 36 binned points with error bars and the paper's best-fit model, transit depth from 20,607 to 23,063 ppm over 0.5 to 5.5 µm, with Na, K, H₂O, CH₄, CO₂ and CO bands marked; the deepest point is at 4.37 µm, the carbon dioxide band. Labelled real data, cited." },
  { view: "methods-starlight", route: "/how-it-works/direct-imaging/", anchor: '#mx-imaging figure[data-vis="cgfam"]',
    alt: "Methods, chapter 7 of 15, Blocking starlight: a Lyot coronagraph computed with Fraunhofer optics in four planes (the entrance pupil, the focal plane with a 4 λ/D occulting disc, the Lyot plane with the stop at 80% of the pupil, the final image) and the starlight's log-intensity profile out to 12 λ/D: at 8 λ/D it is 1.8×10⁻⁷ of the star's peak, against 7.8×10⁻⁵ with no coronagraph. Labelled an illustration: ideal monochromatic optics, a log stretch, the planet at an illustrative 10⁻³." },
];

// a static server for site/
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp" };
const server = createServer((req, res) => {
  const p = join(SITE, decodeURIComponent(new URL(req.url, "http://x").pathname));
  const file = p.endsWith("/") || p === SITE ? join(p, "index.html") : p;
  if (!p.startsWith(SITE) || !existsSync(file)) { res.writeHead(404); res.end(); return; }
  try {
    const body = readFileSync(file);
    res.writeHead(200, { "content-type": TYPES[extname(file)] || "application/octet-stream" });
    res.end(body);
  } catch (e) { res.writeHead(404); res.end(); }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}`;

const commit = execSync("git rev-parse --short=7 HEAD", { cwd: ROOT, encoding: "utf8" }).trim();
const appSha = createHash("sha256").update(readFileSync(join(SITE, "index.html"))).digest("hex");

const browser = await chromium.launch();
const shots = [];
for (const theme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: SCALE, colorScheme: theme, reducedMotion: "reduce" });
  await ctx.addInitScript((t) => { try { localStorage.setItem("setuhq-theme", t); } catch (e) { /* private mode */ } }, theme);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.error(`pageerror (${theme}):`, e.message));
  for (const s of SHOTS) {
    await page.goto("about:blank");
    await page.goto(base + s.route, { waitUntil: "networkidle" });
    await page.waitForFunction(() => document.documentElement.dataset.ready === "1", null, { timeout: 60000 });
    await page.waitForSelector(s.anchor, { state: "visible", timeout: 60000 });
    await page.evaluate(() => document.fonts && document.fonts.ready);
    // One pass down the page so every reveal-on-scroll element has been shown, then back.
    await page.evaluate(async () => {
      for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 40)); }
      scrollTo(0, 0);
    });
    await page.addStyleTag({ content: ".topbar,.pagebar{visibility:hidden !important}" });
    // The frame starts above the anchor, or, for a Methods stage, above the heading that introduces it (the nearest
    // h2, h3 or h4 before it in the chapter), so no frame begins mid-heading.
    const top = await page.evaluate(([sel, heading, above]) => {
      const el = document.querySelector(sel);
      let start = el;
      if (heading) {
        const heads = [...el.closest("article").querySelectorAll("h2, h3, h4")]
          .filter((h) => h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING);
        if (heads.length) start = heads[heads.length - 1];
      }
      const t = start.getBoundingClientRect().top;
      // Never begin inside the content above: start below the last block that ends above the frame's start.
      let prev = -Infinity;
      for (const b of (el.closest("article, section") || document.body).querySelectorAll("p, h1, h2, h3, h4, figure, ul, ol, table, .mxbtns, .chips")) {
        const r = b.getBoundingClientRect();
        if (r.height && r.bottom <= t + 0.5 && !b.contains(start)) prev = Math.max(prev, r.bottom);
      }
      return Math.max(t - above, prev + 6) + scrollY;
    }, [s.anchor, !!s.heading, s.above ?? FRAME.above]);
    const y0 = Math.max(0, Math.round(top));
    const vy = (VIEWPORT.height - FRAME.height) / 2;   // the frame sits in the middle of the window
    await page.evaluate((y) => scrollTo(0, y), y0 - vy);
    await page.waitForTimeout(2500);  // let canvases redraw at rest after the scroll
    const scrolled = await page.evaluate(() => scrollY);
    const clip = { x: FRAME.x, y: y0 - scrolled, width: FRAME.width, height: FRAME.height };
    const file = `${s.view}-${theme}.png`;
    await page.screenshot({ path: join(out, file), clip });
    shots.push({ file, view: s.view, route: s.route, frame: s.anchor, theme, viewport: VIEWPORT, device_scale_factor: SCALE,
      reduced_motion: true, crop_css_px: { x: FRAME.x, y: y0, width: FRAME.width, height: FRAME.height }, alt: s.alt });
    console.log(file, JSON.stringify(clip));
  }
  await ctx.close();
}
// The social card: the committed SVG, drawn by Chromium at its own size, nothing added.
const CARD = join(ROOT, "docs", "assets", "brand", "setuhq-social-card.svg");
const cardSvg = readFileSync(CARD);
{
  const ctx = await browser.newContext({ viewport: { width: 1200, height: 630 }, deviceScaleFactor: 1 });
  const page = await ctx.newPage();
  await page.setContent(`<!doctype html><html><body style="margin:0;background:#0A1226"><img src="data:image/svg+xml;base64,${cardSvg.toString("base64")}" width="1200" height="630" style="display:block"></body></html>`);
  await page.waitForFunction(() => document.images[0] && document.images[0].complete);
  await page.screenshot({ path: join(out, "social-card.png"), clip: { x: 0, y: 0, width: 1200, height: 630 } });
  await ctx.close();
  console.log("social-card.png 1200x630");
}
await browser.close();
server.close();
writeFileSync(join(out, "shots.json"), JSON.stringify({
  note: "Real screenshots of the SetuHQ site as built in site/. Nothing is drawn or edited.",
  social_card: { file: "social-card.png", source: "docs/assets/brand/setuhq-social-card.svg",
    source_sha256: createHash("sha256").update(cardSvg).digest("hex"), width: 1200, height: 630 },
  rule: `window ${VIEWPORT.width}x${VIEWPORT.height} CSS px at device scale ${SCALE}, reduced motion; frame ${FRAME.width}x${FRAME.height} CSS px of the content column (x ${FRAME.x}), starting ${FRAME.above} px above the anchor element (a Methods stage, or the heading before it), never above the end of the block before; top bar and page bar hidden`,
  commit, app_sha256: appSha, captured: new Date().toISOString().slice(0, 10), shots,
}, null, 2) + "\n");

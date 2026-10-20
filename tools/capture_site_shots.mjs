// Capture the README's app screenshots from the built app (site/app/index.html), light and dark.
//
// One rule for every shot, so the README's tiles line up:
//   * one window: 1440 x 900 CSS px at device scale 2, reduced motion on (the app then starts with
//     its intro animations off and every drawing at rest), the colour theme set before first paint;
//   * one frame: 1360 x 850 CSS px (16:10), the app's content column (x 40 to 1400, the 1280 px
//     column plus its 40 px gutters), starting 32 px above the shot's anchor element: the route's
//     section for a page, the chapter's article for a Methods chapter. The top bar is hidden, so no
//     frame carries navigation chrome, and nothing is cut by anything but the frame's bottom edge.
// Nothing is drawn or edited. tools/gen_readme_assets.py --import-shots <out> then scales every PNG
// to 1600 px wide, encodes it as WebP and writes docs/assets/readme/app/SHOTS.json.
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

// view, route (the app's hash route), anchor (the element the frame starts above), and the alt text:
// what the frame shows, stated from the app's own data.
const SHOTS = [
  { view: "mission", route: "#/mission", anchor: "#route-mission",
    alt: "Mission Control: the catalogue line (8,376 planets and 5,684 stars from exoplanet.eu, fetched 2026-10-18; 8,049 planets placed; the run tess-pi-men-s1 with 7 dips; the feed's 28 entries) and six linked panes: the Galaxy with pi Men selected and its three planets, the sky position, the stored light curve with its dips, a catalogue slice, the system view and the Sentinel feed. Selecting a star in one pane selects it in every pane." },
  { view: "overview", route: "#/overview", anchor: "#route-overview",
    alt: "Overview: the landing page, The sky, reviewed. A calibrated panel of Sentinels (Claude) and Probes (deterministic detectors) reads every light curve; every verdict explained; nothing called a planet until it is one. Below, an artist's impression of pi Men, labelled as one." },
  { view: "galaxy", route: "#/galaxy", anchor: "#route-galaxy",
    alt: "Galaxy: every known exoplanet, around the Sun. 8,049 planets around 5,433 stars placed where exoplanet.eu lists them, in 3D galactic coordinates, with distance rings in light-years, a radar and a heads-up readout of the planets near the aim. The app states that it maps these planets and did not find them." },
  { view: "catalogue", route: "#/catalogue", anchor: "#route-catalogue",
    alt: "Catalogue: all 8,376 exoplanet.eu records in a sortable, filterable table with text search and CSV export, each row linking to the planet's own page." },
  { view: "planet", route: "#/planet/pi-men-c", anchor: "#route-planet",
    alt: "A planet page, pi Men c (transit, discovered 2018, super-Earth): the star and planet drawn to scale from stored values (orbit not to scale), the transit light curve from stored values with SetuHQ's own stored points, and the stored parameters from exoplanet.eu with their bounds." },
  { view: "transit", route: "#/transit", anchor: "#route-transit",
    alt: "Transit case for the dip at BTJD 1331.77 on pi Men c: 241 ppm, 2.46 hours, SNR 16.0, a candidate, unconfirmed. The seven dips of the run as tabs, the transit played back from stored values, the panel score of 1.00 with the reason (its period matches pi Men c: a known planet recovered, not a discovery) and each reviewer's stored marks, Probes and Sentinels." },
  { view: "methods-rv", route: "#/methods?ch=rv", anchor: "#mx-rv",
    alt: "Methods, chapter 4 of 15, Radial velocity: 51 Peg b and its star orbiting their shared centre of mass, with the radial-velocity curve (K = 56.7 m/s from m sin i; stored 55.77 m/s) and the star's spectral lines shifting; labelled a model from stored values, the star's motion exaggerated 1,000 times." },
  { view: "methods-atmospheres", route: "#/methods?ch=spectroscopy", anchor: "#mx-spectroscopy",
    alt: "Methods, chapter 11 of 15, Reading atmospheres, an explainer (exoplan does not do spectroscopy): starlight passing through a transiting planet's atmosphere at its edge, and the spectrum of starlight alone and during the transit, with the bands of Na, K, H₂O, CH₄, CO₂ and CO from 0.5 to 5 µm; labelled an illustration, the atmosphere drawn 10 times thicker." },
  { view: "methods-starlight", route: "#/methods?ch=imaging", anchor: "#mx-imaging",
    alt: "Methods, chapter 7 of 15, Blocking starlight: a Jupiter twin reflects about a billionth of its Sun's light, so the starlight must be blocked; HR 8799's planets around a masked star, with the inner working angle marked; labelled an illustration, with a logarithmic brightness stretch." },
];

// a static server for site/
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css",
  ".json": "application/json", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".png": "image/png", ".webp": "image/webp" };
const server = createServer((req, res) => {
  const p = join(SITE, decodeURIComponent(new URL(req.url, "http://x").pathname));
  if (!p.startsWith(SITE) || !existsSync(p)) { res.writeHead(404); res.end(); return; }
  try {
    const body = readFileSync(p.endsWith("/") ? join(p, "index.html") : p);
    res.writeHead(200, { "content-type": TYPES[extname(p)] || "application/octet-stream" });
    res.end(body);
  } catch (e) { res.writeHead(404); res.end(); }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const base = `http://127.0.0.1:${server.address().port}/app/index.html`;

const commit = execSync("git rev-parse --short=7 HEAD", { cwd: ROOT, encoding: "utf8" }).trim();
const appSha = createHash("sha256").update(readFileSync(join(SITE, "app", "index.html"))).digest("hex");

const browser = await chromium.launch();
const shots = [];
for (const theme of ["light", "dark"]) {
  const ctx = await browser.newContext({ viewport: VIEWPORT, deviceScaleFactor: SCALE, colorScheme: theme, reducedMotion: "reduce" });
  await ctx.addInitScript((t) => { try { localStorage.setItem("exoplan-theme", t); } catch (e) { /* private mode */ } }, theme);
  const page = await ctx.newPage();
  page.on("pageerror", (e) => console.error(`pageerror (${theme}):`, e.message));
  for (const s of SHOTS) {
    await page.goto("about:blank");
    await page.goto(base + s.route, { waitUntil: "networkidle" });
    await page.waitForSelector(s.anchor, { state: "visible", timeout: 60000 });
    await page.evaluate(() => document.fonts && document.fonts.ready);
    // One pass down the page so every reveal-on-scroll element has been shown, then back.
    await page.evaluate(async () => {
      for (let y = 0; y < document.body.scrollHeight; y += 600) { scrollTo(0, y); await new Promise((r) => setTimeout(r, 40)); }
      scrollTo(0, 0);
    });
    await page.addStyleTag({ content: ".topbar{visibility:hidden !important}" });
    const top = await page.evaluate((sel) => document.querySelector(sel).getBoundingClientRect().top + scrollY, s.anchor);
    const y0 = Math.max(0, Math.round(top - FRAME.above));
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
await browser.close();
server.close();
writeFileSync(join(out, "shots.json"), JSON.stringify({
  note: "Real screenshots of the SetuHQ app (still named exoplan in this build) as built in site/app/index.html. Nothing is drawn or edited.",
  rule: `window ${VIEWPORT.width}x${VIEWPORT.height} CSS px at device scale ${SCALE}, reduced motion; frame ${FRAME.width}x${FRAME.height} CSS px of the content column (x ${FRAME.x}), starting ${FRAME.above} px above the anchor element; top bar hidden`,
  commit, app_sha256: appSha, captured: new Date().toISOString().slice(0, 10), shots,
}, null, 2) + "\n");

<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# The website: structure, addresses and tests

https://setuhq.com is built by `setuhq site` (src/setuhq/site.py) from the stored runs and committed as `site/`;
`.github/workflows/pages.yml` deploys `site/` as it is. Never edit `site/` by hand: change the code, then run
`scripts/ci_local.sh` (or `setuhq site runs/tess-pi-men-s1 runs/tess-wasp-126-s1 runs/tess-toi-270-s5
runs/tess-hd-15337-s4 runs/tess-toi-236-s2 --catalog docs/discoveries/catalog.json --out site`).

`setuhq site` takes one or more runs. The first is the lead run: the sky map, the panel page and the home page's
reference check are drawn from it (pi Men, checked against Huang et al. 2018). Every run, the lead included, is a
worked example (docs/SHOWCASE.md, described by docs/results/showcase.json): a card on the home page, a group of dips
on Candidates, a page and a case file for each dip, and its own stand-alone case file, plates and run report. A run
whose configuration names no Sentinel is labelled "Probes only; Sentinels not run on this example" on each of them.

## Who it is for, and the five sections

The site has three kinds of visitor, and the top bar has five plain-language sections for them:

| Section | For | What is in it |
| --- | --- | --- |
| **Explore** | curious visitors | the sky map of the run's star, the 3D Galaxy of every known exoplanet, the catalogue of known planets (with a page per planet and star), Everything that dims (SetuHQ's sweep), and Mission Control, the power tool that links them |
| **Candidates** | researchers | every signal the panel marked, a page per dip (the transit played back, who marked it, the verdict), each dip's full case file, the run at a glance (cards you can arrange), and the radius ratios |
| **How it works** | curious visitors | the fifteen illustrated chapters, from how a survey works to the history of the field; the transit chapter is what SetuHQ itself does |
| **Evidence** | researchers | the panel (Sentinels and Probes), its calibration and the blind benchmark on real TOIs, the leaderboard, the runs and their configuration, the archived run report and the plates |
| **Docs** | contributors | install and a first run, contributing a sweep, connecting an assistant over MCP, the data downloads, and the technical details behind the figures |

Why these five, and not the nine tabs the app had (Overview, Sky, Galaxy, Catalogue, Transit, Explorer, Sentinels,
Methods, Mission Control):

* The old tabs were named after the code's views, so a visitor had to know the project to know where to go.
  The new names say what a visitor does: explore, look at candidates, learn how it works, check the evidence,
  run it.
* Each audience gets its own entry: a visitor starts at Explore or How it works, a researcher at Candidates or
  Evidence, a contributor at Docs. The home page's "What you can do here" row says the same in one line each.
* Five items fit the top bar at 1440 px and a phone menu without scrolling sideways; nine did not (on a phone,
  "Transit" was cut off).
* Related views sit together: the sky, the Galaxy and the catalogue all answer "where are the planets", so they are
  one section with a sub-navigation; the case file belongs to its candidate, not to a separate tab; the panel's
  calibration, the benchmark and the leaderboard are all evidence about how far to trust the panel.
* Mission Control is kept, as a power tool inside Explore, because it links Explore's views by one selected star.

Every view the app had is still reachable: from the top bar, a section's sub-navigation (under the top bar on a
section's pages, and in the phone menu), the footer, or search.

## Addresses

One clean address per page; no `#/` routes and no view state in the address.

| Page | Address | Old address |
| --- | --- | --- |
| Home | `/` | `/`, `/app/`, `/app/#/overview` (any `?layout=`) |
| Sky map | `/explore/` | `/app/#/sky`, `#/home` |
| Galaxy | `/explore/galaxy/` | `/app/#/galaxy` (its query is kept: `?focus=`, `?tour=` ...) |
| Mission Control | `/explore/mission-control/` | `/app/#/mission` |
| Catalogue | `/catalogue/` | `/app/#/catalogue` |
| Everything that dims | `/catalogue/everything-that-dims/` | `/app/#/variables` |
| A planet | `/planets/<slug>/` | `/app/#/planet/<slug>` |
| A star | `/stars/<slug>/` | `/app/#/star/<slug>` |
| Candidates | `/candidates/` | `/app/#/explorer`, `#/discoveries`, `#/feed`, `/dashboard/`, `/discoveries/` |
| A dip | `/candidates/<star>/dip-<n>/` (e.g. `/candidates/pi-men/dip-2/`) | `/app/#/transit?dip=<stored id>`, `#/cockpit` (no dip: the lead dip) |
| Its case file | `/candidates/<star>/dip-<n>/case-file/` (`#ledger` etc. for a section) | `/app/#/candidates?dip=<stored id>&section=...`, `/docket/#<stored id>` |
| Case file (stand-alone page) | `/candidates/case-file/` (the lead run); `/candidates/<star>/case-file/` (each other example run) | `/docket/` |
| Radius ratios | `/candidates/radius-ratios/` | `/app/#/planets` |
| How it works (chapter 1) | `/how-it-works/` | `/app/#/methods`, `#/methods?ch=survey` |
| A chapter | `/how-it-works/<chapter>/`, e.g. `radial-velocity`, `atmospheres` | `/app/#/methods?ch=<id>` |
| Evidence: the panel | `/evidence/` | `/app/#/sentinels`, `#/panel` |
| Leaderboard | `/evidence/leaderboard/` | `/app/#/leaderboard` |
| Runs | `/evidence/runs/` | `/app/#/runs` |
| Stars: flares, pulsations, CHEOPS | `/evidence/stellar/` | (new) |
| Run report | `/evidence/report/` (the lead run); `/evidence/report/<star>/` (each other example run) | `/report/` |
| Plates | `/evidence/plates/` (the lead run and the search feed); `/evidence/plates/<star>/` (each other example run) | `/plate/` |
| Docs | `/docs/` | (new) |
| How the pictures are drawn | `/docs/pictures/` | (new) |
| Flares, pulsations and CHEOPS (the commands) | `/docs/stellar/` | (new) |
| CHEOPS proposals | `/docs/cheops-proposals/` | (new) |

The table lives in `src/setuhq/routes.py` (`ROUTE_PATHS`, `CHAPTER_SLUGS`, `LEGACY_PAGES`), with its twin in the
page's script. GitHub Pages cannot redirect, so each old directory (`/app/`, `/docket/`, `/plate/`, `/report/`,
`/dashboard/`, `/discoveries/`) holds a small forwarding page, and `404.html` runs the same forwarding script for
any other old address; both keep the hash where it names a dip or a section.

Rules:

* **Identity in the path, nothing else.** A dip, a planet, a star or a chapter is part of the path. Filters, sorts
  and layouts are not written into the address as you use them. A deep link may still carry a short, readable query
  (`/explore/galaxy/?focus=pi+Men`, `/catalogue/?q=kepler`); it is applied on arrival, and the address goes back to
  the page's own as soon as you change the view.
* **Preferences in the browser.** The card layout on Candidates, the feed's sort and filter, Mission Control's
  default layout and the theme are kept in localStorage (when the browser allows it).
* **Sharing a view is explicit.** "Copy link to this view" (on Candidates, the sky map, the Galaxy, the catalogue and
  Everything that dims; Mission Control has its own) makes a link with the view's settings, for example
  `/candidates/?layout=kpis.L,top.L,runs.M,discoveries.M`. A shared layout shows for that visit only and never
  replaces the recipient's own.
* **History.** A link to another page of the app changes the page in place (the History API), so the header, the
  loaded data and the theme stay; Back and Forward work as on any site, and a reload shows the same page.

### What is pre-rendered

Every page above has its own `index.html`, with its own title, description, canonical address and Open Graph tags,
and its own view rendered in the HTML, so it reads without JavaScript. Planet and star pages are pre-rendered for
every planet and star the site names (the Methods chapters, the Galaxy tour and notables, the run's star): about 50
planets and 30 stars. The catalogue holds 8,376 planets and 5,684 stars; a page for each would add some 14,000
folders to the repository at every rebuild, so the others are written at deploy time and never committed:
`PYTHONPATH=src python3 -m setuhq.stubs site` (standard library only) runs in `pages.yml` and `discover.yml` just
before the upload, and in `scripts/site_e2e.sh` on a copy of the site. Each is a small page (about 3 KB) with its
own title, description, canonical address, heading and one line of facts, from `assets/stub-template.html` (written
by the build); the shared script adds the header and footer (`assets/chrome-*.html`) and draws the full planet or
star page. So every catalogue planet and star is served with status 200 and can be indexed. `sitemap.xml` is an
index of `sitemap-pages.xml` (the build's pages) and, after the stubs, `sitemap-planets-1.xml` and
`sitemap-stars-1.xml`; `robots.txt` points to it.

### Dip addresses are permanent

A dip's address names its star and its number for that star (`/candidates/pi-men/dip-2/`); the stored id stays in
the data, and the old addresses that used it forward. The numbers are pinned in `runs/<run>/slugs.json`, which
`setuhq site` writes the first time it builds a run and only ever adds to (`setuhq.dipslugs`). Each entry holds the
address and its dip's subject, mid-time and duration (and the candidate id it had, for reference). An address
belongs to the dip, not to the id: a candidate id is `{subject}-{rank}`, so a re-run that ranks dips differently
swaps ids, and matching by id would point an address at another dip. On every build:

* each pinned address is matched to the run's dip in the same subject whose mid-time is within the pinned dip's
  duration, and never more than half a day, nearest first, one dip per address; it keeps its address;
* a dip that matches no address gets the next free number of its star (in time order among the new ones);
* an address that matches no dip (the dip left the run, or moved by more than its duration) keeps its entry, so its
  number is never given to another dip. Its address is not
  built, so GitHub Pages answers it with `404.html`, which says "This dip is no longer in the run" and links to the
  candidates (`routes.GONE_DIPS`, `D.routes.gone`). An address the run never had is an ordinary not-found page.
  Neither ever shows another dip in its place.

The re-run on the fixed code (the rerun-fixed branch) rebuilds `runs/tess-pi-men-s1` with the same seven dips, field
for field, in the same subjects at the same mid-times, so the committed `slugs.json` keeps them at `pi-men/dip-1` to
`pi-men/dip-7` (checked against that branch's `candidates.json`). The plates name each run dip the same way
("pi Men, dip 5"), with its stored id after it.
Keep `slugs.json` when a run folder is regenerated: deleting it would let the next build number the dips afresh.

### A dip's status

Only a dip that passed vetting is a candidate ("candidate, unconfirmed", tag "candidate"). A flagged dip is open
(tag "flagged") and a rejected dip is not a candidate (tag "rejected"; its page plays back "the dip", not "the
transit"). One table drives every tag, phrase and count: `names.DIP_STATE` and `names.dip_count` ("7 dips (5 candidates, 1 flagged, 1 rejected)"; page script: `DIPSTATE`, `DIPTAG`).

### Shared files and the page budget

A page's HTML holds the head, the top bar, its own view and the footer. Everything shared is a file under
`/assets/`, named by its content hash so it can be cached for good: the stylesheet (`site-<hash>.css`), the script
(`site-<hash>.js`), the app's data (`data/app-<hash>.json`) and every view's markup (`views-<hash>.html`, which lets
a page switch to another view in place), plus the fonts, the brand files and the data downloads. The case file's
frame is `assets/frame/case-file-<hash>.html`.

Each page stays under 200,000 characters of HTML (`setuhq.site.PAGE_BUDGET`; `setuhq site` fails over it, and a test
checks it). The old single app page was about 1.4 million. The stand-alone case file, plates and run report carry
their own data inline so they work saved or printed; their budget is 400,000.

## The visual system

One source for the look of every page: `src/setuhq/design.py`. The site's stylesheet, the header and footer around
the stand-alone pages (`.shellscope`), the case file, plates, run report, search feed page and dashboard (through
aliases), and the README figures (`tools/gen_readme_assets.py` reads `design.TOKENS` and `design.METHOD`) read the
same tokens.

* **Tokens.** `design.TOKENS` holds each colour as (dark, light); `design.tokens_css(scope, aliases)` writes the dark
  block, the light block and the light block for "your device's setting". The ground is `#04060B` in dark and
  `#F5F5F7` in light; the accents (blue for a known planet and focus, yellow for open, red for rejected, cyan for the
  Sentinels, purple for the Probes) keep the logo's and the plates' hues. Every ink passes 4.5:1 on every surface and
  every accent 3:1 on the ground (tests/test_design.py). A **stage** (`.stage`, and every `[data-render]` figure and
  Methods drawing) is black in both themes, with its own ink.
* **Type.** Self-hosted Geist and Geist Mono only (no new files). `fonts.css` adds metric-matched local fallbacks
  (Arial and Menlo scaled to Geist's average width, with its ascent and descent: `tools/font_fallback.py`,
  `design.FONT_FALLBACK`, checked by a test), and each page preloads the Latin Geist file, so the web font arriving
  shifts nothing. Geist has no ⊕, ☉ or ★, so `tools/symbol_font.py` draws them into an 880-byte font registered under
  both families for exactly those code points: "R⊕" never falls back to a glyph twice a letter's width (an e2e check).
* **Motion.** One curve (`--ease`, `cubic-bezier(.2,.7,.2,1)`) and three durations (`--d-1` 150 ms for hover and
  press, `--d-2` 350 ms for reveals and lifts, `--d-3` 600 ms for view changes and fills). A lint in the tests
  rejects any other curve or duration in any stylesheet (infinite decorative loops are listed in `design.LOOP_ALLOW`).
  Under reduced motion the durations are 0 ms, view transitions are off, and every drawing shows a designed still.
  Changing view in place is a view transition; the home page's header is clear over the hero and fills after 40 px.
* **The renderer** (`src/setuhq/renderer.py`, served as `/assets/render-<hash>.js`, at most 64,000 bytes):
  `window.SetuRender` draws stars in their blackbody colour (Planck × CIE 1931, `looks.teff_rgb`, with Claret 2017
  limb darkening) and planets as artist's impressions, on one WebGL1 context per page, with a Canvas2D fallback, and
  the still `<img>` beneath both. A figure is `<figure class="stage rfig" data-render="planet|star|transit"
  data-params='{…}'>` holding its still (with alt text), its honesty tag and a caption with the numbers and the
  source; `SetuRender.mount()` adds a canvas and hides the still, and a failed upgrade leaves the still. A drawing
  animates only while on screen and the page is visible, at most 4 at once (2 on a small touch screen); a slow device
  drops to 30 fps, then to stills. `SetuRender.stats()` reports the path (`webgl`, `canvas2d` or `still`). The Methods
  drawings' `mxStar` and `mxPlanet` draw through it. The background starfield (V11) is a seeded canvas over the top of
  each page; its SVG is the still.
* **Planet looks** (`src/setuhq/looks.py`, standard library only): composition from the radius (rock below 1.6 R⊕,
  Rogers 2015; envelope to 4; Neptune-like to 10; giant above), or without one from the mass (then drawn not to
  scale); temperature band from Teq = 278.3 K × S^¼ computed from a, R★ and Teff (cold, temperate, warm, hot,
  ultra-hot). Eighteen looks, each with a still (`src/setuhq/data/stills/`, drawn by `node tools/render_stills.mjs`
  on the Canvas2D path; `--check` and a test fail when the renderer or the table changed since). No exoplanet is given
  water, and no look or caption says "habitable". A candidate dip is a silhouette at Rp/R★, never planet art.
  `/docs/pictures/` prints every rule, source and still; every "Artist's impression" tag links there.
* **Components** live in `src/setuhq/viz/` (one module each, fixed signatures: `html(data)`, `CSS`, `JS`, optional
  `data(app_data)`); `viz.write_data` merges their build-time data into `assets/data/stories-<hash>.json` and
  `sky-<hash>.json`. Every component is built; one returns "" only when its stored input is not in the build (no
  catalogue, no stored run or fit, fewer than two planets with a period), and its page then leaves that band out.
* **The renderer's scheduler.** Every renderer drawing that moves runs through it: the starfield, the home page's
  hero (its Pause button calls `SetuRender.play`) and a planet portrait's Spin (0.12 rad/s, started with motion
  allowed, held still under reduced motion until pressed). Each stops off screen and in a hidden tab, counts against
  the 4 (2 on a small touch screen) animating at once, obeys the frame governor, and shows in `SetuRender.stats()`.
  The canvases that are not renderer drawings keep their own loops under the same rules (only on screen and with the
  tab visible, a Pause or Play button, still under reduced motion): the sky by year (V04) and the orbits (V08) play
  with motion allowed; the fold (V05) folds once on arrival; the panel ring (V06) converges once.
* **Honesty rules**, each tested: real data shows its source; every picture carries one of five labels (Artist's
  impression, Model from stored values, Real data, cited, Illustration, Speculative model); SetuHQ's output is never
  called confirmed, discovered, a discovery or a new planet (a lint over every built page and 200 stubs,
  tests/test_honesty_lint.py); the attribution line is always `names.ATTRIBUTION`; a rate always shows its interval.
* **Budgets** (`site.check_asset_budget`, run by `setuhq site`, which fails over any): the stylesheet 140,000 bytes,
  the app's script 430,000, the renderer 64,000, `stories-*.json` 40,000 and `sky-*.json` 160,000, each still 40,000
  (512 px) or 8,000 (160 px) and 850,000 in all, the home page 90,000 characters and `/explore/` 160,000, each
  deploy-time stub 4,096 bytes; every other page 200,000 characters and a stand-alone page 400,000.

### Inventory: what each surface draws

| Surface | Built by | Visual components (label on the picture) |
| --- | --- | --- |
| Home `/` | `home.py` | hero V01 (`viz/hero.py`: Model from stored values, the planet tagged Artist's impression); worked examples V03 (`viz/gallery.py`: Model from stored values); temperature strip V09 (`viz/tempstrip.py`); line-up V07 (`viz/lineup.py`: Artist's impression); fold V05 (`viz/fold.py`: Real data, cited); the lead dip's panel ring V06 (`viz/panelring.py`: Real data, cited); sky by year V04 and timeline V12 (`viz/skyyears.py`, `viz/timeline.py`: Real data, cited); counters V10 (`design.odometer_html`) |
| Explore: sky, Galaxy, catalogue, Everything that dims, Mission Control | `app.py` (Sky), `galaxy.py`, `catalogue.py`, `everything.py`, `mission.py` | the sky by year V04 and timeline V12 on `/explore/`; the host-temperature filter V09 on the catalogue |
| Planet and star pages (pre-rendered and deploy-time) | `catalogue.py`, `stubs.py` | portrait V02 (`renderer.figure`: Artist's impression, with Spin), star disc (Model from stored values), line-up V07 with the planet stepping in, orbits V08 (`viz/orbits.py`: Model from stored values) |
| Candidates: dips, case files, plates | `app.py` (Transit, Explorer), `docket.py`, `plate.py` | a dip's panel ring V06; orbits V08 on TOI-270's dips; the case file and plates draw the star with `renderer.star_svg` (no renderer, works offline) |
| How it works, Evidence, Docs | `methods.py`, `learn.py`, `app.py` (Sentinels, leaderboard, runs), `site.py` | the fold V05 in the Transits chapter; V04 and V12 in Methods population; the panel ring in panel mode on `/evidence/`; `/docs/pictures/` prints every look, rule, source and still |
| Evidence: stars; Docs: the stellar commands and CHEOPS proposals | `stellarpages.py` | `/evidence/stellar/`: a flaring M dwarf's TESS light curve and a δ Scuti star's amplitude spectrum (static SVG on a stage: Real data, cited, each with its source line, the detections and the published values), beside each star drawn by the renderer at its TIC v8.2 Teff (Model from stored values); the validation status of each capability read from `docs/results/stellar_validation.json`, always with its count (flares and pulsations partly validated, CHEOPS not validated); ESA's acknowledgement, programme credit lines, papers, DACE's acknowledgement, the disclaimer and the CC BY-NC 3.0 IGO carve-out. The figures' data: `docs/results/stellar_figures.json`, written by `scripts/stellar_figures.py` from public SPOC files (no CHEOPS data) |
| Run report, search feed page, dashboard (CLI outputs) | `report.py`, `dashboard.py` | see "The CLI outputs" below |

The five labels are the only ones used: Artist's impression, Model from stored values, Real data, cited, Illustration
and Speculative model; an e2e check reads one on every stage of every page it visits.

## The search feed and the embargo

The feed on Candidates (and its card on the overview and in Mission Control, the stand-alone feed page,
the dashboard and the plates) shows only signals that match a known TOI. A signal that matches no known
TOI is held for private review and reporting, and is published only after that: the public catalogue
`docs/discoveries/catalog.json` carries just its count (`held_for_review`) and the date of the most recent
hold (`held_last_date`), and wherever the feed is summarised the site shows one plain line, for example
"2 signals held for review; they are published only after review and reporting." Nothing else about a
held signal reaches a page, the catalogue's run logs (which count a batch's targets, `n_targets`, and do
not list them), the Actions log or the Pages artifact. `setuhq discover` withholds such signals when it
writes the catalogue (`discover.embargo_catalog`), and every page reads the catalogue through
`discover.public_catalog`, which withholds them again unless the catalogue was written by a private
deployment that opted out (`"embargo": false`, from `--publish-new` or `[discover] embargo = false`).
`discover.yml` never opts out and stops before its commit if the catalogue holds anything but known-TOI
matches.

## The CLI outputs

`setuhq report` (the run report, also served on the site at `/evidence/report/`), `setuhq discover` (its search
feed page; see "The search feed and the embargo" below), `setuhq dashboard`, `setuhq docket` (the case file) and `setuhq plate` (the plates) write HTML that works
opened from disk and printed:

* the site's tokens inline, under each page's own names (`design.REPORT_ALIASES`, `DOCKET_ALIASES`,
  `PLATE_ALIASES`), with the light set on white paper for print (`design.PRINT_CSS`);
* Geist and Geist Mono copied beside the page (`assets/fonts/`; a page of the site uses the site's one copy);
* the star as a static disc in its blackbody colour (`renderer.star_svg`, from the run's stellar.json), never the
  renderer or WebGL; the report's hero is a black stage with that disc, the dip count (`names.dip_count`) and, for a
  probes-only run, `names.PROBES_ONLY`;
* each dip named by its vetting outcome as the case file decides it (`names.DIP_STATE`), the blind-coded PNG the
  reviewers saw shown byte for byte on a white plate ("The image the reviewers saw (no markers)"), and
  `names.ATTRIBUTION` in the panel section;
* the dashboard's charts in the status colours (yellow a candidate, grey flagged, red rejected, blue the panel's
  agreement and a known TOI) and the shared crosshair (`design.CROSSHAIR_JS`) on its light curve; the feed page's
  entries per night as a static stacked bar chart with its numbers in a table.

`tests/test_report_style.py` checks the tokens, the fonts, the outcome words, the attribution and the PNG bytes;
`tests/e2e/checks/outputs.mjs` opens all five (built by `tests/e2e/build_outputs.py`) over HTTP and from disk, with
no request to another site, axe in both themes, no sideways scroll on a phone and a PDF print.

## The home page

`src/setuhq/home.py` lays out `/` in bands (`home.BANDS`, pinned by tests/test_home.py), every number read from stored
files:

* **The hero** (`viz/hero.py`): "The sky, reviewed." over a live transit of a featured run's star, in its blackbody
  colour at the Teff its stellar.json stores (TIC v8.2), crossed by the run's catalogue planet at Rp/R★ = the
  catalogue radius over the stored stellar radius and the catalogue's b; the model light curve beneath it, its depth
  and duration in the caption and the alt text. The page is written with the lead run; with motion on, the script
  features one eligible run per UTC day (never a false positive), loops only while on screen and the tab is visible,
  and has a Pause button. Under reduced motion it is the lead run's still. Without JavaScript it is an SVG still.
* **The worked examples** (`viz/gallery.py`), one card per run in docs/results/showcase.json order: a stage with the
  star disc and what the run measured as shadows at its own fitted Rp/R★ (a planet the run missed is a dashed outline;
  the false positive TOI-236 is an unlit occulter, "occulter not identified"), above the card's text, caveat and
  panel label.
* **The temperature strip** (`viz/tempstrip.py`): a 31-stop blackbody gradient from 2,500 to 10,000 K with each
  example star and the Sun marked, under the heading "Five example stars: 3,532 K to 6,422 K, one pipeline" (the
  count and the range read from the stored Teffs: the examples span M to F dwarfs, not every kind of star); in filter
  mode it dispatches `setu:teff-range` with `{lo, hi}`.
* **The line-up** (`viz/lineup.py`): every known planet of the worked examples with a stored radius (the planets
  showcase.json names, so HD 15337's b and c, which exoplanet.eu lists under TOI-402 A, are in it), to one scale
  beside Earth, Neptune and Jupiter.
* **The fold** (`viz/fold.py`): pi Men's stored light curve, which folds itself once on the joint-fit period when it
  comes on screen (its button folds and unfolds it); under reduced motion the two panels side by side.
* **Who reviews a dip** (`viz/panelring.py`): the lead dip's stored panel at a readable size (the ring is at most
  520 px wide), with the attribution line.
* **The sky by year and the timeline** (`viz/skyyears.py`, `viz/timeline.py`).
* **The counters** (`design.odometer_html`): the catalogue's rows, the real-TOI benchmark's sample, its held-out
  completeness with its Wilson interval, and the chapters of How it works, each linking to its proof.
* The reference check, the sweep line, "What you can do here" and "What this page does not claim".

Each gallery card has the same shape: its stage, a one-line caption of the numbers drawn (the star's Teff and each
body's Rp/R★ with its source), then its text; what every stage shares is said once under the cards.
`assets/data/stories-<hash>.json` carries the gallery's stages, the counters, the line-up, the timeline and the fold's
bins. The page carries no Galaxy teaser: the sky band replaced it, and its data and script were removed.
`tests/e2e/checks/home.mjs` checks the bands at both sizes and in both themes, the counters without JavaScript, the
hero's first frame and its Pause button, the strip's Teffs, the tab order and axe with motion on.

## The header

The logo (home), the five sections, a search icon (also `/` or Ctrl/Cmd+K) that opens an overlay, and a theme icon
(dark, light, or the device's setting; named for screen readers, no visible words). The top bar is sticky and keeps
clear of a phone's notch (safe-area insets). Below 900 px the sections move into a menu: a button opens it, Escape,
a tap outside or following a link closes it, and the keyboard stays inside it while it is open. Breadcrumbs show only
on deep pages (a planet, a dip, a case file, a chapter, a sub-page of a section). There is no run chip and no
duplicate page label.

## Provenance notes

There is no site-wide banner. When the stored run was made with code that a later fix changes, the pages that show
its figures (the candidates, a dip, a case file, the radius ratios, the panel, the runs, the report, the plates) carry
one quiet sentence: "These figures come from an earlier version of the pipeline; a re-run on the current code is in
progress." with a Details link to `/docs/#provenance`, which quotes the run's technical note in full. Pages about
known planets, the methods or the sweep carry nothing. When the run is current (no `code_note` in its manifest) the
sentence disappears everywhere.

## Tests

* `pytest` (tests/test_site.py and the page tests): the address table both ways, every old address, the pages'
  metadata, the page budget, no banner, the honesty wording.
* `scripts/site_e2e.sh` (tests/e2e/run.mjs, Playwright and Chromium, run by `scripts/ci_local.sh` and the
  `site-e2e` job of `ci.yml`), against a local server that serves `site/` at the domain root as GitHub Pages does:
  every page at 1440 × 900 and 390 × 844 in dark and light (status 200, no console error or failed request, no
  sideways overflow, title, description, canonical, Open Graph image, alt text on every image, one heading, a reload
  shows the same page, and an axe-core scan with no serious or critical violation); the top bar and sub-navigation
  in place; Back and Forward; the phone menu and the keyboard; the skip link and visible focus; the search overlay;
  every old address; the 404 page; a sample of the deploy-time planet and star pages; and a crawl of every
  internal link from the home page.
* `tests/e2e/visuals.mjs` (run by `scripts/site_e2e.sh` after `run.mjs`) runs every module in `tests/e2e/checks/`;
  `checks/system.mjs` checks the renderer's three paths (WebGL in SwiftShader, Canvas2D with WebGL blocked, the stills
  with JavaScript off), the animation budget, that hidden or scrolled-away drawings stop, reduced-motion stills, the
  labels on every picture, black stages in light mode, layout shift (at most 0.02 on the home page and a planet page),
  the header that settles, and axe with motion on. `checks/home.mjs` (phase 1), `checks/explore.mjs` (2),
  `checks/candidates.mjs` (3), `checks/learn.mjs` (4) and `checks/outputs.mjs` (5, the CLI outputs) check their
  surfaces; `--only <name>` runs one. `SETUHQ_E2E_BROWSERS=chromium,webkit` adds a WebKit pass when Playwright's
  WebKit is installed.
* `node tests/e2e/gallery.mjs --site site --out <dir> [--light] [--full]` takes a screenshot of every page at both
  sizes, with a contact sheet (`index.html`), for looking at the site.

axe-core 4.10.3 is vendored in `tests/e2e/vendor/` (MPL-2.0, see NOTICE) so the scan runs offline.

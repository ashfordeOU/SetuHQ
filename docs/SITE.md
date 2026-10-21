<!-- SPDX-License-Identifier: AGPL-3.0-only -->

# The website: structure, addresses and tests

https://setuhq.com is built by `setuhq site` (src/setuhq/site.py) from the stored run and committed as `site/`;
`.github/workflows/pages.yml` deploys `site/` as it is. Never edit `site/` by hand: change the code, then run
`scripts/ci_local.sh` (or `setuhq site runs/tess-pi-men-s1 --catalog docs/discoveries/catalog.json --out site`).

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
| A dip | `/candidates/<dip>/` | `/app/#/transit?dip=<dip>`, `#/cockpit` (no dip: the lead dip) |
| Its case file | `/candidates/<dip>/case-file/` (`#ledger` etc. for a section) | `/app/#/candidates?dip=<dip>&section=...`, `/docket/#<dip>` |
| Case file (stand-alone page) | `/candidates/case-file/` | `/docket/` |
| Radius ratios | `/candidates/radius-ratios/` | `/app/#/planets` |
| How it works (chapter 1) | `/how-it-works/` | `/app/#/methods`, `#/methods?ch=survey` |
| A chapter | `/how-it-works/<chapter>/`, e.g. `radial-velocity`, `atmospheres` | `/app/#/methods?ch=<id>` |
| Evidence: the panel | `/evidence/` | `/app/#/sentinels`, `#/panel` |
| Leaderboard | `/evidence/leaderboard/` | `/app/#/leaderboard` |
| Runs | `/evidence/runs/` | `/app/#/runs` |
| Run report | `/evidence/report/` | `/report/` |
| Plates | `/evidence/plates/` | `/plate/` |
| Docs | `/docs/` | (new) |

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
folders (over 100 MB) to the repository at every rebuild, so the others are drawn by the app from `404.html` at the
same clean address. They work and can be linked, but GitHub Pages serves them with status 404, so search engines do
not index them. `sitemap.xml` lists the pre-rendered pages; `robots.txt` points to it.

### Shared files and the page budget

A page's HTML holds the head, the top bar, its own view and the footer. Everything shared is a file under
`/assets/`, named by its content hash so it can be cached for good: the stylesheet (`site-<hash>.css`), the script
(`site-<hash>.js`), the app's data (`data/app-<hash>.json`) and every view's markup (`views-<hash>.html`, which lets
a page switch to another view in place), plus the fonts, the brand files and the data downloads. The case file's
frame is `assets/frame/case-file-<hash>.html`.

Each page stays under 200,000 characters of HTML (`setuhq.site.PAGE_BUDGET`; `setuhq site` fails over it, and a test
checks it). The old single app page was about 1.4 million. The stand-alone case file, plates and run report carry
their own data inline so they work saved or printed; their budget is 400,000.

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
  every old address; the 404 page; and a crawl of every internal link from the home page.
* `node tests/e2e/gallery.mjs --site site --out <dir> [--light] [--full]` takes a screenshot of every page at both
  sizes, with a contact sheet (`index.html`), for looking at the site.

axe-core 4.10.3 is vendored in `tests/e2e/vendor/` (MPL-2.0, see NOTICE) so the scan runs offline.

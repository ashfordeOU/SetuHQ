<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# Changelog

All notable changes to SetuHQ are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the project is pre-1.0, file formats and the command line may still change;
breaking changes are called out explicitly.

## [Unreleased]

### Added

- **SetuHQ in 17 languages** ([docs/TRANSLATING.md](docs/TRANSLATING.md)). The website and the tool speak English
  and, machine-assisted and not yet reviewed by native speakers, Dutch, Polish, Portuguese, Finnish, Swedish, Danish,
  Norwegian Bokmål, Czech, Ukrainian, Russian, German, French, Spanish, Estonian, Japanese and Simplified Chinese;
  each language's picker and footer say so and link to the translation guide. Messages are ICU MessageFormat with
  CLDR plural rules, numbers and dates are formatted per language, and one English catalogue
  (`src/setuhq/locales/en.arb`, generated from the code, with stable ids and translator notes) feeds one ARB file
  per language that Weblate reads, each string with its review status. Main pages have an address per language
  (`/de/explore/`, English stays at `/`) with `html lang`, canonical and hreflang links and a sitemap per language;
  the planet and star pages, dip pages, case files and reports keep one address and are localised in the browser. A
  language picker in the top bar remembers the choice; a first-visit suggestion from the browser's language is
  dismissible and never redirects. The CLI's output and help, its reports, dashboard, plates and case files, and the
  MCP server's tool descriptions and honesty labels follow `--lang`, `SETUHQ_LANG` or the locale, English by
  default; files, JSON keys and every machine-read field stay English. `tools/i18n.py` (and the tests and
  `scripts/ci_local.sh`) checks every translation: placeholders, plural forms, markup, brand names, the glossary per
  language (`docs/i18n/glossary.<lang>.json`), no stronger claim than the English, and every honesty caveat present
  and complete; a missing string falls back to English, and coverage is reported per language. A translation memory
  is kept in `docs/i18n/memory.tmx`. The long-form text is translated too: every block of prose on the main pages
  (the *How it works* chapters, the evidence write-ups, *How the pictures are drawn*, the galaxy, the docs) and the
  text the page scripts draw (case files, the docket, planet and star pages) is a message whose id is a hash of its
  template, numbers and names as arguments in the reader's format; figure and hero captions are message templates
  with their numbers, units and references as arguments. Japanese and Chinese headings break only between phrases.

- **Eclipsing binaries, rotation and transients** ([docs/STELLAR.md](docs/STELLAR.md)). `setuhq binaries`,
  `setuhq rotation` and `setuhq transients`, and the MCP tools `find_eclipsing_binary`, `rotation_period` and
  `find_transients`. Binaries: period from a box search and a periodogram with odd/even and equal-minima rules,
  primary and secondary eclipse depths and widths, the secondary phase with an e·cosω hint, a heuristic morphology
  and a candidate flag with reasons, plus advisory vetting hints that the planet vetting does not use (its results
  and the frozen benchmark are unchanged). Rotation: Lomb-Scargle and the autocorrelation function, uncertainties,
  half/double handling, and periods beyond about 13 days reported as beyond one sector's limit. Transients: three
  time scales, rise and decay times, amplitude, flare-like and supernova-like hints, and screens for momentum dumps,
  scattered light, asteroid crossings and periodic stars; TESScut difference photometry for any sky position
  (cutouts not stored). Every eclipsing binary or transient found is a candidate, never new. Validated under
  protocol v4 (`docs/results/stellar_validation_protocol_v4.json`, committed on its own before any v4 code; seeded
  target draws with tuning and held-out splits): eclipsing binaries partly validated (5 of 8 checks pass), rotation
  not validated (3 of 6), transients not validated (1 of 9), and every transient output says the tools are a search aid whose
  candidates need checking by eye. `scripts/stellar_validation_v4_select.py` reproduces the target draws. Results in
  `docs/results/stellar_validation_v4.md`;
  `/evidence/stellar/` gains the three status cards, one "Real data, cited" figure each and every counted check, and
  `/docs/stellar/` the three commands.
- **Each dip's journey, step by step.** Every dip page and case file shows six dated steps: found by SetuHQ, vetted
  (passed, flagged or rejected), panel reviewed (or Probes only), whether it matches a TOI, follow-up ("not
  announced" unless the TFOP Working Group's disposition is recorded) and whether the literature has a planet at its
  period (with the reference). The last three are other teams' records from the NASA Exoplanet Archive, stored in
  `docs/results/showcase_archive.json` by `scripts/fetch_showcase_archive.py`; a step with no record is hollow.
  Dip and star pages also say how long ago the light left the star, from the catalogue's stored distance.
- **Where TESS is now** (`/explore/tess-now/`): each sector's four camera fields from the published schedule, saved
  on 2026-10-24 from the TESS Science Office's sector pages by `scripts/fetch_tess_schedule.py`
  (`docs/results/tess_schedule.json`), on the sky map, with a sector scrubber and the catalogued stars inside the
  fields highlighted. Labelled "Pointing from the published schedule, not live telemetry".
- **Be the vetter** (`/candidates/be-the-vetter/`): eight stored dips from the example runs, each with its light
  curve, fold, odd and even depths and secondary; the visitor calls pass, flag or reject, then sees the stored
  vetting decision and its reasons. A learning exercise: answers stay in the browser and are never collected.
- **Editions** (`/editions/`, linked from the footer and Docs): the open core, SetuHQ Pro (under contract, in
  development) and a custom study compared row by row, the two licences and the CHEOPS carve-out. No prices; every
  paid route starts with a message to contact@ashforde.org.
- **Figures say their source and limits.** Every labelled figure has a "Source / limits" disclosure built from its
  label and caption, and the orbit views carry a dismissible first-visit hint ("Sizes not to scale · phases
  illustrative"). The orbit views (V08) gain focus (all, the star, each planet), zoom and reset buttons; the Galaxy
  gains All, Selected star, zoom and Reset view buttons.
- **A stable public API** (`setuhq.api`, [docs/API.md](docs/API.md)): the names code outside the repository may rely
  on, pinned by `tests/test_api.py`. `setuhq.panel.standard_probes()` returns the standard Probe panel as
  `configs/sweep.toml` lists it; the wheel ships the calibrated reviewer weights
  (`setuhq/data/reviewer_weights_full_panel.json` and its calibration record), which an installed package uses by
  default. Sentinels take a provider key per call (`api_key=` on `ClaudeReviewer`, `OpenAIReviewer`,
  `OpenAICompatibleReviewer`, `GeminiReviewer` and their backends), held as a `Secret` that is never logged, cached,
  pickled or written to a manifest; the environment variables stay the fallback, a config file still never holds
  a key, and an endpoint whose URL or query holds the passed key (as a string or a `Secret`) is refused without
  printing it.
- **Feed embargo: new signals are held for private review and reporting.** `setuhq discover` no longer
  publishes a signal that matches no known TOI (`new_candidate`). The public catalogue, the site (the
  Candidates feed, the overview and Mission Control cards, the runs page), the feed page, the dashboard,
  the plates and the command's output carry only known-TOI matches and one static line: "Signals that
  match no known TOI are held for private review; they are published only after review and reporting."
  A hold leaves no public trace, not even a count or a date: every public output is byte for byte what
  it would be had the signal not been found (tested by running the same targets with and without a
  synthetic `new_candidate`). Run logs keep a count of targets (`n_targets`) instead of their TIC list,
  and an error is recorded the same way whether or not its target gave a held signal. Counts of held
  signals will live only in the private review pipeline (setuhq-ops, v0.3). A held signal is not stored
  publicly; the search is deterministic, so that pipeline re-searches those targets. On by default; a private deployment opts out with `--publish-new` or
  `[discover] embargo = false`, which the public workflow never sets. `discover.yml` checks the
  catalogue before it commits. Tests: `tests/test_embargo.py`.

- **Beyond planets: stellar flares, pulsations and CHEOPS** ([docs/STELLAR.md](docs/STELLAR.md)).
  `setuhq flares`, `setuhq pulsations` and `setuhq cheops`, and the MCP tools `find_flares`,
  `pulsation_spectrum` and `get_cheops_lightcurve` (slash command `/setuhq-stellar`). Flares: a
  flare-preserving detrend, Chang et al. (2015) candidate criteria, optional stationary-wavelet
  denoising (Poyatos et al. 2025; extra `[wavelets]`), Mendoza et al. (2022) template fits with
  multi-component models chosen by BIC, energies for a 9000 K blackbody, the flare frequency
  distribution (maximum-likelihood power law and a log-normal comparison), injection-recovery
  completeness and flux-inverted and quiet-star nulls. Pulsations: pre-whitening to S/N 4 with a
  multi-sine refit, combination flags, Harvey backgrounds, numax and Δν with a bootstrap, a heuristic
  type, and red-noise surrogates. CHEOPS: public DRP light curves only, through DACE (extra
  `[cheops]`), roll-angle decorrelation, one timeline with TESS, and ESA's acknowledgement, the
  programme and visit ids, the credit line and SetuHQ's independence disclaimer on every output.
  Compared against published results under protocol v3
  (`docs/results/stellar_validation_protocol_v3.json`, committed before its run): flares partly
  validated (5 of 8 checks pass), pulsations partly validated (7 of 9), CHEOPS not validated
  (2 of 5). The results are in `docs/results/stellar_validation.md`, with the CHEOPS-derived results
  in `docs/results/stellar_validation_cheops.md` under ESA's terms; what is not validated is listed
  there.
- **A CHEOPS Guest Observers proposal helper** ([docs/CHEOPS-PROPOSALS.md](docs/CHEOPS-PROPOSALS.md)).
  `setuhq propose cheops <target>` writes a preparation pack for the Running Call (the rules and cycles checked,
  the target's coordinates, a Reserved Target List match and its prior public visits, planning estimates from
  published in-flight performance, anonymised drafts, ESA's seven steps as a checklist, and every source with its
  sha256); `setuhq propose lint` is an anonymity aid for drafts and PDFs (extra `[propose]`). The MCP tool
  `cheops_proposal_pack` and `/setuhq-cheops-propose` do the same. It never logs in, submits or automates an ESA
  system; the RTL is downloaded at run time and never committed; archive answers are filtered in memory, so no
  proprietary data and no PI name or id reaches the pack or the cache.
- **The stellar tools on the site, in the visual system.** `/evidence/stellar/` shows each capability's status with
  its count, read from the stored record (flares partly validated, 5 of 8 checks pass; pulsations partly validated,
  7 of 9; CHEOPS not validated, 2 of 5), every counted check, and two figures of real TESS data labelled "Real data,
  cited" with their sources: TIC 150359500's flares in sector 2 against Günther et al. (2020), and beta Pic's
  amplitude spectrum in sector 5 against Zieba et al. (2019), each star drawn by the renderer at its TIC v8.2
  Teff. Its CHEOPS part carries ESA's acknowledgement, each programme's credit line, the three papers, DACE's
  acknowledgement, the disclaimer and the CC BY-NC 3.0 IGO carve-out. `/docs/stellar/` documents the commands and
  `/docs/cheops-proposals/` the proposal helper. The figures' data are `docs/results/stellar_figures.json`
  (`scripts/stellar_figures.py`, public SPOC files only). Checked by `tests/test_stellarpages.py` and the e2e module
  `tests/e2e/checks/stellar.mjs`.
- **CHEOPS data stay under ESA's terms** (CC BY-NC 3.0 IGO; commercial use needs ESA's prior
  authorisation): `LICENSING.md`, `NOTICE` and `docs/PRO.md` exclude them from CC BY 4.0, the
  commercial licence and Pro.
- **DOI and PyPI.** The Zenodo concept DOI `10.5281/zenodo.23568348` (all versions) is in `CITATION.cff`
  (`doi`, `identifiers`), `codemeta.json` (`identifier`) and `paper/paper.bib`; the README has a PyPI badge
  (static, from `__version__`, so `tools/gen_readme_assets.py --check` stays offline) and a DOI badge, its
  install section leads with `pip install setuhq`, and its Cite section names the DOIs.
- **Worked examples on more stars.** Four more stored runs on public TESS SPOC light curves, Probes only (the
  manifest records `"panel": {"mode": "probes_only"}` and pages say "Probes only; Sentinels not run on this
  example"): WASP-126 (a hot Jupiter), TOI-270 (three planets), HD 15337 (small planets near the limit) and
  TOI-236 (a false positive in the TOI table, rejected by vetting). Each is compared with the literature by
  `scripts/showcase_compare.py` (docs/SHOWCASE.md, docs/results/showcase/); pi Men stays as the reference check.
- **A README figure of the showcase planets to scale** (`docs/assets/readme/lineup/`): the worked examples' known
  planets beside Earth, Neptune and Jupiter, drawn by the site's renderer (`node tools/render_stills.mjs --figure
  lineup`) from exoplanet.eu's radii, labelled as artist's impressions, its alt text stating every radius and its
  source; `tools/gen_readme_assets.py --check` fails when it is stale.

### Changed

- The built script and stylesheet are written without comments (`setuhq.minify`): the app's script from 429,046 to
  about 378,000 bytes; the dead `_cap` helper is gone.
- **The stellar commands print their validation status.** `setuhq flares`, `setuhq pulsations` and `setuhq cheops`
  print the capability's status with its count on every run and write it into the record (`validation_status`), as
  the MCP tools already did, so no output presents a detector as more validated than it is.
- **DACE is described as what it is** in the proposal helper's pack and documentation: the University of Geneva's
  public API in front of the CHEOPS Mission Archive, not designated by ESA.
- **The CLI's HTML outputs in the site's visual system.** `setuhq report`, the search feed page of `setuhq
  discover` and `setuhq dashboard` read `setuhq.design`'s tokens (the old indigo palette is gone), print in the
  light set, and use Geist and Geist Mono copied beside the page; nothing loads from another site. The report opens
  on a black stage with the run's star in its blackbody colour (from its stellar.json), its dips counted by vetting
  outcome, and each dip's blind-coded image on a white plate, byte for byte; the dashboard names dips by outcome and
  answers on hover and the arrow keys along its light curve; the feed page adds a bar chart of entries per night.
  Checked by `tests/test_report_style.py` and the e2e module `tests/e2e/checks/outputs.mjs` (axe in both themes,
  opened from disk, printed to PDF).
- **The README figures read their colours from `setuhq.design`** (the dark ground is now the site's `#04060B`), and
  every screenshot was recaptured from the redesigned site.
- **The home page, tidied.** The temperature strip's heading says what the examples span ("Five example stars:
  3,532 K to 6,422 K, one pipeline", not "any star"); the gallery's cards share one shape with a one-line caption
  each; the line-up includes every showcase planet with a radius (HD 15337 b and c were missing); the panel ring is
  drawn at a readable size; the unused Galaxy teaser's data and script (about 23 KB) are gone from `/`. The hero's
  transit and a planet portrait's spin now run through the renderer's scheduler (`SetuRender.play`), so they count
  against the page's animation budget and frame governor.
- **The catalogue's fetch note** reads as a plain sentence; the raw error stays in a folded "Technical detail".

- **`setuhq site` takes several runs** (the lead run first). The home page shows every example run as a card,
  Candidates groups the dips by star, and every run's dips get pages and case files, with its own case file,
  plates and report under its star's address. A manifest now also records the code that ran.
- **The header logo's hit area** matches its drawing: the image box is pinned and centred in a 44 px link
  (WebKit placed the link's box above the logo); e2e checks it on every page.
- **Releases are automatic.** A version bump merged to `main` releases itself once CI is green:
  `auto-tag.yml` is now on by default (opt out with the variable `AUTO_TAG=false`), pushes the tag with the
  workflow's own token and then dispatches `release.yml` on the tag; no `RELEASE_TAG_TOKEN` is needed.
  `release.yml` runs the full release for any run whose ref is a tag, pushed or dispatched, with the same
  strict checks; a dispatch on a branch is still a dry run. A second run for a tag that is already released
  waits for the first (concurrency) and skips building and publishing. See
  [docs/RELEASING.md](docs/RELEASING.md).

### Fixed

- The sweep catalogue page's entry list no longer carries an `aria-label` on a role-less `<div>` (axe:
  `aria-prohibited-attr`).

## [0.1.0] - 2026-10-22

The first public release, under the name **SetuHQ** (*setu*, Sanskrit for bridge). Until this
release the code was developed privately as `exoplan`; the history before this entry is that
project's, and it is kept as it was.

### Changed

- **Every stored result that can be re-run without calling a Sentinel is re-run on the fixed code**
  (after the two fixes that change default results: `preprocess.clean` keeps deep dips, and `vet.py`'s
  odd/even test no longer fails clean deep planets). The first runs are kept beside the re-runs, each
  with the pre-fix note in its own file (`codenote.HISTORICAL`).
  - The stored pi Men run, from the start (`scripts/rerun_pi_men.py`): every dip, vetting result, fit
    and FAP equals the first run's (Rp/R★ 0.0179 ± 0.0017 and T14 3.07 ± 0.17 h against Huang et al.
    2018); the Sentinels' stored answers were reused because the subject images and prompts are
    byte-identical.
  - The real-TOI benchmark, all 662 TOIs, protocol unchanged (`benchmark_real_tois.py --edition
    clipfix`): held-out completeness 60% (90/150) against 57% (86/150), 5 stars gained and 1 lost
    (paired bootstrap 95% CI 0 to +6 points, McNemar p = 0.22); FP found 77% and flagged 68% as
    before; controls 641 and 861 vetted dips per 1,000 star-sectors (573 and 848 before).
  - The pre-registered feed rule, evaluated again unchanged: noise 6.1 (4.0–9.4) false signals per
    100 targets under it, 27.8 (23.1–33.1) under the old rule; feed-level completeness 17%.
  - Why the controls and FP rates moved: on the inverted control 16 of the 24 newly passing dips were
    rejected by the old odd/even test and 5 are deep inverted features the old cleaning deleted; 4 of the
    5 newly passing FP TOIs were rejected by the old odd/even test.
  - The calibration record's provenance is corrected: its Probe rates were measured on the code of
    2026-10-16 (03f23bd); since the limb-darkened injections (fbc1ed9) the same seed gives 0.9, 0.8 and
    0.6. The weights stay frozen; a test shows both sets make the same two-of-three decisions.
  - The threshold sweep's held-out score fell from 0.875 to 0.833 (2 of 48 injections at 1000 ppm), a
    change that came with the limb-darkened injections, not the two fixes: the sweep dates from 2026-10-16.
  - Each historical record's note now names its re-run instead of "Not re-run since".
  - The re-run's report adds a stale-ephemeris audit (one held-out CP/KP miss, TOI 1905.01: no dip on the
    published ephemeris, a comparable dip within 12 h and at least 3σ of the propagated ephemeris error off
    it) and the window-measurement limit; the matching rule is unchanged.
  - The live catalogue, the injection-recovery benchmark and the threshold sweep; the leaderboard
    (Probes J 0.35 against the metadata floor's 0.39, paired ΔJ +0.04, −0.10 to +0.17: still not
    shown to beat it) and the methods paper read the re-run.
  - The Sentinels were not asked again: their stored answers are used on the 37 of the 40 subsample
    stars whose subjects are byte-identical; the 3 others are left out.
- **No site-wide banner.** A page built from a record that carries a code note states it once, in
  plain language, at the top of that page; no page of the current site carries one.
- **`candidates.csv` and `candidates.json` carry 10 more columns** on runs made with the current code:
  `sector`, `crowdsap`, `secondary_phase`, `secondary_snr`, `centroid_offset_arcsec`, `centroid_sigma`, `fpp`,
  `nfpp`, `fpp_method` and `validation_label` (the extended-vetting and reduced-FPP results; the full records are
  under `metrics`). The stored pi Men run now has them: FPP 0.0186 and 0.0148 per subject, class "undetermined".
- The Docket's page data keeps only the metrics the page reads (the extended-vetting record per dip
  stays in `candidates.json`).

- **Python 3.11 or later.** `setuhq.config` reads TOML with `tomllib`, which the standard library has from
  3.11.

- **Renamed from exoplan to SetuHQ.** The Python package is `setuhq` (`src/setuhq`), the
  distribution `setuhq`, the command `setuhq` and the MCP server `setuhq-mcp`. The Claude Code
  plugin, its MCP server entry and its slash commands are `setuhq` and `/setuhq-…`
  (`/setuhq-vet`, `/setuhq-explain`, `/setuhq-sweep`, `/setuhq-catalogue`, `/setuhq-physics`,
  `/setuhq-benchmarks`). The data root is `SETUHQ_ROOT` and the ledger base `SETUHQ_BASE`. The
  repository is https://github.com/ashfordeOU/SetuHQ (the old `ashfordeOU/EXOPLAN` URL redirects)
  and the site is https://setuhq.com.
- **Compatibility kept on purpose:**
  - the `exoplan` and `exoplan-mcp` commands still work as deprecated aliases: each prints one line
    on stderr naming its replacement, then runs it unchanged. They will be removed in a later
    release. There is no `exoplan` import shim: `import exoplan` must become `import setuhq`;
  - `EXOPLAN_ROOT` and `EXOPLAN_BASE` are still read when the new variables are not set;
  - **data format names keep their `exoplan-` prefix** (`exoplan-sweep/1`,
    `exoplan-everything-that-dims/1`, `exoplan-contribution/2`, `exoplan-leaderboard/2`,
    `exoplan-leaderboard-inputs/1`, `exoplan-leaderboard-results/4`): they name schema versions,
    and the committed records, submissions and catalogues carry them;
  - a stored run's manifest from before the rename names its version `exoplan_version`; the pages
    and the MCP tools read it as `setuhq_version`;
  - committed results, the stored run and the archived catalogues are not renamed, and their
    numbers are not touched. Two pieces of display text in them were updated: the pre-fix note now
    reads "Pre-fix code: made with SetuHQ (then called exoplan) up to commit 5a03087" in the code and
    in every stored copy (no fingerprint or ledger covers those files' bytes; the README manifest that
    hashes the stored run was regenerated), and the stored pi Men cross-match names
    `setuhq crossmatch`. The leaderboard's seeded submitters and the sweep's
    contributor credit keep the name `exoplan` they were written with.
- **Code fingerprints survive the rename.** A fingerprint hashes each file's path relative to the
  package and its canonical text: the leading SPDX header lines removed and the package name
  written as it was when the committed results were made (`setuhq`/`SetuHQ` as `exoplan`,
  `SETUHQ` as `EXOPLAN`; `setuhq.starsearch.canonical_source`). Files from before the rename have
  neither, so every committed fingerprint is unchanged and still verifies against its commit:
  the sector-1 sweep record's search code (`20a2c1b2…`, commit 0e87409) and classification code
  (`78b84333…`, the current rules), and the real-TOI benchmark's per-star code fingerprints
  (`14f6f4830a525d78` = 76de67d, `e4fe4c99663ccba8` = 40cceca). `scripts/benchmark_real_tois.py`
  hashes each file under the path it had then (`src/exoplan/…`) and reads old commits from either
  path. The classification fingerprint is unchanged.
  **The fingerprints of the current code change.** The search fingerprint goes from `ff5f2568…` before
  this release to `f7317ec9…`: `starsearch.py`, which holds the fingerprint function, is itself one of the
  fingerprinted search files and gained the canonicalisation, and `transitfit.py` now reads its
  limb-darkening table from the package. For that second reason the real-TOI benchmark's fingerprint of
  the current code goes from `0b8e86a1fb71e777` to `b1bf1166c71abdff`. No committed file records an old
  value: the committed sweep record names the search code of 0e87409, and the benchmark names the
  per-star codes above, which all still verify. The benchmark's threshold audit at the results' own
  commit is unchanged and clean; it now also tracks the sha256 of the reference tables, and accepts the
  table's move into the package only as that exact change of `LD_TABLE`. It therefore records 114 values
  (the 113 before, plus the limb-darkening table's hash). The practical effect is that a sweep cache or a contribution bundle made with the
  pre-release code is treated as made by different search code (a fresh search, or a refused
  bundle), as for any other code change.
- **Licence: AGPL-3.0-only or a commercial licence from Ashforde OÜ** (was MIT), with SetuHQ's own
  data, benchmark, leaderboard data and paper under CC BY 4.0. See [`LICENSING.md`](LICENSING.md),
  [`NOTICE`](NOTICE), [`TRADEMARKS.md`](TRADEMARKS.md) and [`CLA.md`](CLA.md). Every source file
  carries an SPDX header. Every commit before this release was made by Ashforde OÜ's own account.
- **Workflows run on GitHub-hosted runners** (`ubuntu-latest`), not the self-hosted runner, with
  every action pinned to a full commit SHA (its tag in a comment). `pages.yml` deploys on pushes to
  `main` and on request.
- **The discovery batch runs only on request** (`workflow_dispatch`): its six-hourly schedule is
  removed, and any commit it makes is authored as ashfordeOU. Without an `ANTHROPIC_API_KEY`
  secret it runs the Probes only. Before it commits it rebuilds every page that embeds the feed's
  catalogue (the app and landing page, the plates, the dashboard; `setuhq discover` writes the
  feed page) and runs the fast tests, because its push does not start `ci.yml`.
- **The site serves from the domain root,** https://setuhq.com (`site/CNAME`), with the SetuHQ
  logo, favicon and social card, and title, description, canonical, Open Graph and Twitter card
  tags on every page. `pages.yml` deploys the committed `site/`.

### Added

- `codemeta.json` names Ashforde OÜ as copyright holder.

- **Release machinery.** A `v*` tag runs `.github/workflows/release.yml`: it checks the tag against the
  version, this changelog and CI (a green push run on `main` for that commit, which `main` contains), builds
  the sdist and the wheel, runs `twine check`, checks what they carry, installs the wheel cleanly, attests
  build provenance, creates the GitHub Release with this changelog's section as notes, and uploads the same
  attested files to PyPI as `setuhq` by trusted publishing (no token). A re-run never replaces a file
  already on the release. `mcp-publish.yml` lists the server in the official MCP registry as
  `io.github.ashfordeOU/setuhq` by GitHub OIDC; `auto-tag.yml` is optional and off by default. The steps
  are in [docs/RELEASING.md](docs/RELEASING.md).
- **One version.** `__version__` in `src/setuhq/__init__.py` is the only place it is written for the
  package (pyproject reads it); `scripts/check_version_sync.py` fails when CITATION.cff, codemeta.json,
  .zenodo.json, server.json, smithery.yaml or the plugin manifests disagree, when the release date here
  differs from CITATION.cff's `date-released`, and, for a release tag, when `[Unreleased]` is not empty.
  `scripts/set_release_date.py` sets both dates on the release day.
- **The package runs without a checkout.** The two reference tables the pipeline reads, the Claret 2017
  limb-darkening coefficients and the secondary-eclipse calibration, ship in the package as
  `src/setuhq/data/claret2017_tess_quadratic.json` and `src/setuhq/data/secondary_calibration.json`, and
  `transitfit` and `dvtests` read them with `importlib.resources`. They are byte-identical copies of the
  canonical files in `docs/results/`; `tests/test_release.py` fails until a rewritten original is copied
  over. `setuhq run` from a plain `pip install "setuhq[tess]"` searches, vets and fits outside a checkout.
- **`setuhq mcp`** starts the MCP server over stdio, as `setuhq-mcp` does, and says which extra to install
  when the MCP SDK is missing. The MCP registry entry (`server.json`) launches it as
  `uvx --with=mcp>=1.10 setuhq==<version> mcp`.
- The package ships `py.typed`; its PyPI page is `README.pypi.md` (absolute links only). The exact versions
  the README figures need are in `requirements-readme.txt`, not in the package metadata.
- `examples/quickstart.ipynb`: the stored pi Men run offline, from candidates to an MCP tool call; a test
  runs it. `paper/` holds the JOSS paper; issue forms, a pull request template, Dependabot and
  `.editorconfig` are under `.github/` and at the root. CI also runs the fast tests on Python 3.11.

- [`CITATION.cff`](CITATION.cff), [`codemeta.json`](codemeta.json),
  [`GOVERNANCE.md`](GOVERNANCE.md), [`SECURITY.md`](SECURITY.md),
  [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md), [`ROADMAP.md`](ROADMAP.md) and this changelog.
- [`docs/PRO.md`](docs/PRO.md): SetuHQ Pro, **planned and not built**, and the README's Editions
  section (Free, SetuHQ Pro, Custom study). Every paid route starts with a message to
  contact@ashforde.org; there are no prices.

### Removed

- `scripts/session_runner.sh`, which registered a self-hosted Actions runner from a short-lived
  session with a repository-administration token. Hosted runners replace it, and a public
  repository should not route its pull requests to a self-hosted runner.

### What the release contains

Everything developed as exoplan, unchanged in behaviour by this release: the blind-coded panel
of AI Sentinels and deterministic Probes; limb-darkened transit fits, bounded false-alarm
probabilities and DV-style and pixel-level vetting; the reduced false-positive probability with
its stability gate; the ephemeris cone and ExoFOP-style export; the frozen 662-TOI benchmark with
controls, its leaderboard with a catalogue-metadata floor (which the Probes are not shown to beat)
and the methods paper draft; the pre-registered two-sector feed rule (the feed is still dominated
by false alarms); the everything-that-dims sweep with contribution bundles and the append-only
ingest ledger; Sentinels on several providers; the MCP server, the Claude Code plugin and an
example agent; and the app (Mission Control, Galaxy, the catalogue, fifteen Methods chapters, the
Docket and the Plates). The real-TOI benchmark, its leaderboard and the paper's numbers were
measured before the deep-dip clipping fix and have not been re-run.

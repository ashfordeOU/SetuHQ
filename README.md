<!-- PREVIEW of the README for the public release of SetuHQ (formerly exoplan).
     Every figure under docs/assets/readme/ and every logo file under docs/assets/brand/ is
     generated from committed data by tools/gen_readme_assets.py, in light and dark variants,
     with every word outlined; each figure's alt text below is its own <desc>, word for word.
     Regenerate with `python3 tools/gen_readme_assets.py`; check with `--check` (run by
     scripts/ci_local.sh). The app screenshots under docs/assets/readme/app/ are taken from the
     built app by tools/capture_site_shots.mjs, imported with --import-shots and recorded in
     app/SHOTS.json (route, window, theme, frame, commit). -->

<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/assets/brand/setuhq-logo-dark.svg">
    <source media="(prefers-color-scheme: light)" srcset="docs/assets/brand/setuhq-logo-light.svg">
    <img src="docs/assets/brand/setuhq-logo-light.svg" alt="SetuHQ: the Setu mark, a flowing S of two paths with a dashed centre line (setu, the bridge), beside the wordmark SetuHQ, whose Q is a star with a planet crossing its face: a transit." width="420">
  </picture>
</p>

<p align="center">
  <strong>SetuHQ · <span lang="sa">सेतु</span> · <em>the bridge</em></strong><br>
  The open exoplanet observatory: from public sky data to reviewed, explained candidates.
</p>

<!-- generated:badges by tools/gen_readme_assets.py --write-readme; edit the generator, not this block -->
<p align="center">
  <a href="scripts/ci_local.sh"><img src="https://img.shields.io/badge/tests-724%20collected-377D0C?style=flat-square&labelColor=0A1226" height="18" alt="724 tests collected by pytest: 718 run offline in CI, 4 slow ones and 2 network ones by scripts/ci_local.sh"></a>
  <a href="#evidence"><img src="https://img.shields.io/badge/held--out%20completeness-57%25%20%2886%2F150%29-066A86?style=flat-square&labelColor=0A1226" height="18" alt="Held-out completeness on 662 real TOIs: 86 of 150 confirmed or known planets on searchable stars, Wilson 95% interval 49 to 65%"></a>
  <a href="#the-app"><img src="https://img.shields.io/badge/catalogue-8%2C376%20planets-066A86?style=flat-square&labelColor=0A1226" height="18" alt="The catalogue holds all 8,376 exoplanet.eu records, fetched 2026-10-18"></a>
  <a href="#the-app"><img src="https://img.shields.io/badge/Methods-15%20chapters-066A86?style=flat-square&labelColor=0A1226" height="18" alt="15 animated Methods chapters with tested physics"></a>
  <a href="#licence"><img src="https://img.shields.io/badge/licence-AGPL--3.0%20%28at%20release%29-3F4B67?style=flat-square&labelColor=0A1226" height="18" alt="Licence: AGPL-3.0-only from the public release, with a commercial licence from Ashforde OÜ"></a>
  <a href="#editions"><img src="https://img.shields.io/badge/commercial-available-B8288F?style=flat-square&labelColor=0A1226" height="18" alt="A commercial licence and SetuHQ Pro are available on request from Ashforde OÜ"></a>
</p>
<!-- /generated:badges -->

<p align="center">
  <a href="https://setuhq.com"><b>setuhq.com</b></a> ·
  <a href="#the-app">The app</a> ·
  <a href="#how-a-run-works">How it works</a> ·
  <a href="#evidence">Evidence</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#editions">Editions</a> ·
  <a href="#cite">Cite</a>
</p>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/hero-light.svg">
  <img src="docs/assets/readme/hero-light.svg" alt="Every known exoplanet with a distance, around the Sun: 8,049 of the 8,376 planets in exoplanet.eu (fetched 2026-10-18), around 5,433 host stars, seen from above the Galactic plane with the Sun at the centre and the Galactic centre (longitude 0°) at the top. Angle is galactic longitude; distance from the centre is the listed distance on a logarithmic scale, with rings at 10, 100, 1,000 and 10,000 light-years; galactic latitude is dropped. Colour is the first detection method listed: Transit 4,790; Radial velocity 1,329; Imaging 1,216; Microlensing 356; Timing 181; Astrometry 89; Other (TTV, kinematic, other) 88. The 327 planets without a distance are not drawn. pi Men, host of pi Men c and the star of SetuHQ's stored run, is marked at 59.9 light-years. No Milky Way is drawn: every point is a catalogue position, not an illustration. Source: docs/results/exoplanet_map.json, commit befef30." width="100%">
</picture>

> **Preview.** This README is the draft for the public release. The product is being renamed
> from *exoplan* to **SetuHQ**: the Python package and the command are now `setuhq`; the site is
> rebuilt in the release. Nothing on this page is a discovery claim: SetuHQ finds and
> vets *candidates*.

## Every dip in the sky, reviewed and explained

TESS has watched about 98% of the sky. Almost all of that light is public, and almost none of it
has been looked at dip by dip. SetuHQ does the looking: a **reviewer panel** of AI **Sentinels**
and deterministic **Probes** marks every dip in blind-coded light curves, the way Planet Hunters
volunteers do. Each verdict keeps its marks, its weights and, for the Sentinels, their reasons
in words. Then the pipeline does the physics: limb-darkened transit fits, bounded false-alarm
probabilities, odd/even and secondary checks, and an honest label on everything.

*Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic matched-filter detectors.*

**What SetuHQ is built to be:**

- **A search you can audit.** Every candidate carries its provenance: data hash, config hash,
  code fingerprint, every reviewer's marks.
- **A benchmark that keeps everyone honest,** including SetuHQ. A frozen, blind test on 662 real
  TESS candidates, with controls, a public leaderboard and its negative results printed first.
- **An observatory you can explore.** Every known exoplanet in 3D, a full catalogue, and
  fifteen animated chapters on how planets are found, all in one app.

## What's new in this preview

- **The name.** exoplan becomes SetuHQ, *setu* being Sanskrit for bridge: from public sky data
  to reviewed candidates. The logo's Q is a star with a planet crossing its face
  ([brand kit](docs/assets/brand/README.md)).
- **The feed's pre-registered rule.** The search feed now needs a signal in both reviewed sectors
  and a FAP below 0.001. On held-out data it cuts noise about fourfold but still admits about 6
  false signals per 100 targets, so its admissions are leads for review (see Evidence).
- **Merged for this release** (each branch scored by an independent reviewer before it was merged):
  pixel-level and Data-Validation-style vetting, a reduced false-positive probability with a
  stability gate, ExoFOP-style export and the deep-dip clipping fix (accepted, 9.0/10); a methods
  paper and the real-TOI leaderboard with a catalogue-metadata floor that SetuHQ does not yet beat
  (accepted, 9.0/10); the “everything that dims” catalogue, an all-sky sweep and contributor
  bundles (accepted, 9.1/10); Sentinels on any provider, an MCP server and a Claude Code plugin
  (accepted, 9.1/10); this README, its generated figures and the brand kit (accepted, 9.2/10).

## The app

Every screenshot below is one frame rule: a 1440 × 900 window at twice the pixel density, motion
reduced so every drawing is at rest, cropped to the app's 1360 × 850 content frame (16:10)
starting just above the section shown. Light and dark follow your GitHub theme.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/mission-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/mission-light.webp">
  <img src="docs/assets/readme/app/mission-light.webp" alt="Mission Control: the catalogue line (8,376 planets and 5,684 stars from exoplanet.eu, fetched 2026-10-18; 8,049 planets placed; the run tess-pi-men-s1 with 7 dips; the feed's 28 entries) and six linked panes: the Galaxy with pi Men selected and its three planets, the sky position, the stored light curve with its dips, a catalogue slice, the system view and the Sentinel feed. Selecting a star in one pane selects it in every pane." width="100%">
</picture>

**Mission Control.** Six linked panes: the live Galaxy, the sky position, the light curve, a
catalogue slice with a star finder, the animated system view and the Sentinel feed. Selecting a
star in one pane selects it in every pane and in popped-out windows. Every number on the
telemetry strip is computed from the app's own data.

<table>
<tr>
<td width="50%" valign="top">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/overview-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/overview-light.webp">
  <img src="docs/assets/readme/app/overview-light.webp" alt="Overview: the landing page, The sky, reviewed. A calibrated panel of Sentinels (Claude) and Probes (deterministic detectors) reads every light curve; every verdict explained; nothing called a planet until it is one. Below, an artist's impression of pi Men, labelled as one." width="100%">
</picture>

**Overview.** The landing page: what the panel is, and that nothing is called a planet until it
is one.

</td>
<td width="50%" valign="top">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/galaxy-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/galaxy-light.webp">
  <img src="docs/assets/readme/app/galaxy-light.webp" alt="Galaxy: every known exoplanet, around the Sun. 8,049 planets around 5,433 stars placed where exoplanet.eu lists them, in 3D galactic coordinates, with distance rings in light-years, a radar and a heads-up readout of the planets near the aim. The app states that it maps these planets and did not find them." width="100%">
</picture>

**Galaxy.** 8,049 of exoplanet.eu's 8,376 planets placed in 3D around the Sun. The Milky Way is
an artist's impression drawn by the page; every planet position is data.

</td>
</tr>
<tr>
<td width="50%" valign="top">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/catalogue-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/catalogue-light.webp">
  <img src="docs/assets/readme/app/catalogue-light.webp" alt="Catalogue: all 8,376 exoplanet.eu records in a sortable, filterable table with text search and CSV export, each row linking to the planet's own page." width="100%">
</picture>

**Catalogue.** All 8,376 exoplanet.eu records, 5,684 stars, a page for every one, and search
from anywhere (⌘K).

</td>
<td width="50%" valign="top">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/planet-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/planet-light.webp">
  <img src="docs/assets/readme/app/planet-light.webp" alt="A planet page, pi Men c (transit, discovered 2018, super-Earth): the star and planet drawn to scale from stored values (orbit not to scale), the transit light curve from stored values with SetuHQ's own stored points, and the stored parameters from exoplanet.eu with their bounds." width="100%">
</picture>

**Planet pages.** Stored parameters with their bounds, and the system drawn to scale from
stored values, with SetuHQ's own points where it has them.

</td>
</tr>
<tr>
<td width="50%" valign="top">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/transit-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/transit-light.webp">
  <img src="docs/assets/readme/app/transit-light.webp" alt="Transit case for the dip at BTJD 1331.77 on pi Men c: 241 ppm, 2.46 hours, SNR 16.0, a candidate, unconfirmed. The seven dips of the run as tabs, the transit played back from stored values, the panel score of 1.00 with the reason (its period matches pi Men c: a known planet recovered, not a discovery) and each reviewer's stored marks, Probes and Sentinels." width="100%">
</picture>

**Transit cases.** SetuHQ's own dips, with the stored points, the limb-darkened fit and each
reviewer's marks.

</td>
<td width="50%" valign="top">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/methods-rv-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/methods-rv-light.webp">
  <img src="docs/assets/readme/app/methods-rv-light.webp" alt="Methods, chapter 4 of 15, Radial velocity: 51 Peg b and its star orbiting their shared centre of mass, with the radial-velocity curve (K = 56.7 m/s from m sin i; stored 55.77 m/s) and the star's spectral lines shifting; labelled a model from stored values, the star's motion exaggerated 1,000 times." width="100%">
</picture>

<!-- generated:methods-chapters by tools/gen_readme_assets.py --write-readme; edit the generator, not this block -->
**Methods: 15 chapters.** How a survey works, Transit, Toward and away, Radial velocity, Astrometry, Microlensing, Blocking starlight, Timing and phase, Radio, False positives, Reading atmospheres, Molecules and life, Population, Equations of life, History and papers. Physics checked by tests against closed forms and published values.
<!-- /generated:methods-chapters -->

</td>
</tr>
<tr>
<td width="50%" valign="top">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/methods-atmospheres-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/methods-atmospheres-light.webp">
  <img src="docs/assets/readme/app/methods-atmospheres-light.webp" alt="Methods, chapter 11 of 15, Reading atmospheres: A real spectrum, WASP-39 b with JWST. The NIRSpec PRISM transmission spectrum (Carter et al. 2024, CC BY 4.0), 36 binned points with error bars and the paper's best-fit model, transit depth from 20,607 to 23,063 ppm over 0.5 to 5.5 µm, with Na, K, H₂O, CH₄, CO₂ and CO bands marked; the deepest point is at 4.37 µm, the carbon dioxide band. Labelled real data, cited." width="100%">
</picture>

**Real data, labelled.** The real JWST spectrum of WASP-39 b (CO₂ at 4.37 µm), and an
Atmosphere Lab. Every visual says whether it is real data, a model or an illustration.

</td>
<td width="50%" valign="top">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/app/methods-starlight-dark.webp">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/app/methods-starlight-light.webp">
  <img src="docs/assets/readme/app/methods-starlight-light.webp" alt="Methods, chapter 7 of 15, Blocking starlight: a Lyot coronagraph computed with Fraunhofer optics in four planes (the entrance pupil, the focal plane with a 4 λ/D occulting disc, the Lyot plane with the stop at 80% of the pupil, the final image) and the starlight's log-intensity profile out to 12 λ/D: at 8 λ/D it is 1.8×10⁻⁷ of the star's peak, against 7.8×10⁻⁵ with no coronagraph. Labelled an illustration: ideal monochromatic optics, a log stretch, the planet at an illustrative 10⁻³." width="100%">
</picture>

**Coronagraphs, computed.** Lyot, apodised pupil, vortex and adaptive optics with angular
differential imaging, from real Fraunhofer numerics.

</td>
</tr>
</table>

<details>
<summary><b>More in the Methods chapters</b></summary>

<br>

* Physics checked by tests against closed forms and published values; the four below are drawn
  with the same functions.
* **Coronagraphs:** closing the Lyot stop from 150% to 80% cuts the starlight at 8 λ/D from
  6.7×10⁻⁵ to 1.8×10⁻⁷ of the peak.
* **Molecules, mode by mode.** Ten molecules, each vibration linked to its infrared band,
  infrared-silent modes marked, the amplitude exaggeration stated per mode.
* **Radial velocity:** a star and planet orbiting their barycentre, solved with Kepler's
  equation; the star's motion is drawn exaggerated by a stated factor.

</details>

## Capabilities

### A known planet, found blind and fitted

The stored run on pi Men (TESS sector 1): the panel's marks, the seven consensus dips and the
limb-darkened fit, against Huang et al. 2018.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/pi-men-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/pi-men-light.svg">
  <img src="docs/assets/readme/pi-men-light.svg" alt="pi Men c in TESS sector 1, from SetuHQ's stored run. Left: the stored light curve of pi Men (TIC 261136679), 3,485 points in 10-minute bins over BTJD 1325.3 to 1351.3, in parts per million, with the 7 consensus dips: 5 passed and on pi Men c's published ephemeris (known, at BTJD 1325.50, 1331.77, 1338.05, 1344.27, 1350.57), 1 passed but off the ephemeris and flagged (open, at BTJD 1348.94), and 1 rejected by vetting (at BTJD 1348.38). Below it, each reviewer's marks as stored: Probe · Sensitive 8; Probe · Typical 8; Probe · Cautious 8; Sentinel · Volunteer 5; Sentinel · Skeptic 5 spans. Right: the points folded on the joint limb-darkened fit of the five epochs (period 6.2680 d), from 5 hours before to 5 hours after mid-transit, with 20-minute means and the fitted model integrated over the 10-minute bins. Rp/R★ = 0.0179 ± 0.0017, 1.05 times Huang et al. 2018's 0.01703; T14 = 3.07 ± 0.17 h, 1.04 times Huang's 2.953 h; model depth 292 ± 8 ppm. A known planet recovered, not a discovery. Sources: runs/tess-pi-men-s1 (subjects, classifications.csv, candidates.json) and docs/results/pi_men_validation.json, commit c25d1cd." width="100%">
</picture>

### Where the sky has been watched

The survey footprints the Sky page draws, and how many planet hosts fall in each.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/sky-coverage-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/sky-coverage-light.svg">
  <img src="docs/assets/readme/sky-coverage-light.svg" alt="Sky coverage on an equal-area Mollweide map in equatorial coordinates (right ascension increasing to the left: 12h at both rims, 6h, 0h at the centre, 18h; declination ±90°, with the ±60° lines labelled), as of 2026-10-18. TESS sectors 1 to 110 cover 97.8% of the sky, shaded by the number of sectors (1–2, 3–5, 6–12, 13 or more; 13 or more is 4.9%). Kepler's field covers 0.3% and the K2 campaigns C0–C19 4.5%, drawn from their CCD channel outlines; the sky in no footprint (TESS, Kepler, K2, CoRoT or the bulge), drawn as grey cells, is 2.1%. Of 5,433 planet hosts, 5,381 lie in TESS's sky, 1,362 in Kepler's field, 661 in K2's and 35 in none. The dashed line is the Galactic plane. Source: docs/results/survey_coverage.json (tess-point and K2fov footprints), commit 54b255e." width="100%">
</picture>

### How planets are found, computed

Four of the fifteen Methods chapters, drawn by the same functions the app uses and the tests
check.

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/methods-strip-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/methods-strip-light.svg">
  <img src="docs/assets/readme/methods-strip-light.svg" alt="Four methods, computed with setuhq.methods (the functions the app's Methods chapters draw with and the tests check). 1. Transit with limb darkening (transit_flux): pi Men c, k = Rp/R★ = 0.0156 from exoplanet.eu's 0.16719 RJ and 1.1 R☉ star, b = 0.5738, quadratic limb darkening u1 = 0.333, u2 = 0.228 (Claret 2017, Teff 6037 K): depth 267 ppm, against 244 ppm for a uniform disc, plotted against the planet's position across the star in stellar radii. 2. Radial velocity (rv_curve): HD 80606 b, P = 111.44 d, e = 0.93183, ω = 301.213°, K = 469.22 m/s, over one orbit. 3. Microlensing (paczynski): point-lens magnification A(u), on a log scale, against time in Einstein-crossing times for u0 = 0.1: peak A = 10.04, u0 = 0.3: peak A = 3.44, u0 = 1: peak A = 1.34. 4. Blocking starlight (airy_intensity, lyot_final_intensity): the star's image against separation 0 to 12 λ/D on a log scale, for a clear pupil and a Lyot coronagraph with a 4 λ/D mask; at 8 λ/D the clear pupil leaves 7.8×10⁻⁵ of the peak, the Lyot stop at 150% 6.7×10⁻⁵ and at 80% 1.8×10⁻⁷. Axes: relative flux against position across the star in stellar radii; radial velocity in m/s, with zero marked, against orbital phase; magnification on a log scale against time in Einstein-crossing times; intensity relative to the unblocked peak on a log scale against separation in λ/D. Models from stored values, not observations. Sources: src/setuhq/methods.py and docs/results/methods_examples.json (exoplanet.eu, fetched 2026-10-18), commit 903cf24." width="100%">
</picture>

## How a run works

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/flow-pipeline-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/flow-pipeline-light.svg">
  <img src="docs/assets/readme/flow-pipeline-light.svg" alt="How a run works, with the counts of SetuHQ's stored run on pi Men (TESS sector 1): 1. Ingest (TESS, CHEOPS, CSV): 1 light curve of 3,485 points; 2. Clean (clip, detrend, bin): masked local-quadratic baseline, 10-minute bins; 3. Blind-code (13-day subjects): 2 subjects, no target names; 4. Review (the panel marks dips): 2 Sentinels + 3 Probes; 10 classifications; 5. Aggregate (skill-weighted consensus): 7 consensus dips; 6. Vet (SNR, odd/even, secondary): 6 passed (1 flagged off-ephemeris), 1 rejected; 7. Fit (limb-darkened transit): 5 of 5 epochs on the ephemeris; Rp/R★ 0.0179; 8. FAP (block bootstrap): &lt; 10⁻⁴ over 10,000 trials: a bound, not a value; 9. Write (candidates + provenance): CSV, JSON, SQLite, a manifest and the site. Every step's output is kept, so a run can be re-vetted from its stored classifications without asking the reviewers again. Sources: runs/tess-pi-men-s1 (manifest.json, candidates.json, subjects), configs/tess_pi_men_s1.toml and docs/results/pi_men_validation.json, commit c25d1cd." width="100%">
</picture>

<details>
<summary><b>Step by step</b></summary>

<br>

1. **Ingests** TESS SPOC light curves from MAST, CHEOPS light-curve FITS files, or CSV.
2. **Cleans and detrends**: spike clipping, a masked local-quadratic baseline, and binning.
3. **Cuts blind-coded subjects**: fixed 13-day segments with opaque IDs. The target name never reaches a reviewer.
4. **Runs the panel**: every reviewer marks and labels every subject independently. The task is the Planet Hunters task: mark the start and end of each dip, then label `potential_planet` or `noise`.
5. **Aggregates** marks by single-linkage clustering, scores each dip by the share of skill-weighted reviewers who marked it, and requires the panel to call the subject a potential planet.
6. **Vets** each consensus event: SNR, duration, edge effects, odd/even depth, secondary eclipse, and fit to the periodic ephemeris.
   Extended tests after the Kepler/SPOC Data Validation suite add flags beside them (`dvtests.py`, `pixel.py`):
   SPOC crowding (CROWDSAP below 0.8 is `crowded`), a weak-secondary search at every phase with the fitted
   duration (threshold from a white-noise simulation, `scripts/calibrate_secondary.py`), odd/even depths from
   per-epoch fits, per-epoch transit times (linear-ephemeris and odd/even timing tests), all on the light curve
   re-detrended in two passes with the fitted transits masked, as DV masks transits (the second pass also masks
   phase 0.5, and the first pass's strongest other dip only when that pass already finds it significant), and,
   from the SPOC target pixel file, a difference-image centroid in pixels and arcseconds with its significance, the
   centroid motion test, a core/halo ghost check, momentum-dump coincidence, and a table of catalogued neighbours
   with the eclipse depth each would need. **By default these only add flags**: pass/fail is decided as before, so
   runs and benchmarks stay comparable with earlier ones. `[vetting] decide = true` makes `secondary_any_phase`,
   `odd_even_depth`, `odd_even_timing` and `centroid_offset` disqualifying, and lets the all-phase secondary search
   replace the phase-0.5 check. The pixel tests download TPFs and are off unless `[vetting] pixel = true`.
7. **Weighs false-positive scenarios** for every periodic candidate (`validate.py`): SetuHQ's own reduced FPP
   (planet, eclipsing binary at P or 2P, eclipse on a resolved neighbour), built from the S2 measurements with stated
   priors. It is not TRICERATOPS and never says "validated". "Validated (statistically)" is reserved for TRICERATOPS
   with FPP < 0.015 and NFPP < 10⁻³ *and* a high-resolution imaging contrast curve; without a curve every candidate
   is "not validated: no contrast curve". SetuHQ never calls its results confirmed.
8. **Writes** a candidate catalogue (CSV and JSON), a Zooniverse-shaped classification export, a SQLite store, a provenance manifest, and a static report site.
9. **Exports for follow-up** (`setuhq export RUN --out DIR`, `exofop.py`): an ExoFOP CTOI-style table (CSV and
   JSON) of vetted candidates that pass the S2 and S3 gates and duplicate no TOI on the same TIC, plus predicted
   transit windows for the next 12 months with the ephemeris uncertainty cone, σ(Tₙ)² = σ_T0² + n²σ_P² (+ 2n cov),
   the same propagation `match_toi` uses (`ephemeris.py`). **The CTOI field list is unverified against ExoFOP's
   current form** (ExoFOP was unreachable); it lives in one place, `exofop.CTOI_FIELDS`. A person submits CTOIs
   under their own ExoFOP account; SetuHQ does not. Without the archive's TOI table the export refuses unless
   `--allow-unchecked`, and then every row says the check was not done.
10. **Scales** with `setuhq batch CONFIG --targets FILE` (`batch.py`): the `discover` flow over any target list,
   with light curves cached in `cache/lightkurve` and a state file that makes a killed or time-limited session
   resumable (done targets are skipped, failures retried, a changed config starts afresh).

</details>

<details>
<summary><b>The reviewer panel: Sentinels and Probes</b></summary>

<br>

| Reviewer kind | Shown as | What it is | Needs |
|---|---|---|---|
| `simulated` | **Probe** | Deterministic matched-filter detector with human-like limits (threshold, miss rate, boundary jitter). A baseline and a calibration reference. | Nothing |
| `claude_code` | **Sentinel** | Claude reviewing the rendered plot through the **Claude Code CLI**, which signs in with a Claude team or individual subscription. | `claude` on PATH, signed in |
| `claude` | **Sentinel** | Claude through the **Anthropic API** (vision). | `ANTHROPIC_API_KEY` |

The pages show display names; reviewer ids stay unchanged in every data file, CSV, JSON
and URL. The default panel is 2 Sentinels and 3 Probes: Sentinel · Volunteer
(`claude-volunteer`), Sentinel · Skeptic (`claude-skeptic`), and Probe · Sensitive,
Probe · Typical and Probe · Cautious (`volunteer-sensitive`, `volunteer-typical`,
`volunteer-cautious`).

Sentinels receive the same task as volunteers, the blind-coded plot, and no
target name. They return strict JSON, which is validated and clipped to the subject's
time range. A reviewer that is not available is skipped and listed in the manifest.
Responses are cached by a hash of model, prompt and image, so re-runs are free and
reproducible.

The two Sentinels use two personas: `volunteer` (careful, marks dips) and `skeptic`
(rejects binary and systematic signatures unless they are clear). Sentinels can also run on
OpenAI, Gemini or any OpenAI-compatible endpoint, labelled as such (see [AI providers](#ai-providers)).

</details>

## Evidence

SetuHQ reports what it measured, including where it falls short.

| Measure | Result | Source |
|---|---|---|
| pi Men c, Rp/R★ against Huang et al. 2018 | **1.05** (0.0179 ± 0.0017) | [validation](docs/results/pi_men_validation.md) |
| pi Men c, transit duration T14 | **1.04** (3.07 ± 0.17 h) | [validation](docs/results/pi_men_validation.md) |
| Real-TOI benchmark, held-out completeness | **57%** (86/150; 49–65%) | [benchmark](docs/results/benchmark_real_tois.md) |
| … planets below 2 R⊕ | 10% | [benchmark](docs/results/benchmark_real_tois.md) |
| Live feed’s “new” signals | **consistent with noise** under the old rule (≈13 per 100 targets from controls vs 15.8 observed). The pre-registered two-sector rule cuts held-out noise about fourfold, from 23.0 (18.6–28.0) to 6.1 (4.0–9.4) per 100 targets, still far above the 0.3 real new signals per 100, and roughly halves completeness; re-run under it, 0 of the 3 earlier new signals survive | [validation](docs/results/feed_rule_validation.json) |
| Real-TOI leaderboard: the Probes against a floor that reads no light curve | **not shown to beat it** (paired ΔJ interval includes zero) | [leaderboard](docs/leaderboard/leaderboard.md) |

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/benchmark-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/benchmark-light.svg">
  <img src="docs/assets/readme/benchmark-light.svg" alt="Blind benchmark on 662 real TESS Objects of Interest (NASA Exoplanet Archive TOI table, fetched 2026-10-19, seed 20261019), held-out half, the three Probes. Completeness is the share of confirmed or known planets (CP/KP) on searchable stars recovered as a vetted dip on the ephemeris, with Wilson 95% intervals. Left, in the bins the published references use: All radii: SetuHQ 57% (86/150, 49%–65%) against Kepler Robovetter DR25 &gt; 85% (vetting only, on detected TCEs, P &lt; 100 d); 3–4 R⊕: SetuHQ 44% (4/9, 19%–73%) against Planet Hunters TESS 51% (a citizen-science search); &gt; 4 R⊕: SetuHQ 75% (77/102, 66%–83%) against Planet Hunters TESS 85% (a citizen-science search). SetuHQ is below the Kepler Robovetter's completeness and Planet Hunters TESS's rate above 4 R⊕ (each interval excludes the reference); consistent with Planet Hunters TESS's rate at 3 to 4 R⊕ (9 stars: the interval includes it). Right: overall 57% (86/150, 49%–65%); without the stars exposed to the known clipping bug 53% (65/123). By planet radius: &lt; 2 R⊕: 10% (2/20, 3%–30%); 2–4 R⊕: 23% (6/26, 11%–42%); 4–8 R⊕: 36% (4/11, 15%–65%); &gt; 8 R⊕: 80% (73/91, 71%–87%). By period: 0.5–2 d: 41% (12/29, 26%–59%); 2–5 d: 67% (52/78, 56%–76%); 5–13 d: 51% (22/43, 37%–65%). References, each value checked in its source paper: Thompson et al. 2018; Eisner et al. 2021. Measured on a stated benchmark, not discoveries. Sources: docs/results/benchmark_real_tois.json, docs/results/benchmark_toi_sample.json (radii) and docs/paper/references.json (references), commit 8dde211." width="100%">
</picture>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/feed-noise-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/feed-noise-light.svg">
  <img src="docs/assets/readme/feed-noise-light.svg" alt="False new signals per 100 targets: what the feed's own admission rule passes on light curves with every signal destroyed, against the live feed. Wilson 95% intervals; a target is 2 sectors. Live feed under the old rule, “new” signals: 15.8 per 100 targets (3 over 19 targets; 5.5–37.6); Control: block-scrambled light curves: 12.9 per 100 targets (20 over 309 star-sectors; 8.5–19.6); Control: flux-inverted light curves: 11.0 per 100 targets (17 over 309 star-sectors; 6.9–17.3); Real light curves of TOI hosts: 3.2 per 100 targets (5 over 309 star-sectors; 1.4–7.5); Feed-rule test, old rule: worse control: 23.0 per 100 targets (71 over 309 targets; 18.6–28.0); Feed-rule test, two-sector rule: worse control: 6.1 per 100 targets (19 over 309 targets; 4.0–9.4); Live feed re-run, two-sector rule: 0.0 per 100 targets (0 over 19 targets; 0.0–16.8). Expected from noise alone (the worse control): 12.9 per 100 targets, so the live feed's “new” signals were consistent with noise under the old rule. The pre-registered two-sector rule (FAP &lt; 0.001 over 2,000 trials, the signal in both sectors), tested once on the held-out half with the discovery config, lowers the worse control about fourfold, but noise still outnumbers the 0.3 real new signals per 100 targets, so admissions are leads for review. Source: docs/results/benchmark_real_tois.json (held-out half, feed-level table, feed_rule), commit 8dde211." width="100%">
</picture>

<details>
<summary><b>Results in full</b></summary>

<br>

<!-- generated:pimen-results by tools/gen_readme_assets.py --write-readme; edit the generator, not this block -->
Real data, TESS SPOC sector 1 of pi Men (TIC 261136679), the three Probes plus the two Sentinels (Skeptic and Volunteer, on Claude via the CLI), as stored in `runs/tess-pi-men-s1`:

* 7 consensus dips: 6 passed vetting, 1 of them flagged `off_ephemeris`, and 1 failed it (`low_snr`, `off_ephemeris`).
* 5 of them lie on the published pi Men c ephemeris. 5 of the 5 predicted epochs in the 26-day window are recovered, with a mean timing offset of −8 minutes against the NASA Exoplanet Archive value (docs/results/pi_men_crossmatch.json).
* **Transit shape, limb-darkened fit** (re-vetted from the stored classifications; see
  [docs/results/pi_men_validation.md](docs/results/pi_men_validation.md)). A joint fit of
  the 5 epochs, with the period free near the BLS period (6.2680 ± 0.0005 d; Huang: 6.26790 d), gives the like-for-like quantities first: **Rp/R★ = 0.0179 ± 0.0017 (1.05 against Huang et al. 2018) and T14 = 3.07 ± 0.17 h (1.04)**. The mid-transit depth of the limb-darkened model is 292 ± 8 ppm (0.97 against Huang's published 300 ppm, which is defined by that paper, not by this model). The box measure it replaces gave 0.81 in depth and 0.64 in duration. Errors are conservative: the covariance plus the spread along the impact-parameter profile.
* **The impact parameter needs the star.** Free, 5 TESS transits give only b < 0.87 (1σ), so a/R★ and ρ★ are ranges (ρ★ 0.28 to 2.2 g/cm³ at 1σ, consistent with the TIC's 1.02). With the TIC density as a Gaussian prior (1.02 ± 0.20 g/cm³), the fit gives b = 0.64 ± 0.12, a/R★ = 12.85 (1σ 11.5 to 13.6) and T23/T14 = 0.95, against Huang's 0.59, 13.38 and 0.95. The fit is U-shaped, not V-shaped.
* The periodic signal's false-alarm probability is below 10⁻⁴ in both subjects. No one of 10,000 block-bootstrap trials reached the observed SNR, so 10⁻⁴ is a bound, not a value. The null maxima are committed in `runs/tess-pi-men-s1/fap_null/`; a Gumbel fit to them, stored as `fap_tail`, puts the tail below 10⁻⁶ (indicative only, see below).
* The passed dip at BTJD 1348.9 (0.87 h, SNR 9.5) does not fit the ephemeris and is a likely false positive. It is kept and flagged, not hidden.
* The dip at BTJD 1348.4 (SNR 6.7) failed vetting and stays in the stored candidates with its flags.
<!-- /generated:pimen-results -->

The stored run was made with pre-fix code (before the deep-dip clipping fix in Honest limits), which does not
affect a 300 ppm transit. Extended vetting, the reduced FPP and the export on the same run:

* **Extended and pixel-level vetting** (`scripts/vet_pi_men_s2.py`, real SPOC sector-1 files; see
  [docs/results/pi_men_s2_vetting.md](docs/results/pi_men_s2_vetting.md)). On the joint fit of all five epochs
  (P = 6.26795 ± 0.00049 d, T14 = 3.09 ± 0.16 h), on the light curve re-detrended in two passes with the transits
  and phase 0.5 masked (window 1.55 d, 12 T14; the first pass's strongest dip is not significant, so it is not
  masked): CROWDSAP 0.9997, FLFRCSAP 0.980 (not crowded); the strongest dip at any phase away from the transit is
  42 ± 7 ppm at phase 0.622 (5.6σ nominal), against a calibrated threshold of 6.9σ (5.16 times the scan's robust
  spread of 1.33), with 86% of it from one epoch; at phase 0.5, −12 ± 7 ppm. Odd/even depths from per-epoch fits
  agree (301 ± 14 against 311 ± 12 ppm, 0.5σ); the five mid-times fit a linear ephemeris (χ² = 1.9 for 3 dof,
  p = 0.59, O−C within 1.8 min) with no odd/even timing offset (0.5σ). No flag at the run's own setting, but **the
  secondary is at the threshold and its flag depends on the setting**: of 12 nearby run settings (detrend window 1
  or 2 d × bins of 2, 6, 10, 15, 20 and 30 minutes, each through the full two-pass preparation) 3 flag
  `secondary_any_phase`: 15- and 30-minute bins with the 1.55 d vetting window, and 30-minute bins with 2 d; there
  the dip, at phase 0.64, reaches 1.05–1.2 times the threshold, and in the first two the first pass already finds
  it significant. The other 9 do not flag it: 0.68–0.93 of the threshold, or not periodic (with 20-minute bins
  and the 1.55 d window a dip at phase 0.74 reaches 1.05 times the threshold, 90% of it from one epoch). The
  previous code, which masked the strongest first-pass dip whether or not it was significant, raised the default
  setting's dip from 5.6σ to 7.0σ and flagged 8 of 15 settings, including every 6- and 15-minute bin with a window
  up to 1.5 d (the reviewer's measurement). These are not independent trials: every run window up to 12 T14
  collapses to the same 1.55 d vetting window, so the 12 settings are 2 distinct vetting windows (1.55 and 2 d) × 6
  bin sizes, all on the same data (the reviewer's 15-setting grid, windows 0.75–2 d × 3 bin sizes, is 6 distinct
  settings for the same reason).
* **No reduced FPP for pi Men c: it is not stable.** Across the pipeline's five detrending settings (the default,
  and windows ×0.75 and ×1.5 with masks of 1.0 and 2.0 T14) under two noise models, the FPP ranges from 0.0079 to
  0.093 (median 0.0086 at the robust spread; it was 0.008–0.62 before the null's tail was smoothed): refused
  (odds spread 12.9×; 10× allowed), a narrow margin; the label is "not validated: no contrast curve". One setting
  (window ×0.75, mask 2 T14) carries the high end. On a wider grid (absolute windows 0.75–2 d × masks 1.0, 1.5 and
  2.0 T14) the secondary scan passes the white-noise gate on 6 of 15 settings and fails it on 9 (FPP 0.007–0.16
  where it passes), and the largest brightening ranges from 2.6 to 6.2σ with the setting: the 5.8σ brightening once
  quoted for the default setting is not robust, and neither is a single FPP. The earlier quotes (0.0082 here, 0.17
  and 0.0074 before) each came from one setting.
  NFPP would be 0 (every TIC neighbour within 150″ would need an eclipse deeper than 100%, one of them only
  marginally). pi Men c is a published planet with a measured mass; this shows the scheme's limits on real data.
* **Ephemeris cone.** Exporting the stored run (`setuhq export runs/tess-pi-men-s1 --allow-unchecked`; the
  archive's TOI table timed out, HTTP 504) gives one signal, P = 6.2681 ± 0.0012 d from the first subject's joint
  fit, and its predicted transit in October 2026 (epoch 479) carries σ = 13.8 h, a 3σ window of 86 h. A one-subject
  ephemeris is stale within a few years, as ATLAS G5 warns. With the TOI table, this signal is TOI 144.01 and is
  excluded as a duplicate (tested with the published ephemeris).
* **The difference-image centroid of pi Men is not usable, and SetuHQ says so.** The PSF fit puts the difference
  image 2.05 px (40.1″) from the catalogue position, mostly in the row coordinate (row −1.91 px, column −0.74 px),
  which is the direction charge bleeds along a CCD column. SPOC's own DV report for TOI 144.01 finds the same size and
  direction: 40.5″, row −2.07 px, column 0.02 px, with a DV quality metric of 0.58, below DV's 0.7 reliability cut.
  pi Men (Tmag 5.1) is saturated: five pixels of one column sit on a plateau within 5% of the
  peak, a bleed trail. A transit shortens the trail instead of dimming a PSF, so the "offset" is the trail's end.
  The fit says so too: the difference-image PSF collapses to its 0.3 px width bound, 3.4 times narrower than the
  out-of-transit one. SetuHQ flags `saturated` and `centroid_unreliable` and raises no `centroid_offset`. The
  per-cadence centroid motion test sees no shift (0.1σ), but on a saturated star that carries no information
  either: the flux-weighted centroid of a clipped bleed trail need not move when the star dims. Of 56 TIC stars
  within 150″, all but the target would need an eclipse deeper than 100%; the nearest, TIC 261139071 (Tmag
  14.0 ± 0.75, 27″), needs 111%, which is marginal: within 3σ of its Tmag uncertainty.

<!-- generated:sentinel-results by tools/gen_readme_assets.py --write-readme; edit the generator, not this block -->
**What the Sentinels did in this run, read from the stored classifications:**

* On the first subject (BTJD 1325.3 to 1338.3), Sentinel · Volunteer marked the dips at 1325.50, 1331.77 and 1338.05 and labelled the subject `potential_planet` (confidence 0.8); Sentinel · Skeptic marked the dips at 1325.50, 1331.77 and 1338.05 and labelled the subject `potential_planet` (confidence 0.7).
* On the second subject (BTJD 1338.3 to 1351.3), Sentinel · Volunteer marked the dips at 1344.27 and 1350.57 and labelled the subject `potential_planet` (confidence 0.4); Sentinel · Skeptic marked the dips at 1344.27 and 1350.57 and labelled the subject `potential_planet` (confidence 0.7). Neither marked the dip at 1348.38 (rejected by vetting) or the dip at 1348.94 (passed but off the ephemeris).
* In the consensus each Sentinel carries weight 0.5, against 0.4 to 0.6 for the Probes: the Sentinels are voices in a calibrated panel, not the whole panel.
<!-- /generated:sentinel-results -->

**Blind benchmark on real TOIs** (pre-fix code; measured on a stated benchmark, not discoveries; see
[docs/results/benchmark_real_tois.md](docs/results/benchmark_real_tois.md)). 662 TOIs from the NASA
Exoplanet Archive TOI table (fetched 2026-10-19, seed 20261019): 300 CP/KP, 300 FP and 62 FA, one per
star, split into halves by star. Each star's first SPOC 2-minute sector goes through the Probes panel,
along with a flux-inverted and a block-scrambled copy as false-alarm controls. Held-out half, with Wilson
95% intervals:

<!-- generated:benchmark-results by tools/gen_readme_assets.py --write-readme; edit the generator, not this block -->
* **Completeness: 57% (86 of 150 CP/KP on searchable stars; 49 to 65%).** It is 80% above 8 R⊕, 36% at 4 to 8 R⊕, 23% at 2 to 4 R⊕ and 10% below 2 R⊕. In the bins the published references use: all radii: 57% (86/150; 49 to 65%) against Kepler Robovetter DR25's > 85% (vetting only, on detected TCEs, P < 100 d); 3 to 4 R⊕: 44% (4/9; 19 to 73%) against Planet Hunters TESS's 51% (a citizen-science search); above 4 R⊕: 75% (77/102; 66 to 83%) against Planet Hunters TESS's 85% (a citizen-science search). SetuHQ is below the Kepler Robovetter's completeness and Planet Hunters TESS's rate above 4 R⊕ (each interval excludes the reference); consistent with Planet Hunters TESS's rate at 3 to 4 R⊕ (9 stars: the interval includes it).
<!-- /generated:benchmark-results -->
* FP TOIs: the panel found the dip of 77% and rejected or flagged 68% of those as binary-like.
  This applies to FP stars with 2-minute data only (124 of 158). FP TOIs are far more often
  FFI-only, so this is not reliability on the whole FP list.
* **The live feed's "new" signals are consistent with noise.** On the controls, the feed's own
  admission rule passes 55 (inverted) and 65 (scrambled) false signals per 1,000 star-sectors.
  That is about 13 per 100 targets reviewed, against 15.8 per 100 on the live feed (3 over 19
  targets).
* **The fix, pre-registered and tested once.** The feed now requires the signal in both reviewed
  sectors (periods within 0.5%) and a FAP below 0.001 over 2,000 trials. The rule was chosen on the
  tuning half and committed (8909cda) before one held-out evaluation (pre-fix code, like the benchmark).
  Held-out results, measured with the discovery config, old rule to new rule:
  * noise from the controls: 23.0 (95% CI 18.6–28.0) to 6.1 (4.0–9.4) false signals per 100 targets;
  * feed-level completeness: 39% to 17%;
  * FP TOIs kept out: 73% to 94%.

  Noise drops about fourfold, but 6 per 100 targets is still far above the 0.3 new signals per 100
  that real light curves give. The feed is still dominated by false alarms, and an admission is a
  lead for human or follow-up review, not a candidate of any confirmed status. Re-run under the new
  rule, the live feed's 19 targets keep 0 of the 3 earlier new signals and admit 2 known TOIs.
* The Sentinels on a stated subsample of 40 held-out stars: each persona marked 50% of the CP/KP
  dips and 20% of the FP dips as potential planets. They agree on 38 of 40 stars (φ = 0.89):
  one model, so one correlated voter.

Injection-recovery benchmark for the Probes (pre-fix code, see Honest limits):
[docs/results/injection_recovery_simulated_panel.md](docs/results/injection_recovery_simulated_panel.md).
The Sentinels are not in the benchmark. Each injected subject would need its own CLI
call, so the Sentinels are calibrated separately on a small sample (10 injected and 10
empty subjects: weight 0.5 each, against 0.4 to 0.6 for the Probes).

</details>

<details>
<summary><b>Continuous search and what it can claim</b></summary>

<br>

The search, `setuhq discover` (the command keeps its name), runs one batch of TESS targets. It rotates through the TOI host list
so coverage advances each day, reviews the two latest sectors of each target, and keeps
every new dip in a deduplicated catalogue. A dip is `known_toi` when it matches a
published TOI period, and `new_candidate` otherwise.

- [`.github/workflows/discover.yml`](.github/workflows/discover.yml) runs a batch every six hours
  on the self-hosted runner, commits the catalogue, and deploys the site. Claude's API reviewer
  runs when the `ANTHROPIC_API_KEY` secret is set.
- [`scripts/improve.py`](scripts/improve.py) sweeps panel thresholds on injection benchmarks.
  It promotes a setting only if it wins on a held-out seed. Every trial is in the threshold sweep,
  [docs/threshold_sweep.md](docs/threshold_sweep.md), including losers. This synthetic sweep is not the
  real-TOI leaderboard (see [Leaderboard and methods paper](#evidence)).

**Measured false-alarm rate.** Under the earlier rule (FAP < 0.01 over 200 trials, one sector),
light curves with every signal destroyed passed about 13 noise signals per 100 targets. The live
feed showed 15.8 `new_candidate` signals per 100 targets, so its "new" signals were consistent
with noise (see [the benchmark](docs/results/benchmark_real_tois.md)).

The feed now requires the signal in both reviewed sectors and a FAP below 0.001 over 2,000 trials.
That rule was chosen on the tuning half, pre-registered, and evaluated once on the held-out half
([validation](docs/results/feed_rule_validation.json)). It lowers noise about fourfold, from 23.0
(95% CI 18.6–28.0) to 6.1 (4.0–9.4) per 100 targets, and roughly halves completeness (feed level,
39% to 17%). Noise still outweighs the real new signals by far (about 6 per 100 targets against
0.3), so the feed's admissions are leads for human or follow-up review.

Re-run under the new rule (the TOI table was the copy cached on 2026-10-19, because the Archive
returned HTTP 526), the 19 live targets keep 0 of the 3 earlier new signals. The earlier catalogue
is kept in [docs/discoveries/catalog_v1_fap200.json](docs/discoveries/catalog_v1_fap200.json).

**What this can and cannot claim.** Every entry is a candidate. A detection here means the
pipeline saw a vetted dip that matches no published ephemeris. It does not mean a planet has
been found. Confirmation needs radial velocities, ground-based photometry, or the
community's TESS follow-up. The pixel-level centroid test is new, off by default and unusable on saturated
stars, so blended eclipsing binaries can still survive vetting. The claim this project can defend is a reproducible,
calibrated search with open provenance. It is not a claim of new planets or of beating
published pipelines.

</details>

<details>
<summary><b>Leaderboard and methods paper</b></summary>

<br>

* **The real-TOI leaderboard** ([docs/leaderboard/](docs/leaderboard/README.md), and `#/leaderboard` in the app)
  takes a method's detected events per star of the held-out half of the frozen 662-TOI benchmark, and scores them
  itself: completeness, FP rejection, control false alarms and reliability, with Wilson intervals. It ranks by
  Youden's J on the benchmark's searchable set with one predicate (a clean candidate) on both sides, so calling every
  TOI a planet scores zero, flagged or not, and ranks only entries measured on both controls; the 40-star Sentinel
  subsample is listed, never ranked. **A metadata-only floor that never reads a light curve is ranked too, and the
  benchmark cannot show that the Probes beat it**: a paired comparison over the same stars puts the floor ahead by a
  ΔJ whose interval includes zero (docs/leaderboard/leaderboard.md). `setuhq leaderboard my.json` scores a submission and refuses
  one that states anything but the hash of the tuning-half-only inputs or carries a field outside the whitelist.
  It is seeded with SetuHQ's own configurations, built from the benchmark's stored outputs
  (`scripts/leaderboard_seed.py`).
* **The methods paper draft** ([docs/paper/paper.md](docs/paper/paper.md), AAS/AJ style, Markdown) reports the
  benchmark with its negative results. Every number in it comes from the committed JSON through
  `scripts/paper_numbers.py`; results that later work will change are marked pending.

</details>

<details>
<summary><b>Everything that dims: the sweep and its catalogue</b></summary>

<br>

The planet search used to throw away every dip that was not a planet candidate. The sweep keeps them.
`setuhq sweep` works through a TESS sector's SPOC 2-minute targets and, for each star-sector, keeps every
consensus dip of the panel (whatever the panel's label), every brightening and the star's variability, and
classifies each by first-match rules in [src/setuhq/variables.py](src/setuhq/variables.py):

| Class | Rule (summary) |
|---|---|
| Systematic | a subject edge, a momentum dump, a scattered-light or pointing flag, or a data gap within 0.1 d; or the panel says instrumental |
| Eclipsing binary | odd/even mismatch or secondary eclipse; 30,000 ppm or deeper; V-shaped and 5,000 ppm or deeper; a stellar-density mismatch at P < 1 d; or the panel says binary |
| Pulsator or rotational variable | a Lomb-Scargle peak (Baluev FAP < 10⁻³ and a semi-amplitude ≥ 2× the binned scatter); a dip lasting ≥ ¼ of that period |
| Flare | ≥ 3 consecutive points ≥ 3σ above a running median, peaking ≥ 5σ (globally and locally), not on an instrumental cue |
| Planet candidate | passed vetting, potential planet by half the panel's weight, not off its star's own signal, and no rule above |
| Unclassified | everything else, with the reason |

Every entry keeps its confidence and the cues that decided it, its marks, its weights and the Sentinels'
own words, the light curve's sha256, the code fingerprint and config hash, and the name of whoever searched
it. Nothing is ever called confirmed. Every class is set against its own null on the same stars: the dip
classes against the flux-inverted copy (a real dip becomes a bump, though a real flare or pulsation maximum
becomes a dip, so this null is not empty of real signals), flares against downward events with the real dips
masked, and variability against a red-noise copy of the same star, an AR(1) process fitted to its own bins (a
periodogram is unchanged by flipping the flux, so the inverted copy is no null for it, and shuffling removes the
red noise that makes false peaks). The variability rule itself asks for a coherent period: the same best peak,
within 10%, in each half of the light curve. Each kind is compared with the same kind, and the star-sector is the
unit: dips cluster on a few stars, so the excess's 95% interval comes from a paired bootstrap over
star-sectors, beside McNemar's exact test on the star-sectors with events on one side only. A class exceeds
its null only when both agree; otherwise the site calls it "not distinguishable from noise in this slice".

```bash
setuhq sweep configs/sweep.toml --sector 1 --limit 200 --workers 3   # resumable; cached; polite to MAST
setuhq bundle my-sweep/sector_0005.json.gz --contributor "Your Name" --out bundle/
setuhq ingest bundle/ --attested-by <pr-author>   # sealed, not signed: re-searches every finding + max(3, 5%) by a nonce
```

The site reads `docs/sweep/catalogue.json`: the Overview's counter, #/variables (Catalogue › Everything that
dims, with filters, per-TIC pages and CSV/JSON export), the sweep layer on the Sky map, Mission Control's
telemetry and the search. Anyone can add a sector with their own Claude subscription or API key (kept in
their environment, never in a file) and be credited: see [CONTRIBUTING.md](CONTRIBUTING.md).

**First real slice (measured, Probes only).** TESS sector 1: the first 200 of its 15,898 SPOC 2-minute
targets in sweep order, all 200 searched (no download failures) by the search code of `0e87409` and classified
by the rules of this commit (each record's `search_code` and `classify_code`). The panel reviewed 936 consensus
dips (2,662 marks; 60 mark clusters fell below consensus), and the catalogue holds 1,011 entries. Each
comparison against its null on the same 200 star-sectors, kind for kind; the interval is the paired bootstrap
over star-sectors, and "real / null" star-sectors count those with at least one event:

| Comparison | Real | Null | Excess (95%) | Star-sectors real / null | McNemar p | In this slice |
|---|---|---|---|---|---|---|
| Pulsator or rotational variable (coherent periodogram peak) | 8 | 2 | +6 (0 to +12) | 8 / 2 | 0.11 | not distinguishable from noise |
| Eclipsing binary (dips) | 110 | 77 | +33 (−11 to +89) | 26 / 20 | 0.24 | not distinguishable from noise |
| Planet-candidate rule (dips) | 3 | 2 | +1 (−3 to +5) | 3 / 2 | 1.0 | not distinguishable from noise |
| Flare (brightenings) | 11 | 5 | +6 (−6 to +19) | 5 / 3 | 0.73 | not distinguishable from noise |
| Variable-star troughs (dips) | 10 | 17 | −7 (−18 to +1) | 3 / 4 | 1.0 | not distinguishable from noise |
| Systematic (dips) | 720 | 728 | −8 (−103 to +88) | 97 / 99 | 0.87 | not distinguishable from noise |
| Systematic (brightenings) | 22 | 25 | −3 (−42 to +27) | 11 / 6 | 0.23 | not distinguishable from noise |

**No class exceeds its null in this slice.** Two earlier versions of this table claimed one did, and both
claims were wrong:
- The eclipsing-binary claim counted dips as independent events. Two stars supply about a third of them, and
  star by star the excess is not distinguishable from zero.
- The variable-star claim used a periodogram rule that red noise also passes, against a shuffled null that had
  lost the red noise. Of the 36 peaks that pass the FAP and amplitude rule, 8 have a coherent period, the same
  best peak in each half of the light curve (1.0 to 2.7 d). 20 are longer than a half can test, 5 sit at the
  edge of the period grid, and 3 wander between halves; those 28 are now unclassified, with the reason. The
  null is now a red-noise copy of each star, through the same rule.

Six eclipsing-binary entries of the variability kind have no null of their kind and are not compared. The 3
entries that pass the planet-candidate rule (none matching a known TOI) are about what noise alone gives, so
the site does not present them as candidates. Of the 11 flares, 8 rise faster than they decay and 2 the other
way (1 equal). The slice finds no planet, and every class needs many more stars before an excess could show.
FAP trials are off in the sweep (50 trials cost about two minutes a star), and the stellar parameters come from
each file's header. Records: [docs/sweep/sector_0001.json.gz](docs/sweep/sector_0001.json.gz) and
[docs/sweep/catalogue.json](docs/sweep/catalogue.json).

*Provenance of this slice.* The records were searched again at `0e87409`, then reclassified once on this
commit, from the cached files and stored runs, for the coherence rule and the red-noise null. Each record's
`reclassifications` lists that step and its rule changes. The earlier records are in the history of
`docs/sweep/`: searched at `b8647ad`, reclassified at `3c5862e` for two bugs (a flare whose equal rise and decay
read as a fast rise, and two brightenings within 0.01 d that shared an id), and at `1eb9a6f` for the
short-period density rule and the per-class nulls.

One fix after the re-search: the stored run directories still held the earlier search's classifications, and
the first count of marks included them (5,358). The consensus, entries and nulls used only this search's.
`n_marks` was recounted from this search's own classifications (each record that changed says so in
`n_marks_note`). Eight star-sectors searched again in clean directories, including every one with a planet
candidate, reproduce their records exactly. The sweep now clears a star's run directory before searching it.
A resume reuses a stored record only when its config hash, search code and classification code all match. The
catalogue counts one search per star-sector, the latest, and keeps earlier searches as provenance only.

*Data size.* Records are one gzip file per sector (`sector_NNNN.json.gz`, 0.47 MB for these 200 stars; the
catalogue the site fetches is 1.7 MB), so a full sector would be about 37 MB of records. Past a few sectors,
the records would live outside the repository as release assets, with a committed manifest of their sha256
that the site build checks. The catalogue would then hold only the entries and coverage, not the per-star
events and nulls. That second step is not built yet.

</details>

<details>
<summary><b>Honest limits</b></summary>

<br>

* **The Sentinels are calibrated on a small sample only.** The full benchmark needs many
  CLI or API calls. See the calibration file for the sample size used.
* **Synthetic results are not sky results.** The benchmark uses white plus red noise. It
  measures the pipeline's logic, not real completeness.
* **The CHEOPS column mapping is unverified.** The loader accepts several candidate
  names and records the ones used. Check them against a real `SCI_COR_Lightcurve` file.
* **Transit fits are light-curve fits.** Every consensus dip gets a limb-darkened fit (Claret
  2017 TESS coefficients from the TIC's Teff and log g) with depth, T14, impact parameter and
  mid-time with errors, a ρ★ consistency check and a V-shape test. On a periodic signal the
  period is fitted too, near the BLS period, so an approximate search period does not smear
  the epochs. With a few TESS transits the impact parameter, and so a/R★ and ρ★, is poorly
  constrained: b is then printed as an upper limit and ρ★ as a range, and a second fit with
  the TIC density as a prior is stored beside the free one. The density band (0.3 to 3
  times the catalogue value, at 3σ) is illustrative, not a published threshold.
* **False-alarm probabilities are bounded by the trials.** A FAP is (k + 1)/(N + 1) over N
  block-bootstrap trials, and is never printed below 1/(N + 1). The stored pi Men run uses
  10⁴ trials, the search batches 2,000 (stopped once 2 trials reach the signal's SNR), and the
  library default 20. The feed's FAP < 0.001 rule passes at k ≤ 1 of 2,000, which by itself still
  admits about N/1,000 noise signals across N targets. The two-sector part of the rule is what
  removes most of the rest. A Gumbel fit to the null
  maxima is stored with each candidate (`fap_tail`, with `fap_exceed` and `fap_method`). It
  is indicative, extrapolated beyond the trials and conservative (BLS maxima are
  lighter-tailed than Gumbel), and it is never given below 10⁻⁶.
* **Pixel-level vetting is new and limited.** The difference-image centroid uses a circular Gaussian in place of
  the SPOC pixel response function, and its flag is tested against the catalogue position with a systematic floor
  equal to the out-of-transit fit's own offset from that position, which makes it insensitive below a few tenths of a
  pixel. On synthetic TPFs whose PSF is the same Gaussian (the ideal case) it localises a neighbour's eclipse 1.5
  to 3 px away to within 0.002 px (15 cases), and a planet on the target stays below 0.2σ (10 cases). With an
  elongated PSF (8 geometries 1.5–3 px away, 2 seeds each) the model error dominates: the neighbour is placed up to
  1.10 px off at 1.6:1 (median 0.36), 2.15 px at 2:1 (median 0.72) and 2.30 px at 2.5:1 (median 0.95). The binary is
  still flagged in every case at 1.6:1 and 2:1; at 2.5:1, 2 of the 8 geometries are marked unreliable instead (both
  seeds), and the rest flagged. The planet on the target is never flagged (3 seeds per ratio). It has not yet been benchmarked on real false positives (ATLAS S2 asks for Kepler
  `koi_fpflag_co` KOIs and TESS FP TOIs). Saturated stars, like pi Men, get no usable centroid. The neighbour table's
  flux shares use the same Gaussian; an exclusion within 3σ of the star's Tmag uncertainty is reported as marginal.
* **The secondary search is calibrated on white noise.** Its threshold is the white-noise 99.9% quantile of
  (largest dip)/(robust spread) for the scan's number of positions, times max(1, the scan's robust spread); on 3000
  clean simulated planets it flagged none (95% CI 0–0.12%; the 2 once quoted predate the max(1, ·) floor), against
  87 (2.9%) for the rule it replaced and 681 (23%) for a plain 3 × robust spread (`scripts/calibrate_secondary.py`,
  `docs/results/secondary_calibration.json`). On red-ish noise (robust spread 1.7) it flagged 2 in 1000 with seeds
  700000–700999 (the reviewer's run: 0 in 1000). Through the full two-pass preparation, on 600 clean planets at
  10-minute cadence with 270 ppm white plus 100 ppm red noise (the reviewer's seeds), 2 were flagged, against 1 with
  one pass; the second pass lifts the strongest dip by +0.03σ at the median. The previous code, which masked the
  strongest first-pass dip every time, protected the largest noise dip from the trend: 8 of 600 flagged and +0.57σ
  (the "1 of 300" quoted for it was wrong). The second pass now masks phase 0.5 always and that dip only when the
  first pass already finds it significant. The detrending used to cost sensitivity, not the threshold: with only
  the transits masked, the trend absorbed about half of a secondary (134 of ~180 ppm kept), and a 1000/200 ppm
  binary at 600 ppm per 2-minute point was flagged 10 times in 20; with phase 0.5 masked, 161 ppm is kept and 19 of
  20 are flagged (1500/300 ppm at 1000 ppm noise: 5 → 18 of 20). An eccentric secondary below the threshold in the
  first pass is not protected: at phase 0.62, 1000/200 ppm is flagged 13 times in 20 (12 with one pass; 18 when every
  first-pass dip was masked). Not built, future work: recovering those with a lower first-pass threshold for the
  mask together with a second-pass threshold calibrated by simulating that exact two-pass procedure. Long transits used to break the masked detrending (a 1-day quadratic across a 3 T14
  mask extrapolated by 10⁴–10⁶ ppm at 7–10 hours); the trend is now interpolated across the mask and the vetting
  window is at least 12 T14, so in vetting `detrend_window_days` has no effect below that (1.55 d for pi Men c).
* **The reduced FPP is checked for stability.** It is computed on the default detrending and four variants (window
  ×0.75 and ×1.5, masks 1 and 2 T14; a variant whose masks leave less than half the points beside a masked span is
  left out) under two noise models (the scan's robust spread and its std without the strongest dip, never below the
  nominal σ/√n). Above 0.5 on every one, the class is "likely false positive"; otherwise the odds may vary by at most
  a factor of 10 or no FPP is given, and a range across 0.015 or 0.5 is "undetermined". Its no-secondary likelihood
  is the simulated null distribution (the earlier max-of-N model charged a clean planet for an unusually small
  strongest dip: FPP up to 0.97), with an exponential tail fitted above its 99th percentile (fewer than 40 of 40,000
  simulated scans lie beyond z = 5.1). Measured through the vetting path: clean planets with white noise 0 of 150
  refused (10-minute cadence; most are "undetermined", their range straddling 0.015), and 0 of 36 with 6–12 hour
  transits (the 10-hour dozen re-run on the final code), against 7% and about 1 in 6 in the review; with red noise
  refusals remain, about 3% (the reviewer measured 5 of 150 on 2d268cb); simulated binaries "likely false positive" 19 of 20 (1000/200 ppm), 17 of 20
  (1500/300 ppm) and 13 of 20 (1000/200 ppm at phase 0.62), where 15–16 of 20 used to be refused as unstable.
* **Validation is not done.** TRICERATOPS 1.1.0 installs with pip (extra `validate`), but its `target()` queries
  MAST, Gaia and TESSCut on construction, so it cannot run offline, and MAST's API was failing when this was built:
  the adapter (`validate.run_triceratops`) is tested against a stub only and has not been run on a real target. The
  reduced FPP that runs instead is a documented approximation: its scenario priors are a choice (a 25%
  false-positive total after Guerrero et al. 2021), it ignores unresolved companions and background stars, and
  without a reliable centroid it cannot tell a target from a neighbour that could host the depth. No contrast curves
  are ingested yet.
* **Batch mode is tested offline only.** Resumability, retries and caching are tested with synthetic light curves;
  no real batch was run because MAST's search API was failing (2026-10-19), so no real throughput is reported.
  The CTOI export has not been compared with ExoFOP's live form.
* **Two fixes change default results (pass/fail included).** (1) Until commit 5a03087, `preprocess.clean` removed
  every point more than 10 times the point-to-point scatter below a 0.5-day running median, so an eclipse or transit
  deeper than that (a 3% binary, a 1% hot Jupiter on a quiet star, 5000 ppm at 300 ppm noise) vanished before the
  panel saw it. A low outlier is now removed only when it is not part of a dip: a run of at least
  max(3, 20 minutes / cadence) cadences more than 3σ below the median (hysteresis, so a 10–12σ eclipse whose points
  straddle the clip keeps them all). The upward clip is unchanged. (2) With deep dips now reaching vetting, `vet.py`'s
  `odd_even_mismatch` failed 6 of 10 clean 1% hot Jupiters: box depths of a deep transit scatter far beyond white
  noise. Its errors are now inflated by the per-epoch depths' scatter about their parity means and carry a 2%
  systematic floor. Results made before these fixes are labelled "pre-fix code": the stored pi Men run and every
  page built from it, the discovery catalogue, the injection-recovery benchmark, the real-TOI benchmark (and so the real-TOI leaderboard and the methods
  paper's numbers, which read it), the threshold sweep and the
  calibration record (`reviewer_weights_full_panel.calibration.json`; the weights files themselves are plain
  reviewer-to-weight maps and cannot carry a note). pi Men c (300 ppm, about 1.5 times the 2-minute scatter, and
  no odd/even failure) is affected by neither. A consequence of (2): a simulated eccentric binary (0.8% primary,
  0.4% secondary at phase 0.37) now passes default vetting, because its earlier `odd_even_mismatch` failures were
  spurious; each of its 8 events on the primary ephemeris is caught by `secondary_any_phase` (a flag, or a failure
  with `[vetting] decide = true`; its secondary eclipses, found as events of their own, are flagged `off_ephemeris`
  5 times and not at all once), and each of those 8 is classed "likely false positive" by the reduced FPP (above 0.5
  on every detrending setting; before the class-aware gate such binaries mostly read "FPP not computed: unstable",
  not "about 1"). The trade-off of (1): a real event deeper than 10σ that lasts under 20 minutes (an 18-minute eclipse
  at 2-minute cadence) is still removed as a spike.
* **Edge events are the weak spot** for both the statistics and the reviewers.
* **The coherent-variable rule is weak in red noise and blind to long periods.** It finds a 300 ppm
  sinusoid in strong red noise (AR(1), 600 ppm, 1-day correlation) only 3 times in 20 (and 20 in 20 in
  white noise; `scripts/variability_rule_check.py`, `docs/sweep/variability_rule_check.json`), and it
  cannot test periods longer than about 3.8 d in one sector, since each half of the light curve must show it
  (20 of the sector-1 slice's peaks are "coherence not tested" and stay unclassified).
* **Feed admissions are leads, not candidates of any confirmed status, and the feed is still
  dominated by false alarms.** Nothing on the search feed is a confirmed planet. Under the
  pre-registered two-sector rule, noise alone still gives about 6 false signals per 100 targets
  (held-out, 95% CI 4.0–9.4), far above the 0.3 per 100 that real light curves give. The rule
  also costs completeness (feed level, held-out: 39% to 17%).
<!-- generated:limits-completeness by tools/gen_readme_assets.py --write-readme; edit the generator, not this block -->
* **Real-TOI completeness is 57% on searchable stars** (held-out; 49 to 65%), below the Kepler Robovetter's completeness and Planet Hunters TESS's rate above 4 R⊕, and only 10% for planets below 2 R⊕. The FP measures cover only FP stars with 2-minute data, a population skewed away from the full FP list.
<!-- /generated:limits-completeness -->
* **Known bug in the code that produced the benchmark: preprocess clipping.** `preprocess.clean`
  removes every point more than 10× the point-to-point scatter below the running median, with no
  run-length test. Transits deeper than about 10× the per-cadence scatter therefore lose their
  in-transit points. In the held-out half, 27 CP/KP and 11 FP stars are exposed (depth more than 8×
  the scatter), and 3 CP/KP misses are explained by it. Completeness is 53% (65/123) with those
  stars excluded. The fix is now merged (see "Two fixes change default results" above), but the benchmark has
  not been re-run: its numbers, the leaderboard's and the paper's are still those of the pre-fix code. Only the
  affected stars will be re-run, and reported as an update.

</details>

## What it is / is not

| SetuHQ is | SetuHQ is not |
|---|---|
| a reproducible, calibrated transit search on public data | a source of confirmed planets |
| a blind benchmark with controls and a public leaderboard | a claim to beat published pipelines |
| an explorer of every known exoplanet, with sourced numbers | a replacement for follow-up observations |
| explainable: every verdict keeps its marks and reasons | a black box |

## Quick start

```bash
pip install -e ".[tess,dev]"         # add ,claude for the API backend
pytest -q                            # offline tests (network- and slow-marked tests are deselected)

setuhq run configs/tess_pi_men_s1.toml --out runs/tess-pi-men-s1
setuhq rebuild runs/tess-pi-men-s1 configs/tess_pi_men_s1.toml   # re-vet from the stored classifications
setuhq report runs/tess-pi-men-s1 --out site --validation docs/results/pi_men_validation.md
setuhq calibrate configs/tess_pi_men_s1.toml --out weights.json
setuhq benchmark configs/benchmark_simulated_panel.toml --weights weights.json --out bench.md
setuhq export runs/tess-pi-men-s1 --out export   # CTOI-style table and predicted windows (refuses without the TOI check)
setuhq leaderboard my-method.json   # score a submission to the real-TOI leaderboard
setuhq sweep configs/sweep.toml --sector 1 --limit 20   # the everything-that-dims sweep (resumable)
setuhq-mcp --list-tools             # the MCP server (pip install -e ".[mcp]")
pytest -q -m network                 # live MAST download test
scripts/ci_local.sh                  # everything CI runs, plus the slow tests and the README check
```

Configs are documented in [configs/default.toml](configs/default.toml). Every value
that changes a result is in the config, and its hash goes into the manifest.

## Architecture

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/architecture-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="docs/assets/readme/architecture-light.svg">
  <img src="docs/assets/readme/architecture-light.svg" alt="SetuHQ's architecture, with counts read from the repository. Public data: exoplanet.eu (8,376 planets, fetched 2026-10-18); MAST (TESS SPOC light curves); TOI table (662 TOIs sampled with seed 20261019); Claret 2017 (TESS limb darkening); JWST (WASP-39 b spectrum, from Zenodo). Engine: 48 modules (one Python package, src/setuhq); Pipeline (preprocess, subjects, search, vet, transitfit); Scoring (aggregate, calibrate, benchmark_toi); Pages (report, app, galaxy, methods, mission). Reviewer panel: Sentinels (Claude by default; other providers supported and labelled); Probes (deterministic matched-filter detectors, seeded); Consensus (skill-weighted, calibrated). Surfaces: CLI, 18 commands (run, rebuild, calibrate, benchmark, discover, export, batch, sweep, bundle, ingest, check-sweep, dashboard, docket, app, crossmatch, plate, report, leaderboard); App (15 Methods chapters; Galaxy, Catalogue, Mission Control). Evidence: 724 tests (2 need the network, 4 are slow); pi Men c (checked against Huang 2018); Real-TOI benchmark (662 TOIs, with controls); Threshold sweep (7 trials, losers kept); Provenance (data, config and code hashes). Every candidate keeps its data hash, config hash, code fingerprint and every reviewer's marks; a run can be re-vetted without asking the reviewers again. Counts read from src/setuhq, the CLI and pytest --collect-only; data from docs/threshold_sweep.json, docs/results/exoplanet_map.json, docs/results/benchmark_real_tois.json (docs/threshold_sweep.json is the threshold sweep), commit 8dde211." width="100%">
</picture>

<details>
<summary><b>Repository layout</b></summary>

<br>

```
src/setuhq/
  lightcurve.py   container with provenance      loaders.py   TESS (MAST), CHEOPS FITS, CSV
  preprocess.py   clean, detrend, bin            subjects.py  blind-coded 13-day segments
  search.py       BLS and single-event search    vet.py       automatic vetting
  dvtests.py      DV-style light-curve tests      pixel.py     TPF difference images, centroids, neighbours
  validate.py     reduced FPP, TRICERATOPS adapter, validation labels
  ephemeris.py    propagation, uncertainty cone   exofop.py    CTOI-style export, predicted windows
  batch.py        resumable multi-target runs     leaderboard.py the real-TOI leaderboard
  injection.py    synthetic transits              calibrate.py skill-based reviewer weights
  aggregate.py    clustering and consensus       pipeline.py  end-to-end run
  benchmark.py    injection recovery             report.py    static HTML site
  store.py        SQLite and CSV export          config.py    TOML configs
  variables.py    everything-that-dims rules     starsearch.py one star-sector of the sweep
  sweep.py        resumable sector sweep         contrib.py   contribution bundles and ingest
  everything.py   #/variables, counter, Sky layer
  tools.py        the MCP tools' functions       mcp_server.py setuhq-mcp
  agreement.py    Sentinel agreement, effective number of voters
  reviewers/      simulated; Sentinels: sentinel.py (shared), claude (API), claude_code (CLI),
                  openai_compat (OpenAI and compatible endpoints), gemini
configs/          run configs                    scripts/     known-planet validation
docs/             research notes and results     site/        generated report
tests/            offline tests, plus network- and slow-marked tests
tools/            README figures (gen_readme_assets.py) and app screenshots (capture_site_shots.mjs)
skills/, commands/, .claude-plugin/   the Claude Code plugin    examples/  mixed-provider panel, example agent
```

</details>

## Contribute a sweep

Run SetuHQ on a TESS sector with your own Claude subscription or API key, send a sealed bundle in a pull
request, and get credit on every entry you bring: `setuhq sweep`, then `setuhq bundle`; a maintainer runs
`setuhq ingest`, which searches every finding again before it counts. The guide is
[CONTRIBUTING.md](CONTRIBUTING.md), and the sweep itself is under [Evidence](#evidence). Keys never go in a file or
a message: environment variables only.

## AI providers

*Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are
deterministic matched-filter detectors.*

**Only Claude has been benchmarked so far.** Every provider gets the same task, prompt, strict JSON schema,
validation and clipping, so a malformed or out-of-range answer cannot make a candidate on any of them. Each
review records the provider, the exact model id the API reported, the call time and the prompt version;
the cache key holds the provider, the model, the prompt and the image hash.

| `type` in `[[reviewers]]` | Provider | Key (environment only) | Install | Benchmarked |
|---|---|---|---|---|
| `claude_code` | Claude through the Claude Code CLI (subscription) | none: `claude` signed in | Claude Code | yes: 40-star subsample |
| `claude` | Claude through the Anthropic API | `ANTHROPIC_API_KEY` | `.[claude]` | not separately (same models as the CLI) |
| `openai` | OpenAI (Chat Completions, image input) | `OPENAI_API_KEY` | nothing (plain HTTPS) | no |
| `gemini` | Google Gemini (`generateContent`) | `GEMINI_API_KEY` | nothing (plain HTTPS) | no |
| `openai_compatible` | any endpoint by `base_url`: Ollama, vLLM, LM Studio, OpenRouter, Azure OpenAI | the variable named by `api_key_env`, or none | nothing (plain HTTPS) | no |

One panel can mix providers ([`examples/panels/mixed_providers.toml`](examples/panels/mixed_providers.toml):
Sentinel · Volunteer on Claude, Sentinel · Skeptic on OpenAI, a third on Gemini). Names stay
"Sentinel · *persona*"; the provider and model are shown beside them on the pages and stored in
`manifest.json`.

* **Missing key, SDK or CLI:** that Sentinel is skipped, and the manifest lists it with the reason.
* **Keys stay out of every record:** a `base_url` with `user:password@`, a fragment, a `;param`, a token-like
  path segment, a credential-named query parameter or a provider key's value is refused; an endpoint is
  recorded as scheme, host and port plus a hash of its path; a rejected key (401, 403, other 4xx but 429)
  fails at once instead of being retried; error bodies are redacted, base64 forms of the key included.
* **Cache:** the Anthropic API cache key now includes the provider, so answers cached by the `claude` backend
  before this change are asked once more; the Claude Code cache key is unchanged.
* **Weights are per provider and model.** A Sentinel not calibrated on its provider and model votes at the
  floor weight (0.05) and is labelled *uncalibrated* until `setuhq calibrate` measures it.
* **Why it matters:** the two Claude personas agree with φ = 0.89, so they are close to one voter.
  `scripts/benchmark_real_tois.py sentinels --panel <config>` runs any panel's Sentinels on the same
  40-star subsample (only where their keys are set) and the report adds the φ of every pair, to measure
  whether another model makes the panel more independent.

## AI assistant (MCP, agents)

[`setuhq-mcp`](src/setuhq/mcp_server.py) is an MCP server: your assistant runs SetuHQ's own code and
reads its stored results, instead of guessing them. Each of its 16 tools is a thin wrapper over a public
function ([`src/setuhq/tools.py`](src/setuhq/tools.py)), and every answer carries its provenance and
honesty labels. Stdio by default; `--http HOST:PORT` serves streamable HTTP for self-hosting.

> The server runs on your computer; nothing is sent to Ashforde OÜ. What an assistant finds with it is a
> candidate, not a discovery.

| Channel | Command | Requires |
|---|---|---|
| Install | `pip install -e '.[mcp]'` in a checkout, then `setuhq-mcp --list-tools` | Python 3.10+ |
| Claude Code | `claude mcp add setuhq -- /path/to/SetuHQ/.venv/bin/setuhq-mcp` | the install |
| Claude Code plugin | `/plugin install setuhq --marketplace ashfordeOU/SetuHQ` | `setuhq-mcp` on PATH |
| Claude Desktop, Cursor, VS Code, Codex CLI, Gemini CLI | snippets in [`docs/MCP-INSTALL.md`](docs/MCP-INSTALL.md) | the install |
| Remote (streamable HTTP) | `setuhq-mcp --http 8080` (localhost, read-only tools unless `--allow-writes`; no auth) | your own host |

| Tools | What they do |
|---|---|
| `search_catalogue`, `get_planet`, `get_star` | the exoplanet catalogue, as stored, with its source |
| `list_candidates`, `get_candidate` | a stored run's dips with full provenance and every reviewer's verdict |
| `vet_lightcurve`, `fit_transit`, `compute_fap` | BLS and vetting, the limb-darkened fit, the bounded FAP |
| `run_pipeline_csv`, `run_pipeline_tess` | the whole pipeline on a CSV or a TIC (Probes only unless asked) |
| `rv_semi_amplitude`, `transit_depth`, `microlensing_magnification`, `habitable_zone` | the Methods physics |
| `benchmark_results`, `sentinel_providers` | the stored benchmarks; which providers can run here |

The plugin adds slash commands over the tools (`/setuhq-vet`, `/setuhq-explain`, `/setuhq-sweep`,
`/setuhq-catalogue`, `/setuhq-physics`, `/setuhq-benchmarks`) and four skills in [`skills/`](skills/):
vet a TESS target, explain a candidate, run a sector sweep, submit to the leaderboard.
[`examples/agents/vet_agent.py`](examples/agents/vet_agent.py) is an **example** agent (Claude Agent SDK,
`.[agents]`) that vets one candidate end to end through the server: it logs every tool call and result to a
provenance file, runs read-only tools freely, asks before a pipeline run, and refuses anything
outward-facing. Its conclusions are candidates for a person to review, not discoveries.

## Editions

The whole of SetuHQ is open. Paid routes start with a message; there are no prices here.

| | Free | SetuHQ Pro | Custom study |
|---|---|---|---|
| What it is | all of open SetuHQ, no feature gate | a proprietary overlay on the same open engine, under contract | a study done for you, under contract |
| Licence | AGPL-3.0-only, or a commercial licence | proprietary | contract |
| Status | available | **planned, available on request** | on request |
| How to start | [quick start](#quick-start) or [setuhq.com](https://setuhq.com) | [request an evaluation](mailto:contact@ashforde.org?subject=SetuHQ%20Pro%20evaluation) | [request a study](mailto:contact@ashforde.org?subject=SetuHQ%20custom%20study) |

SetuHQ Pro will be a strict superset that depends on open SetuHQ and never forks it. It adds no
new science: every Pro number comes from the open pipeline, and nothing Pro produces confirms or
validates a planet. Directions under consideration, none of them built: hosted sweeps at scale,
private target lists and embargoed candidates, team workspaces, supported on-premises
deployment, and priority follow-up export.

## Research

The methods paper draft is [docs/paper/paper.md](docs/paper/paper.md) and the real-TOI leaderboard is
[docs/leaderboard/](docs/leaderboard/README.md). The injection threshold sweep, which is not the leaderboard, is in
[docs/threshold_sweep.md](docs/threshold_sweep.md); the research notes behind the Methods chapters are in
[docs/RESEARCH.md](docs/RESEARCH.md).

## Cite

A methods paper and a `CITATION.cff` come with the release. Until then, cite the repository and
the commit you used.

## Licence

Code: **AGPL-3.0-only** from the public release, or a commercial licence from Ashforde OÜ
(dual licensing, explained in `LICENSING.md` at release; the current `LICENSE` file is still MIT
and switches with it). Data, benchmark and paper: **CC BY 4.0**. “SetuHQ” and the Setu mark are
trademarks of Ashforde® OÜ; forks must use another name. The README's fonts (Geist, Geist Mono,
Unbounded) are under the SIL Open Font License.

<p align="center"><sub>SetuHQ · सेतु · the bridge — built by Ashforde OÜ. Sentinels run on Claude (Anthropic) by default; other providers are supported and labelled. Probes are deterministic matched-filter detectors.</sub></p>

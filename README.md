# exoplan

An open-source transit search in the style of [Planet Hunters CHEOPS](https://www.zooniverse.org/projects/bmerin/planet-hunters-cheops).
Where that project uses volunteers, exoplan uses a **reviewer panel**: the Sentinels and
the Probes, independent reviewers that mark dips in blind-coded light curves. No people
are on it. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter
detectors. Consensus is skill-weighted, and every candidate keeps its provenance.

Research behind the design: [docs/RESEARCH.md](docs/RESEARCH.md).
The site: [site/index.html](site/index.html) (the Overview) leads into the app at [site/app/](site/app/index.html) (Sky, Transit, Explorer, Sentinels); the full report for the real run is at [site/report/](site/report/index.html).

## What it does

1. **Ingests** TESS SPOC light curves from MAST, CHEOPS light-curve FITS files, or CSV.
2. **Cleans and detrends**: spike clipping, a masked local-quadratic baseline, and binning.
3. **Cuts blind-coded subjects**: fixed 13-day segments with opaque IDs. The target name never reaches a reviewer.
4. **Runs the panel**: every reviewer marks and labels every subject independently. The task is the Planet Hunters task: mark the start and end of each dip, then label `potential_planet` or `noise`.
5. **Aggregates** marks by single-linkage clustering, scores each dip by the share of skill-weighted reviewers who marked it, and requires the panel to call the subject a potential planet.
6. **Vets** each consensus event: SNR, duration, edge effects, odd/even depth, secondary eclipse, and fit to the periodic ephemeris.
   Extended tests after the Kepler/SPOC Data Validation suite add flags beside them (`dvtests.py`, `pixel.py`):
   SPOC crowding (CROWDSAP below 0.8 is `crowded`), a weak-secondary search at every phase with the fitted
   duration, odd/even depths with errors, per-epoch transit times (linear-ephemeris and odd/even timing tests), and,
   from the SPOC target pixel file, a difference-image centroid in pixels and arcseconds with its significance, the
   centroid motion test, a core/halo ghost check, momentum-dump coincidence, and a table of catalogued neighbours
   with the eclipse depth each would need. **By default these only add flags**: pass/fail is decided as before, so
   runs and benchmarks stay comparable with earlier ones. `[vetting] decide = true` makes `secondary_any_phase`,
   `odd_even_depth`, `odd_even_timing` and `centroid_offset` disqualifying, and lets the all-phase secondary search
   replace the phase-0.5 check. The pixel tests download TPFs and are off unless `[vetting] pixel = true`.
7. **Weighs false-positive scenarios** for every periodic candidate (`validate.py`): exoplan's own reduced FPP
   (planet, eclipsing binary at P or 2P, eclipse on a resolved neighbour), built from the S2 measurements with stated
   priors. It is not TRICERATOPS and never says "validated". "Validated (statistically)" is reserved for TRICERATOPS
   with FPP < 0.015 and NFPP < 10⁻³ *and* a high-resolution imaging contrast curve; without a curve every candidate
   is "not validated: no contrast curve". exoplan never calls its results confirmed.
8. **Writes** a candidate catalogue (CSV and JSON), a Zooniverse-shaped classification export, a SQLite store, a provenance manifest, and a static report site.
9. **Exports for follow-up** (`exoplan export RUN --out DIR`, `exofop.py`): an ExoFOP CTOI-style table (CSV and
   JSON) of vetted candidates that pass the S2 and S3 gates and duplicate no TOI on the same TIC, plus predicted
   transit windows for the next 12 months with the ephemeris uncertainty cone, σ(Tₙ)² = σ_T0² + n²σ_P² (+ 2n cov),
   the same propagation `match_toi` uses (`ephemeris.py`). **The CTOI field list is unverified against ExoFOP's
   current form** (ExoFOP was unreachable); it lives in one place, `exofop.CTOI_FIELDS`. A person submits CTOIs
   under their own ExoFOP account; exoplan does not. Without the archive's TOI table the export refuses unless
   `--allow-unchecked`, and then every row says the check was not done.
10. **Scales** with `exoplan batch CONFIG --targets FILE` (`batch.py`): the `discover` flow over any target list,
   with light curves cached in `cache/lightkurve` and a state file that makes a killed or time-limited session
   resumable (done targets are skipped, failures retried, a changed config starts afresh).

## Reviewer panel

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
(rejects binary and systematic signatures unless they are clear).

## Quick start

```bash
pip install -e ".[tess,dev]"         # add ,claude for the API backend
pytest -q                            # offline tests (one network-marked test is deselected)

exoplan run configs/tess_pi_men_s1.toml --out runs/tess-pi-men-s1
exoplan rebuild runs/tess-pi-men-s1 configs/tess_pi_men_s1.toml   # re-vet from the stored classifications
exoplan report runs/tess-pi-men-s1 --out site --validation docs/results/pi_men_validation.md
exoplan calibrate configs/tess_pi_men_s1.toml --out weights.json
exoplan benchmark configs/benchmark_simulated_panel.toml --weights weights.json --out bench.md
pytest -q -m network                 # live MAST download test
```

Configs are documented in [configs/default.toml](configs/default.toml). Every value
that changes a result is in the config, and its hash goes into the manifest.

## Results so far

Real data, TESS SPOC sector 1 of pi Men (TIC 261136679), the three Probes plus the two
Sentinels (Skeptic and Volunteer, on Claude via the CLI). The stored run was made with pre-fix code (before the
deep-dip clipping fix in Honest limits), which does not affect a 300 ppm transit:

* 6 consensus dips, 6 passed vetting, one of them flagged `off_ephemeris`.
* Five of them lie on the published pi Men c ephemeris. All five predicted epochs in the
  25-day window are recovered, with a mean timing offset of -8 minutes against the
  NASA Exoplanet Archive value.
* **Transit shape, limb-darkened fit** (re-vetted from the stored classifications; see
  [docs/results/pi_men_validation.md](docs/results/pi_men_validation.md)). A joint fit of
  the five epochs, with the period free near the BLS period (6.2680 ± 0.0005 d; Huang:
  6.26790 d), gives the like-for-like quantities first: **Rp/R★ = 0.0179 ± 0.0017 (1.05 against
  Huang et al. 2018) and T14 = 3.07 ± 0.17 h (1.04)**. The mid-transit depth of the
  limb-darkened model is 292 ± 8 ppm (0.97 against Huang's published 300 ppm, which is
  defined by that paper, not by this model). The box measure it replaces gave 0.81 in depth
  and 0.64 in duration. Errors are conservative: the covariance plus the spread along the
  impact-parameter profile.
* **The impact parameter needs the star.** Free, five TESS transits give only b < 0.87 (1σ),
  so a/R★ and ρ★ are ranges (ρ★ 0.28 to 2.2 g/cm³ at 1σ, consistent with the TIC's 1.02). With
  the TIC density as a Gaussian prior (1.02 ± 0.20 g/cm³), the fit gives b = 0.64 ± 0.12,
  a/R★ = 12.85 (1σ 11.5 to 13.6) and T23/T14 = 0.95, against Huang's 0.59, 13.38 and 0.95. The
  fit is U-shaped, not V-shaped.
* The periodic signal's false-alarm probability is below 10⁻⁴ in both subjects. No one of
  10,000 block-bootstrap trials reached the observed SNR, so 10⁻⁴ is a bound, not a value. The
  null maxima are committed in `runs/tess-pi-men-s1/fap_null/`; a Gumbel fit to them, stored
  as `fap_tail`, puts the tail below 10⁻⁶ (indicative only, see below).
* The sixth passed event (BTJD 1348.9, 0.87 h, SNR 9.5) does not fit the ephemeris and
  is a likely false positive. It is kept and flagged, not hidden.
* **Extended and pixel-level vetting** (`scripts/vet_pi_men_s2.py`, real SPOC sector-1 files; see
  [docs/results/pi_men_s2_vetting.md](docs/results/pi_men_s2_vetting.md)). On the joint fit of all five epochs
  (P = 6.26795 ± 0.00049 d, T14 = 3.09 ± 0.16 h): CROWDSAP 0.9997, FLFRCSAP 0.980 (not crowded); the strongest
  dip at any phase away from the transit is 41 ± 7 ppm at phase 0.74 (5.6σ), below the 7.1σ threshold and below
  the largest brightening (8.8σ), so no secondary; odd/even depths agree to 0.8σ; the five mid-times fit a linear
  ephemeris (χ² = 0.8 for 3 dof, O−C within 1.6 min) with no odd/even timing offset (0.4σ). No flags.
* **Reduced FPP for pi Men c** (same file): FPP = 0.0074 and NFPP = 0 (every TIC neighbour within 150″ would
  need an eclipse deeper than 100%, one of them only marginally), which by number alone meets the TRICERATOPS
  thresholds. The label is still "not validated: no contrast curve": the scheme is exoplan's, it leaves out
  unresolved companions and background stars, and its priors are illustrative. pi Men c is a published planet
  with a measured mass; this number shows the scheme's behaviour on a real planet, nothing more.
* **Ephemeris cone.** Exporting the stored run (`exoplan export runs/tess-pi-men-s1 --allow-unchecked`; the
  archive's TOI table timed out, HTTP 504) gives one signal, P = 6.2681 ± 0.0012 d from the first subject's joint
  fit, and its predicted transit in October 2026 (epoch 479) carries σ = 13.8 h, a 3σ window of 86 h. A one-subject
  ephemeris is stale within a few years, as ATLAS G5 warns. With the TOI table, this signal is TOI 144.01 and is
  excluded as a duplicate (tested with the published ephemeris).
* **The difference-image centroid of pi Men is not usable, and exoplan says so.** The PSF fit puts the difference
  image 2.05 px (40.1″) from the catalogue position, mostly in the row coordinate (row −1.91 px, column −0.74 px),
  which is the direction charge bleeds along a CCD column. SPOC's own DV report for TOI 144.01 finds the same size and
  direction: 40.5″, row −2.07 px, column 0.02 px, with a DV quality metric of 0.58, below DV's 0.7 reliability cut. pi Men (Tmag 5.1) is saturated: four pixels of one column sit on a plateau within 3% of the
  peak, a bleed trail. A transit shortens the trail instead of dimming a PSF, so the "offset" is the trail's end.
  exoplan flags `saturated` and `centroid_unreliable` and raises no `centroid_offset`. The per-cadence centroid
  motion test sees no shift (0.1σ). Of 56 TIC stars within 150″, all but the target would need an eclipse deeper
  than 100%; the nearest, TIC 261139071 (Tmag 14.0, 27″), needs 111%, which is marginal under the Gaussian PSF
  approximation.

**What the Sentinels did in this run, reported as found:**

* On the second subject, both Sentinels independently marked the two real
  epochs at BTJD 1344.3 and 1350.55 (about 6.2 days apart). They rejected the spurious
  1348.9 dip, with sound reasons.
* On the first subject, both Sentinels called the real epochs at BTJD 1325.5,
  1331.8 and 1338.05 "instrumental" edge ramps and missed them. The Probes found
  them. Those dips sit near the segment start and end, which is a known weak spot for
  a reviewer that reads edges as systematics. This is exactly why the Sentinels are
  voices in a calibrated panel, not the whole panel.

Injection-recovery benchmark for the Probes (pre-fix code, see Honest limits):
[docs/results/injection_recovery_simulated_panel.md](docs/results/injection_recovery_simulated_panel.md).
The Sentinels are not in the benchmark. Each injected subject would need its own CLI
call, so the Sentinels are calibrated separately on a small sample (10 injected and 10
empty subjects: weight 0.5 each, against 0.4 to 0.6 for the Probes).

## Continuous discovery

`exoplan discover` runs one batch of TESS targets. It rotates through the TOI host list
so coverage advances each day, reviews the two latest sectors of each target, and keeps
every new dip in a deduplicated catalogue. A dip is `known_toi` when it matches a
published TOI period, and `new_candidate` otherwise.

- [`.github/workflows/discover.yml`](.github/workflows/discover.yml) runs a batch every six hours
  on the self-hosted runner, commits the catalogue, and deploys the site. Claude's API reviewer
  runs when the `ANTHROPIC_API_KEY` secret is set.
- [`scripts/improve.py`](scripts/improve.py) sweeps panel thresholds on injection benchmarks.
  It promotes a setting only if it wins on a held-out seed. Every trial is in
  [docs/leaderboard.md](docs/leaderboard.md), including losers.

**What this can and cannot claim.** Every entry is a candidate. A detection here means the
pipeline saw a vetted dip that matches no published ephemeris. It does not mean a planet has
been found. Confirmation needs radial velocities, ground-based photometry, or the
community's TESS follow-up. The pixel-level centroid test is new, off by default and unusable on saturated
stars, so blended eclipsing binaries can still survive vetting. The claim this project can defend is a reproducible,
calibrated search with open provenance. It is not a claim of new planets or of beating
published pipelines.

## Honest limits

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
  10⁴ trials, the discovery batches 200, and the library default 20. The feed's FAP < 0.01
  rule with 200 trials passes at k ≤ 1 of 200: a cut at about 1% with Poisson slack, which
  across N targets admits about N/100 noise signals by construction. A Gumbel fit to the null
  maxima is stored with each candidate (`fap_tail`, with `fap_exceed` and `fap_method`). It
  is indicative, extrapolated beyond the trials and conservative (BLS maxima are
  lighter-tailed than Gumbel), and it is never given below 10⁻⁶.
* **Pixel-level vetting is new and limited.** The difference-image centroid uses a circular Gaussian in place of
  the SPOC pixel response function, and its flag is tested against the catalogue position with a systematic floor
  equal to the out-of-transit fit's own offset from that position, which makes it insensitive below a few tenths of a
  pixel. On synthetic TPFs (whose PSF is the same Gaussian, so this is the ideal case) it localises a neighbour's
  eclipse 1.5 to 3 px away to within 0.002 px (15 cases), and a planet on the target stays below 0.2σ (10 cases). It has not yet been benchmarked on real false positives (ATLAS S2 asks for Kepler
  `koi_fpflag_co` KOIs and TESS FP TOIs). Saturated stars, like pi Men, get no usable centroid. The neighbour table's
  flux shares use the same Gaussian, so a needed depth within a factor of two of 100% is reported as marginal.
  The light-curve significances use white noise (robust scatter over √n), so they are optimistic under red noise:
  on pi Men the largest brightening at any phase is 8.8σ.
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
* **Deep dips used to be clipped before review (fixed; this changes default behaviour).** Until commit 5a03087,
  `preprocess.clean` removed every point more than 10 times the point-to-point scatter below a 0.5-day running
  median, so an eclipse or transit deeper than that (a 3% binary, a 1% hot Jupiter on a quiet star, 5000 ppm at
  300 ppm noise) vanished entirely before the panel saw it. A low outlier is now removed only when fewer than
  3 consecutive cadences are below the threshold; the upward clip is unchanged. Results made before the fix are
  labelled "pre-fix code": the stored pi Men run, the injection-recovery benchmark, the leaderboard and the
  calibrated weights. pi Men c (300 ppm, about 1.5 times the 2-minute scatter) was not affected.
* **Edge events are the weak spot** for both the statistics and the reviewers.
* **Discovery candidates are unconfirmed.** Nothing on the discovery feed is a confirmed planet.

## Repository layout

```
src/exoplan/
  lightcurve.py   container with provenance      loaders.py   TESS (MAST), CHEOPS FITS, CSV
  preprocess.py   clean, detrend, bin            subjects.py  blind-coded 13-day segments
  search.py       BLS and single-event search    vet.py       automatic vetting
  dvtests.py      DV-style light-curve tests      pixel.py     TPF difference images, centroids, neighbours
  validate.py     reduced FPP, TRICERATOPS adapter, validation labels
  ephemeris.py    propagation, uncertainty cone   exofop.py    CTOI-style export, predicted windows
  batch.py        resumable multi-target runs
  injection.py    synthetic transits              calibrate.py skill-based reviewer weights
  aggregate.py    clustering and consensus       pipeline.py  end-to-end run
  benchmark.py    injection recovery             report.py    static HTML site
  store.py        SQLite and CSV export          config.py    TOML configs
  reviewers/      simulated, claude (API), claude_code (CLI)
configs/          run configs                    scripts/     known-planet validation
docs/             research notes and results     site/        generated report
tests/            offline tests, plus a network test marked "network"
```

## Development

Python 3.10 or later. MIT licensed. Tests run offline with `pytest`. CI runs the same
command on every push (`.github/workflows/ci.yml`). `scripts/ci_local.sh` runs the same
checks plus the site builds locally.

All workflows run on a self-hosted runner (`runs-on: [self-hosted, linux]`). Runners are
short-lived cloud sessions: `scripts/session_runner.sh` registers an ephemeral runner, serves
the queued jobs, and stops. It needs `EXOPLAN_RUNNER_PAT` in the session's environment: a
fine-grained token limited to this repository with "Administration: Read and write", which
is the minimum GitHub requires to register a runner.

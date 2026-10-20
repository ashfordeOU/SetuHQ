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
7. **Writes** a candidate catalogue (CSV and JSON), a Zooniverse-shaped classification export, a SQLite store, a provenance manifest, and a static report site.

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
Sentinels (Skeptic and Volunteer, on Claude via the CLI):

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

**What the Sentinels did in this run, reported as found:**

* On the second subject, both Sentinels independently marked the two real
  epochs at BTJD 1344.3 and 1350.55 (about 6.2 days apart). They rejected the spurious
  1348.9 dip, with sound reasons.
* On the first subject, both Sentinels called the real epochs at BTJD 1325.5,
  1331.8 and 1338.05 "instrumental" edge ramps and missed them. The Probes found
  them. Those dips sit near the segment start and end, which is a known weak spot for
  a reviewer that reads edges as systematics. This is exactly why the Sentinels are
  voices in a calibrated panel, not the whole panel.

**Blind benchmark on real TOIs** (measured on a stated benchmark, not discoveries; see
[docs/results/benchmark_real_tois.md](docs/results/benchmark_real_tois.md)). 662 TOIs from the NASA
Exoplanet Archive TOI table (fetched 2026-10-19, seed 20261019): 300 CP/KP, 300 FP and 62 FA, one per
star, split into halves by star. Each star's first SPOC 2-minute sector goes through the Probes panel,
along with a flux-inverted and a block-scrambled copy as false-alarm controls. Held-out half, with Wilson
95% intervals:

* **Completeness: 57% (86 of 150 CP/KP on searchable stars; 49 to 65%).** It is 80% above 8 R⊕,
  23% at 2 to 4 R⊕ and 10% below 2 R⊕. The references are Kepler's Robovetter (above 85%) and
  Planet Hunters TESS (85% above 4 R⊕, 51% at 3 to 4 R⊕).
* FP TOIs: the panel found the dip of 77% and rejected or flagged 68% of those as binary-like.
  This applies to FP stars with 2-minute data only (124 of 158). FP TOIs are far more often
  FFI-only, so this is not reliability on the whole FP list.
* **The live feed's "new" signals are consistent with noise.** On the controls, the feed's own
  admission rule passes 55 (inverted) and 65 (scrambled) false signals per 1,000 star-sectors.
  That is about 13 per 100 targets reviewed, against 15.8 per 100 on the live feed (3 over 19
  targets). A fix is proposed in the report and has not been applied.
* The Sentinels on a stated subsample of 40 held-out stars: each persona marked 50% of the CP/KP
  dips and 20% of the FP dips as potential planets. They agree on 38 of 40 stars (φ = 0.89):
  one model, so one correlated voter.

Injection-recovery benchmark for the Probes:
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

**Measured false-alarm rate.** On real light curves with every signal destroyed, the feed's
own rule admits about 13 noise signals per 100 targets reviewed. The live feed shows 15.8
`new_candidate` signals per 100 targets, so its "new" signals are consistent with noise (see
[the benchmark](docs/results/benchmark_real_tois.md)). The proposed fix is to require the signal
independently in both sectors reviewed and to use a stricter FAP. It is not applied: it must be
chosen on the tuning half and validated on the held-out half first.

**What this can and cannot claim.** Every entry is a candidate. A detection here means the
pipeline saw a vetted dip that matches no published ephemeris. It does not mean a planet has
been found. Confirmation needs radial velocities, ground-based photometry, or the
community's TESS follow-up. The pipeline also has no centroid or pixel check, so blended
eclipsing binaries can survive vetting. The claim this project can defend is a reproducible,
calibrated search with open provenance. It is not a claim of new planets or of beating
published pipelines.

## Everything that dims: the sweep and its catalogue

The planet search used to throw away every dip that was not a planet candidate. The sweep keeps them.
`exoplan sweep` works through a TESS sector's SPOC 2-minute targets and, for each star-sector, keeps every
consensus dip of the panel (whatever the panel's label), every brightening and the star's variability, and
classifies each by first-match rules in [src/exoplan/variables.py](src/exoplan/variables.py):

| Class | Rule (summary) |
|---|---|
| Systematic | a subject edge, a momentum dump, a scattered-light or pointing flag, or a data gap within 0.1 d; or the panel says instrumental |
| Eclipsing binary | odd/even mismatch or secondary eclipse; 30,000 ppm or deeper; V-shaped and 5,000 ppm or deeper; or the panel says binary |
| Pulsator or rotational variable | a Lomb-Scargle peak (Baluev FAP < 10⁻³ and a semi-amplitude ≥ 2× the binned scatter); a dip lasting ≥ ¼ of that period |
| Flare | ≥ 3 consecutive points ≥ 3σ above a running median, peaking ≥ 5σ (globally and locally), not on an instrumental cue |
| Planet candidate | passed vetting, potential planet by half the panel's weight, not off its star's own signal, and no rule above |
| Unclassified | everything else, with the reason |

Every entry keeps its confidence and the cues that decided it, its marks, its weights and the Sentinels'
own words, the light curve's sha256, the code fingerprint and config hash, and the name of whoever searched
it. Nothing is ever called confirmed. Each star is also run with its flux inverted, where nothing real can
dim, and the site shows that control's count beside every class.

```bash
exoplan sweep configs/sweep.toml --sector 1 --limit 200 --workers 3   # resumable; cached; polite to MAST
exoplan bundle my-sweep/sector_0005.json --contributor "Your Name" --out bundle/
exoplan ingest bundle/                                                 # refuses on any hash, code or rule mismatch
```

The site reads `docs/sweep/catalogue.json`: the Overview's counter, #/variables (Catalogue › Everything that
dims, with filters, per-TIC pages and CSV/JSON export), the sweep layer on the Sky map, Mission Control's
telemetry and the search. Anyone can add a sector with their own Claude subscription or API key (kept in
their environment, never in a file) and be credited: see [CONTRIBUTING.md](CONTRIBUTING.md).

**First real slice (measured, Probes only).** TESS sector 1: the first 200 of its 15,898 SPOC 2-minute
targets in sweep order, all 200 searched (no download failures). The panel reviewed 936 consensus dips
(2,696 marks; 60 mark clusters fell below consensus). The 1,011 entries are 742 systematic, 108 eclipsing
binary, 98 unclassified, 47 pulsator or rotational variable, 11 flare and 5 planet candidate. On the
flux-inverted copies of the same 200 star-sectors, where nothing real can dim, the same rules gave 783
systematic, 67 eclipsing binary, 124 unclassified, 60 variable, 32 flare and 3 planet candidates. So the 5
planet candidates (none matching a known TOI) are about what noise alone gives: none is a planet. Of the classes, only the
eclipsing-binary count (108 against 67) clearly exceeds its control. The rules did their job of keeping and
sorting everything; finding planets needs far more than 200 stars and Sentinels on the survivors. Records:
[docs/sweep/sector_0001.json](docs/sweep/sector_0001.json) and [docs/sweep/catalogue.json](docs/sweep/catalogue.json).
FAP trials are off in the sweep (50 trials cost about two minutes a star), and the stellar parameters come
from each file's header. After a fix to the flare rule, found by `ingest`'s re-check on this slice, the
entries were reclassified from the stored runs (`exoplan sweep --reclassify`); the reviewers and the
pipeline were not run again.

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
* **Vetting uses only light curves.** There is no centroid or pixel-level check, so
  blended eclipsing binaries can pass.
* **Edge events are the weak spot** for both the statistics and the reviewers.
* **Discovery candidates are unconfirmed, and the feed's false-alarm rate is measured to be high.**
  Nothing on the discovery feed is a confirmed planet. Noise alone gives about 13 `new_candidate`
  signals per 100 targets, close to the feed's observed rate (real-TOI benchmark).
* **Real-TOI completeness is 57% on searchable stars** (held-out; 49 to 65%), well below published
  vetters, and only 10% for planets below 2 R⊕. The FP measures cover only FP stars with 2-minute
  data, a population skewed away from the full FP list.
* **Known bug in the code that produced the benchmark: preprocess clipping.** `preprocess.clean`
  removes every point more than 10× the point-to-point scatter below the running median, with no
  run-length test. Transits deeper than about 10× the per-cadence scatter therefore lose their
  in-transit points. In the held-out half, 27 CP/KP and 11 FP stars are exposed (depth more than 8×
  the scatter), and 3 CP/KP misses are explained by it. Completeness is 53% (65/123) with those
  stars excluded. A fix is on a separate branch; after it merges, only the affected stars will be
  re-run and reported as an update.

## Repository layout

```
src/exoplan/
  lightcurve.py   container with provenance      loaders.py   TESS (MAST), CHEOPS FITS, CSV
  preprocess.py   clean, detrend, bin            subjects.py  blind-coded 13-day segments
  search.py       BLS and single-event search    vet.py       automatic vetting
  injection.py    synthetic transits              calibrate.py skill-based reviewer weights
  aggregate.py    clustering and consensus       pipeline.py  end-to-end run
  benchmark.py    injection recovery             report.py    static HTML site
  store.py        SQLite and CSV export          config.py    TOML configs
  variables.py    everything-that-dims rules     starsearch.py one star-sector of the sweep
  sweep.py        resumable sector sweep         contrib.py   contribution bundles and ingest
  everything.py   #/variables, counter, Sky layer
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

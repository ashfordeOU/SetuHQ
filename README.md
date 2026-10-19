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
  the five epochs gives a depth of 292 ± 8 ppm and T14 = 3.07 ± 0.17 h. Against Huang et al.
  2018 (300 ppm, 2.953 h) that is **0.97 in depth and 1.04 in duration**. The box measure it
  replaces gave 0.81 and 0.64 against the same values (0.91 and 0.64 against the archive's
  current default row). The impact parameter is weakly constrained by five TESS transits
  (b = 0.86, 1σ 0.00 to 0.87; Huang: 0.59). The transit density, 0.29 g/cm³ with a 1σ range
  of 0.28 to 2.2, is therefore consistent with the TIC's 1.02 g/cm³ but does not pin it.
  The fit is U-shaped, not V-shaped.
* The periodic signal's false-alarm probability is below 10⁻⁴ in both subjects. No one of
  10,000 block-bootstrap trials reached the observed SNR, so 10⁻⁴ is a bound, not a value.
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

**What this can and cannot claim.** Every entry is a candidate. A detection here means the
pipeline saw a vetted dip that matches no published ephemeris. It does not mean a planet has
been found. Confirmation needs radial velocities, ground-based photometry, or the
community's TESS follow-up. The pipeline also has no centroid or pixel check, so blended
eclipsing binaries can survive vetting. The claim this project can defend is a reproducible,
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
  mid-time with errors, a ρ★ consistency check and a V-shape test. With a few TESS transits
  the impact parameter, and so a/R★ and ρ★, is poorly constrained. The density band (0.3 to 3
  times the catalogue value, at 3σ) is illustrative, not a published threshold.
* **False-alarm probabilities are bounded by the trials.** A FAP is (k + 1)/(N + 1) over N
  block-bootstrap trials, and is never printed below 1/(N + 1). The stored pi Men run uses
  10⁴ trials, the discovery batches 200 (enough for the feed's 1% rule), and the library
  default 20. A Gumbel fit to the null maxima is stored beside it as an extrapolation and is
  labelled indicative.
* **Vetting uses only light curves.** There is no centroid or pixel-level check, so
  blended eclipsing binaries can pass.
* **Edge events are the weak spot** for both the statistics and the reviewers.
* **Discovery candidates are unconfirmed.** Nothing on the discovery feed is a confirmed planet.

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

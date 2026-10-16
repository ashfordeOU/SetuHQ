# exoplan

An open-source transit search in the style of [Planet Hunters CHEOPS](https://www.zooniverse.org/projects/bmerin/planet-hunters-cheops).
Where that project uses volunteers, exoplan uses a **reviewer panel**: independent
reviewers, some of them Claude, that mark dips in blind-coded light curves. Consensus
is skill-weighted, and every candidate keeps its provenance.

Research behind the design: [docs/RESEARCH.md](docs/RESEARCH.md).
Live report for a real run: [site/index.html](site/index.html).

## What it does

1. **Ingests** TESS SPOC light curves from MAST, CHEOPS light-curve FITS files, or CSV.
2. **Cleans and detrends**: spike clipping, a masked local-quadratic baseline, and binning.
3. **Cuts blind-coded subjects**: fixed 13-day segments with opaque IDs. The target name never reaches a reviewer.
4. **Runs the panel**: every reviewer marks and labels every subject independently. The task is the Planet Hunters task: mark the start and end of each dip, then label `potential_planet` or `noise`.
5. **Aggregates** marks by single-linkage clustering, scores each dip by the share of skill-weighted reviewers who marked it, and requires the panel to call the subject a potential planet.
6. **Vets** each consensus event: SNR, duration, edge effects, odd/even depth, secondary eclipse, and fit to the periodic ephemeris.
7. **Writes** a candidate catalogue (CSV and JSON), a Zooniverse-shaped classification export, a SQLite store, a provenance manifest, and a static report site.

## Reviewer panel

| Reviewer | What it is | Needs |
|---|---|---|
| `simulated` | Deterministic detector with human-like limits (threshold, miss rate, boundary jitter). A baseline and a calibration reference. | Nothing |
| `claude_code` | Claude reviewing the rendered plot through the **Claude Code CLI**, which signs in with a Claude team or individual subscription. | `claude` on PATH, signed in |
| `claude` | Claude through the **Anthropic API** (vision). | `ANTHROPIC_API_KEY` |

Claude reviewers receive the same task as volunteers, the blind-coded plot, and no
target name. They return strict JSON, which is validated and clipped to the subject's
time range. A reviewer that is not available is skipped and listed in the manifest.
Responses are cached by a hash of model, prompt and image, so re-runs are free and
reproducible.

Two personas are included: `volunteer` (careful, marks dips) and `skeptic` (rejects
binary and systematic signatures unless they are clear).

## Quick start

```bash
pip install -e ".[tess,dev]"         # add ,claude for the API backend
pytest -q                            # 46 offline tests

exoplan run configs/tess_pi_men_s1.toml --out runs/tess-pi-men-s1
exoplan report runs/tess-pi-men-s1 --out site --validation docs/results/pi_men_validation.md
exoplan calibrate configs/tess_pi_men_s1.toml --out weights.json
exoplan benchmark configs/benchmark_simulated_panel.toml --weights weights.json --out bench.md
pytest -q -m network                 # live MAST download test
```

Configs are documented in [configs/default.toml](configs/default.toml). Every value
that changes a result is in the config, and its hash goes into the manifest.

## Results so far

Real data, TESS SPOC sector 1 of pi Men (TIC 261136679), deterministic panel plus
skeptic and volunteer Claude reviewers via the CLI:

* 6 consensus dips, 6 passed vetting, one of them flagged `off_ephemeris`.
* Five of them lie on the published pi Men c ephemeris. All five predicted epochs in the
  25-day window are recovered, with a mean timing offset of +8 minutes against the
  NASA Exoplanet Archive value. Depth is 0.83 and duration 0.68 of the published values
  (see [docs/results/pi_men_validation.md](docs/results/pi_men_validation.md)).
* The sixth passed event (BTJD 1348.9, 0.87 h, SNR 7.4) does not fit the ephemeris and
  is a likely false positive. It is kept and flagged, not hidden.

**What Claude did in this run, reported as found:**

* On the second subject, both Claude reviewers independently marked the two real
  epochs at BTJD 1344.3 and 1350.55 (about 6.2 days apart). They rejected the spurious
  1348.9 dip, with sound reasons.
* On the first subject, both Claude reviewers called the real epochs at BTJD 1325.5,
  1331.8 and 1338.05 "instrumental" edge ramps and missed them. The simulated
  volunteers found them. Those dips sit near the segment start and end, which is a
  known weak spot for a reviewer that reads edges as systematics. This is exactly why
  Claude is one voice in a calibrated panel, not the whole panel.

Injection-recovery benchmark for the deterministic panel:
[docs/results/injection_recovery_simulated_panel.md](docs/results/injection_recovery_simulated_panel.md).
Claude reviewers are not in the benchmark. Each injected subject would need its own CLI
call, so Claude is calibrated separately on a small sample.

## Honest limits

* **Claude's panel is calibrated on a small sample only.** The full benchmark needs many
  CLI or API calls. See the calibration file for the sample size used.
* **Synthetic results are not sky results.** The benchmark uses white plus red noise. It
  measures the pipeline's logic, not real completeness.
* **The CHEOPS column mapping is unverified.** The loader accepts several candidate
  names and records the ones used. Check them against a real `SCI_COR_Lightcurve` file.
* **Box fits underestimate depth and duration** compared with published trapezoid fits.
* **Vetting uses only light curves.** There is no centroid or pixel-level check, so
  blended eclipsing binaries can pass.
* **Edge events are the weak spot** for both the statistics and the reviewers.

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
command on every push (`.github/workflows/ci.yml`).

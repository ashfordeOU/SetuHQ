<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# SetuHQ roadmap

This is the honest roadmap for the open SetuHQ. It complements two other sources of truth:
[`CHANGELOG.md`](CHANGELOG.md) records *released* history, and the README's **Evidence** and
**Honest limits** sections state what each capability has and has not been shown to do. When they
disagree with this file, the README's measured statements win.

Horizons are indicative, not commitments, and no item below carries a date. SetuHQ is pre-1.0;
file formats and the command line may still change, and breaking changes are called out in the
changelog. The planned commercial overlay is described separately in [`docs/PRO.md`](docs/PRO.md);
nothing on this page depends on it.

## Priorities

Work is ordered by where the evidence is weakest and matters most, not by the size of the code.

1. **Bring the benchmark up to the current code, first.** The real-TOI benchmark, and so the
   leaderboard and the methods paper's numbers, were measured with the code from before the
   deep-dip clipping fix. Re-run the affected stars (27 CP/KP and 11 FP stars in the held-out half
   are exposed) and publish the update beside the old numbers, not over them.
2. **Beat the floor, or say why not.** The leaderboard cannot show that the Probes beat a
   catalogue-metadata floor that never reads a light curve. Improvements to the search and vetting
   are judged on that paired comparison, pre-registered on the tuning half and evaluated once on
   the held-out half.
3. **Make the feed's admissions worth a person's time.** Under the pre-registered two-sector rule
   the feed still admits about 6 false signals per 100 targets, against about 0.3 real new signals.
   Next: a stricter rule chosen the same way, and the held-out cost to completeness stated with it.
4. **Calibrate the Sentinels properly.** They are calibrated on a small sample (10 injected and 10
   empty subjects) and benchmarked on a 40-star subsample, where the two Claude personas agree with
   φ = 0.89. Next: a larger calibration sample, and other providers on the same subsample
   (`scripts/benchmark_real_tois.py sentinels --panel`) to measure whether another model makes the
   panel more independent.
5. **Measure the cost per star**, for the Probes alone and for the full Sentinel panel, from stored
   runs, so anyone running a sweep knows what it costs before it starts.

## Next

- **Vetting on real false positives.** Benchmark the pixel-level centroid test on Kepler
  `koi_fpflag_co` KOIs and TESS FP TOIs; it has only been tested on synthetic target pixel files.
- **Statistical validation, run for real.** Run the TRICERATOPS adapter on real targets once MAST,
  Gaia and TESSCut answer, and ingest high-resolution imaging contrast curves; without them no
  candidate can be "validated (statistically)".
- **The eccentric-secondary gap.** Recover secondaries below the first-pass threshold, with a
  second-pass threshold calibrated by simulating that exact two-pass procedure.
- **ExoFOP export, checked.** Compare the CTOI-style export's fields with ExoFOP's live form.
- **A real batch.** Run `setuhq batch` on a real target list and report throughput.
- **More sky in the sweep.** More sectors, from more contributors. Past a few sectors the per-star
  records move out of the repository into release assets, with a committed manifest of their sha256
  that the site build checks.

- **Room for the app to grow.** The app is one self-contained page with a 1.4-million-character
  budget, and the release leaves about 6,700 characters of it. Next: split the largest sections
  (the Methods chapters and the Galaxy) into files the page fetches when a route opens, as the
  catalogue already is, with the budget kept as a test.

## Later

- **New missions, as their public data flows:** Roman's microlensing survey in the open engine, and
  PLATO light curves as its public quarters are released.
- **A multi-maintainer model** for governance, as described in [`GOVERNANCE.md`](GOVERNANCE.md).

## Not planned

- Calling any output a confirmed, validated or discovered planet.
- Moving any open feature behind a licence.
- Tuning a threshold on the held-out half of the benchmark.

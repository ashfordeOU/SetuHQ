# The real-TOI leaderboard

A public leaderboard on exoplan's frozen benchmark of 662 real TESS Objects of Interest
([docs/results/benchmark_real_tois.md](../results/benchmark_real_tois.md)). It scores a method's per-star outcomes on
the **held-out half** only. The table is [leaderboard.md](leaderboard.md) (data: [leaderboard.json](leaderboard.json));
the app shows it at `#/leaderboard`.

This is not the injection threshold sweep in [docs/threshold_sweep.md](../threshold_sweep.md), which tunes Probe
thresholds on synthetic light curves and was called "leaderboard" before.

Measured on a stated benchmark; nothing here is a discovery. Sentinels run on Claude (Anthropic). Probes are
deterministic matched-filter detectors.

## What you need

| file | what it is |
|---|---|
| `docs/results/benchmark_toi_sample.json` | the frozen sample (sha256 `6f0e111e…`, stated in full in leaderboard.md). It holds every label, both halves. |
| `docs/leaderboard/tuning_inputs.json` | the **public inputs**: the tuning half with its dispositions, and the held-out half with only TIC, TOI name and ephemeris (no disposition, class, depth or radius). Its canonical sha256 is stated in leaderboard.md. |
| `src/exoplan/benchmark_toi.py` | `inverted` and `scrambled`: the two control light curves for each star. |
| `src/exoplan/discover.py` | `match_toi`: whether an event lies on a TOI's ephemeris. |

Build the method on the tuning half (or on nothing), then run it blind on the held-out stars' light curves and
their two controls.

## Submission format (`exoplan-leaderboard/1`)

```json
{
 "format": "exoplan-leaderboard/1",
 "id": "my-method",
 "name": "My method",
 "sample_sha256": "<the frozen sample's sha256>",
 "inputs_sha256": "<the canonical sha256 of tuning_inputs.json>",
 "tuned_on": "none",
 "scope": "held_out",
 "provenance": {"method": "what it does, in a sentence or two",
                "code_version": "a commit, tag or version",
                "generated_from": [{"file": "...", "sha256": "..."}]},
 "predictions": [
  {"toi": "1201.01", "tic": 12345678, "searched": true, "seen": true, "recovered": true, "flagged": false,
   "controls": {"inverted": 0, "scrambled": 1}}
 ]
}
```

One prediction per star of the scope, no more and no fewer:

* `searched`: the method had a light curve for the star and ran on it. A star it could not search is submitted
  with `"searched": false` (then `seen`, `recovered` and `flagged` are false), never left out.
* `seen`: one of its detected events lies on the TOI's published ephemeris (`match_toi`).
* `recovered`: that event passed the method's own vetting: the method offers it as a candidate.
* `flagged`: the method rejected the on-ephemeris event or marked it binary-like. Recovered and not flagged is a
  **clean candidate**.
* `controls`: events that passed vetting on the flux-inverted and block-scrambled light curves, or `null` (or the
  key left out) when the method was not run on them.

`tuned_on` is `none` or `tuning`. `scope` is `held_out` (all 345 held-out stars) or `sentinel_subsample` (the 40
stars the Sentinels reviewed, listed in the benchmark report).

## Scoring

```bash
exoplan leaderboard my-method.json        # score one submission (exit 2 and the reasons when refused)
exoplan leaderboard                       # rebuild leaderboard.json and leaderboard.md from submissions/
```

| measure | definition |
|---|---|
| completeness, all CP/KP stars (rank key) | CP/KP stars recovered, over every CP/KP star in the scope; a star not searched counts as missed |
| completeness, searchable | CP/KP stars recovered, over the searched ones (the benchmark report's headline) |
| completeness below 4 R⊕ | the same on CP/KP TOIs with a published radius below 4 R⊕ |
| FP rejection | searched FP stars that the method did not offer as a clean candidate |
| control false alarms | searched stars with any vetted event on the inverted (scrambled) light curve, and events per 1,000 star-sectors |
| reliability | clean candidates on TOI dips that are CP/KP, over all clean candidates on TOI dips. It depends on this sample's class mix (about half CP/KP among searched held-out stars), not the TOI catalogue's |

Every rate has a Wilson 95% interval. Equal completeness shares a rank; where intervals overlap, the order is not a
measured difference.

## When a submission is refused

The leaderboard refuses a submission, and lists every reason, when:

* `sample_sha256` is not the frozen sample's;
* `inputs_sha256` is not the public inputs' hash. When it is the hash of the full sample file, which holds the
  held-out labels, the message says it was built with held-out labels;
* `tuned_on` is anything but `none` or `tuning` (`held_out` or `all` touch held-out labels);
* a prediction carries a label field (`class`, `disposition`, `tfopwg_disp`, `label`, `truth` …);
* a star of the scope is missing, a star is predicted twice, a tuning-half star or a star outside the scope is
  included, or a TIC does not match the sample;
* the outcome fields are inconsistent (recovered or flagged without seen; seen on a star not searched; a negative
  or non-integer control count);
* the provenance does not state the method, the code version and what it was generated from.

The hash is an attestation, not a proof. The held-out labels are public in the repository, so no check can show
that a method never read them. The leaderboard refuses every submission that declares or shows that it did, and
each entry's provenance says what it was built from.

## The seeded entries

exoplan's own configurations, scored from stored per-star results without re-running anything
(`scripts/leaderboard_seed.py`):

* **Probes only**, on the whole held-out half, from the per-star rows in `benchmark_real_tois.json`. Its scores
  equal the benchmark report's own (a test checks this).
* On the Sentinels' 40-star subsample: **Probes only** (the same rows, restricted), **Sentinel · Volunteer alone**,
  **Sentinel · Skeptic alone** (from the benchmark's stored Claude Code CLI responses; the script stops unless they
  reproduce the report's committed totals), and two **Probes + Sentinels** rules stated before scoring: *either*
  (a clean candidate when the Probes give one or either Sentinel marks the dip as a potential planet) and *both*
  (only when the Probes give one and a Sentinel marks it too). These are star-level combinations of stored outcomes,
  not a run of the panel's mark-level consensus. The Sentinels were never run on the controls, so those cells read
  "not measured".

The seeded entries state `tuned_on: none`: no threshold changed after the sample was frozen (the benchmark's
threshold audit).

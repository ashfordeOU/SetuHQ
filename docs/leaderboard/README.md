# The real-TOI leaderboard

A public leaderboard on exoplan's frozen benchmark of 662 real TESS Objects of Interest
([docs/results/benchmark_real_tois.md](../results/benchmark_real_tois.md)). It scores a method's detected events
on the **held-out half** only. The table is [leaderboard.md](leaderboard.md) (data: [leaderboard.json](leaderboard.json));
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
| `src/exoplan/benchmark_toi.py` | `inverted` and `scrambled`: the two control light curves for each star (the scrambled one masks every known TOI on the star first). |

Build the method on the tuning half (or on nothing), then run it blind on each held-out star's light curve and on
its two controls.

## Submission format (`exoplan-leaderboard/2`)

```json
{
 "format": "exoplan-leaderboard/2",
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
  {"toi": "1201.01", "tic": 12345678, "searched": true,
   "events": [{"t_center": 1325.503, "duration_hours": 3.1, "period_days": 6.268, "passed": true, "flags": []}],
   "controls": {"inverted": [], "scrambled": [{"t_center": 1330.2, "duration_hours": 2.0, "period_days": null,
                                               "passed": true, "flags": ["edge_event"]}]}}
 ]
}
```

One prediction per star of the scope, no more and no fewer. Only these fields are accepted (a whitelist):

* `searched`: the method had a light curve for the star and ran on it. A star it could not search is submitted
  with `"searched": false`, no events and `"controls": null`, never left out.
* `events`: every event the method detected on the star's real light curve: `t_center` (BTJD), `duration_hours`,
  `period_days` (or null for a single event), `passed` (its own vetting verdict), `flags` (from the vetting
  vocabulary: `low_snr`, `too_short`, `edge_event`, `insufficient_points`, `odd_even_mismatch`,
  `secondary_eclipse`, `off_ephemeris`, `v_shape`, `density_mismatch`), and optionally `snr`.
* `controls`: the same lists for the flux-inverted and block-scrambled curves, or `null` when the method was not run
  on them.

The leaderboard decides which events lie on the TOI's ephemeris with the benchmark's own `score_star`
(`discover.match_toi`): *recovered* is an on-ephemeris event that passed, *flagged* an on-ephemeris event that
failed or carries an eclipsing-binary flag (odd/even, secondary, V shape, density). Control false alarms are the
events that passed on the controls. A method no longer states its own outcomes.

`tuned_on` is `none` or `tuning`. `scope` is `held_out` (all 345 held-out stars) or `sentinel_subsample` (the 40
stars the Sentinels reviewed, listed in the benchmark report).

## Scoring and rank

```bash
exoplan leaderboard my-method.json        # score one submission (exit 2 and the reasons when refused)
exoplan leaderboard                       # rebuild leaderboard.json and leaderboard.md from submissions/
```

| measure | definition |
|---|---|
| **Youden's J (rank key)** | completeness over every CP/KP star + FP rejection over every FP star − 1 (Youden 1950), with Newcombe's (1998) square-and-add Wilson interval. Calling every TOI a planet scores 0 |
| completeness, all CP/KP stars | CP/KP stars recovered, over every CP/KP star in the scope; a star not searched counts as missed |
| completeness, searchable | the same over searched stars (the benchmark report's headline) |
| completeness below 4 R⊕ | on CP/KP TOIs with a published radius below 4 R⊕ |
| FP rejection, all FP stars | FP stars the method did not offer as a clean candidate (recovered and not flagged); a star not searched was not offered |
| control false alarms | searched stars with any passed event on the inverted (scrambled) light curve, and events per 1,000 star-sectors |
| reliability | clean candidates on TOI dips that are CP/KP, over all clean candidates on TOI dips. It depends on this sample's class mix (about half CP/KP among searched held-out stars), not the TOI catalogue's |

The benchmark report's "FP TOIs rejected or flagged" is over the FP dips the Probes found; the leaderboard's FP
rejection is over every held-out FP star, so the two rates differ. Both are printed with their definitions.

Only held-out entries with both control lists on every searched star are ranked; the rest are listed as
unranked. **The 40-star Sentinel subsample is never ranked: 40 stars cannot order these configurations.** Equal J
shares a rank; where intervals overlap, the order is not a measured difference. Every rate has a Wilson 95%
interval.

## When a submission is refused

The leaderboard refuses a submission, and lists every reason, when:

* it is not a JSON object, or carries any field outside the whitelists (labels and label proxies such as
  `class`, `radius_re`, `depth_ppm` or `tfop` cannot get through), or a format other than `exoplan-leaderboard/2`
  (version 1 trusted self-reported outcomes and is retired);
* `sample_sha256` is not the frozen sample's;
* `inputs_sha256` is not the public inputs' hash. When it is a hash of the full sample (canonical, the sample's own
  `sha256` field, or the file's bytes), the message says it was built with held-out labels;
* `tuned_on` is anything but `none` or `tuning`;
* a star of the scope is missing, a star is predicted twice, a tuning-half star or a star outside the scope is
  included, or a TIC does not match the sample;
* an event is malformed (no time, a non-positive duration or period, a non-boolean verdict, a flag outside the
  vocabulary), a star not searched carries events, or the controls are not `{inverted, scrambled}`;
* the provenance does not state the method, the code version and what it was generated from.

## What the leaderboard cannot check

* **Labels.** The held-out labels are public in the repository, so no check can show that a method never read
  them. The hash is an attestation, and each entry's provenance says what it was built from.
* **Verdicts and controls.** `passed`, `flags` and the control lists are the method's own report. A method could
  under-report its control false alarms.
* **Future work, not built:** maintainer-held decoy light curves under opaque ids (injected and empty curves whose
  truth only the maintainers hold), and prospective scoring on TOIs that are still undispositioned, scored when
  TFOPWG dispositions them. Either would make these gaps checkable.

## The seeded entries

exoplan's own configurations, built from the benchmark's stored outputs without re-running anything
(`scripts/leaderboard_seed.py --cache <cache/bench>`):

* **Probes only**, on the whole held-out half: every consensus event of the real and control runs. The scorer's
  outcomes equal the committed per-star rows of `benchmark_real_tois.json` star by star (a test checks this).
* On the Sentinels' 40-star subsample: **Probes only** (the same events, restricted), **Sentinel · Volunteer alone**
  and **Sentinel · Skeptic alone** (each mark an event, passed when the persona called the subject a potential
  planet; the seed script stops unless they reproduce the report's committed totals and agreement).
* Two **Probes + Sentinels** rows, *either* and *both*, derived by the leaderboard (`leaderboard.DERIVED`). They are
  star-level rules, fixed before scoring (commit 9e42c0b), not panel consensus, and their names say so. The
  Sentinels were never run on the controls, so those cells read "not measured".

The seeded entries state `tuned_on: none`: no threshold changed after the sample was frozen (the benchmark's
threshold audit).

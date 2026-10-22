# Leaderboard: the frozen real-TOI benchmark

Not to be confused with the injection threshold sweep in [docs/threshold_sweep.md](../threshold_sweep.md), which tunes Probe thresholds on synthetic light curves.

Measured on a stated benchmark; not discoveries. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

Frozen sample sha256 `6f0e111ec8d2c38d3e7927505f0be4a2c7fae8b73d7cc17c37646baedf044cac` (docs/results/benchmark_toi_sample.json). Public inputs (tuning half with labels, held-out half without) sha256 `d0e4f2d9c5538800e9a34d018757f99e1d1672060e71ae56bbaf87fcaf0c15b4` (docs/leaderboard/tuning_inputs.json). Sentinel subsample sha256 `999c61bddc47cae0f47674ea77e1524c77697ad7da35d52f2abd7578924016b2`. Benchmark code commit `0ae8ccf0a23502a2324759a23a7d5ca277d63bcc`.

## Rules

1. Scored on the held-out half of the frozen sample only (TOIs by sha256(seed:TIC) parity); the tuning half is never scored.
2. A submission lists, for every star of its scope, the events its method detected on the real light curve and on the flux-inverted and block-scrambled controls (time, duration, period, its own pass verdict and flags). The leaderboard decides which events lie on the TOI's ephemeris (the benchmark's score_star and match_toi) and counts control false alarms itself. Self-reported outcomes are not accepted.
3. Rank: Youden's J on the searchable set the benchmark fixed (stars with a SPOC 2-minute light curve), with one predicate on both sides, a clean candidate (on the ephemeris, passed, no eclipsing-binary flag): J = the share of CP/KP stars offered as clean candidates + the share of FP stars not offered − 1, with a square-and-add Wilson interval. Calling every TOI a planet, with or without a flag, scores J = 0; a searchable star called not searched counts as not offered. J over every star of the scope is shown beside it. Where intervals overlap, the order is not a measured difference.
4. The controls gate ranking and do not enter J: only held-out entries with both control lists on every searched star are ranked, others are listed unranked. The control lists are the method's own report; the leaderboard cannot recompute them without the light curves. The Sentinel subsample is never ranked.
5. A floor: the metadata-only baseline uses no light curve at all, only the public TOI number, period, duration, ephemeris errors and epoch, with a logistic regression fitted on the tuning half. A method that does not beat it is not shown to read the light curves better than the catalogue's own metadata predicts dispositions.
6. A submission states the sha256 of the public inputs it was built from (tuning half with labels, held-out half without). Any other hash, tuned_on other than none or tuning, a field outside the whitelist, a missing or extra star, or missing provenance: refused, with the reasons listed.
7. The hash is an attestation: the held-out labels are public in the repository, so the leaderboard cannot prove they were not read, and a method's pass verdicts and control events are its own report. Maintainer-held decoy light curves and prospective scoring on TOIs still undispositioned would close these gaps; neither exists yet.
8. FP rejection: FP stars whose TOI dip the method did not offer as a clean candidate (recovered and not flagged). Reliability: the share of clean candidates on TOI dips that are CP/KP, on this sample's class mix, which is not the TOI catalogue's. All rates carry Wilson 95% intervals. TFOPWG dispositions are the reference, not ground truth for every TOI.
9. Measured on a stated benchmark; nothing on this leaderboard is a discovery.

## Held-out half (every held-out star)

**The benchmark cannot show that the Probes read light curves better than catalogue metadata predicts dispositions (paired ΔJ (floor − Probes) = +0.039, 95% CI -0.096 to +0.173, P(ΔJ ≤ 0) = 0.29).**

| rank | entry | Youden J | Youden J, all stars | clean completeness, searchable CP/KP | FP rejection, searchable FP | recovered below 4 R⊕ | inverted control: stars with any | scrambled control: stars with any | reliability |
|---|---|---|---|---|---|---|---|---|---|
| 1 (interval overlaps #2) | Metadata only, no light curve (a floor) | +0.39 (+0.27 to +0.49) | +0.46 (+0.35 to +0.55) | 76% (114/150; 69–82%) | 63% (78/124; 54–71%) | 70% (32/46; 55–81%) | 54% (166/309; 48–59%) | 54% (166/309; 48–59%) | 69% (114/166; 61–75%) |
| 2 (interval overlaps #1) | Probes only | +0.35 (+0.23 to +0.45) | +0.40 (+0.29 to +0.49) | 60% (90/150; 52–67%) | 75% (93/124; 67–82%) | 17% (8/46; 9–31%) | 22% (67/309; 17–27%) | 25% (78/309; 21–30%) | 72% (90/125; 64–79%) |

Entries:

* **Metadata only, no light curve (a floor)** (`metadata-baseline`, tuned on: tuning). Never reads a light curve. A logistic regression on the public TOI number, period, duration, ephemeris errors and epoch, fitted on the tuning half's CP/KP against FP TOIs; held-out stars above the threshold (0.464, chosen by 5-fold cross-validated J = 0.41 on the tuning half) get one event on the published ephemeris. Stars the benchmark could not search (no SPOC 2-minute light curve) are submitted as not searched. The same events stand on the controls, because the method ignores the light curve. A floor, not a vetter.
* **Probes only** (`probes`, tuned on: none). The three Probes (Sensitive, Typical, Cautious) with their frozen calibrated weights, sector-wide BLS, light-curve vetting and the limb-darkened fit, on each star's first SPOC 2-minute sector, as in the benchmark report; every consensus event on the real and control curves, with its light-curve vetting flags (the extended-vetting flags, which never change pass/fail by default, are left out). No FAP rule. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

## The Sentinels' stated subsample (37 held-out stars), not ranked

**37 stars cannot order these configurations: the subsample is listed, never ranked, and every interval is wide.**

| entry | Youden J | Youden J, all stars | clean completeness, searchable CP/KP | FP rejection, searchable FP | recovered below 4 R⊕ | inverted control: stars with any | scrambled control: stars with any | reliability |
|---|---|---|---|---|---|---|---|---|
| Probes only | +0.14 (-0.16 to +0.41) | +0.14 (-0.16 to +0.41) | 42% (8/19; 23–64%) | 72% (13/18; 49–88%) | 0% (0/8; 0–32%) | 8% (3/37; 3–21%) | 22% (8/37; 11–37%) | 62% (8/13; 36–82%) |
| Sentinel · Skeptic alone | +0.25 (-0.05 to +0.50) | +0.25 (-0.05 to +0.50) | 47% (9/19; 27–68%) | 78% (14/18; 55–91%) | 0% (0/8; 0–32%) | not measured | not measured | 69% (9/13; 42–87%) |
| Sentinel · Volunteer alone | +0.25 (-0.05 to +0.50) | +0.25 (-0.05 to +0.50) | 47% (9/19; 27–68%) | 78% (14/18; 55–91%) | 0% (0/8; 0–32%) | not measured | not measured | 69% (9/13; 42–87%) |
| Probes + Sentinels, both (star-level rule, fixed before scoring, not panel consensus) | +0.25 (-0.04 to +0.50) | +0.25 (-0.04 to +0.50) | 42% (8/19; 23–64%) | 83% (15/18; 61–94%) | 0% (0/8; 0–32%) | not measured | not measured | 73% (8/11; 43–90%) |
| Probes + Sentinels, either (star-level rule, fixed before scoring, not panel consensus) | +0.08 (-0.22 to +0.36) | +0.08 (-0.22 to +0.36) | 47% (9/19; 27–68%) | 61% (11/18; 39–80%) | 0% (0/8; 0–32%) | not measured | not measured | 56% (9/16; 33–77%) |

Entries:

* **Probes only** (`probes-subsample`, tuned on: none). The three Probes (Sensitive, Typical, Cautious) with their frozen calibrated weights, sector-wide BLS, light-curve vetting and the limb-darkened fit, on each star's first SPOC 2-minute sector, as in the benchmark report; every consensus event on the real and control curves, with its light-curve vetting flags (the extended-vetting flags, which never change pass/fail by default, are left out). No FAP rule. Restricted to the Sentinels' subsample, to compare like with like. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Sentinel · Skeptic alone** (`claude-skeptic`, tuned on: none). One Sentinel persona (skeptic) through the Claude Code CLI on every 13-day subject of the star's real light curve; each mark is an event, passed when the persona called the subject a potential planet. Not run on the controls. The answers are the first run's, stored, reused on the 37 stars whose subject images are byte-identical on the current code; no Sentinel was asked again. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Sentinel · Volunteer alone** (`claude-volunteer`, tuned on: none). One Sentinel persona (volunteer) through the Claude Code CLI on every 13-day subject of the star's real light curve; each mark is an event, passed when the persona called the subject a potential planet. Not run on the controls. The answers are the first run's, stored, reused on the 37 stars whose subject images are byte-identical on the current code; no Sentinel was asked again. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Probes + Sentinels, both (star-level rule, fixed before scoring, not panel consensus)** (`probes-and-sentinel`, tuned on: none). A clean candidate only when the Probes give one and either Sentinel also marks the TOI's dip as a potential planet. Applied by the leaderboard to the component entries' scored outcomes.
* **Probes + Sentinels, either (star-level rule, fixed before scoring, not panel consensus)** (`probes-or-sentinel`, tuned on: none). A clean candidate when the Probes give one or either Sentinel marks the TOI's dip as a potential planet. Applied by the leaderboard to the component entries' scored outcomes.

Clean completeness and FP rejection use the same predicate (a clean candidate: on the ephemeris, passed, no eclipsing-binary flag) over the searchable set the benchmark fixed. The benchmark report's headline completeness counts a recovered dip even when flagged, and its "rejected or flagged" rate is over the FP dips the panel found; both are in docs/results/benchmark_real_tois_clipfix.md. Reliability depends on the sample's class mix; it is not the reliability on the TOI catalogue.

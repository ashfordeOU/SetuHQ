# Leaderboard: the frozen real-TOI benchmark

Not to be confused with the injection threshold sweep in [docs/threshold_sweep.md](../threshold_sweep.md), which tunes Probe thresholds on synthetic light curves.

Measured on a stated benchmark; not discoveries. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

Frozen sample sha256 `6f0e111ec8d2c38d3e7927505f0be4a2c7fae8b73d7cc17c37646baedf044cac` (docs/results/benchmark_toi_sample.json). Public inputs (tuning half with labels, held-out half without) sha256 `d0e4f2d9c5538800e9a34d018757f99e1d1672060e71ae56bbaf87fcaf0c15b4` (docs/leaderboard/tuning_inputs.json). Sentinel subsample sha256 `79d9b347ba1667bd3e919ee7e80d50016e1e06d106dd2531ad59ed0c7a0353b9`. Benchmark code commit `76de67d17eeef8a5fc62b26695574d0d63322b72`.

## Rules

1. Scored on the held-out half of the frozen sample only (TOIs by sha256(seed:TIC) parity); the tuning half is never scored.
2. A submission lists, for every star of its scope, the events its method detected on the real light curve and on the flux-inverted and block-scrambled controls (time, duration, period, its own pass verdict and flags). The leaderboard decides which events lie on the TOI's ephemeris (the benchmark's score_star and match_toi) and counts control false alarms itself. Self-reported outcomes are not accepted.
3. Rank: Youden's J on the searchable set the benchmark fixed (stars with a SPOC 2-minute light curve), with one predicate on both sides, a clean candidate (on the ephemeris, passed, no eclipsing-binary flag): J = the share of CP/KP stars offered as clean candidates + the share of FP stars not offered − 1, with a square-and-add Wilson interval. Calling every TOI a planet, with or without a flag, scores J = 0; a searchable star called not searched counts as not offered. J over every star of the scope is shown beside it. Where intervals overlap, the order is not a measured difference.
4. The controls gate ranking and do not enter J: only held-out entries with both control lists on every searched star are ranked, others are listed unranked. The control lists are the method's own report; the leaderboard cannot recompute them without the light curves. The 40-star Sentinel subsample is never ranked.
5. A floor: the metadata-only baseline uses no light curve at all, only the public TOI number, period, duration, ephemeris errors and epoch, with a logistic regression fitted on the tuning half. A method that does not beat it is not shown to read the light curves better than the catalogue's own metadata predicts dispositions.
6. A submission states the sha256 of the public inputs it was built from (tuning half with labels, held-out half without). Any other hash, tuned_on other than none or tuning, a field outside the whitelist, a missing or extra star, or missing provenance: refused, with the reasons listed.
7. The hash is an attestation: the held-out labels are public in the repository, so the leaderboard cannot prove they were not read, and a method's pass verdicts and control events are its own report. Maintainer-held decoy light curves and prospective scoring on TOIs still undispositioned would close these gaps; neither exists yet.
8. FP rejection: FP stars whose TOI dip the method did not offer as a clean candidate (recovered and not flagged). Reliability: the share of clean candidates on TOI dips that are CP/KP, on this sample's class mix, which is not the TOI catalogue's. All rates carry Wilson 95% intervals. TFOPWG dispositions are the reference, not ground truth for every TOI.
9. Measured on a stated benchmark; nothing on this leaderboard is a discovery.

## Held-out half (every held-out star)

**The Probes do not beat the metadata-only floor: J +0.30 (+0.19 to +0.41) against +0.39 (+0.27 to +0.49) for a model that never sees a light curve; the intervals overlap. On this benchmark J mostly measures how separable false positives are from catalogue metadata.**

| rank | entry | Youden J | Youden J, all stars | clean completeness, searchable CP/KP | FP rejection, searchable FP | recovered below 4 R⊕ | inverted control: stars with any | scrambled control: stars with any | reliability |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Metadata only, no light curve (a floor) | +0.39 (+0.27 to +0.49) | +0.43 (+0.32 to +0.52) | 76% (114/150; 69–82%) | 63% (78/124; 54–71%) | 68% (32/47; 54–80%) | 50% (173/345; 45–55%) | 50% (173/345; 45–55%) | 66% (115/173; 59–73%) |
| 2 | Probes only | +0.30 (+0.19 to +0.41) | +0.35 (+0.24 to +0.44) | 55% (83/150; 47–63%) | 75% (93/124; 67–82%) | 17% (8/46; 9–31%) | 21% (65/309; 17–26%) | 25% (78/309; 21–30%) | 70% (83/118; 62–78%) |

Entries:

* **Metadata only, no light curve (a floor)** (`metadata-baseline`, tuned on: tuning). Never reads a light curve. A logistic regression on the public TOI number, period, duration, ephemeris errors and epoch, fitted on the tuning half's CP/KP against FP TOIs; held-out stars above the threshold (0.464, chosen by 5-fold cross-validated J = 0.41 on the tuning half) get one event on the published ephemeris. The same events stand on the controls, because the method ignores the light curve. A floor, not a vetter.
* **Probes only** (`probes`, tuned on: none). The three Probes (Sensitive, Typical, Cautious) with their calibrated weights, sector-wide BLS, light-curve vetting and the limb-darkened fit, on each star's first SPOC 2-minute sector, as in the benchmark report; every consensus event on the real and control curves. No FAP rule. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

## The Sentinels' stated subsample (40 held-out stars: 20 CP/KP, 20 FP), not ranked

**40 stars cannot order these configurations: the subsample is listed, never ranked, and every interval is wide.**

| entry | Youden J | Youden J, all stars | clean completeness, searchable CP/KP | FP rejection, searchable FP | recovered below 4 R⊕ | inverted control: stars with any | scrambled control: stars with any | reliability |
|---|---|---|---|---|---|---|---|---|
| Probes only | +0.15 (-0.14 to +0.41) | +0.15 (-0.14 to +0.41) | 45% (9/20; 26–66%) | 70% (14/20; 48–85%) | 0% (0/8; 0–32%) | 8% (3/40; 3–20%) | 22% (9/40; 12–38%) | 60% (9/15; 36–80%) |
| Sentinel · Skeptic alone | +0.30 (+0.01 to +0.53) | +0.30 (+0.01 to +0.53) | 50% (10/20; 30–70%) | 80% (16/20; 58–92%) | 0% (0/8; 0–32%) | not measured | not measured | 71% (10/14; 45–88%) |
| Sentinel · Volunteer alone | +0.30 (+0.01 to +0.53) | +0.30 (+0.01 to +0.53) | 50% (10/20; 30–70%) | 80% (16/20; 58–92%) | 0% (0/8; 0–32%) | not measured | not measured | 71% (10/14; 45–88%) |
| Probes + Sentinels, both (star-level rule, fixed before scoring, not panel consensus) | +0.30 (+0.02 to +0.53) | +0.30 (+0.02 to +0.53) | 45% (9/20; 26–66%) | 85% (17/20; 64–95%) | 0% (0/8; 0–32%) | not measured | not measured | 75% (9/12; 47–91%) |
| Probes + Sentinels, either (star-level rule, fixed before scoring, not panel consensus) | +0.10 (-0.19 to +0.37) | +0.10 (-0.19 to +0.37) | 50% (10/20; 30–70%) | 60% (12/20; 39–78%) | 0% (0/8; 0–32%) | not measured | not measured | 56% (10/18; 34–75%) |

Entries:

* **Probes only** (`probes-subsample`, tuned on: none). The three Probes (Sensitive, Typical, Cautious) with their calibrated weights, sector-wide BLS, light-curve vetting and the limb-darkened fit, on each star's first SPOC 2-minute sector, as in the benchmark report; every consensus event on the real and control curves. No FAP rule. Restricted to the Sentinels' 40-star subsample, to compare like with like. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Sentinel · Skeptic alone** (`claude-skeptic`, tuned on: none). One Sentinel persona (skeptic) through the Claude Code CLI on every 13-day subject of the star's real light curve; each mark is an event, passed when the persona called the subject a potential planet. Not run on the controls. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Sentinel · Volunteer alone** (`claude-volunteer`, tuned on: none). One Sentinel persona (volunteer) through the Claude Code CLI on every 13-day subject of the star's real light curve; each mark is an event, passed when the persona called the subject a potential planet. Not run on the controls. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Probes + Sentinels, both (star-level rule, fixed before scoring, not panel consensus)** (`probes-and-sentinel`, tuned on: none). A clean candidate only when the Probes give one and either Sentinel also marks the TOI's dip as a potential planet. Applied by the leaderboard to the component entries' scored outcomes.
* **Probes + Sentinels, either (star-level rule, fixed before scoring, not panel consensus)** (`probes-or-sentinel`, tuned on: none). A clean candidate when the Probes give one or either Sentinel marks the TOI's dip as a potential planet. Applied by the leaderboard to the component entries' scored outcomes.

Clean completeness and FP rejection use the same predicate (a clean candidate: on the ephemeris, passed, no eclipsing-binary flag) over the searchable set the benchmark fixed. The benchmark report's headline completeness counts a recovered dip even when flagged, and its "rejected or flagged" rate is over the FP dips the panel found; both are in docs/results/benchmark_real_tois.md. Reliability depends on the sample's class mix; it is not the reliability on the TOI catalogue.

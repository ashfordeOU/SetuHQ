# Leaderboard: the frozen real-TOI benchmark

Not to be confused with the injection threshold sweep in [docs/threshold_sweep.md](../threshold_sweep.md), which tunes Probe thresholds on synthetic light curves.

Measured on a stated benchmark; not discoveries. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

Frozen sample sha256 `6f0e111ec8d2c38d3e7927505f0be4a2c7fae8b73d7cc17c37646baedf044cac` (docs/results/benchmark_toi_sample.json). Public inputs (tuning half with labels, held-out half without) sha256 `d0e4f2d9c5538800e9a34d018757f99e1d1672060e71ae56bbaf87fcaf0c15b4` (docs/leaderboard/tuning_inputs.json). Sentinel subsample sha256 `79d9b347ba1667bd3e919ee7e80d50016e1e06d106dd2531ad59ed0c7a0353b9`. Benchmark code commit `76de67d17eeef8a5fc62b26695574d0d63322b72`.

## Rules

1. Scored on the held-out half of the frozen sample only (TOIs by sha256(seed:TIC) parity); the tuning half is never scored.
2. A submission covers every star of its scope: the whole held-out half, or the Sentinels' stated 40-star subsample. A star without a light curve is submitted with searched: false and counts as missed in the all-stars completeness, which is the rank key.
3. It states the sha256 of the public inputs it was built from (tuning half with labels, held-out half without). Any other hash, tuned_on other than none or tuning, a label field in a prediction, a missing or extra star, or missing provenance: refused, with the reasons listed.
4. The hash is an attestation: the held-out labels are public in the repository, so the leaderboard cannot prove they were not read. It refuses every submission that declares or shows that they were.
5. Completeness: CP/KP stars whose TOI dip the method recovered (passed its vetting). FP rejection: searched FP stars whose TOI dip the method did not offer as a clean candidate (recovered and not flagged). Controls: stars with any vetted event on the flux-inverted and block-scrambled light curves. Reliability: the share of clean candidates on TOI dips that are CP/KP, on this sample's class mix, which is not the TOI catalogue's.
6. All rates carry Wilson 95% intervals. TFOPWG dispositions are the reference, not ground truth for every TOI.
7. Measured on a stated benchmark; nothing on this leaderboard is a discovery.

## Held-out half (every held-out star)

| rank | entry | completeness, all CP/KP stars | completeness, searchable | below 4 R⊕ | FP rejection | inverted control: stars with any | scrambled control: stars with any | reliability |
|---:|---|---|---|---|---|---|---|---|
| 1 | Probes only | 57% (86/152; 49–64%) | 57% (86/150; 49–65%) | 17% (8/46; 9–31%) | 75% (93/124; 67–82%) | 21% (65/309; 17–26%) | 25% (78/309; 21–30%) | 70% (83/118; 62–78%) |

Entries:

* **Probes only** (`probes`, tuned on: none). The three Probes (Sensitive, Typical, Cautious) with their calibrated weights, sector-wide BLS, light-curve vetting and the limb-darkened fit, on each star's first SPOC 2-minute sector, as in the benchmark report. No FAP rule. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

## The Sentinels' stated subsample (40 held-out stars: 20 CP/KP, 20 FP)

| rank | entry | completeness, all CP/KP stars | completeness, searchable | below 4 R⊕ | FP rejection | inverted control: stars with any | scrambled control: stars with any | reliability |
|---:|---|---|---|---|---|---|---|---|
| 1 | Sentinel · Skeptic alone | 50% (10/20; 30–70%) | 50% (10/20; 30–70%) | 0% (0/8; 0–32%) | 80% (16/20; 58–92%) | not measured | not measured | 71% (10/14; 45–88%) |
| 1 | Sentinel · Volunteer alone | 50% (10/20; 30–70%) | 50% (10/20; 30–70%) | 0% (0/8; 0–32%) | 80% (16/20; 58–92%) | not measured | not measured | 71% (10/14; 45–88%) |
| 1 | Probes + Sentinels (either) | 50% (10/20; 30–70%) | 50% (10/20; 30–70%) | 0% (0/8; 0–32%) | 60% (12/20; 39–78%) | not measured | not measured | 56% (10/18; 34–75%) |
| 4 | Probes + Sentinels (both) | 45% (9/20; 26–66%) | 45% (9/20; 26–66%) | 0% (0/8; 0–32%) | 85% (17/20; 64–95%) | not measured | not measured | 75% (9/12; 47–91%) |
| 4 | Probes only | 45% (9/20; 26–66%) | 45% (9/20; 26–66%) | 0% (0/8; 0–32%) | 70% (14/20; 48–85%) | 8% (3/40; 3–20%) | 22% (9/40; 12–38%) | 60% (9/15; 36–80%) |

Entries:

* **Sentinel · Skeptic alone** (`claude-skeptic`, tuned on: none). One Sentinel persona (skeptic) through the Claude Code CLI on every 13-day subject of the star's real light curve. Recovered: it marked a dip on the TOI's ephemeris as a potential planet; flagged: it marked one there but called the subject noise. Not run on the controls. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Sentinel · Volunteer alone** (`claude-volunteer`, tuned on: none). One Sentinel persona (volunteer) through the Claude Code CLI on every 13-day subject of the star's real light curve. Recovered: it marked a dip on the TOI's ephemeris as a potential planet; flagged: it marked one there but called the subject noise. Not run on the controls. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Probes + Sentinels (either)** (`probes-or-sentinel`, tuned on: none). Star-level rule stated before scoring: a clean candidate when the Probes give one or either Sentinel marks the TOI's dip as a potential planet. Not a run of the panel's mark-level consensus. Controls not measured (the Sentinels never saw them). Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Probes + Sentinels (both)** (`probes-and-sentinel`, tuned on: none). Star-level rule stated before scoring: a clean candidate only when the Probes give one and either Sentinel also marks the TOI's dip as a potential planet. Not a run of the panel's mark-level consensus. Controls not measured (the Sentinels never saw them). Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.
* **Probes only** (`probes-subsample`, tuned on: none). The three Probes (Sensitive, Typical, Cautious) with their calibrated weights, sector-wide BLS, light-curve vetting and the limb-darkened fit, on each star's first SPOC 2-minute sector, as in the benchmark report. No FAP rule. Restricted to the Sentinels' 40-star subsample, so the rows below compare like with like. Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

Rank is by completeness over every CP/KP star in the scope; equal completeness shares a rank. Where two entries' intervals overlap, their order is not a measured difference. Reliability depends on the sample's class mix (the held-out searched stars are about half CP/KP); it is not the reliability on the TOI catalogue. The Sentinel entries cover 40 stars, so their intervals are wide, and they were never run on the control light curves.

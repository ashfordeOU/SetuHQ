# pi Men c: the limb-darkened fit against Huang et al. 2018

Run `runs/tess-pi-men-s1` (TESS SPOC sector 1, 10-minute bins), run on the current code (scripts/rerun_pi_men.py), with the limb-darkened
fit (`src/setuhq/transitfit.py`). 5 of 5 predicted epochs are recovered by the panel. Limb darkening:
Claret 2017 TESS quadratic u₁ = 0.341, u₂ = 0.224 for the TIC's Teff 5992 K and log g 4.36.
Reference: NASA Exoplanet Archive, table ps, pl_name = 'pi Men c', fetched 2026-10-19 (`docs/results/pi_men_reference.json`).

## Joint fit of every recovered epoch

Two lines. **Free**: depth, T14 and k are robust; b, a/R★ and ρ★ are degenerate with five TESS transits, so b
is an upper limit when its 1σ set reaches 0 and ρ★ is a range. **With the TIC density prior** (a Gaussian on ρ★,
1.023 ± 0.199 g/cm³): b, a/R★ and T23/T14, to compare with Huang's b = 0.59.
Like-for-like comparisons lead: k and T14.

| quantity | free | with the TIC density prior | Huang et al. 2018 | ratio (free / Huang) | archive default (Kunovac Hodzic Et Al 2021) | ratio |
|---|---:|---:|---:|---:|---:|---:|
| Rp/R★ (k) | 0.0179 ± 0.0017 | 0.0165 ± 0.0005 | 0.01703 | **1.05** | 0.01584 | 1.13 |
| T14 (h) | 3.07 ± 0.17 | 2.96 ± 0.04 | 2.953 | **1.04** | 2.952 | 1.04 |
| depth (ppm)¹ | 292 ± 8 | 293 ± 8 | 300 | 0.97 | 268 | 1.09 |
| P (d), fitted near the BLS period | 6.2680 ± 0.0005 | 6.2680 | 6.26790 | | | |
| b | b < 0.87 (1σ) | b = 0.64 ± 0.12 | 0.59 | | 0.65 | |
| a/R★ | 8.54 at the best-fit b, unconstrained (1σ 8.32–16.64) | 12.85 (1σ 11.54–13.58) | 13.38 | | | |
| T23/T14 | unconstrained | 0.95 | 0.95 (from Huang's b, k, a/R★) | | | |
| ρ★ transit (g/cm³) | 1σ range 0.277–2.216 | 1.02 (prior-dominated; no error quoted, as it would only restate the prior's) | 1.159 from M★, R★ | | | |

¹ Depth definitions differ: SetuHQ's is the limb-darkened model's depth at mid-transit; the archive's `pl_trandep` is the published transit depth as each paper defines it. Compare k and T14 first.

Errors are conservative: the covariance at the best fit (scaled by √χ²ᵣ when above 1) added in quadrature to the spread along the impact-parameter profile (Δχ² ≤ 1), which overlap.

The box measure used before (the mean flux over the panel's marked window): depth 243 ppm, duration 1.90 h, ratios **0.81** and **0.64** against Huang 2018 (0.91 and 0.64 against the archive default row the README used to cite).

ρ★ check (free fit): the transit density against the TIC's 1.023 g/cm³ (consistent within the illustrative 0.3–3 band at 3σ). V-shape test: U-shaped (not grazing).

## The pipeline's own fits (one joint fit per 13-day subject)

| subject | epochs | P (d) | depth (ppm) | T14 (h) | b | ρ★ (g/cm³), 1σ range |
|---|---:|---:|---:|---:|---:|---:|
| tess-fa3483ce6f83 | 3 | 6.2681 | 294 ± 10 | 3.17 ± 0.25 | b < 0.94 (1σ) | 0.091–2.249 |
| tess-04b815001aa6 | 2 | 6.2674 | 310 ± 14 | 2.97 ± 0.09 | b < 0.87 (1σ) | 0.270–2.124 |

Depth is the model's mid-transit depth; errors are conservative, as above. Each subject's fit frees the period near that subject's BLS period.

## Ephemeris recovery (recorded earlier)

Recorded by `scripts/validate_known_planets.py` at commit 0f6dbdc from a live query of the archive's default row
then. Its timing columns stand; its depth and duration ratios came from the box measure and are superseded by
the fit above.

| planet | P (d) | predicted epochs in span | recovered | mean timing offset (min) | depth ratio (box) | duration ratio (box) |
|---|---:|---:|---:|---:|---:|---:|
| pi Men c | 6.26784 | 5 | 5 | -8.0 | 0.91 | 0.62 |

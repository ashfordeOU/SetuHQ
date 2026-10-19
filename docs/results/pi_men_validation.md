# pi Men c: the limb-darkened fit against Huang et al. 2018

Run `runs/tess-pi-men-s1` (TESS SPOC sector 1, 10-minute bins), rebuilt from its stored classifications with the limb-darkened
fit (`src/exoplan/transitfit.py`). 5 of 5 predicted epochs are recovered by the panel. Limb darkening:
Claret 2017 TESS quadratic u₁ = 0.341, u₂ = 0.224 for the TIC's Teff 5992 K and log g 4.36.
Reference: NASA Exoplanet Archive, table ps, pl_name = 'pi Men c', fetched 2026-10-19 (`docs/results/pi_men_reference.json`).

## Joint fit of every recovered epoch

| quantity | exoplan (this fit) | Huang et al. 2018 | ratio | archive default (Kunovac Hodzic Et Al 2021) | ratio |
|---|---:|---:|---:|---:|---:|
| depth (ppm) | 292 ± 8 | 300 | **0.97** | 268 | 1.09 |
| T14 (h) | 3.07 ± 0.17 | 2.953 | **1.04** | 2.952 | 1.04 |
| Rp/R★ | 0.0179 ± 0.0017 | 0.01703 | 1.05 | 0.01584 | 1.13 |
| b | 0.86 (1σ 0.00–0.87) | 0.59 | | 0.65 | |
| a/R★ | 8.48 | 13.38 | | | |
| ρ★ transit (g/cm³) | 0.294 (1σ 0.278–2.220) | 1.159 from M★, R★ | | | |
| T23/T14 | 0.87 | 0.95 (ATLAS E4) | | | |

The box measure used before (the mean flux over the panel's marked window): depth 243 ppm, duration 1.90 h, ratios **0.81** and **0.64** against Huang 2018 (0.91 and 0.64 against the archive default row the README used to cite).

ρ★ check: the transit density against the TIC's 1.023 g/cm³ (consistent within the illustrative 0.3–3 band at 3σ). V-shape test: U-shaped (not grazing).

## The pipeline's own fits (one joint fit per 13-day subject)

| subject | epochs | depth (ppm) | T14 (h) | b | ρ★ (g/cm³) |
|---|---:|---:|---:|---:|---:|
| tess-fa3483ce6f83 | 3 | 297 ± 11 | 3.36 ± 0.15 | 0.95 | 0.068 |
| tess-04b815001aa6 | 2 | 309 ± 14 | 3.17 ± 0.22 | 0.91 | 0.161 |

Depth is the model's mid-transit depth. Errors combine the covariance at the best fit with the spread
along the impact-parameter profile (b is weakly constrained by five TESS transits).

## Ephemeris recovery (recorded earlier)

Recorded by `scripts/validate_known_planets.py` at commit 0f6dbdc from a live query of the archive's default row
then. Its timing columns stand; its depth and duration ratios came from the box measure and are superseded by
the fit above.

| planet | P (d) | predicted epochs in span | recovered | mean timing offset (min) | depth ratio (box) | duration ratio (box) |
|---|---:|---:|---:|---:|---:|---:|
| pi Men c | 6.26784 | 5 | 5 | -8.0 | 0.91 | 0.62 |

# pi Men (TIC 261136679), TESS sector 1: S2 extended and pixel-level vetting

Made 2026-10-20T13:03:21+00:00 by `scripts/vet_pi_men_s2.py` from the SPOC files `tess2018206045859-s0001-0000000261136679-0120-s_lc.fits` and `tess2018206045859-s0001-0000000261136679-0120-s_tp.fits` (sha256 0145804d17a9…). MAST's search service was failing on 2026-10-19; the files came from the public STScI bucket that MAST's download links redirect to. Every test below only adds flags; none changes a pass/fail decision by default.

Ephemeris from a joint limb-darkened fit of all 5 sector-1 epochs: P = 6.26795 ± 0.00049 d, T0 = 1338.0394 BTJD, T14 = 3.09 ± 0.16 h, depth 300 ± 8 ppm.

## Light-curve tests

On the light curve re-detrended with the fitted transits masked (1.5 T14 each side), as DV does, and phase 0.5 masked too (masked phases: 0.500; the first pass's strongest dip is masked only when that pass already finds it significant).

| test | result | flag |
|---|---|---|
| crowding | CROWDSAP = 0.9997, FLFRCSAP = 0.9800 (flag below 0.8) | none |
| secondary, all phases | strongest dip at phase 0.622: 41.6 ± 7.4 ppm (5.6σ; largest brightening 4.8σ; 187 coarse positions); threshold 6.9σ (5.16 × max(1, the scan's robust spread) (white-noise 99.9% quantile for 187 positions); robust spread 1.33); 4 epochs, the largest carrying 86% (not periodic); at phase 0.5: -12.1 ± 7.2 ppm | none at the default setting; **secondary at threshold; flag setting-dependent (3 of 12 settings flag it)** |
| odd/even depth (per-epoch fits (transit shape plus a local baseline)) | odd 301 ± 14 ppm (n = 2), even 311 ± 12 ppm (n = 3): 0.5σ | none |
| timing, linear ephemeris | 5 epochs, χ² = 1.9 for 3 dof, p = 0.593; O−C (min): 0.3, -1.5, 1.8, 0.5, -0.8 | none |
| odd/even timing | odd − even offset -0.9 ± 1.6 min (0.5σ) | none |

### The secondary flag across run settings

The same two-pass preparation and secondary test on nearby run settings (the run's detrend window × bin size; the vetting window is never below 12 T14 = 1.55 d, so every window up to that gives the same light curve). 3 of 12 settings flag the dip: **secondary at threshold; flag setting-dependent (3 of 12 settings flag it)**. 12 settings = 2 distinct vetting windows (1.547, 2 d; every run window up to 12 T14 collapses to the first) x 6 bin sizes. They share the same data, so they are 12 correlated settings, not 12 independent trials.

| window (d) | vetting window (d) | bin (min) | first pass | masked phases | strongest dip | threshold | dip / threshold | epochs: largest share | flag |
|---|---|---|---|---|---|---|---|---|---|
| 1.0 | 1.55 | 2 | 5.46σ | 0.500 | 5.34σ at 0.645 | 7.83σ | 0.682 | 46% | none |
| 1.0 | 1.55 | 6 | 6.01σ | 0.500 | 5.93σ at 0.645 | 7.37σ | 0.804 | 40% | none |
| 1.0 | 1.55 | 10 | 5.79σ | 0.500 | 5.64σ at 0.622 | 6.87σ | 0.821 | 86% (not periodic) | none |
| 1.0 | 1.55 | 15 | 6.81σ (significant) | 0.500, 0.637 | 7.81σ at 0.637 | 7.24σ | 1.079 | 43% | secondary_any_phase |
| 1.0 | 1.55 | 20 | 6.58σ | 0.500 | 6.39σ at 0.741 | 6.09σ | 1.050 | 90% (not periodic) | none |
| 1.0 | 1.55 | 30 | 7.61σ (significant) | 0.500, 0.635 | 8.60σ at 0.635 | 7.20σ | 1.195 | 53% | secondary_any_phase |
| 2.0 | 2.00 | 2 | 5.82σ | 0.500 | 6.17σ at 0.645 | 8.25σ | 0.747 | 48% | none |
| 2.0 | 2.00 | 6 | 6.22σ | 0.500 | 6.66σ at 0.645 | 7.52σ | 0.885 | 43% | none |
| 2.0 | 2.00 | 10 | 5.77σ | 0.500 | 6.36σ at 0.643 | 7.95σ | 0.800 | 42% | none |
| 2.0 | 2.00 | 15 | 6.88σ | 0.500 | 7.05σ at 0.637 | 7.61σ | 0.927 | 46% | none |
| 2.0 | 2.00 | 20 | 5.69σ | 0.500 | 5.80σ at 0.622 | 7.07σ | 0.820 | 82% (not periodic) | none |
| 2.0 | 2.00 | 30 | 7.38σ | 0.500 | 7.89σ at 0.635 | 7.48σ | 1.054 | 59% | secondary_any_phase |

## Pixel-level tests

Difference image over 5 transits (344 in-transit and 904 out-of-transit cadences; errors scaled ×1.13 by the scatter between transits). Pixel scale 19.58″ from the TPF's WCS. Depth in the aperture pixels: 291 ppm.

| measure | offset | significance | note |
|---|---|---|---|
| PSF fit to the difference image, from the catalogue position | 2.047 px = 40.1″ (column -0.740, row -1.908) | 2.3σ | systematic floor 0.731 px |
| PSF fit, from the out-of-transit centroid (DV 'control') | 2.243 px = 43.9″ (column -0.089, row -2.242) | 14.6σ | fit quality 0.78 (reliable above 0.7) |
| flux-weighted, inside the aperture | 0.322 px = 6.3″ | 9.5σ | |
| centroid motion (per cadence) | shift (-0.07, -0.62) millipixel; source offset 42.2″ | 0.1σ (χ²₂ = 0.1) | uninformative on a saturated star |

Saturation: yes (5 contiguous pixels within 5% of the brightest in column 5; Tmag 5.11). Centroid reliable: **no** (saturated: a 5-pixel plateau in column 5; difference-image PSF width at its 0.3 px bound; difference and out-of-transit PSF widths differ by 3.4x (> 2x)).

Ghost diagnostic: core 32.0, halo 3.2. Momentum dumps: 70 in the sector, 0 within half a duration of a transit.

Pixel flags: saturated, centroid_unreliable. Light-curve flags: none.

## Nearby stars

Source: TIC v8.2 (MAST), within 150″. Depth in the aperture 300 ppm (PDCSAP depth × CROWDSAP); a star more than 8.81 mag fainter than the target cannot produce it even with a total eclipse if all its light fell in the aperture. Gaussian PSF σ = 1.0 px (an approximation).

| star | Tmag | separation | share of aperture flux | needed depth | ruled out |
|---|---|---|---|---|---|
| TIC 261136679 | 5.11 | 0.0″ | 1.00e+00 | 3.00e-04 | no |
| TIC 261139070 | 12.22 | 112.9″ | 2.83e-05 | 1.06e+01 | needs a depth above 100% |
| TIC 261139071 | 13.99 | 27.4″ | 2.70e-04 | 1.11e+00 | needs a depth above 100% (marginal: within 3σ of its Tmag uncertainty, ±0.75 mag) |
| TIC 10001480022 | 14.74 | 116.1″ | 4.87e-06 | 6.16e+01 | needs a depth above 100% |
| TIC 261139061 | 15.15 | 106.3″ | 5.32e-06 | 5.64e+01 | needs a depth above 100% |
| TIC 261136670 | 15.62 | 110.2″ | 2.07e-06 | 1.45e+02 | needs a depth above 100% |
| TIC 261136680 | 15.71 | 96.7″ | 4.48e-06 | 6.70e+01 | needs a depth above 100% |
| TIC 261136674 | 16.20 | 118.4″ | 9.59e-07 | 3.13e+02 | needs a depth above 100% |
| TIC 261139082 | 16.45 | 125.0″ | 1.11e-08 | 2.71e+04 | needs a depth above 100% |
| TIC 261139074 | 16.64 | 74.3″ | 6.71e-06 | 4.47e+01 | needs a depth above 100% |
| TIC 261139065 | 16.77 | 113.3″ | 5.25e-07 | 5.71e+02 | needs a depth above 100% |
| TIC 261136676 | 17.12 | 40.8″ | 1.47e-05 | 2.03e+01 | needs a depth above 100% |
| TIC 261136683 | 17.19 | 67.8″ | 6.46e-06 | 4.65e+01 | needs a depth above 100% |
| TIC 261139063 | 17.22 | 107.3″ | 6.24e-07 | 4.81e+02 | needs a depth above 100% |
| TIC 261136685 | 17.30 | 88.6″ | 1.13e-06 | 2.66e+02 | needs a depth above 100% |
| … 41 more | | | | | |

## S3: reduced FPP (exoplan's scheme, not TRICERATOPS)

FPP not computed: unstable across 5 detrending settings and two noise models (range 0.00788–0.0931): refused (odds spread 12.9×; 10× allowed). Label: **not validated: no contrast curve**.

Stability: the FPP was computed on 5 detrending settings (the default and windows ×0.75 and ×1.5 with masks of 1.0 and 2.0 T14) under two noise models: range 0.0079–0.0931, median 0.0086 at the robust spread; 2 of 5 settings pass the white-noise gate.

Wider grid (absolute windows 0.75–2 d × masks 1.0/1.5/2.0 T14): the white-noise gate passes on 6 of 15 settings; where it passes, FPP 0.007–0.164 (with both noise models on every setting, 0.007–0.989); the largest brightening is 2.6–6.2σ.

| window (d) | mask (T14) | gate | largest brightening | strongest dip | FPP (robust spread) |
|---|---|---|---|---|---|
| 0.75 | 1.0 | not white | 2.6σ | 6.3σ | n/a |
| 0.75 | 1.5 | white | 2.6σ | 6.4σ | 0.0073 |
| 0.75 | 2.0 | not white | 3.1σ | 6.3σ | n/a |
| 1.0 | 1.0 | white | 3.3σ | 5.7σ | 0.0087 |
| 1.0 | 1.5 | white | 6.2σ | 5.8σ | 0.0079 |
| 1.0 | 2.0 | white | 2.9σ | 5.8σ | 0.0077 |
| 1.25 | 1.0 | white | 3.3σ | 5.5σ | 0.1019 |
| 1.25 | 1.5 | white | 5.8σ | 5.6σ | 0.1642 |
| 1.25 | 2.0 | not white | 2.6σ | 5.5σ | n/a |
| 1.5 | 1.0 | not white | 3.2σ | 5.5σ | n/a |
| 1.5 | 1.5 | not white | 5.3σ | 5.7σ | n/a |
| 1.5 | 2.0 | not white | 3.0σ | 5.5σ | n/a |
| 2.0 | 1.0 | not white | 3.3σ | 6.3σ | n/a |
| 2.0 | 1.5 | not white | 4.4σ | 6.6σ | n/a |
| 2.0 | 2.0 | not white | 3.2σ | 6.6σ | n/a |

Not modelled: unresolved bound companions (HEB, planet on a companion); unresolved background stars (BEB, planet on a background star). Notes: no reliable difference-image centroid: positions carry no information; 1 neighbour(s) excluded only marginally (within 3σ of the Tmag uncertainty of reaching the depth); FPP not computed: unstable across 5 detrending settings and two noise models (range 0.00788–0.0931): refused (odds spread 12.9×; 10× allowed). Priors: illustrative: a 25% false-positive total (Guerrero et al. 2021, TOIs) split 10/5/10 between EB, EBx2P and nearby stars by choice.

## SPOC's own DV centroid result, for comparison

* TOI 144.01: offset from the TIC position 40.5 ± 0.1″ (row -2.075 px, column 0.024 px); DV quality metric 0.58 (DV counts above 0.7 as reliable).

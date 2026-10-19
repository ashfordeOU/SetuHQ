# pi Men (TIC 261136679), TESS sector 1: S2 extended and pixel-level vetting

Made 2026-10-19T18:12:53+00:00 by `scripts/vet_pi_men_s2.py` from the SPOC files `tess2018206045859-s0001-0000000261136679-0120-s_lc.fits` and `tess2018206045859-s0001-0000000261136679-0120-s_tp.fits` (sha256 0145804d17a9…). MAST's search service was failing on 2026-10-19; the files came from the public STScI bucket that MAST's download links redirect to. Every test below only adds flags; none changes a pass/fail decision by default.

Ephemeris from a joint limb-darkened fit of all 5 sector-1 epochs: P = 6.26795 ± 0.00049 d, T0 = 1338.0394 BTJD, T14 = 3.09 ± 0.16 h, depth 300 ± 8 ppm.

## Light-curve tests

| test | result | flag |
|---|---|---|
| crowding | CROWDSAP = 0.9997, FLFRCSAP = 0.9800 (flag below 0.8) | none |
| secondary, all phases | strongest dip at phase 0.742: 41.3 ± 7.4 ppm (5.6σ; largest brightening 8.8σ; 187 coarse positions); threshold 5.2σ (4.09 × the scan's robust spread (look-elsewhere over 47 positions); robust spread 1.27); 4 epochs, the largest carrying 83% (not periodic); at phase 0.5: -5.9 ± 7.2 ppm | none |
| odd/even depth (box mean over T14) | odd 216 ± 10 ppm (n = 2), even 205 ± 8 ppm (n = 3): 0.8σ | none |
| timing, linear ephemeris | 5 epochs, χ² = 1.6 for 3 dof, p = 0.660; O−C (min): 0.3, -1.4, 1.7, 0.5, -0.8 | none |
| odd/even timing | odd − even offset -0.8 ± 1.7 min (0.5σ) | none |

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

FPP = 0.1716, NFPP = 0.000000; class: likely planet (by number, reduced scheme). Label: **not validated: no contrast curve**.

Not modelled: unresolved bound companions (HEB, planet on a companion); unresolved background stars (BEB, planet on a background star). Notes: no reliable difference-image centroid: positions carry no information; 1 neighbour(s) excluded only marginally (within 3σ of the Tmag uncertainty of reaching the depth). Priors: illustrative: a 25% false-positive total (Guerrero et al. 2021, TOIs) split 10/5/10 between EB, EBx2P and nearby stars by choice.

## SPOC's own DV centroid result, for comparison

* TOI 144.01: offset from the TIC position 40.5 ± 0.1″ (row -2.075 px, column 0.024 px); DV quality metric 0.58 (DV counts above 0.7 as reliable).

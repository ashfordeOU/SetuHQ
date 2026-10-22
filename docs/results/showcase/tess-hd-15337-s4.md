# HD 15337 against the literature

*Small planets near the limit.* A bright K dwarf with two small known planets: b (about 1.6 Earth radii, 4.8 days, roughly 350 ppm deep) and c (17.2 days).

Run `runs/tess-hd-15337-s4` (TESS SPOC 2-minute, sector 4; config `configs/showcase/tess-hd-15337-s4.toml`, sha256 `e21c63a794b2aeb3…`; code `v0.1.0-6-g2bf0522`). Light curves: public TESS data from MAST `tess2018292075959-s0004-0000000120896927-0124-s_lc.fits` (sha256 `a0d03d3e07a18ab1…`).

**Probes only; Sentinels not run on this example.** 3 dips (2 candidates, 1 flagged).

A small planet whose single transits are near the noise of one sector: it shows what the panel and vetting do at the edge of what a 10-minute-binned search can see, and the page says what it missed.

## Against the discovery paper

Published values: NASA Exoplanet Archive, table ps (every row for each planet), fetched 2026-10-22 (`docs/results/showcase_reference.json`). Each planet's transits are predicted from the archive row named below; SetuHQ's values are the medians over the dips on that ephemeris that were not rejected (the limb-darkened fit's Rp/R★, T14 and mid-transit depth, and the BLS period). Depth definitions differ between papers and this fit, so compare Rp/R★ and T14 first. A blank published value is one the archive does not hold for that paper; it is not compared.

### HD 15337 b

Ephemeris from Rosário et al. 2024; compared with Gandolfi et al. 2019 (https://ui.adsabs.harvard.edu/abs/2019ApJ...876L..24G/abstract).

| quantity | SetuHQ | Gandolfi et al. 2019 | ratio | archive default (Rosário et al. 2024) | ratio |
|---|---:|---:|---:|---:|---:|
| P (d) | 5.97872 | 4.75615 | 1.257 | 4.75598 | 1.257 |
| Rp/R★ | 0.0246 | 0.0176 | 1.397 | 0.0190 | 1.296 |
| T14 (h) | 2.36 | 2.49 | 0.949 |  |  |
| depth (ppm) | 536 |  |  |  |  |

The BLS period stored on these dips (5.9787 d) is not this planet's: within a 13-day subject the search paired dips that belong to different transits (another planet's, or an alias), so the period ratio is a miss, not a recovery, and the fit that used it (Rp/R★, depth) is less reliable than its T14. The dips sit on the published ephemeris; the period does not.

Transits predicted in the stored light curve: 5; with a dip on them: 1 (1 dip; 1 passed; mean offset -3.2 min).

### HD 15337 c

Ephemeris from Rosário et al. 2024; compared with Gandolfi et al. 2019 (https://ui.adsabs.harvard.edu/abs/2019ApJ...876L..24G/abstract).

| quantity | SetuHQ | Gandolfi et al. 2019 | ratio | archive default (Rosário et al. 2024) | ratio |
|---|---:|---:|---:|---:|---:|
| P (d) | 4.0429, 5.9787 (one per dip, BLS; not one period) | 17.17840 |  | 17.18055 |  |
| Rp/R★ | 0.0238 | 0.0256 | 0.931 | 0.0271 | 0.880 |
| T14 (h) | 2.27 | 2.25 | 1.007 |  |  |
| depth (ppm) | 588 |  |  |  |  |

The BLS period stored on these dips (4.0429, 5.9787 d) is not this planet's: within a 13-day subject the search paired dips that belong to different transits (another planet's, or an alias), so the period ratio is a miss, not a recovery, and the fit that used it (Rp/R★, depth) is less reliable than its T14. The dips sit on the published ephemeris; the period does not.

Transits predicted in the stored light curve: 2; with a dip on them: 2 (2 dips; 1 passed, 1 flagged; mean offset +0.7 min).

A known planet found again is a check of the pipeline, not a discovery. HD 15337 b: 1 of 5 transits (1 candidate; BLS period not the planet's); HD 15337 c: 2 of 2 transits (1 candidate, 1 flagged; BLS period not the planet's).


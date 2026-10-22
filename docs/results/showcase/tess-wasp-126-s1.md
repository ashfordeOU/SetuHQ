# WASP-126 against the literature

*Hot Jupiter.* A Jupiter-sized planet on a 3.3-day orbit: deep, easy transits, in the TESS southern continuous viewing zone.

Run `runs/tess-wasp-126-s1` (TESS SPOC 2-minute, sector 1; config `configs/showcase/tess-wasp-126-s1.toml`, sha256 `23bb51a268efd59e…`; code `v0.1.0-3-g0c029a2`). Light curves: public TESS data from MAST `tess2018206045859-s0001-0000000025155310-0120-s_lc.fits` (sha256 `12ddd623b04bdd35…`).

**Probes only; Sentinels not run on this example.** 8 dips (8 candidates).

The easy case: a transit about 0.6% deep that any search should find, so it shows the whole path from light curve to fit with little doubt about the signal.

## Against the discovery paper

Published values: NASA Exoplanet Archive, table ps (every row for each planet), fetched 2026-10-22 (`docs/results/showcase_reference.json`). Each planet's transits are predicted from the archive row named below; SetuHQ's values are the medians over the dips on that ephemeris that were not rejected (the limb-darkened fit's Rp/R★, T14 and mid-transit depth, and the BLS period). Depth definitions differ between papers and this fit, so compare Rp/R★ and T14 first. A blank published value is one the archive does not hold for that paper; it is not compared.

### WASP-126 b

Ephemeris from Ivshina & Winn 2022; compared with Maxted et al. 2016 (https://ui.adsabs.harvard.edu/abs/2016A&A...591A..55M/abstract).

| quantity | SetuHQ | Maxted et al. 2016 | ratio | archive default (Pearson 2019) | ratio |
|---|---:|---:|---:|---:|---:|
| P (d) | 3.28895 | 3.28880 | 1.000 | 3.28883 | 1.000 |
| Rp/R★ | 0.0780 |  |  | 0.0780 | 1.000 |
| T14 (h) | 3.48 | 3.41 | 1.021 |  |  |
| depth (ppm) | 7,056 |  |  |  |  |

Transits predicted in the stored light curve: 8; with a dip on them: 8 (8 dips; 8 passed; mean offset -14.7 min).

A known planet found again is a check of the pipeline, not a discovery. 1 of 1 known planet has dips on its published ephemeris: WASP-126 b, 8 of 8 transits (8 candidates).


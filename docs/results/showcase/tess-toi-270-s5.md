# TOI-270 against the literature

*Multi-planet system.* An M dwarf with three known transiting planets at 3.4, 5.7 and 11.4 days: several periods in one star.

Run `runs/tess-toi-270-s5` (TESS SPOC 2-minute, sector 5; config `configs/showcase/tess-toi-270-s5.toml`, sha256 `e60af3c4e98d4a76…`; code `v0.1.0-3-g0c029a2`). Light curves: public TESS data from MAST `tess2018319095959-s0005-0000000259377017-0125-s_lc.fits` (sha256 `739250df0d1ccda4…`).

**Probes only; Sentinels not run on this example.** 7 dips (5 candidates, 2 flagged).

One light curve, three periods. It shows what the search does when a star has more than one planet, and which of them a 13-day subject can hold.

## Against the discovery paper

Published values: NASA Exoplanet Archive, table ps (every row for each planet), fetched 2026-10-22 (`docs/results/showcase_reference.json`). Each planet's transits are predicted from the archive row named below; SetuHQ's values are the medians over the dips on that ephemeris that were not rejected (the limb-darkened fit's Rp/R★, T14 and mid-transit depth, and the BLS period). Depth definitions differ between papers and this fit, so compare Rp/R★ and T14 first. A blank published value is one the archive does not hold for that paper; it is not compared.

### TOI-270 b

Ephemeris from Kaye et al. 2022; compared with Günther et al. 2019 (https://ui.adsabs.harvard.edu/abs/2019NatAs...3.1099G/abstract).

| quantity | SetuHQ | Günther et al. 2019 | ratio | archive default (Kaye et al. 2022) | ratio |
|---|---:|---:|---:|---:|---:|
| P (d) | n/a | 3.36008 |  | 3.35992 |  |
| Rp/R★ | n/a | 0.0300 |  | 0.0307 |  |
| T14 (h) | n/a | 1.39 |  | 1.29 |  |
| depth (ppm) | n/a | 901 |  |  |  |

The panel marked no dip on this planet's transits in this run, so nothing is compared.

Transits predicted in the stored light curve: 6; with a dip on them: 0 (0 dips; none).

### TOI-270 c

Ephemeris from Kaye et al. 2022; compared with Günther et al. 2019 (https://ui.adsabs.harvard.edu/abs/2019NatAs...3.1099G/abstract).

| quantity | SetuHQ | Günther et al. 2019 | ratio | archive default (Kaye et al. 2022) | ratio |
|---|---:|---:|---:|---:|---:|
| P (d) | 5.65610 | 5.66017 | 0.999 | 5.66051 | 0.999 |
| Rp/R★ | 0.0659 | 0.0583 | 1.132 | 0.0560 | 1.177 |
| T14 (h) | 1.85 | 1.66 | 1.117 | 1.68 | 1.101 |
| depth (ppm) | 4,090 | 3,394 | 1.205 |  |  |

Transits predicted in the stored light curve: 5; with a dip on them: 5 (5 dips; 5 passed; mean offset +6.6 min).

### TOI-270 d

Ephemeris from Kaye et al. 2022; compared with Günther et al. 2019 (https://ui.adsabs.harvard.edu/abs/2019NatAs...3.1099G/abstract).

| quantity | SetuHQ | Günther et al. 2019 | ratio | archive default (Kaye et al. 2022) | ratio |
|---|---:|---:|---:|---:|---:|
| P (d) | n/a | 11.38014 |  | 11.38194 |  |
| Rp/R★ | 0.0598 | 0.0514 | 1.163 | 0.0491 | 1.218 |
| T14 (h) | 2.50 | 2.15 | 1.162 | 2.12 | 1.180 |
| depth (ppm) | 3,254 | 2,645 | 1.230 |  |  |

Each 13-day subject holds only one of its transits, so the search found no period for these dips; vetting flags each `off_ephemeris` (open, not a candidate). The period is not compared.

Transits predicted in the stored light curve: 2; with a dip on them: 2 (2 dips; 2 flagged; mean offset -8.8 min).

A known planet found again is a check of the pipeline, not a discovery. TOI-270 b: none of 6 transits; TOI-270 c: 5 of 5 transits (5 candidates); TOI-270 d: 2 of 2 transits (2 flagged; no period).


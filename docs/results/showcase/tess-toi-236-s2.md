# TOI-236 against the literature

*Known false positive.* A TESS Object of Interest the TOI table dispositions as a false positive (FP): a 2.4% dip every 4.5 days.

Run `runs/tess-toi-236-s2` (TESS SPOC 2-minute, sector 2; config `configs/showcase/tess-toi-236-s2.toml`, sha256 `eef6f1318b3b1dac…`; code `v0.1.0-3-g0c029a2`). Light curves: public TESS data from MAST `tess2018234235059-s0002-0000000009727392-0121-s_lc.fits` (sha256 `35374d1f753db7ea…`).

**Probes only; Sentinels not run on this example.** 6 dips (6 rejected).

A test SetuHQ must fail to pass: TOI-236.01 is in the real-TOI benchmark's false-positive set. The page says what the vetting did with it, whatever it did.

## The TOI table's values, and what SetuHQ did

Source: NASA Exoplanet Archive, table toi, fetched 2026-10-19 (the real-TOI benchmark's frozen sample, sha256 6f0e111ec8d2c38d…).

| quantity | TOI table | SetuHQ |
|---|---:|---:|
| disposition | FP | Caught: all 6 dips on the TOI ephemeris were rejected by vetting (secondary_any_phase, secondary_eclipse), so none is a candidate. |
| period (d) | 4.53445 | 4.5358 (BLS) |
| depth (ppm) | 23,575 | 17,478 (box); 23,280 / 23,501 (fit, per signal) |
| Rp/R★ | | 0.1411 / 0.1418 (fit, per signal) |
| T14 (h) | 4.94 | 4.96 (fit) |
| transits predicted in the data / with a dip | 6 | 6 |
| dips on the ephemeris, by vetting outcome | | 6 rejected |
| vetting flags on those dips | | `secondary_any_phase`, `secondary_eclipse` |
| secondary eclipse at phase 0.5, SNR (vetting's search) | | 10.9 |


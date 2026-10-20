# Research notes: Planet Hunters CHEOPS and how SetuHQ maps onto it

This file is the deep dive behind the project. It separates what is confirmed on the
project page or in papers from what is inferred, so each design choice can be checked.

## 1. What the project is

[Planet Hunters CHEOPS](https://www.zooniverse.org/projects/bmerin/planet-hunters-cheops)
is a Zooniverse citizen-science project. Partners listed on the page are the Adler
Planetarium, the University of Minnesota and the University of Oxford. The researcher
who wrote the project message is Bruno Merín. The page does not name a principal
investigator explicitly.

Stated goal: find exoplanet candidates in CHEOPS light curves that, according to the
page, "has never been examined in detail to our knowledge". The page says CHEOPS is
mainly used to characterise known planets, and that its data may contain shallow
transits from small, Earth-sized worlds and multi-planet signals that automated
methods miss.

Data (per the page): light curves extracted from "thousands of background sources"
over "over five years of public observations". The page names no archive and no
target stars.

Volunteer task (per the page): "Inspect star brightness plots for dips signaling
transits. Mark the dip's start and end, then classify the signal as a potential
planet or noise. Submit your findings." Two labels: `potential planet` and `noise`.
The page links workflow 32667 but gives no further steps. Each target is reviewed by
"many volunteers", and the page says "thousands of classifications per target" are
needed. Activity on the page at the time of research: 0 all-time classifications and
2% complete.

## 2. The method of the closest published Planet Hunters projects

The CHEOPS project page does not describe its aggregation. The closest documented
methods are the Planet Hunters TESS and NGTS projects, which use the same
Zooniverse-style marking workflow.

* **Marking and redundancy.** Volunteers mark times of possible transit-like dips with
  the mouse. Each light curve is seen by several independent classifiers, reported as
  between 8 and 15 volunteers. Source: [Planet Hunters TESS II, arXiv:2011.13944](https://ar5iv.arxiv.org/html/2011.13944).
* **Aggregation.** Marks are merged with a density-based clustering method. The
  clustered events are ranked, and the top events are vetted by the science team.
  Source: the same paper.
* **Scoring.** A transit score combines the number of volunteers who flagged an event
  with per-user weights. The weights come from a calibration step where simulated
  transits are injected and each volunteer's skill is measured. Source: the same paper.
* **Scale and yield.** Over 22,000 volunteers inspected the first 26 TESS sectors. The
  team recovers 85% of TOIs with radii above 4 Earth radii. Source: the same paper.
* **NGTS.** [Planet Hunters NGTS, arXiv:2404.15395](https://arxiv.org/abs/2404.15395) uses
  138,198 light curves from NGTS Public Data Releases 1 and 2. Over 8,000 volunteers
  took part. The project uses "a user weighting scheme to combine the classifications
  of multiple users". It recovered 74% of confirmed NASA Exoplanet Archive planets and
  63% of TESS Objects of Interest that NGTS detects, and highlights five short-period
  giant-planet candidates.
* **Original Kepler project.** Volunteers saw a single 33.5-day quarter per star. Each
  segment was reviewed by 5 to 10 volunteers.

Planet Hunters' distinctive strength is single transits, the one-off dips that
periodic searches miss. That is why the design keeps a single-event channel as well
as a periodic one.

## 3. CHEOPS data: what is confirmed

From [ESA's CHEOPS guest-observer pages](https://cosmos.esa.int/web/cheops-guest-observers-programme/data-and-analysis)
and the [CHEOPS mission archive](https://cheops.unige.ch/archive_browser/):

* Data are processed centrally at ESA's Science Operations Centre. The DRP
  (data reduction pipeline) is not released to users. Its description is in
  [Hoyer et al. 2020, arXiv:1909.08363](https://arxiv.org/pdf/1909.08363).
* Public data are free to access. Proprietary periods last up to 18 months.
* The main light-curve product is `SCI_COR_Lightcurve`, one file per photometric aperture.
  The levels run from Level 0 to Level 2, and Level 2 light curves are the final data product.
* The Data Analysis Center for Exoplanets (dace.unige.ch) hosts public GTO data.
* Community tools: [pycheops](https://github.com/pycheops), [linea](https://linea.readthedocs.io/),
  and PIPE, a third-party PSF photometry package by Alexis Brandeker.
* The pre-launch DRP paper notes that deviations from expected performance can come
  from smear trails of background stars, cosmic rays and background contamination.

**Not confirmed:** the exact column names of `SCI_COR_Lightcurve` and the meaning of
its data-flag values. Community tools name them differently. The loader therefore
accepts several candidate names (`BJD_TIME`/`TIME`, `FLUX`, `FLUXERR`/`FLUX_ERR`,
`DATA_FLAG`/`FLAG`) and records which ones it used in the run provenance. Confirm
them against a real product before relying on CHEOPS results. This environment could
not download a CHEOPS file to check.

## 4. What the workflow is, in engineering terms

| Stage | Planet Hunters | SetuHQ |
|---|---|---|
| Input | Light curves prepared by the team | TESS SPOC via MAST, CHEOPS FITS, CSV |
| Preparation | Not public | Spike clip, masked local-quadratic detrend, 10-min bins |
| Units shown to reviewers | Segments of a light curve | Fixed 13-day subjects with opaque IDs |
| Blinding | Not described | Target name never reaches a reviewer |
| Review | Human volunteers, several each | Panel of reviewers: simulated detectors and Claude |
| Labels | potential planet / noise | Same two labels, plus a noise reason |
| Aggregation | Clustering and user-weighted score | Single-linkage clustering, skill-weighted score |
| Calibration | Injected transits | Injected transits, same panel, skill = TPR - FPR |
| Vetting | Science team | Automatic: SNR, duration, edges, odd/even, secondary, ephemeris |
| Output | Classification export | Zooniverse-shaped CSV, SQLite, candidate catalogue, manifest |

## 5. Data management decisions

* **Provenance.** Each light curve keeps its source, sector, SHA-256 and time system.
  Time systems (BTJD for TESS, BJD_TDB for CHEOPS) are never converted or mixed.
* **Reproducibility.** A run is defined by its TOML config, whose SHA-256 goes into
  `manifest.json`, along with package versions, the prompt version and the reviewer weights.
* **Storage.** SQLite holds subjects and classifications. The classification export
  follows the column shape of a Zooniverse export (`classification_id`, `user_name`,
  `subject_ids`, `created_at`, `annotations`, `metadata`), with one annotation per task:
  T0 for marks and T1 for the label.
* **Caching.** Claude responses are cached by a hash of the model, prompt version,
  prompt and image. Re-running a config costs nothing and reproduces the same panel output.

## 6. Known limits

* A running median is biased by curvature. The detrend therefore uses a local
  quadratic fit to unmasked points. On a steep 2%, 3-day trend the 1-day window still
  biases a 3000 ppm transit by about a third. Real stellar variability is usually much
  gentler, but this is a real limit.
* White-noise sigma underestimates significance on red noise. Single-event
  significance is therefore measured empirically for each duration. BLS SNR is still
  white-noise based, so the periodic threshold was set from a measured null
  distribution (median 7.4, maximum 8.8 over 40 subjects) and is 10.
* Box fits are shallower and shorter than published trapezoid fits. On pi Men c the
  depth ratio is 0.83 and the duration ratio 0.68.
* The CHEOPS column mapping is unverified (section 3).

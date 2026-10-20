# Blind benchmark on real TESS Objects of Interest

Measured on a stated benchmark; not discoveries. Sample: NASA Exoplanet Archive, table toi, fetched 2026-10-19, seed 20261019, sha256 `6f0e111ec8d2c38d…` (300 CP/KP, 300 FP, 62 FA TOIs). Rule: tfopwg_disp in CP/KP (positive), FP, FA; 0.5 ≤ P ≤ 13.0 d; period, mid-time and duration published; one TOI per star; seeded order; halves by sha256(seed:TIC) parity.

Panel: the three Probes (deterministic detectors) with their calibrated weights; sector-wide BLS; vetting; limb-darkened fit; the feed-level table adds the feed's FAP (200 trials). Each star's first SPOC 2-minute sector; the same light curve flux-inverted and block-scrambled as false-alarm controls. Nothing was tuned on this sample, so both halves are reported; the held-out half (by a hash of the TIC) is the headline. The headline completeness is over searchable stars (those with a SPOC 2-minute light curve), because that is what the pipeline can search and what the references measure; completeness over all stars is given beside it.

**Headline: the live discovery feed's "new" signals are consistent with noise.** On light curves with every real signal destroyed (flux-inverted and scrambled), the feed's own rule admits about 13 false new signals per 100 targets reviewed; the live feed shows 15.8 new signals per 100 targets (3 over 19 targets; 95% CI 6–38). On the real light curves of TOI hosts the same rule found 16 new signals per 1,000 star-sectors. A fix is proposed below; it was later pre-registered and tested, see the update at the end.

## Held-out half

| measure | result | reference (not an exoplan requirement) |
|---|---|---|
| **Completeness, headline: CP/KP TOIs recovered on searchable stars** (a vetted dip on the ephemeris) | 57% (86/150; 95% CI 49–65%) | Kepler Robovetter DR25 > 85% for P < 100 d (Thompson et al. 2018); Planet Hunters TESS: 85% of TOIs > 4 R⊕, 51% at 3–4 R⊕ (Eisner et al. 2021); both searched only stars with data |
| Completeness over all CP/KP stars (a star with no 2-minute data counts as missed) | 57% (86/152; 95% CI 49–64%) | |
| Not searchable: no SPOC 2-minute light curve | 36 stars (2 CP/KP, 34 FP, 0 FA); excluded from every rate except the all-stars completeness; **skewed toward FP**, see the class breakdown below | |
| FP TOIs whose dip the panel found | 77% (96/124; 95% CI 69–84%) | |
| … of those, rejected or flagged as binary-like | 68% (65/96; 95% CI 58–76%) | light-curve-only; no published reference found (ATLAS R) |
| CP/KP dips flagged as binary-like (the cost of the flags) | 33% (40/123; 95% CI 25–41%) | |
| FA TOIs whose dip the panel found | 34% (12/35; 95% CI 21–51%) | |
| False alarms on inverted light curves | 177 vetted dips over 309 star-sectors (573 per 1,000; 93 on a ≥2-transit periodic signal, 84 single); stars with any: 21% (65/309; 95% CI 17–26%) | proposed target ≤ 1 per 1,000 star-sectors (ATLAS R) |
| False alarms on scrambled light curves | 262 vetted dips over 309 star-sectors (848 per 1,000; 67 on a ≥2-transit periodic signal, 195 single); stars with any: 25% (78/309; 95% CI 21–30%) | proposed target ≤ 1 per 1,000 star-sectors (ATLAS R) |

### Known bug in this code version: preprocess clipping

`preprocess.clean` in the code that produced these numbers deletes every point more than 10× the point-to-point scatter below the 0.5-day running median, with no run-length test, so a transit or eclipse deeper than about 10× the per-cadence scatter loses its in-transit points before review and BLS. A star is marked affected when the TOI depth is more than 8× the per-cadence scatter of the light curve used. The fix is on a separate branch; after it merges only the affected stars are re-run, reported as a separate update.

Held-out affected stars: 27 CP/KP, 11 FP, 0 FA (of 309 measured). Affected CP/KP recovered anyway: 21; missed: 6, of which 3 lost at least half of their in-transit points to clean() (explained by the bug): TOI 5801.01, 5972.01, 7475.01. Median share of in-transit points removed on affected stars: 31%.

| held-out measure | all stars | affected stars excluded |
|---|---|---|
| Completeness (headline, searchable stars) | 57% (86/150; 95% CI 49–65%) | 53% (65/123; 95% CI 44–61%) |
| FP TOIs found | 77% (96/124; 95% CI 69–84%) | 75% (85/113; 95% CI 67–82%) |
| … rejected or flagged binary-like | 68% (65/96; 95% CI 58–76%) | 68% (58/85; 95% CI 58–77%) |
| inverted control, feed-level false signals per 1,000 star-sectors | 55 | 48 |
| scrambled control, feed-level false signals per 1,000 star-sectors | 65 | 59 |


### At the discovery feed's level (held-out)

The live feed admits a dip only when it passed vetting, is on its own star's periodic signal (not `off_ephemeris`), is at most 5,000 ppm deep, has at least two transits and a FAP below 0.01 over 200 block-bootstrap trials (discover.run_discovery, configs/discovery.toml). The same rule, run with the feed's weights file, on each curve:

| curve | star-sectors | dips before the FAP test | admitted | as `new_candidate` (entries) | distinct new signals | per 1,000 star-sectors | star-sectors with any |
|---|---:|---:|---:|---:|---:|---:|---|
| real | 309 | 225 | 222 | 16 | 5 | 16 | 2% (5/309; 95% CI 1–4%) |
| inverted | 309 | 81 | 76 | 38 | 17 | 55 | 6% (17/309; 95% CI 3–9%) |
| scrambled | 309 | 41 | 30 | 26 | 20 | 65 | 6% (20/309; 95% CI 4–10%) |

On the controls every admitted dip is a false alarm. On the real curves a `new_candidate` is a dip on no published TOI of that star: it may be another planet, but most are expected to be false alarms.

**What this implies for the live feed.** The worse control gives 65 false new signals per 1,000 star-sectors. The feed reviews 2 sectors per target, so it should expect about 12.9 false `new_candidate` signals per 100 targets from noise alone. The live catalogue (docs/discoveries/catalog_v1_fap200.json) holds 3 distinct new signals over 19 targets, 15.8 per 100 targets. **This is bad: false alarms alone could account for at least half of the feed's `new_candidate` rate, so a `new_candidate` on the feed is more likely noise than a signal.**

**Proposed next step (not applied here).** Require the signal to be found independently in each of the two sectors the feed reviews, and raise the FAP evidence to 2,000 trials with a 0.001 cut. Choose the rule on the tuning half only, then measure it once on the held-out half (both controls and CP/KP completeness) before changing configs/discovery.toml. No threshold was changed on this sample.

### Completeness by planet radius and period (held-out)

| bin | recovered |
|---|---|
| 0–2 R⊕ | 10% (2/20; 95% CI 3–30%) |
| 2–4 R⊕ | 23% (6/26; 95% CI 11–42%) |
| 4–8 R⊕ | 36% (4/11; 95% CI 15–65%) |
| 8–30 R⊕ | 80% (73/91; 95% CI 71–87%) |
| 0.5–2 d | 41% (12/29; 95% CI 26–59%) |
| 2–5 d | 67% (52/78; 95% CI 56–76%) |
| 5–13.0 d | 51% (22/43; 95% CI 37–65%) |

Periods of recovered CP/KP signals: P: 82, None: 68 (None: single-transit or other).
Median fit/TOI ratios on recovered CP/KP: depth 0.97, duration 1.02.

## Whole sample (both halves)

Completeness 56% (166/298; 95% CI 50–61%); FP found 74% (170/230; 95% CI 68–79%), of which flagged 70% (119/170; 95% CI 63–76%); inverted false alarms 301 and scrambled 405 over 588 star-sectors. Stars with no SPOC 2-minute data: 74.

## The Sentinels on a stated subsample

Both Sentinels (one Claude model, two personas, through the Claude Code CLI) reviewed every subject of 40 held-out stars drawn with a fixed seed (half CP/KP, half FP), on the real light curves only. Scored per star: did the persona mark a dip on the TOI's ephemeris as a potential planet.

| persona | CP/KP dips marked | FP dips marked as a potential planet | failed calls |
|---|---|---|---:|
| claude-volunteer | 50% (10/20; 95% CI 30–70%) | 20% (4/20; 95% CI 8–42%) | 0 |
| claude-skeptic | 50% (10/20; 95% CI 30–70%) | 20% (4/20; 95% CI 8–42%) | 0 |

Model, as the Claude Code CLI reported it: not recorded: 172 reviews. Reviews answered before exoplan stored the model id say "not recorded": the CLI ran its default model then, and the cache key holds only "default".

The two personas agree on 38 of 40 stars (φ = 0.89). They share one model, so their errors are correlated and they count as one correlated voter, not two independent ones (ATLAS K4).

## What could not be measured, by class and half

| half | class | TOIs | run with data | not searchable (no SPOC 2-min) | download or run failed | not run |
|---|---|---:|---:|---:|---:|---:|
| held-out | CP/KP | 152 | 150 | 2 | 0 | 0 |
| held-out | FP | 158 | 124 | 34 | 0 | 0 |
| held-out | FA | 35 | 35 | 0 | 0 | 0 |
| tuning | CP/KP | 148 | 148 | 0 | 0 | 0 |
| tuning | FP | 142 | 106 | 36 | 0 | 0 |
| tuning | FA | 27 | 25 | 2 | 0 | 0 |

held-out half: no star was lost to a download or run failure.
held-out half, class mix: sample 152 CP/KP (44%), 158 FP (46%), 35 FA (10%); searched 150 CP/KP (49%), 124 FP (40%), 35 FA (11%).
held-out half, not searchable (no SPOC 2-minute light curve): CP/KP 1%, FP 22%, FA 0%. **This loss is skewed toward FP (22 points): FP TOIs are more often found in full-frame images only. The FP measures describe the 124 of 158 FP TOIs whose stars have 2-minute data, a different population from the full TOI FP list, so they are not the panel's reliability on all FP TOIs.**
tuning half: no star was lost to a download or run failure.
tuning half, class mix: sample 148 CP/KP (47%), 142 FP (45%), 27 FA (9%); searched 148 CP/KP (53%), 106 FP (38%), 25 FA (9%).
tuning half, not searchable (no SPOC 2-minute light curve): CP/KP 0%, FP 25%, FA 7%. **This loss is skewed toward FP (25 points): FP TOIs are more often found in full-frame images only. The FP measures describe the 106 of 142 FP TOIs whose stars have 2-minute data, a different population from the full TOI FP list, so they are not the panel's reliability on all FP TOIs.**

Not searchable is a property of the star (the TOI came from full-frame images) and is reported, not repaired.

## Code version

Every per-star result records a fingerprint of the pipeline code that produced it (search, vetting, fit, reviewers): `14f6f4830a525d78` = the pipeline code of commit 76de67d; `e4fe4c99663ccba8` = the pipeline code of commit 40cceca. Results from earlier code were re-vetted with it from their stored classifications (`rescore`), controls included.

## Was the held-out half used to choose a threshold?

No. All 113 threshold values in configs, docs/results/reviewer_weights.json, docs/results/reviewer_weights_full_panel.json, src/exoplan/aggregate.py, src/exoplan/config.py, src/exoplan/discover.py, src/exoplan/pipeline.py, src/exoplan/preprocess.py, src/exoplan/search.py, src/exoplan/subjects.py, src/exoplan/transitfit.py, src/exoplan/vet.py, src/exoplan/reviewers (module constants, config keys, reviewer weights) are the same at 76de67d, the code that produced these numbers, as at fbc1ed9, the last commit before the sample was frozen. The Probe thresholds and weights come from synthetic injection tests; the vetting, V-shape, density and FAP rules were set before any TOI light curve was downloaded. Commits since the freeze, none of which changed a threshold: 76de67d Review nits: docket says what is fitted, prior rho without a restated error, rekey record; 40cceca Science review fixes: free period in joint fits, honest b/rho, no box, stored FAP tail; c78b981 Mission Control: compact chrome, both rows of panes fit a 900 px window. Changed values that decide nothing: configs/tess_pi_men_s1.toml:[search]fap_cache (None → "runs/tess-pi-men-s1/fap_null"); src/exoplan/search.py:FAP_CACHE_VERSION (None → 2); src/exoplan/search.py:FAP_TAIL_FLOOR (None → 1e-6).


## Update 2026-10-20: the two-sector feed rule, pre-registered and tested once

The fix proposed above was chosen on the tuning half only and pre-registered at commit `8909cda` (docs/results/feed_rule_preregistration.json) before its one held-out evaluation (docs/results/feed_rule_validation.json). Rule: the signal must reach the feed rule in both reviewed sectors with periods within 0.5%, and its FAP must be below 0.001 over 2,000 trials. No rule in the grid met the stated noise target (at most 1 false signal per 100 targets on the tuning half), so the pre-stated fallback chose the lowest noise.

Measured with the discovery config itself (subject-mode BLS, the Probes, the feed's weights file) on each held-out star's first two SPOC 2-minute sectors and the same two controls per sector: 309 targets, 562 star-sectors.

| held-out | old rule (FAP < 0.01, 200 trials, one sector) | new rule |
|---|---|---|
| False signals per 100 targets, worse control (95% CI) | 23.0 (18.6–28.0) | 6.1 (4.0–9.4) |
| Inverted control: false signals | 71 (126 per 1,000 star-sectors) | 19 (34 per 1,000) |
| Scrambled control: false signals | 43 (77 per 1,000) | 0 (0 per 1,000) |
| CP/KP admitted on their ephemeris (feed-level completeness) | 39% (58/150; 95% CI 31–47%) | 17% (26/150; 95% CI 12–24%) |
| FP TOIs kept out | 73% (91/124; 95% CI 65–80%) | 94% (116/124; 95% CI 88–97%) |
| New (no-TOI) signals on the real curves, per 100 targets | 2.9 | 0.3 |

The rule lowers the noise clearly (the 95% intervals do not overlap): about fourfold. **It does not make the feed reliable.** Noise alone still gives about 6 false signals per 100 targets, far above the 0.3 new signals per 100 targets the real light curves of TOI hosts produce, so what the feed admits is still dominated by false alarms. Completeness at the feed's level fell from 39% to 17%. A feed admission is a lead for human or follow-up review, not a candidate of any confirmed status.

**The live feed re-run under the new rule** (19 targets of the live catalogue, their latest two sectors, 2026-10-20; TOI table from cache/toi/toi.csv fetched 2026-10-19T11:00:16Z (the NASA Exoplanet Archive TAP returned HTTP 526 on 2026-10-20)): 0 of the 3 earlier new signals survive, and 2 known-TOI signals are admitted. The earlier catalogue is kept as docs/discoveries/catalog_v1_fap200.json.

Recovered means the panel's consensus dip passed vetting and lies on the TOI's published ephemeris (`match_toi`). Flagged means vetting rejected the on-ephemeris dip, or marked it odd/even, secondary eclipse, V shape or density mismatch. Wilson 95% intervals. TFOPWG dispositions are the reference; they are not ground truth for every TOI.

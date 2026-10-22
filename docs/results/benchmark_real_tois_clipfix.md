# Blind benchmark on real TESS Objects of Interest: re-run on the fixed code

This is the pre-registered protocol run again on the current code, after the two fixes that change default results (`preprocess.clean` keeps dips deeper than 10× the point-to-point scatter; `vet.py`'s odd/even test no longer fails clean deep planets). The sample, seed, split, light curves, controls and scoring are unchanged and nothing was tuned; every star was run again from its light curve. The first run, made with the pre-fix code, is kept as the historical record in docs/results/benchmark_real_tois.md; the comparison is below.

Measured on a stated benchmark; not discoveries. Sample: NASA Exoplanet Archive, table toi, fetched 2026-10-19, seed 20261019, sha256 `6f0e111ec8d2c38d…` (300 CP/KP, 300 FP, 62 FA TOIs). Rule: tfopwg_disp in CP/KP (positive), FP, FA; 0.5 ≤ P ≤ 13.0 d; period, mid-time and duration published; one TOI per star; seeded order; halves by sha256(seed:TIC) parity.

Panel: the three Probes (deterministic detectors) with their frozen calibrated weights; sector-wide BLS; vetting; limb-darkened fit; the feed-level table adds the feed's FAP (200 trials). Each star's first SPOC 2-minute sector; the same light curve flux-inverted and block-scrambled as false-alarm controls. Nothing was tuned on this sample, so both halves are reported; the held-out half (by a hash of the TIC) is the headline. The headline completeness is over searchable stars (those with a SPOC 2-minute light curve), because that is what the pipeline can search and what the references measure; completeness over all stars is given beside it.

**Headline: the live discovery feed's "new" signals are consistent with noise.** On light curves with every real signal destroyed (flux-inverted and scrambled), the feed's own rule admits about 12 false new signals per 100 targets reviewed; the live feed shows 15.8 new signals per 100 targets (3 over 19 targets; 95% CI 6–38). On the real light curves of TOI hosts the same rule found 23 new signals per 1,000 star-sectors. The feed has since moved to a pre-registered two-sector rule, measured on this code at the end of this report.

## Held-out half

| measure | result | reference (not an SetuHQ requirement) |
|---|---|---|
| **Completeness, headline: CP/KP TOIs recovered on searchable stars** (a vetted dip on the ephemeris) | 60% (90/150; 95% CI 52–67%) | Kepler Robovetter DR25 > 85% for P < 100 d (Thompson et al. 2018); Planet Hunters TESS: 85% of TOIs > 4 R⊕, 51% at 3–4 R⊕ (Eisner et al. 2021); both searched only stars with data |
| Completeness over all CP/KP stars (a star with no 2-minute data counts as missed) | 59% (90/152; 95% CI 51–67%) | |
| Not searchable: no SPOC 2-minute light curve | 36 stars (2 CP/KP, 34 FP, 0 FA); excluded from every rate except the all-stars completeness; **skewed toward FP**, see the class breakdown below | |
| FP TOIs whose dip the panel found | 77% (96/124; 95% CI 69–84%) | |
| … of those, rejected or flagged as binary-like | 68% (65/96; 95% CI 58–76%) | light-curve-only; no published reference found (ATLAS R) |
| CP/KP dips flagged as binary-like (the cost of the flags) | 26% (32/122; 95% CI 19–35%) | |
| FA TOIs whose dip the panel found | 34% (12/35; 95% CI 21–51%) | |
| False alarms on inverted light curves | 198 vetted dips over 309 star-sectors (641 per 1,000; 106 on a ≥2-transit periodic signal, 92 single); stars with any: 22% (67/309; 95% CI 17–27%) | proposed target ≤ 1 per 1,000 star-sectors (ATLAS R) |
| False alarms on scrambled light curves | 266 vetted dips over 309 star-sectors (861 per 1,000; 68 on a ≥2-transit periodic signal, 198 single); stars with any: 25% (78/309; 95% CI 21–30%) | proposed target ≤ 1 per 1,000 star-sectors (ATLAS R) |

### The clipping bug, fixed: the stars it affected

The first run's `preprocess.clean` deleted every point more than 10× the point-to-point scatter below the 0.5-day running median, so a transit deeper than about 10× the per-cadence scatter lost its in-transit points before review and BLS. This code removes a low point only when it is not part of a dip (a run of at least max(3, 20 minutes / cadence) cadences more than 3σ below the median). A star is exposed when the TOI depth is more than 8× the per-cadence scatter of the light curve used (the same light curves as the first run, so the same stars).

Held-out exposed stars: 27 CP/KP, 11 FP, 0 FA (of 309 measured). Share of in-transit points clean() removes on them now: median 0% (first run: 31%). Exposed CP/KP recovered: 23 of 27 (first run: 21 of 27). The 3 misses the first run's bug explained (TOI 5801.01, 5972.01, 7475.01): recovered now: TOI 5801.01, 5972.01, 7475.01.

| held-out measure, this run | all stars | exposed stars excluded |
|---|---|---|
| Completeness (headline, searchable stars) | 60% (90/150; 95% CI 52–67%) | 54% (67/123; 95% CI 46–63%) |
| FP TOIs found | 77% (96/124; 95% CI 69–84%) | 75% (85/113; 95% CI 67–82%) |
| … rejected or flagged binary-like | 68% (65/96; 95% CI 58–76%) | 66% (56/85; 95% CI 55–75%) |


### At the discovery feed's level (held-out)

The live feed admits a dip only when it passed vetting, is on its own star's periodic signal (not `off_ephemeris`), is at most 5,000 ppm deep, has at least two transits and a FAP below 0.01 over 200 block-bootstrap trials (discover.run_discovery, configs/discovery.toml). The same rule, run with the feed's weights file, on each curve:

| curve | star-sectors | dips before the FAP test | admitted | as `new_candidate` (entries) | distinct new signals | per 1,000 star-sectors | star-sectors with any |
|---|---:|---:|---:|---:|---:|---:|---|
| real | 309 | 229 | 226 | 19 | 7 | 23 | 2% (7/309; 95% CI 1–5%) |
| inverted | 309 | 96 | 91 | 46 | 18 | 58 | 6% (18/309; 95% CI 4–9%) |
| scrambled | 309 | 45 | 29 | 25 | 19 | 61 | 6% (19/309; 95% CI 4–9%) |

On the controls every admitted dip is a false alarm. On the real curves a `new_candidate` is a dip on no published TOI of that star: it may be another planet, but most are expected to be false alarms.

**What this implies for the live feed.** The worse control gives 61 false new signals per 1,000 star-sectors. The feed reviews 2 sectors per target, so it should expect about 12.3 false `new_candidate` signals per 100 targets from noise alone. The live catalogue (docs/discoveries/catalog_v1_fap200.json) holds 3 distinct new signals over 19 targets, 15.8 per 100 targets. **This is bad: false alarms alone could account for at least half of the feed's `new_candidate` rate, so a `new_candidate` on the feed is more likely noise than a signal.**

This table keeps the rule the protocol was frozen with (FAP < 0.01 over 200 trials, one sector), and the live catalogue it compares with is the one built under that rule, with pre-fix code. The feed has since moved to the pre-registered two-sector rule; it is measured on this code at the end of this report.

## Against the first run (pre-fix code)

The first run (docs/results/benchmark_real_tois.json, pipeline code commit 76de67d, commit 40cceca) is kept as the historical pre-fix record. Same sample, seed, split, light curves, controls and scoring; only the code differs. Where both runs measured the same stars the change is paired: a bootstrap over the stars (20,000 draws, seed 20261019) and the exact McNemar test on the stars whose outcome changed.

| held-out measure | first run (pre-fix code) | this run | change, paired on the same stars |
|---|---|---|---|
| **Completeness: CP/KP recovered on searchable stars** | 57% (86/150; 95% CI 49–65%) | 60% (90/150; 95% CI 52–67%) | +3 points (95% CI +0 to +6); 5 gained, 1 lost; McNemar p = 0.22 |
| Completeness over all CP/KP stars | 57% (86/152; 95% CI 49–64%) | 59% (90/152; 95% CI 51–67%) |  |
| … 0–2 R⊕ | 10% (2/20; 95% CI 3–30%) | 10% (2/20; 95% CI 3–30%) | +0 points (95% CI +0 to +0); 0 gained, 0 lost; McNemar p = 1 |
| … 2–4 R⊕ | 23% (6/26; 95% CI 11–42%) | 23% (6/26; 95% CI 11–42%) | +0 points (95% CI +0 to +0); 0 gained, 0 lost; McNemar p = 1 |
| … 4–8 R⊕ | 36% (4/11; 95% CI 15–65%) | 45% (5/11; 95% CI 21–72%) | +9 points (95% CI +0 to +27); 1 gained, 0 lost; McNemar p = 1 |
| … 8–30 R⊕ | 80% (73/91; 95% CI 71–87%) | 84% (76/91; 95% CI 75–90%) | +3 points (95% CI −1 to +9); 4 gained, 1 lost; McNemar p = 0.38 |
| … 0.5–2 d | 41% (12/29; 95% CI 26–59%) | 41% (12/29; 95% CI 26–59%) | +0 points (95% CI +0 to +0); 0 gained, 0 lost; McNemar p = 1 |
| … 2–5 d | 67% (52/78; 95% CI 56–76%) | 73% (57/78; 95% CI 62–82%) | +6 points (95% CI +1 to +13); 5 gained, 0 lost; McNemar p = 0.062 |
| … 5–13 d | 51% (22/43; 95% CI 37–65%) | 49% (21/43; 95% CI 35–63%) | −2 points (95% CI −7 to +0); 0 gained, 1 lost; McNemar p = 1 |
| FP TOIs whose dip the panel found | 77% (96/124; 95% CI 69–84%) | 77% (96/124; 95% CI 69–84%) | +0 points (95% CI +0 to +0); 0 gained, 0 lost; McNemar p = 1 |
| … of those, rejected or flagged binary-like | 68% (65/96; 95% CI 58–76%) | 68% (65/96; 95% CI 58–76%) |  |
| FP TOIs whose dip passed vetting | 31% (38/124; 95% CI 23–39%) | 34% (42/124; 95% CI 26–43%) | +3 points (95% CI +0 to +7); 5 gained, 1 lost; McNemar p = 0.22 |
| CP/KP dips flagged binary-like | 33% (40/123; 95% CI 25–41%) | 26% (32/122; 95% CI 19–35%) |  |
| FA TOIs whose dip the panel found | 34% (12/35; 95% CI 21–51%) | 34% (12/35; 95% CI 21–51%) | +0 points (95% CI +0 to +0); 0 gained, 0 lost; McNemar p = 1 |
| Inverted control: vetted false alarms per 1,000 star-sectors | 573 | 641 |  |
| Inverted control: stars with any false alarm | 21% (65/309; 95% CI 17–26%) | 22% (67/309; 95% CI 17–27%) | +1 points (95% CI +0 to +2); 2 gained, 0 lost; McNemar p = 0.5 |
| Scrambled control: vetted false alarms per 1,000 star-sectors | 848 | 861 |  |
| Scrambled control: stars with any false alarm | 25% (78/309; 95% CI 21–30%) | 25% (78/309; 95% CI 21–30%) | +0 points (95% CI −1 to +1); 1 gained, 1 lost; McNemar p = 1 |
| Feed level (frozen rule), real curves: distinct new signals per 1,000 star-sectors | 16 | 23 |  |
| Feed level (frozen rule), inverted curves: distinct new signals per 1,000 star-sectors | 55 | 58 |  |
| Feed level (frozen rule), scrambled curves: distinct new signals per 1,000 star-sectors | 65 | 61 |  |
| Whole sample (both halves): completeness | 56% (166/298; 95% CI 50–61%) | 60% (179/298; 95% CI 54–65%) | +4 points (95% CI +2 to +7); 14 gained, 1 lost; McNemar p = 0.00098 |

Why the inverted control and the FP TOIs pass more often: of the dips on inverted curves that pass vetting now and did not before, 16 were rejected in the first run by the old odd/even test, 5 are new dips deeper than 10× the point-to-point scatter (inverted bumps the old cleaning deleted) and 3 are other; 3 that passed before no longer do. Of the 5 FP TOIs whose dip now passes vetting, 4 were rejected in the first run by the old odd/even test; 1 FP TOI's dip no longer passes.


## Known limits of the matching and of the dip measurement

**Stale published ephemerides.** The frozen rule counts a TOI as recovered only when a vetted dip lies on its published ephemeris. An audit (not a rule; the matching is unchanged) finds 1 held-out CP/KP TOI (1 in both halves) counted as missed although no dip lies on the published ephemeris but a vetted dip matching no TOI of the star, of depth within 3x the TOI's (window or fitted depth, the larger), lies off the nearest predicted epoch by more than the matching tolerance and by at least 3 sigma of the propagated ephemeris error, but by at most 12 h and a quarter period. Such a dip may be the TOI's own transit against an ephemeris that has drifted since it was published; the frozen rule still counts it as a miss.

| half | TOI | offset from the predicted epoch (h)¹ | offset / ephemeris σ | dip depth / TOI depth | dip duration (h) | TOI duration (h) | dip period (d) | TOI period (d) |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| held-out | 1905.01 | -8.4 | 8.3 | 0.99 | 0.79 | 2.65 | 8.5813 | 5.7223 |

¹ The offset of the dip's centre, which is the centre of the window the Probes marked. For TOI 1905.01 that window covers only the ingress, so its centre sits 8.4 h before the prediction while the transit's own centre is 7.2 h before it.

Checked by hand: TOI 1905.01. Its sector holds two full transits about 25 ppt deep and 2.5 h long (BTJD 3776.91 and 3794.09); the published ephemeris predicts them 7.2 h later, 7σ of its propagated error, so even a perfect detection would not match. The first run's "recovery" was a residual dip left at the predicted time after the clipping had cut the transit out.

**Window depth and duration on deep, clear transits.** A dip's depth and duration are measured over the window the Probes marked. On TOI 1905.01 the marks cover only the ingress, so the dip reads 0.79 h and 2.9 ppt against the transit's 2.5 h and 25 ppt (the limb-darkened fit of the same dip gets them right: 25.3 ppt, 2.75 h), and the BLS period is an alias (3P/2). Changing how the window is measured would change frozen outcomes, so it is recorded as a known limit (ROADMAP), not changed here.


### Completeness by planet radius and period (held-out)

| bin | recovered |
|---|---|
| 0–2 R⊕ | 10% (2/20; 95% CI 3–30%) |
| 2–4 R⊕ | 23% (6/26; 95% CI 11–42%) |
| 4–8 R⊕ | 45% (5/11; 95% CI 21–72%) |
| 8–30 R⊕ | 84% (76/91; 95% CI 75–90%) |
| 0.5–2 d | 41% (12/29; 95% CI 26–59%) |
| 2–5 d | 73% (57/78; 95% CI 62–82%) |
| 5–13.0 d | 49% (21/43; 95% CI 35–63%) |

Periods of recovered CP/KP signals: P: 87, None: 63 (None: single-transit or other).
Median fit/TOI ratios on recovered CP/KP: depth 0.99, duration 1.02.

## Whole sample (both halves)

Completeness 60% (179/298; 95% CI 54–65%); FP found 74% (170/230; 95% CI 68–79%), of which flagged 68% (116/170; 95% CI 61–75%); inverted false alarms 360 and scrambled 412 over 588 star-sectors. Stars with no SPOC 2-minute data: 74.

## The Sentinels on a stated subsample

The Sentinels were not asked again: no API key or signed-in CLI was available for this run. Their answers from the first run are carried over only for the stars whose every subject image and prompt are byte-identical on this code (37 of the 40 stars of the stated subsample); the other 3 stars' subjects changed with the fix, so they are left out of this table, not guessed. Left out: TOI 1070.01, 2547.01, 416.01.

Both Sentinels (one Claude model, two personas, through the Claude Code CLI) reviewed every subject of 37 held-out stars drawn with a fixed seed (19 CP/KP and 18 FP here; half CP/KP, half FP as drawn), on the real light curves only. Scored per star: did the persona mark a dip on the TOI's ephemeris as a potential planet.

| persona | CP/KP dips marked | FP dips marked as a potential planet | failed calls |
|---|---|---|---:|
| claude-volunteer | 47% (9/19; 95% CI 27–68%) | 22% (4/18; 95% CI 9–45%) | 0 |
| claude-skeptic | 47% (9/19; 95% CI 27–68%) | 22% (4/18; 95% CI 9–45%) | 0 |

Model, as the Claude Code CLI reported it: not recorded: 160 reviews. Reviews answered before SetuHQ stored the model id say "not recorded": the CLI ran its default model then, and the cache key holds only "default".

The two personas agree on 35 of 37 stars (φ = 0.88). They share one model, so their errors are correlated and they count as one correlated voter, not two independent ones (ATLAS K4).

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

Every per-star result records a fingerprint of the pipeline code that produced it (search, vetting, fit, reviewers): `0b8e86a1fb71e777` = the pipeline code of commit 8dde211 (the current code differs from it only in comments and docstrings). Every star, controls included, was run again from its light curve on this code (`rerun`); no stored classification was reused.

## Was the held-out half used to choose a threshold?

Of 177 threshold values in configs, docs/results/reviewer_weights.json, docs/results/reviewer_weights_full_panel.json, src/setuhq/aggregate.py, src/setuhq/config.py, src/setuhq/discover.py, src/setuhq/pipeline.py, src/setuhq/preprocess.py, src/setuhq/search.py, src/setuhq/subjects.py, src/setuhq/transitfit.py, src/setuhq/vet.py, src/setuhq/reviewers, these differ between fbc1ed9 (the last commit before the sample was frozen) and 8dde211 (the code of this run). Each is listed with why it changed; none was chosen on this sample's held-out results.

* New configs for the all-sky sweep (setuhq sweep), added after the freeze; the benchmark does not read them (`configs/sweep.toml` (18 values); `configs/sweep_sentinels.toml` (19 values)).
* The discovery feed's two-sector rule, chosen on the tuning half only and pre-registered at 8909cda; this report's feed-level table keeps the frozen rule (FAP < 0.01 over 200 trials), and the new rule is measured separately below (`configs/discovery.toml:[search]fap_stop_after`, `configs/discovery.toml:[search]fap_trials`; `src/setuhq/discover.py:FAP`, `src/setuhq/discover.py:MAX_FEED_FAP`, `src/setuhq/discover.py:TWO_SECTOR_PERIOD_TOL`).
* The odd/even fix (106c797): a 2% systematic floor on the odd/even depth errors, motivated by synthetic clean hot Jupiters and checked on pi Men c (`src/setuhq/vet.py:ODD_EVEN_FLOOR`).
* Extended (DV-style) and pixel-level vetting (bc43219, bd2dad4), which by default only add flags (decide = false); this report's scores read neither those flags nor the pixel tests, which are off (`configs/default.toml` (7 values); `src/setuhq/pipeline.py:SCAN_KEYS`, `src/setuhq/pipeline.py:TRANSIT_MASK_T14`).
* The reduced false-positive probability and its stability gate (0361a27, b0ab1c1), reported per candidate; this report's scores do not read it (`configs/default.toml:[validation]contrast_curves`; `src/setuhq/pipeline.py:DETREND_VARIANTS`, `src/setuhq/pipeline.py:MIN_ANCHOR_SUPPORT`).
* Not a threshold: the list of URL parameters a Sentinel's error message redacts (`src/setuhq/reviewers/http.py:CREDENTIAL_PARAMS`).

`preprocess.clean`'s new run-length rule is a keyword default, not a module constant, so the audit does not list it: it was set and tested on synthetic eclipses (commits ab84328 and c25d1cd). Changed values that decide nothing: configs/sweep.toml:[search]fap_cache (None → ""); configs/sweep_sentinels.toml:[search]fap_cache (None → ""); configs/tess_pi_men_s1.toml:[search]fap_cache (None → "runs/tess-pi-men-s1/fap_null"); src/setuhq/config.py:SENTINEL_TYPES (None → {); src/setuhq/reviewers/claude.py:DEFAULT_MODEL (None → "claude-sonnet-5-5"); src/setuhq/reviewers/gemini.py:BLOCKED (None → {"SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "IMAGE_SAFETY"}); src/setuhq/reviewers/gemini.py:GEMINI_BASE_URL (None → "https://generativelanguage.googleapis.com/v1beta"); src/setuhq/reviewers/http.py:PROVIDER_KEY_ENVS (None → ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY")); src/setuhq/reviewers/openai_compat.py:OPENAI_BASE_URL (None → "https://api.openai.com/v1"); src/setuhq/reviewers/sentinel.py:KEY_ENV (None → {); src/setuhq/reviewers/sentinel.py:PROVIDER_LABELS (None → {); src/setuhq/search.py:FAP_CACHE_VERSION (None → 2); src/setuhq/search.py:FAP_TAIL_FLOOR (None → 1e-6).


## The two-sector feed rule on this code

The feed's rule since 2026-10-20 was chosen on the tuning half only and pre-registered at commit `8909cda` (docs/results/feed_rule_preregistration.json). Its first held-out evaluation (docs/results/feed_rule_validation.json) ran on the pre-fix code. Here the same rule, unchanged and not tuned again (signal in both reviewed sectors with periods within 0.5%, FAP below 0.001 over 2,000 trials), is measured on this code (docs/results/feed_rule_validation_clipfix.json): the discovery config, each held-out star's same first two SPOC 2-minute sectors, the same two controls per sector, every pipeline run and FAP trial made afresh. 309 targets, 562 star-sectors.

| held-out | old rule (FAP < 0.01, 200 trials, one sector) | two-sector rule | two-sector rule, first evaluation (pre-fix code) |
|---|---|---|---|
| False signals per 100 targets, worse control (95% CI) | 27.8 (23.1–33.1) | 6.1 (4.0–9.4) | 6.1 (4.0–9.4) |
| Inverted control: false signals | 86 (153 per 1,000 star-sectors) | 19 (34 per 1,000) | 19 (34 per 1,000) |
| Scrambled control: false signals | 51 (91 per 1,000) | 0 (0 per 1,000) | 0 (0 per 1,000) |
| CP/KP admitted on their ephemeris (feed-level completeness) | 39% (58/150; 95% CI 31–47%) | 17% (26/150; 95% CI 12–24%) | 17% (26/150; 95% CI 12–24%) |
| FP TOIs kept out | 70% (87/124; 95% CI 62–78%) | 94% (117/124; 95% CI 89–97%) | 94% (116/124; 95% CI 88–97%) |
| New (no-TOI) signals on the real curves, per 100 targets | 5.8 | 1.6 | 0.3 |

On this code the rule lowers the noise clearly (the 95% intervals do not overlap): 4.5-fold. **It does not make the feed reliable.** Noise alone still gives about 6.1 false signals per 100 targets, against 1.6 new signals per 100 targets on the real light curves of TOI hosts, so what the feed admits is still dominated by false alarms. Completeness at the feed's level: 39% under the old rule, 17% under this one. A feed admission is a lead for human or follow-up review, not a candidate of any confirmed status.

**The live feed re-run on this code** (19 targets of the live catalogue, the same sectors as its previous run, 2026-10-21; TOI table cache/toi/toi.csv fetched 2026-10-19T11:00:16Z (the copy the previous live run used)): 0 new signals (0 entries) and 2 known-TOI signals (24 entries) are admitted. The previous re-run, on the pre-fix code (docs/results/feed_rule_live_rerun.json), admitted 0 new and 2 known-TOI signals.

Recovered means the panel's consensus dip passed vetting and lies on the TOI's published ephemeris (`match_toi`). Flagged means vetting rejected the on-ephemeris dip, or marked it odd/even, secondary eclipse, V shape or density mismatch. Wilson 95% intervals. TFOPWG dispositions are the reference; they are not ground truth for every TOI.

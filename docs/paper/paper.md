<!--
  Source of docs/paper/paper.md. Do not edit paper.md by hand: run `python scripts/paper_numbers.py`.
  Every result is a double-brace placeholder filled from the committed JSON; tests/test_paper.py fails when
  a percentage, a k/n count or a decimal is typed here instead. Typed here, and only as definitions or
  context: physical units, identifiers (TIC, sector, TOI names), the published papers' own ranges, and the
  clipping factor of the bug as the benchmark report states it.
-->

# exoplan: a blind benchmark of a calibrated panel of language-model and matched-filter reviewers for TESS transit search

**The exoplan contributors** (repository: ashfordeOU/EXOPLAN)

*Draft methods paper in the style of the AAS journals (AJ). Markdown only: the aastex631 class is not
available offline in the environment that produced this draft, so no LaTeX version is provided yet.*

*Generated from the committed results by `scripts/paper_numbers.py` (benchmark report of 2026-10-19,
code commit `76de67d`). Results that later work will change are marked pending; see the section
"Pending results".*

Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

## Abstract

We describe exoplan, an open-source transit search that copies the Planet Hunters task (mark the start and
end of each dip in a blind-coded light curve, then label it a potential planet or noise) but replaces the
volunteers with a panel of reviewers: *Sentinels*, which are personas of one large language model (Claude)
that read the rendered plot and give their reasons in words, and *Probes*, deterministic matched-filter
detectors. Marks are clustered and scored by skill-weighted consensus, then vetted from the light curve
alone, fitted with a limb-darkened model, and given a bounded block-bootstrap false-alarm probability. We
measure the deterministic panel on a frozen, blind sample of 662 TESS Objects of Interest
(300 confirmed or known planets, 300 false positives and 62 false alarms, one per star),
split by star into a tuning and a held-out half, with flux-inverted and block-scrambled copies of every light
curve as false-alarm controls. On the held-out half the panel recovers 57% (86/150; 95% CI 49–65%) of the CP/KP TOIs
on stars with SPOC 2-minute data, but only 10% (2/20; 95% CI 3–30%) below 2 R⊕ and 23% (6/26; 95% CI 11–42%) at 2 to 4 R⊕. It finds the
dip of 77% (96/124; 95% CI 69–84%) of the false-positive TOIs with 2-minute data and rejects or flags 68% (65/96; 95% CI 58–76%) of the
dips it found; counted over every held-out FP star, 80% (127/158; 95% CI 73–86%) are not offered as clean candidates.
The controls
show that the live discovery feed's "new" signals are consistent with noise: the feed's own admission rule passes
55 and 65 false signals per 1,000 star-sectors on the inverted and
scrambled curves, about 12.9 per 100 targets, against 15.8 per 100 on the live
feed. The two Sentinel personas, tested on a stated subsample of 40 held-out stars, each mark
50% (10/20; 95% CI 30–70%) of the CP/KP dips and agree on 38 of 40 stars (φ = 0.89): they are one
correlated voter, not two. We report a known bug in the code that produced these numbers, the class skew
of the stars that could not be searched, and a public leaderboard on the frozen sample that scores submitted
events itself and ranks by Youden's J, so that calling every TOI a planet scores zero. Nothing here is a
discovery, and no exoplan output is called a confirmed or validated planet.

## 1 Introduction

Volunteers inspecting light curves by eye have found transit candidates and planets: two planet candidates
in the first month of Planet Hunters on Kepler data (Fischer et al. 2012), and TOI-813 b, the first Planet
Hunters TESS planet (Eisner et al. 2020). In Planet Hunters TESS, more than 22,000 volunteers marked transit-like events in
sectors 1 to 26; a clustering step ranked them, the science team vetted the top events, and the project
recovered 85% of TOIs larger than 4 R⊕ and 51% of those at 3 to 4 R⊕ (Eisner et al. 2021).
The Planet Hunters CHEOPS project on Zooniverse (see References) uses the same task on CHEOPS light curves; exoplan copies
that task exactly.

Automated vetting has a longer quantitative record. Kepler's Robovetter, a deterministic decision tree, was
measured for completeness with injected transits and for reliability with inverted and scrambled light
curves (Coughlin et al. 2016; Thompson et al. 2018); for periods below 100 days its DR25 catalogue reached a
completeness above 85% and a reliability above 98% (Thompson et al. 2018).
That completeness is the vetter's alone: it is measured on injected transits that the pipeline had already detected
as threshold-crossing events, whereas exoplan's completeness below is end to end, from light curve to vetted dip.
Machine-learned vetters rank threshold-crossing events by learning from labelled examples: AstroNet ranked a
plausible planet above a false positive in 98.8% of test pairs (Shallue & Vanderburg 2018), a variant
triages and vets TESS candidates (Yu et al. 2019), and ExoMiner reports 93.6% recall at 99% precision
(Valizadegan et al. 2022). These classifiers inherit label noise and distribution shift, and their scores are
not probabilities unless calibrated.

Large language models that read images and explain their reasoning are a newer kind of reviewer. They have
classified images of astronomical transients and explained the classifications in text (Stoppa et al. 2025). In the
literature collected for this work we found no published benchmark of such reviewers on TESS transit vetting
with controls and a held-out split, so we make no comparison with one. exoplan treats a language-model reviewer as one calibrated voice in a panel, beside
deterministic detectors whose behaviour can be measured exactly, and asks what such a panel can claim on a
stated benchmark.

The answer here is modest and partly negative. This paper describes the method (Section 3), a blind benchmark
on real TOIs with controls (Section 4), the results with their failures (Section 5), a comparison with published
reference numbers (Section 6), the limitations (Section 7) and how to reproduce every number (Section 8).

## 2 Data

**Light curves.** TESS (Ricker et al. 2015) SPOC 2-minute PDCSAP light curves (Jenkins et al. 2016), downloaded
from MAST. For the benchmark each star's first SPOC 2-minute sector is used. Stellar effective temperature,
surface gravity and density come from the TESS Input Catalog (Stassun et al. 2019) when the fit needs them.

**The benchmark sample.** From the NASA Exoplanet Archive `toi` table (fetched 2026-10-19): TOIs whose
TFOPWG disposition is CP or KP (positives), FP or FA, with 0.5 ≤ P ≤ 13.0 d (so a 27-day sector
holds at least two transits) and a published period, mid-time and duration; one TOI per star, drawn in a
seeded order (seed 20261019) until each class was full: 300 CP/KP, 300 FP and 62 FA
(the FA class ran out of eligible stars below its quota). The sample, its dispositions and the table's fetch
date were stored with a hash before any light curve was downloaded: sha256 `6f0e111ec8d2c38d3e7927505f0be4a2c7fae8b73d7cc17c37646baedf044cac`.

**The split.** Each star is assigned to a tuning or a held-out half by the parity of sha256(seed:TIC). The
held-out half has 152 CP/KP, 158 FP and 35 FA TOIs (345 stars).

**Not searchable.** A star with no SPOC 2-minute light curve cannot be searched by this pipeline. In the held-out
half that is 2 CP/KP (1%), 34 FP (22%) and
0 FA (0%) stars; in the tuning half 0%, 25% and
7%. No star was lost to a download or run failure (0 in the held-out half). **The loss
is skewed toward false positives**, which are more often found in full-frame images only (Section 5.5).

**pi Mensae.** The single-star validation uses TESS sector 1 of pi Men (TIC 261136679) and the parameters of
pi Men c from Huang et al. 2018, read from the archive's `ps` table.

## 3 Method

### 3.1 Subjects and blinding

Light curves are cleaned (spike clipping), detrended with a masked local-quadratic baseline over a
1-day window, binned to 10 minutes and cut into fixed 13-day *subjects* with opaque
identifiers. No reviewer sees the target's name, its TOI status or its ephemeris; dispositions and ephemerides
are used only when scoring.

### 3.2 The reviewer panel

**Probes.** Three deterministic detectors (Sensitive, Typical and Cautious) run a single-event matched-filter
search and a box least-squares search (BLS; Kovács, Zucker & Mazeh 2002) on each subject and mark every event above their
signal-to-noise threshold, with a stated miss probability and boundary jitter so that they behave like
human markers with limits. They are seeded and fully reproducible.

**Sentinels.** Two personas of one model, Claude, reached through the Claude Code CLI: *Volunteer* (careful,
marks dips) and *Skeptic* (rejects binary and systematic signatures unless they are clear). Each receives the
volunteers' task text, the rendered blind-coded plot and nothing else, and returns strict JSON (marks, a
label, a noise reason and a sentence of rationale), which is validated and clipped to the subject's time
range. Responses are cached by a hash of the backend, the model setting, the prompt version
(2026-10-16.1), the persona and the request, so a re-run reproduces them at no cost.

**Calibration.** Each reviewer's weight is its skill on injected transits: the true-positive rate on
injected subjects minus the false-positive rate on empty ones, floored at 0.05. The Probes were calibrated on synthetic white-plus-red-noise light curves; the Sentinels, each needing
one CLI call per subject, on only 10 injected and 10 empty subjects: weight 0.5 each,
against 0.4 to 0.6 for the Probes. That sample is too small to separate the reviewers' skills.

### 3.3 Aggregation

Marks closer than 0.05 d are one dip (single-linkage clustering). A dip's score is the skill-weighted
share of the panel that marked it, and a consensus dip needs a score of at least 0.5 on a subject the
panel calls a potential planet with a weighted share of at least 0.5. This mirrors the
user-weighted scores of Planet Hunters TESS (Eisner et al. 2021).

### 3.4 Vetting

Every consensus dip is vetted from the light curve alone: an SNR of at least 7, a duration of at least
15 minutes, an edge test (0.1 d), and, on a periodic signal, odd/even depth and half-phase secondary
eclipse tests at 3σ, plus the fit's V-shape and stellar-density tests below. These mirror part of the
Kepler and TESS Data Validation suite (Twicken et al. 2018; Guerrero et al. 2021). There is no centroid,
difference-image or pixel-level test.

### 3.5 Limb-darkened fit

Each consensus dip gets a quadratic limb-darkened transit fit (Mandel & Agol 2002) with coefficients from
Claret 2017 for the TIC's effective temperature and surface gravity. It reports depth, T14, the impact
parameter b, mid-time and the transit stellar density ρ★ with errors that add the covariance to the spread
along the impact-parameter profile. On a periodic signal the period is fitted near the BLS period. When b is
poorly constrained it is printed as an upper limit and ρ★ as a range, and a second fit with the TIC density as
a Gaussian prior is stored beside the free one. A ρ★ outside 0.3 to 3 times the catalogue value at 3σ
is flagged (an illustrative band, not a published threshold), and a V-shaped fit is flagged as binary-like.

### 3.6 False-alarm probability

A periodic signal's FAP is (k + 1)/(N + 1) over N block-bootstrap trials: the detected box is removed, the
residuals are cut into 0.5-day blocks and shuffled, and BLS reruns on each copy; k copies reach the
observed SNR. The FAP is never given below 1/(N + 1), so with k = 0 it is an upper bound. A Gumbel fit to the
null maxima is stored as an indicative tail, never below 10⁻⁶. The library default is 20
trials and the discovery feed uses 200.

### 3.7 The discovery feed

A scheduled job reviews the two latest sectors of TOI host stars and keeps every vetted dip in a catalogue,
marked `known_toi` when it matches a published TOI ephemeris and `new_candidate` otherwise. A dip is admitted
when it passed vetting, lies on its star's periodic signal, is at most 5,000 ppm deep, has at least
2 transits and a FAP below 0.01. Section 5.2 measures what this rule admits from noise.

## 4 Benchmark design

**Frozen sample and blinding.** Section 2. The pipeline sees only light curves with opaque subject ids.

**The panel measured.** The three Probes with their calibrated weights, sector-wide BLS, vetting and the
limb-darkened fit, without the FAP rule (it is not part of vetting). The feed-level table adds the feed's FAP
(200 trials) and its admission rule. The benchmark runs did not query the TIC: each star's parameters came from the TOI table's own columns (Teff, log g, R★). Limb darkening used Teff and log g (the Sun's values where missing; Teff was published for 306 of 309 searched held-out stars), and ρ★ was computed from log g and R★, so the density test could act only on the 268 stars with both. The Sentinels are measured separately on a stated subsample
(Section 5.4), because every subject needs a CLI call.

**Scoring.** A TOI is *recovered* when a dip that passed vetting lies on its published ephemeris (within the
larger of 1 h, half the dip's duration and half the TOI's duration, widened by the propagated ephemeris error at
3σ, or on the BLS period or twice it). A found TOI is *flagged* when vetting rejected its dip or marked it
odd/even, secondary eclipse, V-shaped or density-mismatched. Rates carry Wilson 95% score intervals
(Wilson 1927). TFOPWG dispositions are the reference, not ground truth for every TOI.

**Controls.** Every star's light curve is also run flux-inverted (dips become bumps) and block-scrambled (every
known TOI's transits masked, then 0.5-day blocks shuffled, so no real transit or periodicity survives).
Any vetted dip on a control is a false alarm: the reliability idea of Thompson et al. 2018.

**Held-out split and threshold audit.** Nothing was tuned on this sample, so both halves are reported and the
held-out half is the headline. An automated audit compares every threshold-like value (113 module
constants, config keys and reviewer weights) with the commit before the sample was frozen (`fbc1ed9`):
0 changed (clean) across the 3 commits since. The Probe thresholds and weights
come from synthetic injection tests, and the vetting, V-shape, density and FAP rules were set before any TOI
light curve was downloaded.

**Code version.** Each per-star result records a fingerprint of the pipeline code that produced it:
`14f6f4830a525d78` = commit 76de67d (HEAD differs only in comments and docstrings); `e4fe4c99663ccba8` = commit 40cceca (HEAD differs only in comments and docstrings). The report was generated at commit `76de67d17eeef8a5fc62b26695574d0d63322b72`. Results from the earlier
fingerprint were re-vetted from their stored classifications with the later code, controls included.

## 5 Results

All rates are for the held-out half unless stated, with Wilson 95% intervals.

### 5.1 Completeness

| measure | result |
|---|---|
| CP/KP TOIs recovered, searchable stars (headline) | 57% (86/150; 95% CI 49–65%) |
| CP/KP TOIs recovered, all stars (no 2-minute data counts as missed) | 57% (86/152; 95% CI 49–64%) |
| below 2 R⊕ | 10% (2/20; 95% CI 3–30%) |
| 2 to 4 R⊕ | 23% (6/26; 95% CI 11–42%) |
| 4 to 8 R⊕ | 36% (4/11; 95% CI 15–65%) |
| 8 to 30 R⊕ | 80% (73/91; 95% CI 71–87%) |
| P in 0.5–2 d | 41% (12/29; 95% CI 26–59%) |
| P in 2–5 d | 67% (52/78; 95% CI 56–76%) |
| P in 5–13 d | 51% (22/43; 95% CI 37–65%) |
| CP/KP dips flagged binary-like (the cost of the flags) | 33% (40/123; 95% CI 25–41%) |
| tuning half, for comparison | 54% (80/148; 95% CI 46–62%) |
| both halves | 56% (166/298; 95% CI 50–61%) |

**Completeness is low for small planets.** Below 4 R⊕ the panel recovers 17% (8/46; 95% CI 9–31%); at 8 to 30 R⊕ it recovers
80% (73/91; 95% CI 71–87%). The headline is therefore carried by giant planets, which dominate the CP/KP sample. Of the
150 searchable CP/KP TOIs, 86 were recovered (82 on a periodic signal at the TOI's
period, 0 at an alias of it, 4 without a period) and 64 were not. On recovered CP/KP
TOIs the fit's median depth and duration ratios to the TOI values are 0.97 and 1.02.

The injection-recovery benchmark of the Probes on synthetic light curves agrees in shape. Recovered, by injected
depth, at durations of 1, 2 and 4 h: 300 ppm: 0/20, 0/20, 0/20; 1,000 ppm: 1/20, 12/20, 18/20; 3,000 ppm: 20/20, 19/20, 20/20; with 0.000 vetted candidates per empty subject over
40 empty subjects. Synthetic noise is not sky noise: the empty-subject rate there is far below what the
real-data controls show next.

### 5.2 False alarms: the controls, and the live feed

| control | vetted false dips | per 1,000 star-sectors | star-sectors with any |
|---|---|---|---|
| inverted | 177 over 309 (93 periodic, 84 single) | 573 | 21% (65/309; 95% CI 17–26%) |
| scrambled | 262 over 309 (67 periodic, 195 single) | 848 | 25% (78/309; 95% CI 21–30%) |

At the level of vetting alone, real light curves with every signal destroyed produce
573 (inverted) and 848 (scrambled) vetted dips per 1,000 star-sectors. The discovery feed's admission rule (Section 3.7) removes most
of them:

| curve | admitted | distinct `new_candidate` signals | per 1,000 star-sectors | star-sectors with any |
|---|---|---|---|---|
| real | 222 (206 on a known TOI) | 5 | 16 | |
| inverted | 76 | 17 | 55 | 6% (17/309; 95% CI 3–9%) |
| scrambled | 30 | 20 | 65 | 6% (20/309; 95% CI 4–10%) |

**The feed's "new" signals are consistent with noise.** The worse control gives 65 false new signals per
1,000 star-sectors. The feed reviews 2 sectors per target, so noise alone should give about
12.9 false `new_candidate` signals per 100 targets. This estimate is an approximation: it adds the
single-sector control rate over the sectors the feed reviews, as if each sector were an independent draw, and it
ignores that the feed reviews a star's two latest sectors, not its first, and that noise in the two sectors may be
correlated. The live catalogue (updated 2026-10-17) holds 3 distinct new signals over
19 targets: 15.8 per 100 (95% CI 6–38). Noise alone would account for 0.82 of that rate, at least half, so a `new_candidate` on the feed is more likely noise than a signal. The proposed fix (requiring the signal in each
of the two sectors independently, and a stricter FAP) has not been applied in the code measured here. It is
to be chosen on the tuning half and measured once on the held-out half:

| stricter feed rule | held-out result |
|---|---|
| rule | *pending: stricter feed rule* |
| false signals per 1,000 star-sectors, inverted | *pending: stricter feed rule* |
| false signals per 1,000 star-sectors, scrambled | *pending: stricter feed rule* |
| CP/KP completeness | *pending: stricter feed rule* |
| false `new_candidate` signals expected per 100 targets | *pending: stricter feed rule* |

### 5.3 False-positive TOIs

| measure | result |
|---|---|
| FP TOIs whose dip the panel found | 77% (96/124; 95% CI 69–84%) |
| … of those, rejected or flagged binary-like | 68% (65/96; 95% CI 58–76%) |
| FP TOIs whose dip passed vetting (with or without flags) | 31% (38/124; 95% CI 23–39%) |
| FA TOIs whose dip the panel found | 34% (12/35; 95% CI 21–51%) |

These rates describe only FP stars with 2-minute data (Section 5.5). We found no published light-curve-only
reference for the share of FP TOIs flagged.

### 5.4 The Sentinels on a stated subsample

Both Sentinels reviewed every subject of 40 held-out stars drawn with a fixed seed (20 CP/KP and
20 FP), on the real light curves only. Scored per star: did the persona mark a dip on the TOI's
ephemeris as a potential planet.

| persona | CP/KP dips marked | FP dips marked as a potential planet | failed calls |
|---|---|---|---|
| Sentinel · Volunteer | 50% (10/20; 95% CI 30–70%) | 20% (4/20; 95% CI 8–42%) | 0 |
| Sentinel · Skeptic | 50% (10/20; 95% CI 30–70%) | 20% (4/20; 95% CI 8–42%) | 0 |

**The two personas are correlated.** They agree on 38 of 40 stars (φ = 0.89). They share
one model, so the panel should count them as one correlated voter, not two independent ones. On the CP/KP
TOIs below 4 R⊕ in this subsample, Volunteer marked 0% (0/8; 95% CI 0–32%) and Skeptic
0% (0/8; 95% CI 0–32%). The
Sentinels were never run on the control light curves, so their false-alarm rate on real noise is not measured.

### 5.5 The class skew in the stars that could not be searched

In the held-out half 1% of CP/KP stars but 22% of FP stars have no SPOC
2-minute light curve, a skew of 20 percentage points. FP TOIs are more often found in full-frame images
only. The FP measures above therefore
describe 124 of 158 held-out FP TOIs, a population different from the full TOI FP list, and
are not the panel's reliability on all FP TOIs. The loss is a property of the stars and is reported, not
repaired.

### 5.6 A known bug in the code that produced these numbers

`preprocess.clean` deletes every point more than 10 times the point-to-point scatter below the running median,
with no run-length test, so a transit or eclipse deeper than about 10 times the per-cadence scatter loses its
in-transit points before review and BLS. A star is counted as exposed when the TOI depth exceeds 8
times the per-cadence scatter. In the held-out half 27 CP/KP, 11 FP and 0 FA stars are
exposed (of 309 measured); 21 exposed CP/KP TOIs were recovered anyway and 6
were missed, of which 3 lost at least half of their in-transit points to the bug (TOI
5801.01, 5972.01, 7475.01). The median share of in-transit points removed on exposed stars is 31%. In the
tuning half 7 of 8 exposed misses are explained by it.

| held-out measure | all stars | exposed stars excluded | after the fix |
|---|---|---|---|
| completeness (searchable) | 57% (86/150; 95% CI 49–65%) | 53% (65/123; 95% CI 44–61%) | *pending: clipping-fixed re-run* |
| FP TOIs found | 77% (96/124; 95% CI 69–84%) | 75% (85/113; 95% CI 67–82%) | *pending: clipping-fixed re-run* |
| … rejected or flagged | 68% (65/96; 95% CI 58–76%) | 68% (58/85; 95% CI 58–77%) | *pending: clipping-fixed re-run* |
| feed-level false signals per 1,000, inverted | 55 | 48 | *pending: clipping-fixed re-run* |
| feed-level false signals per 1,000, scrambled | 65 | 59 | *pending: clipping-fixed re-run* |

Excluding exposed stars changes the completeness from 57% to 53% (65/123; 95% CI 44–61%): exposed
CP/KP TOIs are deep, and 21 of 27 were recovered despite the bug. The
fix is on a separate branch; after it merges only the exposed stars are re-run (code *pending: clipping-fixed re-run*), and the
last column is filled from that re-run.

### 5.7 The leaderboard's seeded entries

The public leaderboard (Section 8) takes each method's detected events per held-out star and scores them itself
with the benchmark's own matching. Its rank key is Youden's J (Youden 1950), completeness over every CP/KP
star plus FP rejection over every FP star minus one, with a square-and-add interval from the two Wilson
intervals (Newcombe 1998): a method that calls every TOI a planet scores J = 0. Only held-out entries
measured on both controls are ranked. Seeded from the benchmark's stored events without re-running anything:

| entry | scope | rank | Youden J | completeness, all CP/KP stars | below 4 R⊕ | FP rejection, all FP stars | inverted control: stars with any | reliability |
|---|---|---|---|---|---|---|---|---|
| Probes only | held-out half | 1 | +0.37 (+0.26 to +0.46) | 57% (86/152; 95% CI 49–64%) | 17% (8/46; 95% CI 9–31%) | 80% (127/158; 95% CI 73–86%) | 21% (65/309; 95% CI 17–26%) | 70% (83/118; 95% CI 62–78%) |
| Probes only | Sentinel subsample | not ranked | +0.15 (-0.14 to +0.41) | 45% (9/20; 95% CI 26–66%) | 0% (0/8; 95% CI 0–32%) | 70% (14/20; 95% CI 48–85%) | 8% (3/40; 95% CI 3–20%) | 60% (9/15; 95% CI 36–80%) |
| Sentinel · Volunteer alone | Sentinel subsample | not ranked | +0.30 (+0.01 to +0.53) | 50% (10/20; 95% CI 30–70%) | 0% (0/8; 95% CI 0–32%) | 80% (16/20; 95% CI 58–92%) | not measured | 71% (10/14; 95% CI 45–88%) |
| Sentinel · Skeptic alone | Sentinel subsample | not ranked | +0.30 (+0.01 to +0.53) | 50% (10/20; 95% CI 30–70%) | 0% (0/8; 95% CI 0–32%) | 80% (16/20; 95% CI 58–92%) | not measured | 71% (10/14; 95% CI 45–88%) |
| Probes + Sentinels, either (star-level rule, fixed before scoring, not panel consensus) | Sentinel subsample | not ranked | +0.10 (-0.19 to +0.37) | 50% (10/20; 95% CI 30–70%) | 0% (0/8; 95% CI 0–32%) | 60% (12/20; 95% CI 39–78%) | not measured | 56% (10/18; 95% CI 34–75%) |
| Probes + Sentinels, both (star-level rule, fixed before scoring, not panel consensus) | Sentinel subsample | not ranked | +0.30 (+0.02 to +0.53) | 45% (9/20; 95% CI 26–66%) | 0% (0/8; 95% CI 0–32%) | 85% (17/20; 95% CI 64–95%) | not measured | 75% (9/12; 95% CI 47–91%) |

Two FP measures appear in this paper and they differ by definition. Section 5.3's "rejected or flagged" is over
the FP dips the panel found (68% (65/96; 95% CI 58–76%)); the leaderboard's FP rejection is over every FP star of the
scope, counting a star whose TOI dip was not found, not searched, or found and flagged as not offered as a clean
candidate (80% (127/158; 95% CI 73–86%) for the Probes; 75% (93/124; 95% CI 67–82%) over the searched FP stars only).
Reliability is the share of clean candidates on TOI dips that are CP/KP, on this sample's class mix
(150 CP/KP, 124 FP and 35 FA searched held-out stars), which is not the TOI catalogue's. The
two Probes + Sentinels rules were stated before any of them was scored, as star-level combinations of the stored
outcomes: *either* gives a clean candidate when the Probes give one or either Sentinel marks the dip as a
potential planet; *both* only when the Probes give one and a Sentinel marks it too. They are not a run of the
panel's mark-level consensus. **40 stars cannot order these configurations:** the subsample is never ranked,
and every pair of their completeness intervals overlaps.

### 5.8 Single-star validation: pi Men c

On TESS sector 1 of pi Men the panel recovered 5 of 5 predicted epochs of pi Men c. A
joint limb-darkened fit (u₁ = 0.341, u₂ = 0.224 for Teff 5992 K and log g 4.36) with the period free
gives Rp/R★ = 0.0179 ± 0.0017 (ratio 1.05 to Huang et al. 2018's 0.01703) and T14 = 3.07 ± 0.17 h (ratio
1.04 to 2.953 h); the model's mid-transit depth is 292 ± 8 ppm (ratio 0.97 to the
published 300 ppm, a differently defined quantity) and P = 6.2680 ± 0.0005 d (Huang: 6.26790 d).
5 TESS transits constrain the impact parameter only to b < 0.87 (1σ), so ρ★ is a range
(0.28 to 2.2 g/cm³). With the TIC density as a prior (1.02 ± 0.20 g/cm³) the fit gives b = 0.64 ± 0.12,
a/R★ = 12.85 (1σ 11.5 to 13.6) and T23/T14 = 0.95, against Huang's 0.59 and 13.38. The box
measure this fit replaced gave ratios of 0.81 in depth and 0.64 in duration. The periodic
signal's FAP is below 10⁻⁴: 0 of 10,000 block-bootstrap trials reached the observed SNR,
so the value is a bound set by the number of trials. One star is a check of the fit, not a benchmark.

## 6 Comparison with published reference numbers

These references measure different populations, data and tasks; they are context, not exoplan requirements.

| quantity | exoplan (held-out) | published reference |
|---|---|---|
| completeness | 57% (86/150; 95% CI 49–65%) on searchable stars, end to end (search, review, vetting) | Robovetter DR25: above 85% for P < 100 d, vetting alone, on injected transits already detected as TCEs (Thompson et al. 2018) |
| completeness, 3 to 4 R⊕ | 44% (4/9; 95% CI 19–73%) | Planet Hunters TESS: 51% (Eisner et al. 2021) |
| completeness, above 4 R⊕ | 75% (77/102; 95% CI 66–83%) | Planet Hunters TESS: 85% (Eisner et al. 2021) |
| reliability against inverted and scrambled data | vetted false dips on 21% (65/309; 95% CI 17–26%) and 25% (78/309; 95% CI 21–30%) of star-sectors | Robovetter DR25: reliability above 98% for P < 100 d (Thompson et al. 2018) |
| how many TOIs are false positives | the sample is stratified, not representative | prime mission: 565 of 2,241 (about 25%) found false positive by follow-up (Guerrero et al. 2021); Kepler KOIs overall 9.4% (Fressin et al. 2013) |
| statistical validation | none in the code measured; S3, FP TOIs labelled validated: *pending: S3 FPP* | TRICERATOPS "validated": FPP < 0.015 and NFPP < 10⁻³ (Giacalone et al. 2021); vespa on all KOIs (Morton et al. 2016) |

The radius rows use the bins Planet Hunters TESS reported, computed from the per-star rows and the TOI table's
radii. exoplan is below the Robovetter and Planet Hunters TESS on completeness in every comparable row, and far
from Robovetter-level reliability: its vetted false-alarm rate on the controls is 573 and
848 per 1,000 star-sectors before the feed's rule, and 55 and
65 after it, against the project's own proposed target of at most one per 1,000. The
comparison is not like for like. The Robovetter's completeness measures the vetting step on events the Kepler
pipeline had already detected, while exoplan's includes its own search; Kepler had a four-year baseline against
one TESS sector here; Planet Hunters TESS searched sectors 1 to 26 with human volunteers and science-team vetting;
and the Robovetter's reliability is a property of its candidate catalogue, ours a rate per star-sector. We make no
claim of matching either.

## 7 Limitations

* **No pixel-level vetting.** There is no centroid or difference-image test, so blended and background eclipsing
  binaries can pass. Pixel-level results are pending: FP stars flagged *pending: S2 pixel vetting*, CP/KP stars flagged
  *pending: S2 pixel vetting*.
* **No false-positive probability.** Nothing here is statistically validated; S3 results are pending
  (*pending: S3 FPP* of FP TOIs labelled validated; *pending: S3 FPP* of CP/KP TOIs likely planets).
* **The Sentinels are measured on 40 stars,** were calibrated on 10 injected and 10 empty subjects,
  and never ran on the controls. The model version that answered is not recorded: the cache key holds the
  CLI's model setting ("default"), not the served model. Their errors are correlated.
* **The clipping bug** (Section 5.6) affects deep transits in the code version measured.
* **The density test could act only on 268 of 309 searched held-out stars,** those whose TOI-table entry gives both log g and R★.
* **One sector per star, 2-minute data only.** Stars with only full-frame-image data are not searchable, and
  that loss is skewed toward FP TOIs (Section 5.5). Single transits and long periods are outside the sample's
  0.5 to 13.0 d range.
* **Dispositions are the reference, not the truth.** Some CP/KP and FP labels may be wrong.
* **The feed's `new_candidate` signals are consistent with noise:** noise alone would account for 0.82 of their
  rate (Section 5.2).
* **FAPs are bounded by the trials;** the Gumbel tail is extrapolated and indicative only.
* **Synthetic injections are not sky noise** (Section 5.1).

Every exoplan entry is a candidate. A detection means the pipeline saw a vetted dip; confirmation needs
independent evidence such as radial velocities, and no exoplan output is called confirmed or validated.

## 8 Reproducibility

* **Code.** The benchmark report was generated at commit `76de67d17eeef8a5fc62b26695574d0d63322b72` (Section 4 lists the pipeline
  fingerprints). The frozen sample is `docs/results/benchmark_toi_sample.json` (sha256 `6f0e111ec8d2c38d3e7927505f0be4a2c7fae8b73d7cc17c37646baedf044cac`); the report
  is `docs/results/benchmark_real_tois.md` and `.json`; the commands are in `scripts/benchmark_real_tois.py`
  (`freeze`, `run`, `sentinels`, `clipping`, `feed`, `report`). Downloads and per-subject outputs live in the
  gitignored `cache/`; the committed JSON holds every per-star outcome.
* **Sentinel responses** are cached by hash and replayed without new calls; the per-star Sentinel outcomes are
  committed in the leaderboard's seeded submissions.
* **This paper.** `python scripts/paper_numbers.py` regenerates `docs/paper/paper.md` and
  `docs/paper/numbers.json` from the committed JSON; `--check` fails when they differ, and `tests/test_paper.py`
  checks the paper's numbers against the JSON.
* **The leaderboard.** `docs/leaderboard/` holds the submission format, the rules, the public inputs (the
  tuning half with labels, the held-out half without; sha256 `d0e4f2d9c5538800e9a34d018757f99e1d1672060e71ae56bbaf87fcaf0c15b4`) and the scored table
  (6 entries, 0 refused). A submission lists each star's detected events on the real and
  control light curves; the leaderboard matches them to the ephemeris and counts control false alarms itself.
  `exoplan leaderboard <file>` scores a submission and refuses one that states anything but that hash, says it was
  tuned on the held-out half, carries a field outside the whitelist, or does not cover its scope.
* **What the leaderboard cannot check, and future work.** The hash is an attestation: the held-out labels are
  public, so no check can prove they were not read, and a method's own pass verdicts and control lists are its own
  report. Two designs would close these gaps and are not built: maintainer-held decoy light curves under opaque
  ids, whose truth only the maintainers hold, and prospective scoring on TOIs still undispositioned, scored once
  TFOPWG dispositions them.

## Pending results

These numbers will change. Their placeholders print *pending* until the stated file exists; the numbers
script then fills them, and never guesses.

* **clipping-fixed re-run**: pending; will be read from `docs/results/benchmark_real_tois_clipfix.json`.
* **stricter feed rule**: pending; will be read from `docs/results/feed_rule_validation.json`.
* **S2 pixel vetting**: pending; will be read from `docs/results/pixel_vetting.json`.
* **S3 FPP**: pending; will be read from `docs/results/fpp_validation.json`.

## References

* Claret, A. 2017, Limb and gravity-darkening coefficients for the TESS satellite at several metallicities, surface gravities, and microturbulent velocities. A&A, 600, A30. doi:[10.1051/0004-6361/201629705](https://doi.org/10.1051/0004-6361/201629705)
* Coughlin, J. L., Mullally, F., Thompson, S. E., et al. 2016, Planetary Candidates Observed by Kepler. VII. The First Fully Uniform Catalog Based on the Entire 48-month Data Set (Q1-Q17 DR24). ApJS, 224, 12. doi:[10.3847/0067-0049/224/1/12](https://doi.org/10.3847/0067-0049/224/1/12)
* Eisner, N. L., Barragán, O., Aigrain, S., et al. 2020, Planet Hunters TESS I: TOI 813, a subgiant hosting a transiting Saturn-sized planet on an 84-day orbit. MNRAS, 494, 750. doi:[10.1093/mnras/staa138](https://doi.org/10.1093/mnras/staa138)
* Eisner, N. L., Barragán, O., Lintott, C., et al. 2021, Planet Hunters TESS II: findings from the first two years of TESS. MNRAS, 501, 4669. doi:[10.1093/mnras/staa3739](https://doi.org/10.1093/mnras/staa3739)
* Fischer, D. A., Schwamb, M. E., Schawinski, K., et al. 2012, Planet Hunters: the first two planet candidates identified by the public using the Kepler public archive data. MNRAS, 419, 2900. doi:[10.1111/j.1365-2966.2011.19932.x](https://doi.org/10.1111/j.1365-2966.2011.19932.x)
* Fressin, F., Torres, G., Charbonneau, D., et al. 2013, The False Positive Rate of Kepler and the Occurrence of Planets. ApJ, 766, 81. doi:[10.1088/0004-637X/766/2/81](https://doi.org/10.1088/0004-637X/766/2/81)
* Giacalone, S., Dressing, C. D., Jensen, E. L. N., et al. 2021, Vetting of 384 TESS Objects of Interest with TRICERATOPS and Statistical Validation of 12 Planet Candidates. AJ, 161, 24. doi:[10.3847/1538-3881/abc6af](https://doi.org/10.3847/1538-3881/abc6af)
* Guerrero, N. M., Seager, S., Huang, C. X., et al. 2021, The TESS Objects of Interest Catalog from the TESS Prime Mission. ApJS, 254, 39. doi:[10.3847/1538-4365/abefe1](https://doi.org/10.3847/1538-4365/abefe1)
* Huang, C. X., Burt, J., Vanderburg, A., et al. 2018, TESS Discovery of a Transiting Super-Earth in the pi Mensae System. ApJL, 868, L39. doi:[10.3847/2041-8213/aaef91](https://doi.org/10.3847/2041-8213/aaef91)
* Jenkins, J. M., Twicken, J. D., McCauliff, S., et al. 2016, The TESS science processing operations center. Proc. SPIE, 9913, 99133E. doi:[10.1117/12.2233418](https://doi.org/10.1117/12.2233418)
* Kovács, G., Zucker, S., & Mazeh, T. 2002, A box-fitting algorithm in the search for periodic transits. A&A, 391, 369. doi:[10.1051/0004-6361:20020802](https://doi.org/10.1051/0004-6361:20020802)
* Mandel, K., & Agol, E. 2002, Analytic Light Curves for Planetary Transit Searches. ApJL, 580, L171. doi:[10.1086/345520](https://doi.org/10.1086/345520)
* Morton, T. D., Bryson, S. T., Coughlin, J. L., et al. 2016, False Positive Probabilities for all Kepler Objects of Interest: 1284 Newly Validated Planets and 428 Likely False Positives. ApJ, 822, 86. doi:[10.3847/0004-637X/822/2/86](https://doi.org/10.3847/0004-637X/822/2/86)
* Newcombe, R. G. 1998, Interval estimation for the difference between independent proportions: comparison of eleven methods. Statistics in Medicine, 17, 873. doi:[10.1002/(SICI)1097-0258(19980430)17:8<873::AID-SIM779>3.0.CO;2-I](https://doi.org/10.1002/(SICI)1097-0258(19980430)17:8%3C873::AID-SIM779%3E3.0.CO;2-I)
* Ricker, G. R., Winn, J. N., Vanderspek, R., et al. 2015, Transiting Exoplanet Survey Satellite. Journal of Astronomical Telescopes, Instruments, and Systems, 1, 014003. doi:[10.1117/1.JATIS.1.1.014003](https://doi.org/10.1117/1.JATIS.1.1.014003)
* Shallue, C. J., & Vanderburg, A. 2018, Identifying Exoplanets with Deep Learning: A Five-planet Resonant Chain around Kepler-80 and an Eighth Planet around Kepler-90. AJ, 155, 94. doi:[10.3847/1538-3881/aa9e09](https://doi.org/10.3847/1538-3881/aa9e09)
* Stassun, K. G., Oelkers, R. J., Paegert, M., et al. 2019, The Revised TESS Input Catalog and Candidate Target List. AJ, 158, 138. doi:[10.3847/1538-3881/ab3467](https://doi.org/10.3847/1538-3881/ab3467)
* Stoppa, F., Bulmus, T., Bloemen, S., et al. 2025, Textual interpretation of transient image classifications from large language models. Nature Astronomy, 9, 1869. doi:[10.1038/s41550-025-02670-z](https://doi.org/10.1038/s41550-025-02670-z)
* Thompson, S. E., Coughlin, J. L., Hoffman, K., et al. 2018, Planetary Candidates Observed by Kepler. VIII. A Fully Automated Catalog with Measured Completeness and Reliability Based on Data Release 25. ApJS, 235, 38. doi:[10.3847/1538-4365/aab4f9](https://doi.org/10.3847/1538-4365/aab4f9)
* Twicken, J. D., Catanzarite, J. H., Clarke, B. D., et al. 2018, Kepler Data Validation I: Architecture, Diagnostic Tests, and Data Products for Vetting Transiting Planet Candidates. PASP, 130, 064502. doi:[10.1088/1538-3873/aab694](https://doi.org/10.1088/1538-3873/aab694)
* Valizadegan, H., Martinho, M. J. S., Wilkens, L. S., et al. 2022, ExoMiner: A Highly Accurate and Explainable Deep Learning Classifier That Validates 301 New Exoplanets. ApJ, 926, 120. doi:[10.3847/1538-4357/ac4399](https://doi.org/10.3847/1538-4357/ac4399)
* Wilson, E. B. 1927, Probable Inference, the Law of Succession, and Statistical Inference. Journal of the American Statistical Association, 22, 209. doi:[10.1080/01621459.1927.10502953](https://doi.org/10.1080/01621459.1927.10502953)
* Youden, W. J. 1950, Index for rating diagnostic tests. Cancer, 3, 32. doi:[10.1002/1097-0142(1950)3:1<32::AID-CNCR2820030106>3.0.CO;2-3](https://doi.org/10.1002/1097-0142(1950)3:1%3C32::AID-CNCR2820030106%3E3.0.CO;2-3)
* Yu, L., Vanderburg, A., Huang, C., et al. 2019, Identifying Exoplanets with Deep Learning. III. Automated Triage and Vetting of TESS Candidates. AJ, 158, 25. doi:[10.3847/1538-3881/ab21d6](https://doi.org/10.3847/1538-3881/ab21d6)
* Zooniverse project page (Merín, B., researcher) 2026, Planet Hunters CHEOPS. https://www.zooniverse.org/projects/bmerin/planet-hunters-cheops.

<!--
  Source of docs/paper/paper.md. Do not edit paper.md by hand: run `python scripts/paper_numbers.py`.
  Every result is a double-brace placeholder filled from the committed JSON; tests/test_paper.py fails when
  a percentage, a k/n count or a decimal is typed here instead. Typed here, and only as definitions or
  context: physical units, identifiers (TIC, sector, TOI names), the published papers' own ranges, and the
  clipping factor of the bug as the benchmark report states it.
-->

# SetuHQ: a blind benchmark of a calibrated panel of language-model and matched-filter reviewers for TESS transit search

**The SetuHQ contributors** (repository: ashfordeOU/SetuHQ)

*Draft methods paper in the style of the AAS journals (AJ). Markdown only: the aastex631 class is not
available offline in the environment that produced this draft, so no LaTeX version is provided yet.*

*Generated from the committed results by `scripts/paper_numbers.py` (benchmark report of {{generated_at}},
code commit `{{code_commit}}`: the benchmark re-run on the current code, after the two fixes of Section 5.6). Results
that later work will change are marked pending; see the section "Pending results".*

Sentinels run on Claude (Anthropic). Probes are deterministic matched-filter detectors.

## Abstract

We describe SetuHQ, an open-source transit search that copies the Planet Hunters task (mark the start and
end of each dip in a blind-coded light curve, then label it a potential planet or noise) but replaces the
volunteers with a panel of reviewers: *Sentinels*, which are personas of one large language model (Claude)
that read the rendered plot and give their reasons in words, and *Probes*, deterministic matched-filter
detectors. Marks are clustered and scored by skill-weighted consensus, then vetted from the light curve
alone, fitted with a limb-darkened model, and given a bounded block-bootstrap false-alarm probability. We
measure the deterministic panel on a frozen, blind sample of {{sample_total}} TESS Objects of Interest
({{sample_pos}} confirmed or known planets, {{sample_fp}} false positives and {{sample_fa}} false alarms, one per star),
split by star into a tuning and a held-out half, with flux-inverted and block-scrambled copies of every light
curve as false-alarm controls. On the held-out half the panel recovers {{ho_completeness}} of the CP/KP TOIs
on stars with SPOC 2-minute data, but only {{ho_rad_r0}} {{ho_rad_r0_bin}} and {{ho_rad_r1}} at {{ho_rad_r1_bin}}. It finds the
dip of {{ho_fp_seen}} of the false-positive TOIs with 2-minute data and rejects or flags {{ho_fp_flagged}} of the
dips it found; counted over every held-out FP star, {{lb_probes_fprej_all}} are not offered as clean candidates.
The controls
show that the live discovery feed's "new" signals are {{feed_bad}}: the feed's own admission rule passes
{{feed_inverted_per1000}} and {{feed_scrambled_per1000}} false signals per 1,000 star-sectors on the inverted and
scrambled curves, about {{feed_expected_per100}} per 100 targets, against {{feed_live_per100}} per 100 on the live
feed. The two Sentinel personas, tested on a stated subsample of {{sen_n}} held-out stars, each mark
{{sen_vol_cpkp}} of the CP/KP dips and agree on {{sen_agree}} of {{sen_agree_n}} stars (φ = {{sen_phi}}): they are one
correlated voter, not two. We report a bug in the code of the benchmark's first run, fixed since, and the same
protocol re-run on the fixed code (the numbers above), the class skew
of the stars that could not be searched, and a public leaderboard on the frozen sample that scores submitted
events itself and ranks by Youden's J. On that leaderboard a baseline that never reads a light curve, a logistic
regression on catalogue metadata fitted on the tuning half, scores J = {{lb_metadata_baseline_j}} against
{{lb_probes_j}} for the Probes. {{floor_sentence}} Nothing here is a
discovery, and no SetuHQ output is called a confirmed or validated planet.

## 1 Introduction

Volunteers inspecting light curves by eye have found transit candidates and planets: two planet candidates
in the first month of Planet Hunters on Kepler data ({{cite_fischer2012}}), and TOI-813 b, the first Planet
Hunters TESS planet ({{cite_eisner2020}}). In Planet Hunters TESS, {{ref_pht_volunteers}} volunteers marked transit-like events in
sectors 1 to 26; a clustering step ranked them, the science team vetted the top events, and the project
recovered {{ref_pht_large}} of TOIs larger than 4 R⊕ and {{ref_pht_mid}} of those at 3 to 4 R⊕ ({{cite_eisner2021}}).
The Planet Hunters CHEOPS project on Zooniverse (see References) uses the same task on CHEOPS light curves; SetuHQ copies
that task exactly.

Automated vetting has a longer quantitative record. Kepler's Robovetter, a deterministic decision tree, was
measured for completeness with injected transits and for reliability with inverted and scrambled light
curves ({{cite_coughlin2016}}; {{cite_thompson2018}}); for periods below 100 days its DR25 catalogue reached a
completeness {{ref_robovetter_completeness}} and a reliability {{ref_robovetter_reliability}} ({{cite_thompson2018}}).
That completeness is the vetter's alone: it is measured on injected transits that the pipeline had already detected
as threshold-crossing events, whereas SetuHQ's completeness below is end to end, from light curve to vetted dip.
Machine-learned vetters rank threshold-crossing events by learning from labelled examples: AstroNet ranked a
plausible planet above a false positive in {{ref_astronet_ranking}} of test pairs ({{cite_shallue2018}}), a variant
triages and vets TESS candidates ({{cite_yu2019}}), and ExoMiner reports {{ref_exominer_recall}}
({{cite_valizadegan2022}}). These classifiers inherit label noise and distribution shift, and their scores are
not probabilities unless calibrated.

Large language models that read images and explain their reasoning are a newer kind of reviewer. They have
classified images of astronomical transients and explained the classifications in text ({{cite_stoppa2025}}). In the
literature collected for this work we found no published benchmark of such reviewers on TESS transit vetting
with controls and a held-out split, so we make no comparison with one. SetuHQ treats a language-model reviewer as one calibrated voice in a panel, beside
deterministic detectors whose behaviour can be measured exactly, and asks what such a panel can claim on a
stated benchmark.

The answer here is modest and partly negative. This paper describes the method (Section 3), a blind benchmark
on real TOIs with controls (Section 4), the results with their failures (Section 5), a comparison with published
reference numbers (Section 6), the limitations (Section 7) and how to reproduce every number (Section 8).

## 2 Data

**Light curves.** TESS ({{cite_ricker2015}}) SPOC 2-minute PDCSAP light curves ({{cite_jenkins2016}}), downloaded
from MAST. For the benchmark each star's first SPOC 2-minute sector is used. Stellar effective temperature,
surface gravity and density come from the TESS Input Catalog ({{cite_stassun2019}}) when the fit needs them.

**The benchmark sample.** From the NASA Exoplanet Archive `toi` table (fetched {{sample_fetched}}): TOIs whose
TFOPWG disposition is CP or KP (positives), FP or FA, with {{period_lo}} ≤ P ≤ {{period_hi}} d (so a 27-day sector
holds at least two transits) and a published period, mid-time and duration; one TOI per star, drawn in a
seeded order (seed {{sample_seed}}) until each class was full: {{sample_pos}} CP/KP, {{sample_fp}} FP and {{sample_fa}} FA
(the FA class ran out of eligible stars below its quota). The sample, its dispositions and the table's fetch
date were stored with a hash before any light curve was downloaded: sha256 `{{sample_sha}}`.

**The split.** Each star is assigned to a tuning or a held-out half by the parity of sha256(seed:TIC). The
held-out half has {{held_out_positive_n}} CP/KP, {{held_out_fp_n}} FP and {{held_out_fa_n}} FA TOIs ({{held_out_total}} stars).

**Not searchable.** A star with no SPOC 2-minute light curve cannot be searched by this pipeline. In the held-out
half that is {{held_out_positive_ns}} CP/KP ({{held_out_positive_ns_pct}}), {{held_out_fp_ns}} FP ({{held_out_fp_ns_pct}}) and
{{held_out_fa_ns}} FA ({{held_out_fa_ns_pct}}) stars; in the tuning half {{tuning_positive_ns_pct}}, {{tuning_fp_ns_pct}} and
{{tuning_fa_ns_pct}}. No star was lost to a download or run failure ({{held_out_failed}} in the held-out half). **The loss
is skewed toward false positives**, which are more often found in full-frame images only (Section 5.5).

**pi Mensae.** The single-star validation uses TESS sector 1 of pi Men (TIC 261136679) and the parameters of
pi Men c from {{cite_huang2018}}, read from the archive's `ps` table.

## 3 Method

### 3.1 Subjects and blinding

Light curves are cleaned (spike clipping), detrended with a masked local-quadratic baseline over a
{{m_detrend}}-day window, binned to {{m_bin}} minutes and cut into fixed {{m_subject_days}}-day *subjects* with opaque
identifiers. No reviewer sees the target's name, its TOI status or its ephemeris; dispositions and ephemerides
are used only when scoring.

### 3.2 The reviewer panel

**Probes.** Three deterministic detectors (Sensitive, Typical and Cautious) run a single-event matched-filter
search and a box least-squares search (BLS; {{cite_kovacs2002}}) on each subject and mark every event above their
signal-to-noise threshold, with a stated miss probability and boundary jitter so that they behave like
human markers with limits. They are seeded and fully reproducible.

**Sentinels.** Two personas of one model, Claude, reached through the Claude Code CLI: *Volunteer* (careful,
marks dips) and *Skeptic* (rejects binary and systematic signatures unless they are clear). Each receives the
volunteers' task text, the rendered blind-coded plot and nothing else, and returns strict JSON (marks, a
label, a noise reason and a sentence of rationale), which is validated and clipped to the subject's time
range. Responses are cached by a hash of the backend, the model setting, the prompt version
({{sen_prompt}}), the persona and the request, so a re-run reproduces them at no cost.

**Calibration.** Each reviewer's weight is its skill on injected transits: the true-positive rate on
injected subjects minus the false-positive rate on empty ones, floored at {{cal_floor}}. The Probes were calibrated on synthetic white-plus-red-noise light curves; the Sentinels, each needing
one CLI call per subject, on only {{cal_n_inj}} injected and {{cal_n_empty}} empty subjects: weight {{cal_sen_w}} each,
against {{cal_probe_w}} for the Probes. That sample is too small to separate the reviewers' skills.

### 3.3 Aggregation

Marks closer than {{m_gap}} d are one dip (single-linkage clustering). A dip's score is the skill-weighted
share of the panel that marked it, and a consensus dip needs a score of at least {{m_min_score}} on a subject the
panel calls a potential planet with a weighted share of at least {{m_min_planet}}. This mirrors the
user-weighted scores of Planet Hunters TESS ({{cite_eisner2021}}).

### 3.4 Vetting

Every consensus dip is vetted from the light curve alone: an SNR of at least {{m_min_snr}}, a duration of at least
{{m_min_dur}} minutes, an edge test ({{m_edge}} d), and, on a periodic signal, odd/even depth and half-phase secondary
eclipse tests at {{m_sigma}}σ, plus the fit's V-shape and stellar-density tests below. These mirror part of the
Kepler and TESS Data Validation suite ({{cite_twicken2018}}; {{cite_guerrero2021}}). There is no centroid,
difference-image or pixel-level test.

### 3.5 Limb-darkened fit

Each consensus dip gets a quadratic limb-darkened transit fit ({{cite_mandel2002}}) with coefficients from
{{cite_claret2017}} for the TIC's effective temperature and surface gravity. It reports depth, T14, the impact
parameter b, mid-time and the transit stellar density ρ★ with errors that add the covariance to the spread
along the impact-parameter profile. On a periodic signal the period is fitted near the BLS period. When b is
poorly constrained it is printed as an upper limit and ρ★ as a range, and a second fit with the TIC density as
a Gaussian prior is stored beside the free one. A ρ★ outside {{m_rho_lo}} to {{m_rho_hi}} times the catalogue value at 3σ
is flagged (an illustrative band, not a published threshold), and a V-shaped fit is flagged as binary-like.

### 3.6 False-alarm probability

A periodic signal's FAP is (k + 1)/(N + 1) over N block-bootstrap trials: the detected box is removed, the
residuals are cut into {{m_fap_block}}-day blocks and shuffled, and BLS reruns on each copy; k copies reach the
observed SNR. The FAP is never given below 1/(N + 1), so with k = 0 it is an upper bound. A Gumbel fit to the
null maxima is stored as an indicative tail, never below {{m_tail_floor}}. The library default is {{m_fap_default}}
trials and the discovery feed uses {{feed_fap_trials}}.

### 3.7 The discovery feed

A scheduled job reviews the two latest sectors of TOI host stars and keeps every vetted dip in a catalogue,
marked `known_toi` when it matches a published TOI ephemeris and `new_candidate` otherwise. A dip is admitted
when it passed vetting, lies on its star's periodic signal, is at most {{m_feed_depth}} ppm deep, has at least
{{m_feed_transits}} transits and a FAP below {{m_feed_fap}}{{m_feed_two_sector}}. Section 5.2 measures what the earlier
rule (FAP below {{bench_feed_fap}} over {{bench_feed_fap_trials}} trials, one sector) admitted from noise; the current rule
is the one proposed in Section 5.2.

## 4 Benchmark design

**Frozen sample and blinding.** Section 2. The pipeline sees only light curves with opaque subject ids.

**The panel measured.** The three Probes with their frozen calibrated weights (measured on the code of 2026-10-16; on the current code the same
calibration gives other rates but the same two-of-three consensus decisions), sector-wide BLS, vetting and the
limb-darkened fit, without the FAP rule (it is not part of vetting). The feed-level table adds the feed's FAP
({{bench_feed_fap_trials}} trials) and its admission rule at the time. {{bench_stellar_sentence}} The Sentinels are measured separately on a stated subsample
(Section 5.4), because every subject needs a CLI call.

**Scoring.** A TOI is *recovered* when a dip that passed vetting lies on its published ephemeris (within the
larger of 1 h, half the dip's duration and half the TOI's duration, widened by the propagated ephemeris error at
3σ, or on the BLS period or twice it). A found TOI is *flagged* when vetting rejected its dip or marked it
odd/even, secondary eclipse, V-shaped or density-mismatched. Rates carry Wilson 95% score intervals
({{cite_wilson1927}}). TFOPWG dispositions are the reference, not ground truth for every TOI.

**Controls.** Every star's light curve is also run flux-inverted (dips become bumps) and block-scrambled (every
known TOI's transits masked, then {{m_fap_block}}-day blocks shuffled, so no real transit or periodicity survives).
Any vetted dip on a control is a false alarm: the reliability idea of {{cite_thompson2018}}.

**Held-out split and threshold audit.** Nothing was tuned on this sample, so both halves are reported and the
held-out half is the headline. An automated audit compares every threshold-like value ({{audit_values}} module
constants, config keys and reviewer weights) with the commit before the sample was frozen (`{{audit_frozen}}`):
{{audit_sentence}}. The Probe thresholds and weights
come from synthetic injection tests, and the vetting, V-shape, density and FAP rules were set before any TOI
light curve was downloaded.

**Code version.** Each per-star result records a fingerprint of the pipeline code that produced it:
{{code_fingerprints}}. The report was generated at commit `{{code_commit_full}}`. Every star, controls included, was
run again from its light curve with this code; no stored classification was reused. The first run, on the pre-fix
code (commit {{first_code}}), is kept as `docs/results/benchmark_real_tois.json`.

## 5 Results

All rates are for the held-out half unless stated, with Wilson 95% intervals.

### 5.1 Completeness

| measure | result |
|---|---|
| CP/KP TOIs recovered, searchable stars (headline) | {{ho_completeness}} |
| CP/KP TOIs recovered, all stars (no 2-minute data counts as missed) | {{ho_completeness_all}} |
| {{ho_rad_r0_bin}} | {{ho_rad_r0}} |
| {{ho_rad_r1_bin}} | {{ho_rad_r1}} |
| {{ho_rad_r2_bin}} | {{ho_rad_r2}} |
| {{ho_rad_r3_bin}} | {{ho_rad_r3}} |
| P in {{ho_per_0_bin}} | {{ho_per_0}} |
| P in {{ho_per_1_bin}} | {{ho_per_1}} |
| P in {{ho_per_2_bin}} | {{ho_per_2}} |
| CP/KP dips flagged binary-like (the cost of the flags) | {{ho_pos_flagged}} |
| tuning half, for comparison | {{tu_completeness}} |
| both halves | {{all_completeness}} |

**Completeness is low for small planets.** {{ho_rad_small_bin_cap}} the panel recovers {{ho_rad_small}}; at {{ho_rad_r3_bin}} it recovers
{{ho_rad_r3}}. The headline is therefore carried by giant planets, which dominate the CP/KP sample. Of the
{{ho_pos_searched}} searchable CP/KP TOIs, {{ho_rec_total}} were recovered ({{ho_rec_at_p}} on a periodic signal at the TOI's
period, {{ho_rec_alias}} at an alias of it, {{ho_rec_noperiod}} without a period) and {{ho_not_rec}} were not. On recovered CP/KP
TOIs the fit's median depth and duration ratios to the TOI values are {{ho_depth_ratio}} and {{ho_duration_ratio}}.

The injection-recovery benchmark of the Probes on synthetic light curves agrees in shape. Recovered, by injected
depth, at durations of {{inj_durations}}: {{inj_grid}}; with {{inj_fp}} vetted candidates per empty subject over
{{inj_empty}} empty subjects. Synthetic noise is not sky noise: the empty-subject rate there is far below what the
real-data controls show next.

### 5.2 False alarms: the controls, and the live feed

| control | vetted false dips | per 1,000 star-sectors | star-sectors with any |
|---|---|---|---|
| inverted | {{ho_inverted_dips}} over {{ho_inverted_ss}} ({{ho_inverted_periodic}} periodic, {{ho_inverted_single}} single) | {{ho_inverted_per1000}} | {{ho_inverted_any}} |
| scrambled | {{ho_scrambled_dips}} over {{ho_scrambled_ss}} ({{ho_scrambled_periodic}} periodic, {{ho_scrambled_single}} single) | {{ho_scrambled_per1000}} | {{ho_scrambled_any}} |

At the level of vetting alone, real light curves with every signal destroyed produce
{{ho_inverted_per1000}} (inverted) and {{ho_scrambled_per1000}} (scrambled) vetted dips per 1,000 star-sectors. The discovery feed's admission rule (Section 3.7) removes most
of them:

| curve | admitted | distinct `new_candidate` signals | per 1,000 star-sectors | star-sectors with any |
|---|---|---|---|---|
| real | {{feed_real_admitted}} ({{feed_real_known}} on a known TOI) | {{feed_real_new}} | {{feed_real_per1000}} | |
| inverted | {{feed_inverted_admitted}} | {{feed_inverted_new}} | {{feed_inverted_per1000}} | {{feed_inverted_any}} |
| scrambled | {{feed_scrambled_admitted}} | {{feed_scrambled_new}} | {{feed_scrambled_per1000}} | {{feed_scrambled_any}} |

**The feed's "new" signals are {{feed_bad}}.** The worse control gives {{feed_worst_per1000}} false new signals per
1,000 star-sectors. The feed reviews {{feed_sectors_per_target}} sectors per target, so noise alone should give about
{{feed_expected_per100}} false `new_candidate` signals per 100 targets. This estimate is an approximation: it adds the
single-sector control rate over the sectors the feed reviews, as if each sector were an independent draw, and it
ignores that the feed reviews a star's two latest sectors, not its first, and that noise in the two sectors may be
correlated. The live catalogue (updated {{feed_live_updated}}) holds {{feed_live_new}} distinct new signals over
{{feed_live_targets}} targets: {{feed_live_per100}} per 100 (95% CI {{feed_live_ci}}). {{feed_half_sentence}} This table keeps the rule the
protocol was frozen with. The fix the first run proposed (requiring the signal in each of the two sectors
independently, and a stricter FAP) is now the feed's rule. {{feedrule_intro}}

| stricter feed rule | held-out result |
|---|---|
| rule | {{feedrule_rule}} |
| false signals per 1,000 star-sectors, inverted | {{feedrule_inverted}} |
| false signals per 1,000 star-sectors, scrambled | {{feedrule_scrambled}} |
| CP/KP completeness | {{feedrule_completeness}} |
| false `new_candidate` signals expected per 100 targets | {{feedrule_per100}} |

{{feedrule_after}}

### 5.3 False-positive TOIs

| measure | result |
|---|---|
| FP TOIs whose dip the panel found | {{ho_fp_seen}} |
| … of those, rejected or flagged binary-like | {{ho_fp_flagged}} |
| FP TOIs whose dip passed vetting (with or without flags) | {{ho_fp_passed}} |
| FA TOIs whose dip the panel found | {{ho_fa_seen}} |

These rates describe only FP stars with 2-minute data (Section 5.5). We found no published light-curve-only
reference for the share of FP TOIs flagged.

### 5.4 The Sentinels on a stated subsample

Both Sentinels reviewed every subject of {{sen_n}} held-out stars drawn with a fixed seed ({{sen_n_pos}} CP/KP and
{{sen_n_fp}} FP), on the real light curves only. {{sen_carry_sentence}} Scored per star: did the persona mark a dip on the TOI's
ephemeris as a potential planet.

| persona | CP/KP dips marked | FP dips marked as a potential planet | failed calls |
|---|---|---|---|
| Sentinel · Volunteer | {{sen_vol_cpkp}} | {{sen_vol_fp}} | {{sen_vol_errors}} |
| Sentinel · Skeptic | {{sen_skp_cpkp}} | {{sen_skp_fp}} | {{sen_skp_errors}} |

**The two personas are correlated.** They agree on {{sen_agree}} of {{sen_agree_n}} stars (φ = {{sen_phi}}). They share
one model, so the panel should count them as one correlated voter, not two independent ones. On the CP/KP
TOIs {{ho_rad_small_bin}} in this subsample, Volunteer marked {{lb_claude_volunteer_small}} and Skeptic
{{lb_claude_skeptic_small}}. The
Sentinels were never run on the control light curves, so their false-alarm rate on real noise is not measured.

### 5.5 The class skew in the stars that could not be searched

In the held-out half {{held_out_positive_ns_pct}} of CP/KP stars but {{held_out_fp_ns_pct}} of FP stars have no SPOC
2-minute light curve, a skew of {{skew_points}} percentage points. FP TOIs are more often found in full-frame images
only. The FP measures above therefore
describe {{held_out_fp_data}} of {{held_out_fp_n}} held-out FP TOIs, a population different from the full TOI FP list, and
are not the panel's reliability on all FP TOIs. The loss is a property of the stars and is reported, not
repaired.

### 5.6 A bug in the first run's code, fixed, and the re-run

In the code of the benchmark's first run (commit {{first_code}}), `preprocess.clean` deleted every point more than 10
times the point-to-point scatter below the running median, with no run-length test, so a transit or eclipse deeper
than about 10 times the per-cadence scatter lost its in-transit points before review and BLS. A star is counted as
exposed when the TOI depth exceeds {{clip_ratio}} times the per-cadence scatter. In the held-out half {{clip_pos}} CP/KP,
{{clip_fp}} FP and {{clip_fa}} FA stars were exposed (of {{clip_measured}} measured); {{clip_recovered}} exposed CP/KP TOIs were
recovered anyway and {{clip_missed}} were missed, of which {{clip_explained}} lost at least half of their in-transit points
to the bug (TOI {{clip_tois}}). The median share of in-transit points removed on exposed stars was
{{clip_median_removed}}. In the tuning half {{clip_tuning_explained}} of {{clip_tuning_missed}} exposed misses were explained by it.

Two fixes followed. `clean` now keeps a low point that is part of a dip (a run of at least max(3, 20 minutes /
cadence) cadences more than 3σ below the median), and `vet.py`'s odd/even test, which the deep dips now reaching it
failed spuriously, inflates its errors by the per-epoch depths' scatter and carries a {{m_odd_even_floor}} systematic floor. Both change
default results. The whole benchmark was then run again on the fixed code with the protocol unchanged: the same
sample, seed, split, light curves, controls and scoring, nothing tuned. The numbers in Section 5.1 to Section 5.5 are the
re-run's.

| held-out measure | first run | first run, exposed stars excluded | re-run on the fixed code |
|---|---|---|---|
| completeness (searchable) | {{first_completeness}} | {{clip_unaff_completeness}} | {{ho_completeness}} |
| FP TOIs found | {{first_fp_seen}} | {{clip_unaff_fp_seen}} | {{ho_fp_seen}} |
| … rejected or flagged | {{first_fp_flagged}} | {{clip_unaff_fp_flagged}} | {{ho_fp_flagged}} |
| feed-level false signals per 1,000, inverted | {{first_feed_inverted}} | {{clip_unaff_feed_inverted}} | {{feed_inverted_per1000}} |
| feed-level false signals per 1,000, scrambled | {{first_feed_scrambled}} | {{clip_unaff_feed_scrambled}} | {{feed_scrambled_per1000}} |

{{rerun_change_sentence}} Of the {{rerun_exposed_n}} exposed CP/KP stars, the first run recovered {{rerun_exposed_first}}
and the re-run {{rerun_exposed_now}}; of the misses the bug explained, the re-run recovers TOI {{rerun_explained_now}} (still
missed: {{rerun_explained_still}}). The first run's report is kept as `docs/results/benchmark_real_tois.md`; the re-run's,
with every measure side by side, is `docs/results/benchmark_real_tois_clipfix.md`.

### 5.7 The leaderboard's seeded entries

The public leaderboard (Section 8) takes each method's detected events per held-out star and scores them itself
with the benchmark's own matching. Its rank key is Youden's J ({{cite_youden1950}}) with a square-and-add interval
from the two Wilson intervals ({{cite_newcombe1998}}), computed on the searchable set the benchmark fixed (stars with
a SPOC 2-minute light curve) with one predicate on both sides, a *clean candidate*: an event on the TOI's ephemeris
that passed vetting with no eclipsing-binary flag. J is the share of CP/KP stars offered as clean candidates plus
the share of FP stars not offered, minus one. Calling every TOI a planet scores J = 0 whether or not every event
carries a flag, and calling a searchable star "not searched" counts it as not offered. An earlier version counted a
flagged dip as found for CP/KP and as rejected for FP, which a copy of the public ephemerides with a V-shape flag on
every star exploited to score J = +1; a test now covers each flag. J over every star of the scope is reported beside
the rank key. Only held-out entries with both control lists are ranked; the controls gate ranking, do not enter J,
and are the method's own report.

| entry | scope | rank | Youden J | Youden J, all stars | clean completeness, searchable CP/KP | FP rejection, searchable FP | inverted control: stars with any | reliability |
|---|---|---|---|---|---|---|---|---|
| Metadata only, no light curve (a floor) | held-out half | {{lb_metadata_baseline_rank}} | {{lb_metadata_baseline_j}} | {{lb_metadata_baseline_j_all}} | {{lb_metadata_baseline_ccs}} | {{lb_metadata_baseline_fprs}} | {{lb_metadata_baseline_inv}} | {{lb_metadata_baseline_rel}} |
| Probes only | held-out half | {{lb_probes_rank}} | {{lb_probes_j}} | {{lb_probes_j_all}} | {{lb_probes_ccs}} | {{lb_probes_fprs}} | {{lb_probes_inv}} | {{lb_probes_rel}} |
| Probes only | Sentinel subsample | not ranked | {{lb_probes_subsample_j}} | {{lb_probes_subsample_j_all}} | {{lb_probes_subsample_ccs}} | {{lb_probes_subsample_fprs}} | {{lb_probes_subsample_inv}} | {{lb_probes_subsample_rel}} |
| Sentinel · Volunteer alone | Sentinel subsample | not ranked | {{lb_claude_volunteer_j}} | {{lb_claude_volunteer_j_all}} | {{lb_claude_volunteer_ccs}} | {{lb_claude_volunteer_fprs}} | {{lb_claude_volunteer_inv}} | {{lb_claude_volunteer_rel}} |
| Sentinel · Skeptic alone | Sentinel subsample | not ranked | {{lb_claude_skeptic_j}} | {{lb_claude_skeptic_j_all}} | {{lb_claude_skeptic_ccs}} | {{lb_claude_skeptic_fprs}} | {{lb_claude_skeptic_inv}} | {{lb_claude_skeptic_rel}} |
| Probes + Sentinels, either (star-level rule, fixed before scoring, not panel consensus) | Sentinel subsample | not ranked | {{lb_probes_or_sentinel_j}} | {{lb_probes_or_sentinel_j_all}} | {{lb_probes_or_sentinel_ccs}} | {{lb_probes_or_sentinel_fprs}} | {{lb_probes_or_sentinel_inv}} | {{lb_probes_or_sentinel_rel}} |
| Probes + Sentinels, both (star-level rule, fixed before scoring, not panel consensus) | Sentinel subsample | not ranked | {{lb_probes_and_sentinel_j}} | {{lb_probes_and_sentinel_j_all}} | {{lb_probes_and_sentinel_ccs}} | {{lb_probes_and_sentinel_fprs}} | {{lb_probes_and_sentinel_inv}} | {{lb_probes_and_sentinel_rel}} |

**A baseline that never reads a light curve.** The first row is a floor: a logistic regression on the public TOI
number, period, duration, ephemeris errors and epoch, fitted on the tuning half, that places one passed event on the
published ephemeris of each held-out star with a SPOC 2-minute light curve that it predicts to be a planet, and
submits the others as not searched, so its columns count the same stars as the Probes'. It reports the same events
on the controls, because it ignores the light curve, so its control false-alarm rate is high. The two entries are
compared by a paired ΔJ over the same stars ({{floor_draws}} stratified bootstrap resamples of the searchable CP/KP and FP
stars, both entries scored on each), not by whether their marginal intervals overlap. **{{floor_sentence}}** A
light-curve method should be judged against this floor, not against zero.

The FP measures in this paper differ by definition. Section 5.3's "rejected or flagged" is over the FP dips the
panel found ({{ho_fp_flagged}}); the leaderboard's FP rejection counts every star of the searchable set whose TOI dip
was not offered as a clean candidate ({{lb_probes_fprs}} for the Probes; over every held-out FP star, counting stars
without 2-minute data as not offered, {{lb_probes_fprej_all}}). Likewise the headline completeness counts a recovered
dip even when flagged, while J's completeness term does not. Reliability is the share of clean candidates on TOI dips
that are CP/KP, on this sample's class mix ({{lb_mix_pos}} CP/KP, {{lb_mix_fp}} FP and {{lb_mix_fa}} FA searched held-out stars),
which is not the TOI catalogue's. The two Probes + Sentinels rules were stated before any of them was scored, as
star-level combinations of the stored outcomes: *either* gives a clean candidate when the Probes give one or either
Sentinel marks the dip as a potential planet; *both* only when the Probes give one and a Sentinel marks it too. They
are not a run of the panel's mark-level consensus. **{{sen_n}} stars cannot order these configurations:** the subsample
is never ranked, and {{lb_subsample_overlap}}.

### 5.8 Single-star validation: pi Men c

On TESS sector 1 of pi Men the panel recovered {{pm_epochs}} of {{pm_epochs_pred}} predicted epochs of pi Men c. A
joint limb-darkened fit (u₁ = {{pm_u1}}, u₂ = {{pm_u2}} for Teff {{pm_teff}} K and log g {{pm_logg}}) with the period free
gives Rp/R★ = {{pm_k}} (ratio {{pm_k_ratio}} to {{cite_huang2018}}'s {{pm_k_huang}}) and T14 = {{pm_t14}} h (ratio
{{pm_t14_ratio}} to {{pm_t14_huang}} h); the model's mid-transit depth is {{pm_depth}} ppm (ratio {{pm_depth_ratio}} to the
published {{pm_depth_huang}} ppm, a differently defined quantity) and P = {{pm_period}} d (Huang: {{pm_period_huang}} d).
{{pm_epochs}} TESS transits constrain the impact parameter only to b < {{pm_b_upper}} (1σ), so ρ★ is a range
({{pm_rho_range}} g/cm³). With the TIC density as a prior ({{pm_rho_prior}} g/cm³) the fit gives b = {{pm_b_prior}},
a/R★ = {{pm_ars_prior}} (1σ {{pm_ars_range}}) and T23/T14 = {{pm_t23}}, against Huang's {{pm_b_huang}} and {{pm_ars_huang}}. The box
measure this fit replaced gave ratios of {{pm_box_depth}} in depth and {{pm_box_duration}} in duration. The periodic
signal's FAP is below {{pm_fap_bound}}: {{pm_fap_exceed}} of {{pm_fap_trials}} block-bootstrap trials reached the observed SNR,
so the value is a bound set by the number of trials. One star is a check of the fit, not a benchmark.

## 6 Comparison with published reference numbers

These references measure different populations, data and tasks; they are context, not SetuHQ requirements.

| quantity | SetuHQ (held-out) | published reference |
|---|---|---|
| completeness | {{ho_completeness}} on searchable stars, end to end (search, review, vetting) | Robovetter DR25: {{ref_robovetter_completeness}} for P < 100 d, vetting alone, on injected transits already detected as TCEs ({{cite_thompson2018}}) |
| completeness, 3 to 4 R⊕ | {{ho_rad_3to4}} | Planet Hunters TESS: {{ref_pht_mid}} ({{cite_eisner2021}}) |
| completeness, above 4 R⊕ | {{ho_rad_above4}} | Planet Hunters TESS: {{ref_pht_large}} ({{cite_eisner2021}}) |
| reliability against inverted and scrambled data | vetted false dips on {{ho_inverted_any}} and {{ho_scrambled_any}} of star-sectors | Robovetter DR25: reliability {{ref_robovetter_reliability}} for P < 100 d ({{cite_thompson2018}}) |
| how many TOIs are false positives | the sample is stratified, not representative | prime mission: {{ref_toi_fp_fraction}} found false positive by follow-up ({{cite_guerrero2021}}); Kepler KOIs overall {{ref_kepler_fp_rate}} ({{cite_fressin2013}}) |
| statistical validation | none: the code computes a reduced FPP per periodic candidate, which by design never labels one validated; on this benchmark's FP TOIs: {{fpp_fp_validated}} | TRICERATOPS "validated": {{ref_triceratops_thresholds}} ({{cite_giacalone2021}}); vespa on all KOIs ({{cite_morton2016}}) |

The radius rows use the bins Planet Hunters TESS reported, computed from the per-star rows and the TOI table's
radii. Against Planet Hunters TESS, SetuHQ's completeness is, at {{cmp_pht_sentence}}.{{cmp_pht_note}} Its headline completeness is {{cmp_robo}} the Robovetter's, and it is
far from Robovetter-level reliability: its vetted false-alarm rate on the controls is {{ho_inverted_per1000}} and
{{ho_scrambled_per1000}} per 1,000 star-sectors before the feed's rule, and {{feed_inverted_per1000}} and
{{feed_scrambled_per1000}} after it, against the project's own proposed target of at most one per 1,000. The
comparison is not like for like. The Robovetter's completeness measures the vetting step on events the Kepler
pipeline had already detected, while SetuHQ's includes its own search; Kepler had a four-year baseline against
one TESS sector here; Planet Hunters TESS searched sectors 1 to 26 with human volunteers and science-team vetting;
and the Robovetter's reliability is a property of its candidate catalogue, ours a rate per star-sector. We make no
claim of matching either.

## 7 Limitations

* **Against a metadata-only floor, {{floor_short}}** (Section 5.7): J {{lb_probes_j}} against
  {{lb_metadata_baseline_j}} for a model that never reads a light curve; {{floor_dj}}. The
  ephemeris is given to every method, so J mixes detection with vetting; separate detection (ephemeris withheld)
  and vetting rankings are future work.
* **No pixel-level vetting in the benchmark.** The code has a difference-image centroid test (off by default, read
  from the SPOC target pixel file), but the benchmark did not run it, so blended and background eclipsing binaries
  can pass here. FP stars flagged {{pixel_fp_flagged}}, CP/KP stars
  flagged {{pixel_cpkp_flagged}}.
* **No statistical validation.** Nothing here is statistically validated. The code computes a reduced
  false-positive probability per periodic candidate (a documented approximation that never says "validated"). FP
  TOIs labelled validated: {{fpp_fp_validated}}; CP/KP TOIs likely planets: {{fpp_cpkp_likely}}.
* **The Sentinels are measured on {{sen_n}} stars,** were calibrated on {{cal_n_inj}} injected and {{cal_n_empty}} empty subjects,
  and never ran on the controls. The model version that answered is not recorded: the cache key holds the
  CLI's model setting ("default"), not the served model. Their errors are correlated.
* **The clipping bug** (Section 5.6) is fixed in the code measured here; the first run, made before the fix, is kept
  as the historical record.
* {{bench_density_limit}}
* **One sector per star, 2-minute data only.** Stars with only full-frame-image data are not searchable, and
  that loss is skewed toward FP TOIs (Section 5.5). Single transits and long periods are outside the sample's
  {{period_lo}} to {{period_hi}} d range.
* **Dispositions are the reference, not the truth.** Some CP/KP and FP labels may be wrong.
* **The feed's `new_candidate` signals are {{feed_bad}}:** noise alone would account for {{feed_ratio}} of their
  rate (Section 5.2).
* **FAPs are bounded by the trials;** the Gumbel tail is extrapolated and indicative only.
* **Synthetic injections are not sky noise** (Section 5.1).

Every SetuHQ entry is a candidate. A detection means the pipeline saw a vetted dip; confirmation needs
independent evidence such as radial velocities, and no SetuHQ output is called confirmed or validated.

## 8 Reproducibility

* **Code.** The benchmark report was generated at commit `{{code_commit_full}}` (Section 4 lists the pipeline
  fingerprints). The frozen sample is `docs/results/benchmark_toi_sample.json` (sha256 `{{sample_sha}}`); the report
  is `docs/results/benchmark_real_tois_clipfix.md` and `.json` (the first run, on the pre-fix code:
  `docs/results/benchmark_real_tois.md` and `.json`); the commands are in `scripts/benchmark_real_tois.py`
  (`freeze`, `run`, `sentinels`, `clipping`, `feed`, `report`, and with `--edition clipfix`: `rerun`,
  `sentinels-carry`, `clipping`, `feed`, `report`). Downloads and per-subject outputs live in the
  gitignored `cache/`; the committed JSON holds every per-star outcome.
* **Sentinel responses** are cached by hash and replayed without new calls; the per-star Sentinel outcomes are
  committed in the leaderboard's seeded submissions.
* **This paper.** `python scripts/paper_numbers.py` regenerates `docs/paper/paper.md` and
  `docs/paper/numbers.json` from the committed JSON; `--check` fails when they differ, and `tests/test_paper.py`
  checks the paper's numbers against the JSON.
* **The leaderboard.** `docs/leaderboard/` holds the submission format, the rules, the public inputs (the
  tuning half with labels, the held-out half without; sha256 `{{lb_inputs_sha}}`) and the scored table
  ({{lb_entries}} entries, {{lb_refused}} refused). A submission lists each star's detected events on the real and
  control light curves; the leaderboard matches them to the ephemeris and counts control false alarms itself. The
  metadata-only floor is rebuilt from the public inputs by `scripts/leaderboard_metadata_baseline.py`.
  `setuhq leaderboard <file>` scores a submission and refuses one that states anything but that hash, says it was
  tuned on the held-out half, carries a field outside the whitelist, or does not cover its scope.
* **What the leaderboard cannot check, and future work.** The hash is an attestation: the held-out labels are
  public, so no check can prove they were not read, and a method's own pass verdicts and control lists are its own
  report. Two designs would close these gaps and are not built: maintainer-held decoy light curves under opaque
  ids, whose truth only the maintainers hold, and prospective scoring on TOIs still undispositioned, scored once
  TFOPWG dispositions them.

## Pending results

These numbers will change. Their placeholders print *pending* until the stated file exists; the numbers
script then fills them, and never guesses.

{{pending_list}}

## References

{{references}}

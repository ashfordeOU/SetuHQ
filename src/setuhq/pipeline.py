# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""End-to-end run: light curves in, vetted candidate catalogue and provenance manifest out.

Stages, in order:

1. Clean, detrend and bin each light curve (:mod:`setuhq.preprocess`).
2. Cut into blind-coded subjects (:mod:`setuhq.subjects`) and render each as a PNG.
3. Every available reviewer classifies every subject independently.
4. Aggregate the panel into weighted consensus events (:mod:`setuhq.aggregate`).
5. Vet each consensus event (:mod:`setuhq.vet`).
6. Write candidates, classifications and a manifest that records versions and inputs.
"""

from __future__ import annotations

import csv
import json
import math
import platform
import sys
import warnings
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

from setuhq import __version__
import numpy as np

from setuhq.aggregate import Consensus, aggregate, audit_marks, counting_rule
from setuhq.config import RunConfig
from setuhq.lightcurve import LightCurve
from setuhq.preprocess import bin_lightcurve, clean, detrend
from setuhq.render import render_subject
from setuhq.reviewers.base import Classification
from setuhq.reviewers.claude import PROMPT_VERSION, ReviewError
from setuhq.search import PeriodicSignal, bls_search, fap_tail_label, stitch, with_fap
from setuhq.store import Store
from setuhq.subjects import Subject, split_subjects
from setuhq.stellar import tic_id, tic_params
from setuhq.transitfit import TransitFit, fit_transit, ld_coeffs
from setuhq.vet import DISQUALIFYING as BASE_DISQUALIFYING
from setuhq.vet import VettingResult, measure_epochs, vet_event


@dataclass(frozen=True)
class Candidate:
    subject_id: str
    target: str
    mission: str
    t_start: float
    t_end: float
    time_unit: str
    score: float
    n_reviewers: int
    planet_fraction: float
    reviewers: tuple[str, ...]
    passed: bool
    flags: tuple[str, ...]
    depth_ppm: float
    snr: float
    period_days: float | None
    n_transits: int = 0
    # Empirical false-alarm probability of the periodic signal that covers this dip (search.false_alarm_probability).
    fap: float | None = None
    metrics: dict = field(default_factory=dict)
    candidate_id: str = ""
    # BLS ephemeris of the periodic signal, set only when it covers this dip.
    # Per subject by default; per target over all stitched sectors when search_scope is "sector".
    bls_t0: float | None = None
    bls_duration_days: float | None = None
    # Stored per-epoch measurements at each BLS-predicted epoch inside the subject.
    epochs: tuple = ()
    secondary_epochs: tuple = ()
    # Every reviewer's marks over the consensus window, each with its overlap
    # fraction, centre gap and whether it counted (aggregate.audit_marks), and
    # the counting rule they were judged by. Reported, not used to count.
    mark_audit: tuple = ()
    count_rule: dict = field(default_factory=dict)
    search_scope: str = "subject"
    # The limb-darkened transit fit (transitfit.TransitFit.as_dict), or {} when it was not run. On a periodic
    # signal it is joint over the signal's N epochs in the subject (fit["n_epochs"]) and shared by its dips, so the
    # v_shape and density_mismatch flags it sets are signal-level; the odd/even test stays the per-dip guard.
    fit: dict = field(default_factory=dict)
    fap_label: str = ""
    # The FAP's working: trials, how many reached the observed SNR, the method, and the Gumbel tail (indicative).
    fap_trials: int = 0
    fap_exceed: int | None = None
    fap_tail: float | None = None
    fap_tail_label: str = ""
    fap_method: str = ""
    fap_snr: float | None = None  # the periodic signal's BLS SNR that the trials are compared with
    sector: int | None = None     # the TESS sector (or other segment label) of this dip's subject

    @property
    def t_center(self) -> float:
        return 0.5 * (self.t_start + self.t_end)

    def as_row(self) -> dict:
        row = asdict(self)
        row["reviewers"] = ";".join(self.reviewers)
        row["flags"] = ";".join(self.flags)
        row["epochs"] = list(self.epochs)
        row["secondary_epochs"] = list(self.secondary_epochs)
        row["mark_audit"] = list(self.mark_audit)
        row["t_center"] = self.t_center
        row["duration_hours"] = (self.t_end - self.t_start) * 24.0
        f = self.fit or {}
        for key, src in (("fit_t0", "t0"), ("fit_t0_err", "t0_err"), ("fit_depth_ppm", "depth_ppm"), ("fit_depth_err_ppm", "depth_err_ppm"),
                         ("fit_t14_hours", "t14_hours"), ("fit_t14_err_hours", "t14_err_hours"), ("fit_b", "b"), ("fit_b_err", "b_err"),
                         ("fit_k", "k"), ("fit_rho_star", "rho_star"), ("fit_rho_star_err", "rho_star_err"), ("star_rho", "rho_catalogue")):
            row[key] = f.get(src)
        dv = (self.metrics or {}).get("dv") or {}
        sec = dv.get("secondary") or {}
        row["crowdsap"] = (dv.get("crowding") or {}).get("crowdsap")
        row["secondary_phase"], row["secondary_snr"] = sec.get("phase"), sec.get("snr")
        cen = ((self.metrics or {}).get("pixel") or {}).get("centroid") or {}
        test = cen.get("psf_target") or cen.get("psf_control") or {}
        row["centroid_offset_arcsec"], row["centroid_sigma"] = test.get("offset_arcsec"), test.get("sigma")
        val = (self.metrics or {}).get("validation") or {}
        row["fpp"], row["nfpp"], row["fpp_method"] = val.get("fpp"), val.get("nfpp"), val.get("method")
        row["validation_label"] = val.get("label", "")
        row["outcome"] = self.outcome
        return row

    @property
    def outcome(self) -> str:
        """The dip's vetting outcome, ``passed``, ``flagged`` or ``rejected``, by the rule the report and the case file
        use (``docket.outcome`` over ``docket.vetting_checks``): a disqualifying flag or a failed check rejects, any
        other flag or an unmeasured check flags for review, and only every check measured and passing passes."""
        from setuhq.docket import outcome, vetting_checks

        c = {"metrics": self.metrics or {}, "flags": [f for f in self.flags if f], "period_days": self.period_days}
        return outcome(vetting_checks(c), c["flags"], bool(self.passed))


@dataclass
class RunSummary:
    run_dir: Path
    n_light_curves: int
    n_subjects: int
    n_classifications: int
    n_consensus: int
    n_passed: int
    skipped_reviewers: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    # Per Sentinel ({reviewer id: n}): answers that took a call to the provider, and answers read from the reviewer's
    # answer cache (no call). A review that failed after its retries gave no answer and is in neither.
    provider_calls: dict[str, int] = field(default_factory=dict)
    cached_answers: dict[str, int] = field(default_factory=dict)


def prepare_lightcurves(lightcurves: list[LightCurve], config: RunConfig) -> list[LightCurve]:
    """Clean, normalise, detrend and bin each light curve (each sector on its own)."""
    out = []
    for lc in lightcurves:
        cleaned = clean(lc)
        level = float(np.median(cleaned.flux)) if len(cleaned) else 1.0
        if np.isfinite(level) and level > 0:
            cleaned = cleaned.with_data(cleaned.time, cleaned.flux / level, cleaned.flux_err / level)
        detrended = detrend(cleaned, window_days=config.detrend_window_days)
        out.append(bin_lightcurve(detrended, config.bin_minutes))
    return out


TRANSIT_MASK_T14 = 1.5  # the extended vetting re-detrends with points within this many T14 of each mid-transit masked


def vetting_window(config: RunConfig, duration: float) -> float:
    """The detrending window of the extended vetting: the run's window, or four times the masked span around each
    transit (2 × TRANSIT_MASK_T14 × T14) when that is longer, so a long transit's mask leaves the trend support on
    both sides and the box statistic keeps its white-noise scale.

    Below 12 T14 the run's ``detrend_window_days`` therefore has no effect on the vetting light curve: for pi Men c
    (T14 = 3.09 h) any window up to 1.55 d gives the same 1.55 d. It still sets the review light curve."""
    return max(config.detrend_window_days, 4.0 * 2.0 * TRANSIT_MASK_T14 * duration)


def vetting_mask(time, *, period: float, t0: float, duration: float, extra_phases=(), mask_t14: float | None = None):
    """The points the vetting detrend leaves out: within ``mask_t14`` (default :data:`TRANSIT_MASK_T14`) × T14 of
    each mid-transit and of each of ``extra_phases`` (a secondary, see :func:`vetting_lightcurve_two_pass`)."""
    time = np.asarray(time, float)
    half = (TRANSIT_MASK_T14 if mask_t14 is None else mask_t14) * duration
    exclude = np.zeros(time.size, bool)
    for phase in (0.0, *extra_phases):
        centre = t0 + phase * period
        exclude |= np.abs((time - centre + 0.5 * period) % period - 0.5 * period) <= half
    return exclude


MIN_ANCHOR_SUPPORT = 0.5   # a variant is used only if each masked span keeps this share of the points beside it


def mask_anchor_support(time, exclude, window: float) -> float:
    """How well the masked spans are anchored: over every masked span and each of its two sides, the smallest share
    of the points within ``window``/2 of the span's edge that the mask leaves in (1.0 when nothing is masked). A side
    with fewer than 5 points at all (the data's ends or a gap) is not counted: there the trend is held flat anyway."""
    time = np.asarray(time, float)
    ex = np.asarray(exclude, bool)
    worst = 1.0
    if not ex.any():
        return worst
    change = np.flatnonzero(np.diff(ex.astype(np.int8)))
    for i in change:
        if ex[i + 1]:      # a span starts at i + 1: its left side
            side = (time >= time[i + 1] - window / 2) & (time < time[i + 1])
        else:              # a span ends at i: its right side
            side = (time > time[i]) & (time <= time[i] + window / 2)
        if side.sum() >= 5:
            worst = min(worst, float((~ex[side]).sum() / side.sum()))
    return worst


def vetting_lightcurve(lightcurves: list[LightCurve], config: RunConfig, *, period: float, t0: float, duration: float,
                       start: float | None = None, end: float | None = None, extra_phases=(), window_scale: float = 1.0,
                       mask_t14: float | None = None) -> Subject | None:
    """The light curve the extended (DV-style) tests read: prepared as for review (clean, normalise, detrend, bin),
    except that the detrending leaves out every point within ``TRANSIT_MASK_T14`` × T14 of a mid-transit of the
    fitted ephemeris, as DV does, with the window widened for long transits (:func:`vetting_window`) and the trend
    interpolated across each masked span (:func:`setuhq.preprocess.detrend`). Without the mask the trend overshoots
    beside each transit, and those shoulders looked like brightenings to the secondary search; without the wider
    window and the interpolation, a 7-10 hour transit's mask left the quadratic extrapolating by 10⁴-10⁶ ppm. Cut to
    [start, end) when given; None when nothing is left. ``window_scale`` and ``mask_t14`` vary the window and the
    mask for :func:`secondary_variants`."""
    out = []
    for lc in lightcurves:
        cleaned = clean(lc)
        level = float(np.median(cleaned.flux)) if len(cleaned) else 1.0
        if np.isfinite(level) and level > 0:
            cleaned = cleaned.with_data(cleaned.time, cleaned.flux / level, cleaned.flux_err / level)
        exclude = vetting_mask(cleaned.time, period=period, t0=t0, duration=duration, extra_phases=extra_phases,
                               mask_t14=mask_t14)
        detrended = detrend(cleaned, window_days=vetting_window(config, duration) * window_scale, exclude=exclude)
        binned = bin_lightcurve(detrended, config.bin_minutes)
        if start is not None:
            keep = (binned.time >= start) & (binned.time < (end if end is not None else np.inf))
            binned = binned.masked(keep)
        if len(binned):
            out.append(binned)
    return stitch(out) if out else None


def vetting_lightcurve_two_pass(lightcurves: list[LightCurve], config: RunConfig, *, period: float, t0: float,
                                duration: float, start: float | None = None, end: float | None = None):
    """:func:`vetting_lightcurve` in two passes. A secondary eclipse that is not masked is partly absorbed by the trend
    (about half of a 200 ppm secondary was lost), so the second pass re-detrends with the primaries and phase 0.5 (a
    circular orbit's secondary) always masked, and with the first pass's strongest dip masked too, but only when the
    first pass already finds it significant (:func:`setuhq.dvtests.assess_secondary`, the same calibrated test).

    The condition keeps the secondary search calibrated. Masking the strongest dip of every first pass also protects
    the largest noise dip from the trend, which biases the second pass's maximum upward (pi Men: 5.6σ to 7.0σ), and
    the white-noise tables describe a single scan, not that selection. Masking a fixed phase (0.5) selects nothing;
    masking a dip that is already significant can move a flag only where the first pass would have raised it. The
    price: an eccentric secondary below the threshold in the first pass is not protected from the trend. Returns
    (light curve, masked phases); (None, ()) when nothing is left."""
    from setuhq.dvtests import assess_secondary, secondary_search

    first = vetting_lightcurve(lightcurves, config, period=period, t0=t0, duration=duration, start=start, end=end)
    if first is None or len(first) < 10:
        return first, ()
    phases = [0.5]
    sec = secondary_search(first.time, first.flux, period=period, t0=t0, duration=duration)
    if sec is not None and abs(sec["phase"] - 0.5) * period > duration and \
            assess_secondary(sec, secondary_sigma=config.secondary_sigma)["significant"]:
        phases.append(float(sec["phase"]))
    second = vetting_lightcurve(lightcurves, config, period=period, t0=t0, duration=duration, start=start, end=end,
                                extra_phases=phases)
    return second, tuple(phases)


# The small fixed set of detrending variants the reduced FPP is checked across (window factor, mask in T14); the
# default setting (1.0, TRANSIT_MASK_T14) is the light curve the extended tests read.
DETREND_VARIANTS = ((0.75, 1.0), (0.75, 2.0), (1.5, 1.0), (1.5, 2.0))
SCAN_KEYS = ("phase", "depth_ppm", "sigma_ppm", "snr", "n_trials", "scan_robust_sigma", "scan_std_snr",
             "max_brightening_snr", "periodic", "max_epoch_share", "n_epochs", "phase_05")


def secondary_variants(lightcurves: list[LightCurve], config: RunConfig, *, period: float, t0: float, duration: float,
                       extra_phases=(), start: float | None = None, end: float | None = None) -> list[dict]:
    """The all-phase secondary scan repeated on each of :data:`DETREND_VARIANTS` (same masked phases), for the
    reduced FPP's stability check. Each entry is the scan's summary with its ``window_scale``, ``mask_t14`` and
    ``anchor_support`` (:func:`mask_anchor_support`).

    A variant whose masks leave a span poorly anchored (less than :data:`MIN_ANCHOR_SUPPORT` of the points within
    half a window of either edge kept) is left out: with a short window and wide masks around several phases, the
    one-sided quadratic at the span's edges, interpolated across it, made spurious dips (111 ppm, 5.1σ, inside a
    masked span when the reviewer measured it), and the FPP was refused on them."""
    from setuhq.dvtests import assess_secondary, secondary_search

    out = []
    for scale, mask in DETREND_VARIANTS:
        window = vetting_window(config, duration) * scale
        support = min((mask_anchor_support(lc.time, vetting_mask(lc.time, period=period, t0=t0, duration=duration,
                                                                 extra_phases=extra_phases, mask_t14=mask), window)
                       for lc in lightcurves), default=1.0)
        if support < MIN_ANCHOR_SUPPORT:
            continue
        lc = vetting_lightcurve(lightcurves, config, period=period, t0=t0, duration=duration, start=start, end=end,
                                extra_phases=extra_phases, window_scale=scale, mask_t14=mask)
        if lc is None or len(lc) < 10:
            continue
        sec = secondary_search(lc.time, lc.flux, period=period, t0=t0, duration=duration)
        if sec is None or sec.get("scan_robust_sigma") is None:
            continue
        sec = assess_secondary(sec)
        out.append({**{k: sec.get(k) for k in SCAN_KEYS}, "window_scale": scale, "mask_t14": mask,
                    "anchor_support": support})
    return out


def prepare_subjects(lightcurves: list[LightCurve], config: RunConfig, *, prepared: list[LightCurve] | None = None) -> list[Subject]:
    subjects: list[Subject] = []
    for binned in prepared if prepared is not None else prepare_lightcurves(lightcurves, config):
        subjects.extend(split_subjects(binned, length_days=config.subject_days, min_points=config.min_points))
    return subjects


def sector_signals(prepared: list[LightCurve], config: RunConfig) -> dict[str, PeriodicSignal | None]:
    """One BLS search per target over all its sectors stitched together, keyed by target.

    The maximum period is half the stitched time span, so a period longer than
    half a subject can be found when the sectors cover two transits.
    """
    by_target: dict[str, list[LightCurve]] = {}
    for lc in prepared:
        if len(lc):
            by_target.setdefault(lc.target, []).append(lc)
    out: dict[str, PeriodicSignal | None] = {}
    for target, curves in by_target.items():
        stitched = stitch(curves)
        signal = bls_search(stitched, min_period=config.min_period)
        out[target] = with_fap(stitched, signal, min_period=config.min_period, n_trials=config.fap_trials, cache_dir=config.fap_cache,
                               stop_after=config.fap_stop_after)
    return out


def plot_arrays(subject: Subject, points: int | None = None) -> dict:
    """Plot arrays for the dashboard and the Docket.

    By default these are the subject's own bins (``bin_minutes`` from the run
    config), with ``flux_err`` the error of each bin mean that
    :func:`setuhq.preprocess.bin_lightcurve` propagated from the same bin sums
    as the flux. Pass ``points`` to re-bin coarser; the error is then propagated
    the same way, sqrt(sum of squared errors) / n.
    """
    if points is None:
        time, flux, flux_err = subject.time, subject.flux, subject.flux_err
    else:
        edges = np.linspace(subject.start, subject.end, points + 1)
        index = np.clip(np.searchsorted(edges, subject.time, side="right") - 1, 0, points - 1)
        counts = np.bincount(index, minlength=points)
        keep = counts > 0
        time = np.bincount(index, weights=subject.time, minlength=points)[keep] / counts[keep]
        flux = np.bincount(index, weights=subject.flux, minlength=points)[keep] / counts[keep]
        flux_err = np.sqrt(np.bincount(index, weights=subject.flux_err**2, minlength=points)[keep]) / counts[keep]
    return {
        "subject_id": subject.subject_id,
        "time_unit": subject.time_unit,
        "start": subject.start,
        "end": subject.end,
        "time": [round(float(t), 5) for t in time],
        "flux": [round(float(f), 6) for f in flux],
        "flux_err": [round(float(e), 7) for e in flux_err],
    }


def review_subjects(
    subjects: list[Subject],
    reviewers,
    *,
    image_dir: str | Path | None,
    store: Store | None = None,
) -> list[Classification]:
    """Every reviewer classifies every subject. Subjects are rendered first, so every reviewer sees the same image."""
    classifications: list[Classification] = []
    for subject in subjects:
        image = None
        if image_dir is not None:
            image = render_subject(subject, Path(image_dir) / f"{subject.subject_id}.png")
            (Path(image_dir) / f"{subject.subject_id}.json").write_text(json.dumps(plot_arrays(subject)))
        if store is not None:
            store.add_subject(subject, image)
        for reviewer in reviewers:
            try:
                classification = reviewer.review(subject, image)
            except ReviewError as exc:
                warnings.warn(f"{reviewer.reviewer_id} skipped {subject.subject_id}: {exc}", stacklevel=2)
                continue
            classifications.append(classification)
            if store is not None:
                store.add_classification(classification)
    return classifications


def build_candidates(
    subjects: list[Subject],
    classifications: list[Classification],
    weights: dict[str, float],
    config: RunConfig,
    *,
    target_signals: dict[str, PeriodicSignal | None] | None = None,
    stars: dict[str, dict] | None = None,
    lightcurves: list[LightCurve] | None = None,
) -> list[Candidate]:
    """Aggregate, search and vet. With ``target_signals`` (sector mode), each subject uses its
    target's multi-sector BLS signal instead of a search of the subject alone. With the raw ``lightcurves``, the
    extended tests read them re-detrended with the fitted transits masked (:func:`vetting_lightcurve`)."""
    subject_by_id = {s.subject_id: s for s in subjects}
    consensus = aggregate(
        classifications,
        weights,
        gap_days=config.cluster_gap_days,
        min_score=config.min_score,
        min_planet_fraction=config.min_planet_fraction,
    )
    periodic_cache: dict[str, PeriodicSignal | None] = {}
    # One joint fit per (subject, periodic signal): every dip on that signal shares it, with the reference
    # mid-time moved to the dip's own epoch.
    fit_cache: dict[tuple, tuple] = {}
    ext_cache: dict[tuple, tuple] = {}
    candidates: list[Candidate] = []
    for event in consensus:
        subject = subject_by_id[event.subject_id]
        if event.subject_id not in periodic_cache:
            if target_signals is not None:
                periodic_cache[event.subject_id] = target_signals.get(str(subject.provenance.get("target", "")))
            else:
                signal = bls_search(subject, min_period=config.min_period)
                periodic_cache[event.subject_id] = with_fap(subject, signal, min_period=config.min_period,
                                                            n_trials=config.fap_trials, cache_dir=config.fap_cache,
                                                            stop_after=config.fap_stop_after)
        result = _vet(event, subject, periodic_cache[event.subject_id])
        periodic = periodic_cache[event.subject_id]
        supported = periodic if periodic is not None and periodic.covers(event.center) else None
        candidate = _to_candidate(event, subject, result, supported)
        if config.fit_transits:
            key = (event.subject_id, supported.period, supported.t0) if supported is not None else None
            if key is not None and key in fit_cache:
                fit, prior = (_at_epoch(f, event.center) if f is not None else None for f in fit_cache[key])
            else:
                fit, prior = fit_candidate(event, subject, supported, (stars or {}).get(candidate.target) or {}, result.metrics.get("depth"))
                if key is not None:
                    fit_cache[key] = (fit, prior)
            if fit is not None:
                extra = tuple(f for f, on in (("v_shape", fit.v_shape), ("density_mismatch", fit.rho_flag)) if on)
                d = fit.as_dict()
                if prior is not None:
                    d["with_density_prior"] = prior.as_dict()
                object.__setattr__(candidate, "fit", d)
                object.__setattr__(candidate, "flags", candidate.flags + extra)
        if config.vetting_extended or config.vetting_pixel:
            extended_vetting(candidate, subject, supported, config, subjects, ext_cache, lightcurves)
        if supported is not None:
            object.__setattr__(candidate, "fap_label", supported.fap_label)
            if supported.fap_trials:
                for key, value in (("fap_trials", supported.fap_trials), ("fap_exceed", supported.fap_exceed),
                                   ("fap_tail", supported.fap_tail), ("fap_tail_label", fap_tail_label(supported.fap_tail)),
                                   ("fap_method", supported.fap_method), ("fap_snr", float(supported.snr))):
                    object.__setattr__(candidate, key, value)
        object.__setattr__(candidate, "search_scope", "sector" if target_signals is not None else "subject")
        sec = subject.provenance.get("sector")
        object.__setattr__(candidate, "sector", int(sec) if isinstance(sec, (int, float)) or str(sec).isdigit() else None)
        object.__setattr__(candidate, "mark_audit", tuple(audit_marks(event, classifications, config.cluster_gap_days)))
        object.__setattr__(candidate, "count_rule", {
            "gap_days": config.cluster_gap_days,
            "min_score": config.min_score,
            "text": counting_rule(config.cluster_gap_days, config.min_score),
        })
        candidates.append(candidate)
    candidates.sort(key=lambda c: (not c.passed, -c.score))
    for index, candidate in enumerate(candidates):
        object.__setattr__(candidate, "candidate_id", f"{candidate.subject_id}-{index:03d}")
    return candidates


def extended_vetting(candidate: Candidate, subject: Subject, supported: PeriodicSignal | None,
                     config: RunConfig, subjects: list[Subject], cache: dict,
                     lightcurves: list[LightCurve] | None = None) -> None:
    """The S2 tests for one candidate, stored in ``metrics["dv"]`` and ``metrics["pixel"]`` with their flags added.

    The ephemeris is the transit fit's (period, mid-time, T14) when it has a period, else the BLS signal's; a dip
    off any periodic signal gets only the crowding test. In sector mode the light-curve tests use every subject of
    the target stitched; otherwise the subject alone, like :func:`setuhq.vet.measure_epochs`. When the raw light
    curves are given they are re-detrended with the fitted transits masked (:func:`vetting_lightcurve`); otherwise
    the review data are used and ``metrics["dv"]["transit_masked_detrend"]`` is False. The pass/fail
    decision changes only when ``config.vetting_decide`` is set (:func:`setuhq.dvtests.decide`)."""
    from setuhq import dvtests

    fit = candidate.fit or {}
    if supported is not None and fit.get("period_days") and fit.get("t14_hours"):
        period, t0, duration, source = float(fit["period_days"]), float(fit["t0"]), float(fit["t14_hours"]) / 24.0, "transit fit"
    elif supported is not None:
        period, t0, duration, source = supported.period, supported.t0, supported.duration, "BLS"
    else:
        period = t0 = duration = None
        source = "none (no periodic signal covers this dip)"
    flags: list[str] = []
    if config.vetting_extended:
        target = str(subject.provenance.get("target", ""))
        key = ("dv", target if config.search == "sector" else subject.subject_id, period, t0, duration)
        if key not in cache:
            data, masked, variants = subject, False, []
            if config.search == "sector" and period is not None:
                same = [s for s in subjects if str(s.provenance.get("target", "")) == target]
                data = stitch(same) if len(same) > 1 else subject
            if lightcurves and period is not None:
                mine = [lc for lc in lightcurves if lc.target == target and
                        (config.search == "sector" or lc.provenance.get("sector") == subject.provenance.get("sector"))]
                window = {} if config.search == "sector" else {"start": subject.provenance.get("segment_start"),
                                                               "end": subject.provenance.get("segment_end")}
                redone, phases = (vetting_lightcurve_two_pass(mine, config, period=period, t0=t0, duration=duration,
                                                              **window) if mine else (None, ()))
                if redone is not None and len(redone) >= 10:
                    data, masked = redone, list(phases)
                    variants = secondary_variants(mine, config, period=period, t0=t0, duration=duration,
                                                  extra_phases=phases, **window)
            found, metrics = dvtests.extended_vet(data.time, data.flux, data.flux_err, period=period, t0=t0,
                                                  duration=duration, fit=fit or None, provenance=subject.provenance,
                                                  crowding_min=config.crowding_min,
                                                  secondary_sigma=config.secondary_sigma)
            cache[key] = (found, dict(metrics, transit_masked_detrend=bool(masked),
                                      masked_phases=masked if masked else [], secondary_variants=variants))
        found, metrics = cache[key]
        candidate.metrics["dv"] = dict(metrics, ephemeris_source=source)
        flags += found
    if config.vetting_pixel and period is not None:
        candidate.metrics["pixel"] = _pixel_report(subject, period, t0, duration, fit, candidate, config, cache)
        flags += candidate.metrics["pixel"].get("flags", [])
    new = tuple(f for f in dict.fromkeys(flags) if f not in candidate.flags)
    object.__setattr__(candidate, "flags", candidate.flags + new)
    if period is not None:
        from setuhq.validate import reduced_fpp

        depth = (fit.get("depth_ppm") or candidate.depth_ppm) * 1e-6
        dv = candidate.metrics.get("dv") or {}
        candidate.metrics["validation"] = reduced_fpp(
            depth=depth, dv=dv, fit=fit, pixel=candidate.metrics.get("pixel"),
            contrast_curve=config.contrast_curves.get(candidate.target),
            variants=dv.get("secondary_variants") or None).as_dict()
    if config.vetting_decide:
        from setuhq.pixel import DISQUALIFYING as PIXEL_DISQUALIFYING

        object.__setattr__(candidate, "passed", dvtests.decide(
            candidate.flags, base_disqualifying=BASE_DISQUALIFYING, extra=dvtests.DISQUALIFYING | PIXEL_DISQUALIFYING))


def _pixel_report(subject, period, t0, duration, fit, candidate, config, cache) -> dict:
    """Pixel tests on the SPOC target pixel file of the subject's sector (downloaded once into ``config.tpf_cache``).
    A failure to get the file is recorded, never raised: the light-curve result stands on its own."""
    from setuhq import pixel

    tic, sector = tic_id(candidate.target), subject.provenance.get("sector")
    if tic is None or sector in (None, ""):
        return {"error": "the pixel tests need a TIC target and a sector", "flags": []}
    key = ("pixel", tic, sector, period, t0, duration)
    if key not in cache:
        depth = (fit.get("depth_ppm") or candidate.depth_ppm) * 1e-6
        try:
            tpf = pixel.fetch_tpf(tic, int(sector), cache_dir=config.tpf_cache)
            h = tpf.header
            near = pixel.fetch_neighbours(h["ra"], h["dec"], cache_dir=Path(config.tpf_cache).parent / "neighbours",
                                          epoch_years_since_2000=h.get("years_since_2000"), key=f"tic{tic}")
            stars = pixel.order_target_first(near.get("stars", []), h.get("ra_epoch") or h["ra"], h.get("dec_epoch") or h["dec"])
            report = pixel.pixel_vet(tpf, period=period, t0=t0, duration=duration, depth=depth, stars=stars or None,
                                     sigma_threshold=config.centroid_sigma)
            report.pop("header", None)
            report["neighbour_source"] = near.get("source")
            cache[key] = report
        except Exception as exc:  # noqa: BLE001 (network, missing product or a malformed file)
            cache[key] = {"error": f"{type(exc).__name__}: {exc}", "flags": []}
    return cache[key]


def run_pipeline(
    config: RunConfig,
    lightcurves: list[LightCurve],
    reviewers,
    out_dir: str | Path,
    *,
    weights: dict[str, float] | None = None,
    weights_source: str | None = None,
    calibration: dict | None = None,
) -> RunSummary:
    """Run the panel and write the run directory.

    ``calibration`` is the record stored next to a weights file (``calibrate.calibration_record``):
    with it, a Sentinel's weight is used only on the provider and model it was measured on, and a
    Sentinel without one gets the floor weight and is labelled uncalibrated (``calibrate.apply_calibration``).
    """
    from setuhq.calibrate import apply_calibration

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    active = [r for r in reviewers if r.available()]
    skipped = [r.reviewer_id for r in reviewers if not r.available()]
    skipped_detail = [_skip_entry(r) for r in reviewers if not r.available()]
    if weights_source is None:
        weights_source = "supplied by caller" if weights else "uniform 1.0"
    supplied = dict(weights or {})
    weights, basis = apply_calibration(active, supplied or None, calibration)
    # Weights the caller gave for reviewers that are not active stay on record, as before.
    weights = {k: float(v) for k, v in supplied.items()} | weights

    prepared = prepare_lightcurves(lightcurves, config)
    subjects = prepare_subjects(lightcurves, config, prepared=prepared)
    target_signals = sector_signals(prepared, config) if config.search == "sector" else None
    stars = star_parameters(lightcurves, config, out)
    store = Store(out / "setuhq.sqlite")
    try:
        classifications = review_subjects(subjects, active, image_dir=out / "subjects", store=store)
        candidates = build_candidates(subjects, classifications, weights, config, target_signals=target_signals, stars=stars,
                                      lightcurves=lightcurves)
        store.export_classifications_csv(out / "classifications.csv")
    finally:
        store.close()

    write_candidates(candidates, out)
    write_manifest(out, config, lightcurves, active, skipped, weights, subjects, classifications, candidates,
                   weights_source=weights_source, weight_basis=basis, skipped_detail=skipped_detail)
    return RunSummary(
        run_dir=out,
        n_light_curves=len(lightcurves),
        n_subjects=len(subjects),
        n_classifications=len(classifications),
        n_consensus=len(candidates),
        n_passed=sum(c.passed for c in candidates),
        skipped_reviewers=skipped,
        candidates=candidates,
        **_call_counts(active, classifications),
    )


def _call_counts(active, classifications: list[Classification]) -> dict:
    """Each active Sentinel's provider calls and cached answers in this run, from its classifications' metadata."""
    sentinels = [r.reviewer_id for r in active if getattr(r, "describe", None) is not None]
    calls, cached = dict.fromkeys(sentinels, 0), dict.fromkeys(sentinels, 0)
    for c in classifications:
        if c.reviewer_id in calls:
            (cached if (c.metadata or {}).get("cached") else calls)[c.reviewer_id] += 1
    return {"provider_calls": calls, "cached_answers": cached}


def rebuild_run(config: RunConfig, lightcurves: list[LightCurve], run_dir: str | Path, *, weights: dict[str, float] | None = None) -> list[Candidate]:
    """Re-vet a stored run with the current search, fit and FAP code, reusing its stored classifications.

    The light curves are prepared exactly as in the run (same config), so the blind subject ids must match the
    stored ones; the reviewers are not asked again. Candidates are rewritten, and the manifest records the
    rebuild (when, what changed, what was reused)."""
    from setuhq.store import read_classifications_csv

    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    classifications = read_classifications_csv(run_dir / "classifications.csv")
    prepared = prepare_lightcurves(lightcurves, config)
    subjects = prepare_subjects(lightcurves, config, prepared=prepared)
    have = {s.subject_id for s in subjects}
    need = {c.subject_id for c in classifications}
    if not need <= have:
        raise ValueError(f"stored subjects not reproduced: {sorted(need - have)}")
    weights = weights or {k: float(v) for k, v in manifest.get("weights", {}).items()}
    target_signals = sector_signals(prepared, config) if config.search == "sector" else None
    stars = star_parameters(lightcurves, config, run_dir)
    candidates = build_candidates([s for s in subjects if s.subject_id in need], classifications, weights, config,
                                  target_signals=target_signals, stars=stars, lightcurves=lightcurves)
    write_candidates(candidates, run_dir)
    manifest.setdefault("rebuilds", []).append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "setuhq_version": __version__,
        "reused": "stored classifications (classifications.csv); the reviewers were not asked again",
        "transit_fit": "limb-darkened model (transitfit.py), Claret 2017 TESS LD from the TIC Teff and log g" if config.fit_transits else "off",
        "fap_trials": config.fap_trials, "stellar": config.stellar, "config_sha256": config.digest(),
        "code": _git_describe(),
        "inputs": [{"target": lc.target, "sector": lc.provenance.get("sector"), "file": lc.provenance.get("file"),
                    "file_sha256": lc.provenance.get("file_sha256")} for lc in lightcurves],
    })
    manifest["counts"]["consensus_events"] = len(candidates)
    manifest["counts"]["passed_vetting"] = sum(c.passed for c in candidates)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    return candidates


def _git_describe() -> str | None:
    """``git describe --always --dirty`` of the code that ran, or None outside a git checkout."""
    import subprocess

    try:
        out = subprocess.run(["git", "describe", "--always", "--dirty"], cwd=Path(__file__).resolve().parent,
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def write_candidates(candidates: list[Candidate], out: Path) -> None:
    rows = [c.as_row() for c in candidates]
    fields = [
        "candidate_id", "target", "mission", "subject_id", "t_start", "t_end", "t_center", "time_unit",
        "duration_hours", "score", "n_reviewers", "planet_fraction", "reviewers", "passed", "flags",
        "depth_ppm", "snr", "period_days", "n_transits", "fap", "fap_label", "fap_trials", "fap_exceed", "fap_tail",
        "fap_tail_label", "fap_method", "fap_snr", "sector", "bls_t0", "bls_duration_days",
        "fit_t0", "fit_t0_err", "fit_depth_ppm", "fit_depth_err_ppm", "fit_t14_hours", "fit_t14_err_hours",
        "fit_b", "fit_b_err", "fit_k", "fit_rho_star", "fit_rho_star_err", "star_rho",
        "crowdsap", "secondary_phase", "secondary_snr", "centroid_offset_arcsec", "centroid_sigma",
        "fpp", "nfpp", "fpp_method", "validation_label",
    ]
    with (out / "candidates.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    (out / "candidates.json").write_text(json.dumps(rows, indent=2, default=str))


def _skip_entry(reviewer) -> dict:
    """A skipped reviewer, with why: no key, no SDK, no CLI. Never holds a key."""
    reason = getattr(reviewer, "unavailable_reason", None)
    describe = getattr(reviewer, "describe", None)
    entry = {"id": reviewer.reviewer_id, "kind": reviewer.kind}
    if describe is not None:
        d = describe()
        entry |= {"provider": d["provider"], "model": d["model"]}
    entry["reason"] = (reason() if reason else None) or "unavailable"
    return entry


def _reviewer_entry(r, weights: dict, basis: dict, classifications: list[Classification]) -> dict:
    """One active reviewer in the manifest: weight and calibration status, and for a Sentinel its provider,
    configured model, persona, prompt version, the model ids the provider reported and when it was called."""
    entry = {"id": r.reviewer_id, "kind": r.kind, "weight": weights.get(r.reviewer_id, 1.0)}
    b = basis.get(r.reviewer_id) or {}
    if b:
        entry |= {"calibration": b["status"], "calibration_note": b["note"]}
    describe = getattr(r, "describe", None)
    if describe is not None:
        entry |= describe()
        mine = [c.metadata for c in classifications if c.reviewer_id == r.reviewer_id]
        entry["models_reported"] = sorted({m["model"] for m in mine if m.get("model_reported")})
        called = sorted(m["called_at"] for m in mine if m.get("called_at"))
        entry["called_at"] = {"first": called[0], "last": called[-1]} if called else None
        entry["cached_answers"] = sum(1 for m in mine if m.get("cached"))
    return entry


def _panel_record(config) -> dict:
    """The run's panel as configured: 'probes_only' when no Sentinel is in the config, with the label pages show."""
    from setuhq.config import SENTINEL_TYPES
    from setuhq.names import PROBES_ONLY

    sentinels = [str(s.get("id")) for s in config.reviewers if s.get("type") in SENTINEL_TYPES]
    if sentinels:
        return {"mode": "probes_and_sentinels", "sentinels_configured": sentinels}
    return {"mode": "probes_only", "sentinels_configured": [], "note": PROBES_ONLY}


def write_manifest(out, config, lightcurves, active, skipped, weights, subjects, classifications, candidates,
                   *, weights_source: str = "uniform 1.0", weight_basis: dict | None = None,
                   skipped_detail: list[dict] | None = None) -> None:
    basis = weight_basis or {}
    manifest = {
        "setuhq_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": _package_versions(["numpy", "scipy", "astropy", "matplotlib", "lightkurve", "anthropic"]),
        "config_name": config.name,
        "config_sha256": config.digest(),
        "subject_days": config.subject_days,
        # Where the periodic (BLS) search ran: each subject alone, or all sectors of a target stitched.
        "search_scope": config.search,
        # The Sentinel task's prompt version, the same for every provider (kept under its first name too).
        "claude_prompt_version": PROMPT_VERSION,
        "sentinel_prompt_version": PROMPT_VERSION,
        "inputs": [lc.provenance | {"target": lc.target, "mission": lc.mission} for lc in lightcurves],
        "reviewers": [_reviewer_entry(r, weights, basis, classifications) for r in active],
        "skipped_reviewers": skipped,
        # Why each one was skipped (no key, no SDK, no CLI), with its provider and model.
        "skipped_reviewers_detail": skipped_detail or [{"id": rid, "reason": "unavailable"} for rid in skipped],
        # The weights used for consensus, for every reviewer the run knew about, and their source.
        "weights": {k: float(v) for k, v in sorted(weights.items())},
        "weights_source": weights_source,
        # Which reviewers the configuration named: a run with no Sentinel in it says so here and on every page.
        "panel": _panel_record(config),
        # The code that ran (git describe --always --dirty), next to the data and config hashes.
        "code": _git_describe(),
        "counts": {
            "light_curves": len(lightcurves),
            "subjects": len(subjects),
            "classifications": len(classifications),
            "consensus_events": len(candidates),
            "passed_vetting": sum(c.passed for c in candidates),
        },
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=str))


EPHEMERIS_SNR = 10.0  # a periodic signal this strong is trusted to explain the other dips in its subject


def fit_candidate(event: Consensus, subject: Subject, supported: PeriodicSignal | None, star: dict,
                  depth_guess: float | None) -> tuple[TransitFit | None, TransitFit | None]:
    """The limb-darkened fit of one consensus dip, and the same fit with the density prior (or None). On a periodic signal's ephemeris, every epoch of that signal
    in the subject is fitted jointly (one shape, reference mid-time at this dip's epoch, and with two or more
    epochs the period free near the BLS period); otherwise the dip alone. LD from the star's TIC Teff and log g
    (Sun-like when unknown). When the star has a catalogue density with an error, a second fit with that density
    as a Gaussian prior is stored as ``fit["with_density_prior"]``: the free fit gives the robust depth, T14 and k;
    the prior fit gives b, a/R★ and T23/T14."""
    u1, u2 = ld_coeffs(star.get("teff"), star.get("logg"))
    duration = max(event.t_end - event.t_start, 1 / 24)
    depth = max(float(depth_guess or 0.0), 2e-5)
    period = epochs = None
    t0 = event.center
    if supported is not None:
        period = supported.period
        cover = [e["t_mid"] for e in measure_epochs(subject, supported) if e["n_points"] >= 2]
        if cover:
            epochs = cover
            t0 = min(cover, key=lambda c: abs(c - event.center))
            duration = max(duration, supported.duration)
    args = dict(t0=t0, duration=duration, depth=depth, period=period, u1=u1, u2=u2, epochs=epochs, stellar_density=star.get("rho"))
    try:
        free = fit_transit(subject.time, subject.flux, subject.flux_err, **args)
    except (ValueError, np.linalg.LinAlgError):
        return None, None
    if free is None or not period or not star.get("rho") or not star.get("rho_err"):
        return free, None
    try:
        prior = fit_transit(subject.time, subject.flux, subject.flux_err, **args, rho_prior=(star["rho"], star["rho_err"]))
    except (ValueError, np.linalg.LinAlgError):
        prior = None
    return (free, prior)


def _at_epoch(fit: TransitFit, centre: float) -> TransitFit:
    """A joint fit with its reference mid-time moved to the fitted epoch nearest ``centre`` (the same fit)."""
    if not fit.period_days:
        return fit
    n = round((centre - fit.t0) / fit.period_days)
    if n == 0:
        return fit
    t0_err = math.hypot(fit.t0_err, n * fit.period_err) if fit.period_err is not None and math.isfinite(fit.t0_err) else fit.t0_err
    return replace(fit, t0=fit.t0 + n * fit.period_days, t0_err=t0_err)


def star_parameters(lightcurves: list[LightCurve], config: RunConfig, out: Path | None = None) -> dict[str, dict]:
    """Stellar parameters per target for the transit fit, from the TIC when ``config.stellar`` is "tic".
    A run directory's ``stellar.json`` (written here) is used first, so a re-run needs no network."""
    stored = {}
    if out is not None and (out / "stellar.json").exists():
        stored = json.loads((out / "stellar.json").read_text())
    stars: dict[str, dict] = {}
    for lc in lightcurves:
        target = lc.target
        if target in stars:
            continue
        if target in stored:
            stars[target] = stored[target]
        elif config.stellar == "tic" and (tic := tic_id(target)) is not None:
            p = tic_params(tic)
            if p:
                stars[target] = p
    if out is not None and stars:
        (out / "stellar.json").write_text(json.dumps(stars, indent=1))
    return stars


def _vet(event: Consensus, subject: Subject, periodic: PeriodicSignal | None) -> VettingResult:
    """Vet one consensus event. A dip that does not fit a strong periodic signal is flagged, not rejected.

    A single real transit can sit beside an unrelated dip, so this flag only
    tells a reader to look twice. It does not change ``passed``.
    """
    on_ephemeris = periodic is not None and periodic.covers(event.center)
    result = vet_event(event.t_start, event.t_end, subject, periodic if on_ephemeris else None)
    if periodic is not None and periodic.snr >= EPHEMERIS_SNR and not on_ephemeris:
        return VettingResult(result.passed, result.flags + ("off_ephemeris",), result.metrics)
    return result


def _to_candidate(event: Consensus, subject: Subject, result: VettingResult, supported: PeriodicSignal | None = None) -> Candidate:
    period = result.metrics.get("period")
    epochs = measure_epochs(subject, supported) if supported is not None else ()
    secondary = measure_epochs(subject, supported, phase=0.5) if supported is not None else ()
    return Candidate(
        subject_id=event.subject_id,
        target=str(subject.provenance.get("target", "")),
        mission=subject.mission,
        t_start=event.t_start,
        t_end=event.t_end,
        time_unit=subject.time_unit,
        score=event.score,
        n_reviewers=event.n_reviewers,
        planet_fraction=event.planet_fraction,
        reviewers=event.reviewers,
        passed=result.passed,
        flags=result.flags,
        depth_ppm=float(result.metrics.get("depth", 0.0)) * 1e6,
        snr=float(result.metrics.get("snr", 0.0)),
        period_days=float(period) if period is not None else None,
        n_transits=supported.n_transits if supported is not None else 0,
        fap=supported.fap if supported is not None else None,
        bls_t0=supported.t0 if supported is not None else None,
        bls_duration_days=supported.duration if supported is not None else None,
        epochs=tuple(epochs),
        secondary_epochs=tuple(secondary),
        metrics={k: (float(v) if isinstance(v, (int, float, np.floating)) else v) for k, v in result.metrics.items()},
    )


def _package_versions(names) -> dict[str, str]:
    found = {}
    for name in names:
        try:
            found[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
    return found

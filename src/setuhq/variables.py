"""Everything that dims: keep every consensus dip, find brightenings and periodic variability, and classify each.

The planet search throws away every dip that is not a planet candidate. This module keeps them. For one
star-sector it builds a list of catalogue entries, each with a class, a confidence, the cues that decided
it, and its provenance: the reviewers' marks, their weights, and the Sentinels' own words.

Three kinds of entry:

* ``dip``: a consensus dip of the reviewer panel (every one, whatever the panel's label for the subject).
* ``brightening``: an upward event from :func:`find_flares`, a deterministic detector. The reviewers' task
  is dips only, so these entries carry no marks and say so.
* ``variability``: the star's out-of-transit Lomb-Scargle periodogram (:func:`variability`).

Classes, and the rules that give them (first match wins; ``RULES`` is the same text the page shows):

====================  =====================================================================================
class                 rule
====================  =====================================================================================
systematic            the event sits on an instrumental cue: a subject edge (vet.py's ``edge_event``), a
                      momentum dump (TESS quality bit 32), a scattered-light flag (bits 2048 or 4096) or a
                      pointing or manual-exclude flag (bits 1, 4, 16, 128) within 0.1 d, a data gap of more
                      than 0.5 d within 0.1 d, or half the panel's weight called the subject noise for an
                      instrumental reason
eclipsing_binary      an odd/even depth mismatch or a secondary eclipse (vet.py), a depth of 30,000 ppm or
                      more, a V shape (transitfit.py) on a dip of 5,000 ppm or more, a stellar-density
                      mismatch at a period under 1 d, or half the panel's weight said eclipsing binary;
                      for variability, a period within 2% of an eclipsing-binary
                      dip's period or half of it
flare                 a brightening: 3 or more consecutive points 3σ or more above a 0.5-day running median,
                      peaking 5σ or more (σ the robust scatter about that median, globally and within 0.25 d)
variable              variability: a periodogram peak with a Baluev false-alarm probability below 10⁻³ and a
                      semi-amplitude at least twice the scatter of the 10-minute bins, that is the best peak
                      of each half of the light curve too (within 10%) and is not within 10% of the longest
                      period searched (a peak shared by 3 or more stars of a sector is made systematic in the
                      catalogue, sweep.py); a dip lasting a quarter
                      of that period or more is a trough of it, and so is a dip half the panel's weight
                      called stellar variability
planet_candidate      a dip that passed vetting, that half the panel's weight labelled a potential planet,
                      that is not off its star's own periodic signal, and that no rule above took
unclassified          everything else, with the reason it was not given a class
====================  =====================================================================================

Confidence is ``high``, ``medium`` or ``low`` by a stated rule per class (``CONFIDENCE``). A planet candidate
is never ``high``: a light curve alone cannot make a planet likely enough for that. Nothing here is ever
called confirmed; a class is what the light-curve cues suggest, not a disposition.
"""

from __future__ import annotations

import csv
import json
import math
from pathlib import Path

import numpy as np

from setuhq.preprocess import diff_sigma, mad_sigma, running_median

# The classes, in the order the rules try them; labels as the page shows them.
CLASSES = [
    ("planet_candidate", "Planet candidate"),
    ("eclipsing_binary", "Eclipsing binary"),
    ("flare", "Flare"),
    ("variable", "Pulsator or rotational variable"),
    ("systematic", "Systematic"),
    ("unclassified", "Unclassified"),
]
CLASS_IDS = [c for c, _ in CLASSES]
KINDS = ("dip", "brightening", "variability")
CONFIDENCES = ("high", "medium", "low", "n/a")

# Instrumental cues
CUE_PAD_DAYS = 0.1          # a dump, a scattered-light flag or a gap edge this close to an event explains it
GAP_DAYS = 0.5              # a stretch with no good cadence longer than this is a data gap
DUMP_BITS = 32              # TESS quality flag "Desat": reaction-wheel desaturation (momentum dump)
SCATTERED_BITS = 2048 | 4096  # TESS quality flags "Straylight" and "Straylight2"
POINTING_BITS = 1 | 4 | 16 | 128  # "AttitudeTweak", "CoarsePoint", "Argabrightening", "ManualExclude"
# Eclipsing-binary cues
DEEP_EB_PPM = 30_000.0      # deeper than a Jupiter-size planet across a Sun-like star gives (Rp/R* ≈ 0.17)
V_SHAPE_EB_PPM = 5_000.0    # a V shape on a dip this deep or more (the feed's own depth cut)
SHORT_PERIOD_DAYS = 1.0     # a density mismatch on a period this short is far more often a contact or close binary
EB_PERIOD_TOLERANCE = 0.02
# Panel cues
REASON_SHARE = 0.5          # share of the panel's weight giving one noise reason
PLANET_FRACTION = 0.5       # share of the panel's weight labelling the subject a potential planet
# Variability
LS_BIN_MINUTES = 10.0
LS_MIN_PERIOD_DAYS = 1.0 / 48.0  # 30 minutes: above the 20-minute Nyquist period of 10-minute bins
LS_MAX_PERIOD_FRACTION = 1.0 / 3.0  # of the baseline: longer periods are not searched (TESS's 13.7 d orbit)
LS_FAP_MAX = 1e-3
LS_AMPLITUDE_RATIO = 2.0
TROUGH_FRACTION = 0.25
LS_EDGE_FRACTION = 0.9      # a peak within 10% of the longest period searched is a trend
COHERENCE_TOLERANCE = 0.10  # the same period, within 10%, as the best peak of each half
# Flares
FLARE_SIGMA = 3.0
FLARE_MIN_POINTS = 3
FLARE_PEAK_SIGMA = 5.0
FLARE_WINDOW_DAYS = 0.5
FLARE_MAX_GAP_CADENCES = 3.0
FLARE_LOCAL_DAYS = 0.25

RULES = {
    "systematic": ("On an instrumental cue: a subject edge; a momentum dump, a scattered-light flag or a pointing or "
                   f"manual-exclude flag within {CUE_PAD_DAYS:g} d; a data gap over {GAP_DAYS:g} d within {CUE_PAD_DAYS:g} d; or half "
                   "the panel's weight calling it instrumental."),
    "eclipsing_binary": ("Odd/even depth mismatch or secondary eclipse; or a depth of "
                         f"{DEEP_EB_PPM:,.0f} ppm or more; or V-shaped and {V_SHAPE_EB_PPM:,.0f} ppm or more; or a stellar-density "
                         f"mismatch at a period under {SHORT_PERIOD_DAYS:g} d; or half the panel's weight saying eclipsing binary. "
                         "Variability at an eclipsing binary's period, or half of it."),
    "flare": (f"A brightening: {FLARE_MIN_POINTS} or more consecutive points at least {FLARE_SIGMA:g}σ above a "
              f"{FLARE_WINDOW_DAYS:g}-day running median, peaking at {FLARE_PEAK_SIGMA:g}σ or more, against both the star's "
              f"scatter and the scatter within {FLARE_LOCAL_DAYS:g} d; not on an instrumental cue."),
    "variable": (f"A periodogram peak with Baluev FAP below {LS_FAP_MAX:g} and a semi-amplitude at least "
                 f"{LS_AMPLITUDE_RATIO:g}× the scatter of {LS_BIN_MINUTES:g}-minute bins, coherent: the same period (within "
                 f"{COHERENCE_TOLERANCE:.0%}) is the best peak of each half of the light curve, and not within 10% of the longest period "
                 "searched; a period shared by 3 or more stars of a sector is systematic. A dip lasting "
                 f"{TROUGH_FRACTION:g} of that period or more is a trough of it; so is a dip half the panel's weight called stellar variability."),
    "planet_candidate": ("Passed vetting, labelled a potential planet by half the panel's weight, not off its star's own "
                         "periodic signal, and taken by no rule above. A candidate, unconfirmed."),
    "unclassified": "Everything else, with the reason no class applied.",
}
CONFIDENCE = {
    "systematic": "high: two or more instrumental cues; medium: one; low: the panel's reason alone.",
    "eclipsing_binary": "high: odd/even mismatch or secondary eclipse; medium: depth, V shape, a short-period density mismatch, or the eclipse period; low: the panel's reason alone.",
    "flare": f"high: {FLARE_MIN_POINTS + 2} or more points, a peak of 10σ or more and a faster rise than decay; medium: two of those; low: otherwise.",
    "variable": "high: FAP below 1e-10 and a semi-amplitude 5× the binned scatter or more; medium: semi-amplitude 3× or more; low: otherwise (or a dip by the panel's reason alone).",
    "planet_candidate": "medium: on a periodic signal with two or more transits, neither V-shaped nor density-mismatched; low: otherwise. Never high.",
    "unclassified": "n/a.",
}


# ---------- instrumental context, from the light-curve file ----------
def quality_events(time, quality, good=None) -> dict:
    """Instrumental cues from a TESS light curve's full cadence list (before quality masking).

    ``good`` marks the cadences the pipeline kept (quality 0 and finite); gaps are measured on them.
    Returns momentum-dump times, scattered-light spans and data gaps, as lists of floats and [start, end]."""
    time = np.asarray(time, dtype=float)
    quality = np.asarray(quality, dtype=np.int64)
    finite = np.isfinite(time)
    good = finite & (quality == 0) if good is None else np.asarray(good, bool) & finite
    dumps = time[finite & ((quality & DUMP_BITS) != 0)]
    # Keep one time per dump (consecutive flagged cadences are one event).
    dump_times: list[float] = []
    for t in np.sort(dumps):
        if not dump_times or t - dump_times[-1] > 0.02:
            dump_times.append(float(t))
    scattered = _spans(time[finite & ((quality & SCATTERED_BITS) != 0)], join=0.05)
    pointing = _spans(time[finite & ((quality & POINTING_BITS) != 0)], join=0.05)
    tg = np.sort(time[good])
    gaps = [[float(a), float(b)] for a, b in zip(tg[:-1], tg[1:]) if b - a > GAP_DAYS]
    span = [float(tg[0]), float(tg[-1])] if tg.size else None
    return {"momentum_dumps": dump_times, "scattered_light": scattered, "pointing": pointing, "gaps": gaps, "span": span}


def _spans(times, join: float) -> list[list[float]]:
    out: list[list[float]] = []
    for t in np.sort(np.asarray(times, dtype=float)):
        if out and t - out[-1][1] <= join:
            out[-1][1] = float(t)
        else:
            out.append([float(t), float(t)])
    return out


def instrument_cues(t_start: float, t_end: float, events: dict | None, flags=()) -> list[dict]:
    """The instrumental cues for an event spanning [t_start, t_end]: each a rule id and a sentence."""
    cues = []
    if "edge_event" in flags:
        cues.append({"rule": "edge_event", "text": "within 0.1 d of a subject edge (vet.py edge_event)"})
    if not events:
        return cues
    pad = CUE_PAD_DAYS
    near = [t for t in events.get("momentum_dumps") or [] if t_start - pad <= t <= t_end + pad]
    if near:
        cues.append({"rule": "momentum_dump", "text": f"momentum dump at BTJD {near[0]:.3f}, within {pad:g} d (quality bit 32)"})
    for a, b in events.get("scattered_light") or []:
        if a - pad <= t_end and b + pad >= t_start:
            cues.append({"rule": "scattered_light", "text": f"scattered-light flags from BTJD {a:.2f} to {b:.2f} (quality bits 2048/4096)"})
            break
    for a, b in events.get("pointing") or []:
        if a - pad <= t_end and b + pad >= t_start:
            cues.append({"rule": "pointing", "text": f"pointing or manual-exclude flags from BTJD {a:.2f} to {b:.2f} (quality bits 1/4/16/128)"})
            break
    for a, b in events.get("gaps") or []:
        if (t_start - pad <= b <= t_end + pad) or (t_start - pad <= a <= t_end + pad):
            cues.append({"rule": "data_gap", "text": f"next to a {b - a:.1f}-day data gap (BTJD {a:.2f} to {b:.2f})"})
            break
    return cues


# ---------- the panel's own reasons ----------
def panel_shares(classifications: list[dict], weights: dict[str, float]) -> dict:
    """Weighted shares of one subject's panel: ``potential_planet`` and each noise reason.

    ``classifications`` are dicts with ``reviewer_id``, ``label`` and ``reason`` (one per reviewer; a later
    one replaces an earlier one, as in aggregate.py). Weights default to 1.0."""
    latest = {}
    for c in classifications:
        latest[c["reviewer_id"]] = c
    total = sum(float(weights.get(r, 1.0)) for r in latest)
    if total <= 0:
        return {}
    out: dict[str, float] = {}
    for r, c in latest.items():
        key = "potential_planet" if c.get("label") == "potential_planet" else (c.get("reason") or "noise")
        out[key] = out.get(key, 0.0) + float(weights.get(r, 1.0)) / total
    return {k: round(v, 4) for k, v in sorted(out.items())}


# ---------- the rules ----------
def classify_dip(dip: dict, events: dict | None = None, star_var: dict | None = None) -> dict:
    """Class, confidence, cues and (for unclassified) the reason, for one consensus dip.

    ``dip`` needs ``t_start``, ``t_end``, ``flags``, ``passed``, ``depth_ppm``, ``planet_fraction`` and
    optionally ``shares`` (:func:`panel_shares`), ``n_transits``, ``period_days``. ``star_var`` is the
    star's variability result (:func:`variability`) when it qualifies as variable."""
    flags = set(dip.get("flags") or ())
    shares = dip.get("shares") or {}
    depth = float(dip.get("depth_ppm") or 0.0)
    dur = float(dip["t_end"]) - float(dip["t_start"])

    inst = instrument_cues(dip["t_start"], dip["t_end"], events, flags)
    said = shares.get("instrumental", 0.0) >= REASON_SHARE
    if inst or said:
        cues = inst + ([{"rule": "panel_instrumental", "text": f"{shares['instrumental']:.0%} of the panel's weight called it instrumental"}] if said else [])
        conf = "high" if len(inst) >= 2 else "medium" if inst else "low"
        return _verdict("systematic", conf, cues)

    eb = []
    if "odd_even_mismatch" in flags:
        eb.append({"rule": "odd_even_mismatch", "text": "odd and even transits differ in depth (vet.py)"})
    if "secondary_eclipse" in flags:
        eb.append({"rule": "secondary_eclipse", "text": "a significant dip at phase 0.5 (vet.py)"})
    strong = bool(eb)
    if depth >= DEEP_EB_PPM:
        eb.append({"rule": "deep", "text": f"{depth:,.0f} ppm deep: {DEEP_EB_PPM:,.0f} ppm or more"})
    if "v_shape" in flags and depth >= V_SHAPE_EB_PPM:
        eb.append({"rule": "v_shape_deep", "text": f"V-shaped (transitfit.py) and {depth:,.0f} ppm deep"})
    if "density_mismatch" in flags and dip.get("period_days") and dip["period_days"] < SHORT_PERIOD_DAYS:
        eb.append({"rule": "density_short_period", "text": f"stellar density inconsistent with the star (transitfit.py) "
                                                           f"at P = {dip['period_days']:.3f} d, under {SHORT_PERIOD_DAYS:g} d"})
    shape = bool(eb)
    if shares.get("eclipsing_binary", 0.0) >= REASON_SHARE:
        eb.append({"rule": "panel_eb", "text": f"{shares['eclipsing_binary']:.0%} of the panel's weight said eclipsing binary"})
    if eb:
        return _verdict("eclipsing_binary", "high" if strong else "medium" if shape else "low", eb)

    var = []
    if star_var and star_var.get("period_days") and dur >= TROUGH_FRACTION * star_var["period_days"]:
        var.append({"rule": "trough", "text": f"lasts {dur * 24:.1f} h, {dur / star_var['period_days']:.2f} of the star's "
                                              f"{star_var['period_days']:.3f}-day variability period"})
    if shares.get("stellar_variability", 0.0) >= REASON_SHARE:
        var.append({"rule": "panel_variability", "text": f"{shares['stellar_variability']:.0%} of the panel's weight said stellar variability"})
    if var:
        return _verdict("variable", "medium" if var[0]["rule"] == "trough" else "low", var)

    pf = float(dip.get("planet_fraction") or 0.0)
    why = []
    if not dip.get("passed"):
        bad = sorted(flags & {"insufficient_points", "low_snr", "too_short", "odd_even_mismatch", "secondary_eclipse"})
        why.append("failed vetting: " + (", ".join(bad) if bad else "see flags"))
    if pf < PLANET_FRACTION:
        why.append(f"the panel's potential-planet share is {pf:.0%}, below {PLANET_FRACTION:.0%}")
    if "off_ephemeris" in flags:
        why.append("off its star's own strong periodic signal (off_ephemeris)")
    if why:
        return {**_verdict("unclassified", "n/a", []), "why": "; ".join(why)}

    periodic = (dip.get("n_transits") or 0) >= 2 and dip.get("period_days")
    worry = sorted(flags & {"v_shape", "density_mismatch"})
    cues = [{"rule": "passed", "text": "passed vetting"},
            {"rule": "panel_planet", "text": f"{pf:.0%} of the panel's weight labelled the subject a potential planet"}]
    if periodic:
        cues.append({"rule": "periodic", "text": f"on a periodic signal: {dip['n_transits']} transits, P = {dip['period_days']:.4f} d"})
    for w in worry:
        cues.append({"rule": w, "text": f"flagged {w} (transitfit.py): lowers confidence"})
    return _verdict("planet_candidate", "medium" if periodic and not worry else "low", cues)


def classify_flare(flare: dict, events: dict | None = None) -> dict:
    """A brightening is a flare unless it sits on an instrumental cue."""
    inst = instrument_cues(flare["t_start"], flare["t_end"], events)
    if inst:
        return _verdict("systematic", "high" if len(inst) >= 2 else "medium", inst)
    many = flare["n_points"] >= FLARE_MIN_POINTS + 2
    bright = flare["peak_sigma"] >= 10.0
    # Faster rise than decay by more than a second: equal times (whole cadences) differ only by float noise.
    shaped = flare["decay_days"] - flare["rise_days"] > 1.0 / 86400
    cues = [{"rule": "brightening", "text": f"{flare['n_points']} consecutive points over {FLARE_SIGMA:g}σ, peak {flare['peak_sigma']:.1f}σ "
                                            f"({flare['amplitude_ppm']:,.0f} ppm)"}]
    if shaped:
        cues.append({"rule": "fast_rise", "text": f"rises in {flare['rise_days'] * 1440:.0f} min, decays in {flare['decay_days'] * 1440:.0f} min"})
    n = many + bright + shaped
    return _verdict("flare", "high" if n == 3 else "medium" if n == 2 else "low", cues)


def _verdict(cls: str, confidence: str, cues: list[dict]) -> dict:
    return {"class": cls, "confidence": confidence, "cues": cues}


def _fap_text(fap: float) -> str:
    return "below 1e-300" if fap <= 0 else f"{fap:.1e}"


# ---------- detectors ----------
def find_flares(time, flux) -> list[dict]:
    """Upward events: runs of at least ``FLARE_MIN_POINTS`` consecutive points ``FLARE_SIGMA`` above a
    ``FLARE_WINDOW_DAYS`` running median, with a peak of ``FLARE_PEAK_SIGMA`` or more.

    σ is the robust scatter about the running median (preprocess.mad_sigma of the residuals), so a star's
    own pulsations raise the bar instead of passing as flares; the peak must also stand ``FLARE_PEAK_SIGMA``
    above the local scatter (``FLARE_LOCAL_DAYS`` either side, the run left out), so a disturbed stretch of
    data does not pass either. A run ends at a point below the threshold or at a gap of more than three
    cadences."""
    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    ok = np.isfinite(time) & np.isfinite(flux)
    time, flux = time[ok], flux[ok]
    if time.size < 10:
        return []
    order = np.argsort(time)
    time, flux = time[order], flux[order]
    base = running_median(time, flux, FLARE_WINDOW_DAYS)
    resid = flux - base
    sigma = mad_sigma(resid)
    if not np.isfinite(sigma) or sigma <= 0:
        return []
    cadence = float(np.median(np.diff(time)))
    above = resid >= FLARE_SIGMA * sigma
    out = []
    i, n = 0, time.size
    while i < n:
        if not above[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and above[j + 1] and time[j + 1] - time[j] <= FLARE_MAX_GAP_CADENCES * cadence:
            j += 1
        k = i + int(np.argmax(resid[i:j + 1]))
        npts = j - i + 1
        peak = float(resid[k] / sigma)
        near = (np.abs(time - time[k]) <= FLARE_LOCAL_DAYS) & ((time < time[i]) | (time > time[j]))
        local = mad_sigma(resid[near]) if near.sum() >= 20 else sigma
        if npts >= FLARE_MIN_POINTS and peak >= FLARE_PEAK_SIGMA and resid[k] >= FLARE_PEAK_SIGMA * max(local, sigma):
            out.append({"t_start": float(time[i]), "t_end": float(time[j]), "t_peak": float(time[k]), "n_points": int(npts),
                        "peak_sigma": round(peak, 2), "amplitude_ppm": round(float(resid[k]) * 1e6, 1),
                        "rise_days": float(time[k] - time[i]), "decay_days": float(time[j] - time[k])})
        i = j + 1
    return out


def _binned(time, flux, mask_windows=()):
    """10-minute bins of the out-of-dip light curve (bins with at least 3 points), or None when too few."""
    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    keep = np.isfinite(time) & np.isfinite(flux)
    for a, b in mask_windows:
        keep &= ~((time >= a) & (time <= b))
    time, flux = time[keep], flux[keep]
    if time.size < 50:
        return None
    width = LS_BIN_MINUTES / 1440.0
    idx = np.floor((time - time.min()) / width).astype(int)
    counts = np.bincount(idx)
    use = counts >= 3
    tb = (np.bincount(idx, weights=time) / np.maximum(counts, 1))[use]
    fb = (np.bincount(idx, weights=flux) / np.maximum(counts, 1))[use]
    return (tb, fb) if tb.size >= 30 else None


def _periodogram(tb, fb) -> dict | None:
    from astropy.timeseries import LombScargle

    if tb.size < 30:
        return None
    baseline = float(tb.max() - tb.min())
    max_p = LS_MAX_PERIOD_FRACTION * baseline
    if max_p <= LS_MIN_PERIOD_DAYS * 2:
        return None
    fmin, fmax = 1.0 / max_p, 1.0 / LS_MIN_PERIOD_DAYS
    ls = LombScargle(tb, fb)
    freq = np.linspace(fmin, fmax, int(min(200_000, max(2000, 10 * baseline * (fmax - fmin)))))
    power = ls.power(freq)
    best = int(np.argmax(power))
    f0 = float(freq[best])
    fap = float(ls.false_alarm_probability(power[best], method="baluev", minimum_frequency=fmin, maximum_frequency=fmax))
    theta = ls.model_parameters(f0)
    amp = float(math.hypot(theta[1], theta[2]))
    scatter = diff_sigma(fb)
    return {"period_days": round(1.0 / f0, 6), "power": round(float(power[best]), 5), "fap": fap,
            "fap_method": "Baluev 2008 (astropy LombScargle), white-noise assumption: optimistic on real light curves",
            "amplitude_ppm": round(amp * 1e6, 1), "binned_scatter_ppm": round(scatter * 1e6, 1),
            "amplitude_ratio": round(amp / scatter, 2) if scatter > 0 else 0.0,
            "n_bins": int(tb.size), "baseline_days": round(baseline, 3),
            "period_range_days": [round(LS_MIN_PERIOD_DAYS, 5), round(max_p, 3)]}


def _with_halves(tb, fb) -> dict | None:
    out = _periodogram(tb, fb)
    if out is None:
        return None
    mid = float(np.median(tb))
    halves = [_periodogram(tb[m], fb[m]) for m in (tb < mid, tb >= mid)]
    out["halves_period_days"] = [h["period_days"] if h else None for h in halves]
    out["half_period_max_days"] = round(min((h["period_range_days"][1] for h in halves if h), default=0.0), 3)
    return out


def variability(time, flux, mask_windows=()) -> dict | None:
    """The out-of-transit Lomb-Scargle periodogram of a light curve (astropy), on 10-minute bins
    (``LS_BIN_MINUTES``), and the same periodogram of each half of the light curve.

    Points inside ``mask_windows`` ([start, end] pairs, the consensus dips) are left out. Periods from
    30 minutes (``LS_MIN_PERIOD_DAYS``, above the 20-minute Nyquist period of the bins) to a third of the
    baseline (each half: a third of its own). Returns the best period, its power, the Baluev (2008)
    false-alarm probability (astropy; it assumes white noise, so it is optimistic on real light curves), the
    semi-amplitude of the best sinusoid and its ratio to the point-to-point scatter of the bins, the best
    period of each half, and the longest period a half can test."""
    b = _binned(time, flux, mask_windows)
    return _with_halves(*b) if b else None


def classify_variability(var: dict, eb_periods=()) -> dict | None:
    """The star's variability entry's class, or None when the periodogram shows nothing that qualifies.

    A peak that passes the FAP and amplitude rule is a pulsator or rotational variable only when the same period
    (within 10%) is the best peak of each half of the light curve: a coherent period. Red noise makes peaks that
    pass the amplitude rule but wander between halves. A peak within 10% of the longest period searched is a
    trend, a peak longer than a half can test is untested, and a peak in neither half's place is incoherent:
    each of those is unclassified, with the reason. Variability at an eclipsing binary's period is the binary's."""
    if not var or var.get("fap") is None:
        return None
    if not (var["fap"] < LS_FAP_MAX and var["amplitude_ratio"] >= LS_AMPLITUDE_RATIO):
        return None
    p = var["period_days"]
    top = (var.get("period_range_days") or [0, 0])[1]
    peak = (f"Lomb-Scargle peak at {p:.4f} d, semi-amplitude {var['amplitude_ppm']:,.0f} ppm "
            f"({var['amplitude_ratio']:.1f}× the binned scatter), Baluev FAP {_fap_text(var['fap'])}")
    if top and p >= LS_EDGE_FRACTION * top:
        return {**_verdict("unclassified", "n/a", []), "why": f"{peak}; within 10% of the longest period searched ({top:.2f} d): a trend, not a period"}
    for q in eb_periods:
        for k, lab in ((1.0, "the period"), (0.5, "half the period")):
            if q and abs(p - k * q) <= EB_PERIOD_TOLERANCE * k * q:
                return _verdict("eclipsing_binary", "medium", [{"rule": "eb_period", "text": f"variability at {lab} of an eclipsing-binary dip ({q:.4f} d)"}])
    half_top = var.get("half_period_max_days") or 0.0
    halves = var.get("halves_period_days") or [None, None]
    if not half_top or p >= LS_EDGE_FRACTION * half_top:
        return {**_verdict("unclassified", "n/a", []),
                "why": f"{peak}; longer than a half of the light curve can test ({half_top:.2f} d): coherence not tested"}
    if not all(h and abs(h - p) <= COHERENCE_TOLERANCE * p for h in halves):
        return {**_verdict("unclassified", "n/a", []),
                "why": f"{peak}; not the same period in both halves ({', '.join(f'{h:.3f} d' if h else 'none' for h in halves)}): "
                       "red noise, not a coherent period"}
    cues = [{"rule": "periodogram", "text": peak},
            {"rule": "coherent", "text": f"the same period in both halves of the light curve ({halves[0]:.3f} and {halves[1]:.3f} d)"}]
    conf = "high" if var["fap"] < 1e-10 and var["amplitude_ratio"] >= 5 else "medium" if var["amplitude_ratio"] >= 3 else "low"
    return _verdict("variable", conf, cues)


def qualifies_variable(var: dict | None) -> dict | None:
    """The star's variability when it is a coherent pulsator or rotational variable (for the trough rule), else None."""
    v = classify_variability(var) if var else None
    return var if v and v["class"] == "variable" else None


# ---------- the nulls: what each rule finds where its signal cannot be ----------
# Each class has its own null, because flipping the flux is not a null for everything: it turns a real flare or
# a pulsation maximum into a dip, and it leaves a periodogram unchanged.
NULL_FLARE_PAD_DAYS = 0.1
NULL_BLOCK_DAYS = 0.5


def dip_windows(entries, pad: float = NULL_FLARE_PAD_DAYS) -> list[tuple[float, float]]:
    return [(e["t_start"] - pad, e["t_end"] + pad) for e in entries if e.get("kind") == "dip"]


def flare_null(time, flux, dips, events=None) -> dict:
    """The flare rule on the flux turned upside down with the real consensus dips masked: downward events the
    same size and shape as a flare, which no star makes, so their count is the rule's noise level. Also the
    shape of each set: a real flare rises faster than it decays; noise has no preferred direction."""
    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    keep = np.ones(time.size, bool)
    for a, b in dips:
        keep &= ~((time >= a) & (time <= b))
    found = [classify_flare(f, events)["class"] for f in find_flares(time[keep], 2.0 - flux[keep])]
    return {"counts": {c: found.count(c) for c in sorted(set(found))}, "events": len(found)}


def flare_shape(entries) -> dict:
    """Of the brightenings classed flare: how many rise faster than they decay, and how many the other way."""
    fl = [e for e in entries if e.get("kind") == "brightening" and e.get("class") == "flare"]
    return {"fast_rise": sum(1 for e in fl if e["decay_minutes"] > e["rise_minutes"]),
            "slow_rise": sum(1 for e in fl if e["decay_minutes"] < e["rise_minutes"]),
            "equal": sum(1 for e in fl if e["decay_minutes"] == e["rise_minutes"])}


def block_shuffled(time, flux, *, block_days: float = NULL_BLOCK_DAYS, seed: int = 0, demean: bool = True):
    """The flux in 0.5-day blocks put back in a random order (times kept): a period longer than a block cannot
    survive, the noise on hour timescales does.

    With ``demean`` (the default) each block's median is removed first (and the flux's median put back), so the
    shuffle does not make level steps at the joins: a star's slow variability would otherwise reappear in the
    null as a square wave with a period of a few blocks, and the null would pass for the very signal it tests."""
    time = np.asarray(time, dtype=float)
    flux = np.asarray(flux, dtype=float)
    idx = np.floor((time - time.min()) / block_days).astype(int)
    blocks = [np.flatnonzero(idx == k) for k in np.unique(idx)]
    if demean and flux.size:
        level = float(np.median(flux))
        flux = flux.copy()
        for b in blocks:
            flux[b] = flux[b] - np.median(flux[b]) + level
    order = np.random.default_rng(seed).permutation(len(blocks))
    out = np.concatenate([flux[blocks[k]] for k in order])[: time.size]
    if out.size < time.size:
        out = np.concatenate([out, flux[out.size:]])
    return out


def red_noise_copy(tb, fb, *, seed: int = 0):
    """A red-noise copy of a binned light curve: an AR(1) process with the bins' own variance and lag-one
    correlation (a gap of n bins correlates as rho^n), on the same times. It keeps the star's red noise, the
    noise that makes periodogram peaks, and none of its periodicity."""
    x = np.asarray(fb, dtype=float) - float(np.mean(fb))
    sigma = float(np.std(x))
    rho = float(np.clip(np.corrcoef(x[:-1], x[1:])[0, 1], 0.0, 0.9999)) if x.size > 2 and sigma > 0 else 0.0
    width = LS_BIN_MINUTES / 1440.0
    steps = np.maximum(1.0, np.round(np.diff(tb) / width))
    rng = np.random.default_rng(seed)
    e = rng.normal(0.0, 1.0, x.size)
    y = np.empty(x.size)
    y[0] = sigma * e[0]
    for i in range(1, x.size):
        a = rho ** steps[i - 1]
        y[i] = a * y[i - 1] + math.sqrt(max(0.0, 1.0 - a * a)) * sigma * e[i]
    return 1.0 + y, {"rho_10min": round(rho, 4), "sigma_ppm": round(sigma * 1e6, 1)}


def variability_null(time, flux, dips, *, seed: int = 0) -> dict:
    """The variability rule, coherence test included, on a red-noise copy of the same star (``red_noise_copy``,
    fitted to its own out-of-dip bins): 1 when the copy passes. Unlike shuffling, it keeps the red noise that
    makes false periodogram peaks, so it is the right null for "is this a coherent period"."""
    b = _binned(time, flux, dips)
    if not b:
        return {"variable": 0, "method": "fitted AR(1) red noise"}
    y, fit = red_noise_copy(*b, seed=seed)
    v = classify_variability(_with_halves(b[0], y))
    return {"variable": int(bool(v and v["class"] == "variable")), "method": "fitted AR(1) red noise", **fit}


# ---------- one star-sector's entries, from a stored run ----------
def read_classifications(path: str | Path) -> list[dict]:
    """The run's classifications.csv as plain dicts: reviewer, subject, label, reason, rationale, marks."""
    out = []
    with Path(path).open(newline="") as handle:
        for row in csv.DictReader(handle):
            tasks = {t["task"]: t["value"] for t in json.loads(row["annotations"])}
            meta = json.loads(row["metadata"] or "{}")
            out.append({"reviewer_id": row["user_name"], "subject_id": row["subject_ids"], "label": row["label"] or tasks.get("T1"),
                        "reason": meta.get("reason"), "rationale": meta.get("rationale") or "",
                        "confidence": meta.get("confidence"), "marks": [[m["t_start"], m["t_end"]] for m in tasks.get("T0") or []]})
    return out


def entry_id(tic, sector, kind: str, t: float) -> str:
    """A stable id: the same event in a re-run gets the same id (time to 0.01 d)."""
    return f"tic{int(tic)}-s{int(sector)}-{kind}-{t:.2f}"


def star_entries(run_dir: str | Path, *, tic: int, sector: int, time=None, flux=None, events: dict | None = None,
                 extra: dict | None = None) -> dict:
    """Every catalogue entry for one star-sector, from a pipeline run directory (candidates.json,
    classifications.csv, manifest.json) and the quality-masked, normalised light curve (``time``, ``flux``).

    Returns ``{"entries": [...], "variability": {...} | None, "counts": {...}}``. Every dip in candidates.json
    becomes an entry; so does every brightening, and the variability when it qualifies."""
    run_dir = Path(run_dir)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    cands = json.loads((run_dir / "candidates.json").read_text())
    clfs = read_classifications(run_dir / "classifications.csv") if (run_dir / "classifications.csv").exists() else []
    weights = {k: float(v) for k, v in (manifest.get("weights") or {}).items()}
    kinds = {r["id"]: r["kind"] for r in manifest.get("reviewers") or []}
    by_subject: dict[str, list[dict]] = {}
    for c in clfs:
        by_subject.setdefault(c["subject_id"], []).append(c)
    # Each entry carries the weights its panel voted with (reviewer id → weight); kinds are on the star record.
    base = {"tic": int(tic), "sector": int(sector), "weights": {r: weights.get(r, 1.0) for r in sorted(kinds)}, **(extra or {})}

    dips = []
    for c in cands:
        flags = [f for f in (c.get("flags") or "").split(";") if f] if isinstance(c.get("flags"), str) else list(c.get("flags") or [])
        panel = by_subject.get(c["subject_id"], [])
        dips.append({**c, "flags": flags, "shares": panel_shares(panel, weights), "_panel": panel})
    var = variability(time, flux, [(d["t_start"] - 0.5 * (d["t_end"] - d["t_start"]), d["t_end"] + 0.5 * (d["t_end"] - d["t_start"])) for d in dips]) \
        if time is not None and flux is not None else None
    star_var = qualifies_variable(var)

    entries = []
    for d in dips:
        v = classify_dip(d, events, star_var)
        words = [{"reviewer": p["reviewer_id"], "label": p["label"], "reason": p["reason"], "rationale": p["rationale"]}
                 for p in d["_panel"] if kinds.get(p["reviewer_id"]) in ("claude", "claude_code") and p.get("rationale")]
        marks = [[a["reviewer_id"], m["t_start"], m["t_end"], bool(m["counted"])] for a in d.get("mark_audit") or [] for m in a.get("marks") or []]
        entries.append({
            "id": entry_id(tic, sector, "dip", d["t_center"]), "kind": "dip", **v,
            "t_start": d["t_start"], "t_end": d["t_end"], "t_center": d["t_center"], "time_unit": d.get("time_unit", "BTJD"),
            "duration_hours": d.get("duration_hours"), "depth_ppm": d.get("depth_ppm"), "snr": d.get("snr"),
            "period_days": d.get("period_days"), "n_transits": d.get("n_transits"), "fap_label": d.get("fap_label") or "",
            "flags": d["flags"], "passed": bool(d.get("passed")), "score": d.get("score"), "planet_fraction": d.get("planet_fraction"),
            "shares": d["shares"], "marks": marks, "words": words, "subject_id": d["subject_id"], "candidate_id": d.get("candidate_id"),
            "fit_depth_ppm": d.get("fit_depth_ppm"), "fit_t14_hours": d.get("fit_t14_hours"),
        })
    for f in find_flares(time, flux) if time is not None and flux is not None else []:
        v = classify_flare(f, events)
        entries.append({"id": entry_id(tic, sector, "flare", f["t_peak"]), "kind": "brightening", **v,
                        "t_start": f["t_start"], "t_end": f["t_end"], "t_center": f["t_peak"], "time_unit": "BTJD",
                        "duration_hours": (f["t_end"] - f["t_start"]) * 24.0, "amplitude_ppm": f["amplitude_ppm"],
                        "peak_sigma": f["peak_sigma"], "n_points": f["n_points"], "rise_minutes": round(f["rise_days"] * 1440, 1),
                        "decay_minutes": round(f["decay_days"] * 1440, 1), "marks": [], "words": [],
                        "note": "found by the upward-event detector (variables.find_flares); the reviewers mark dips only"})
    eb_periods = [e["period_days"] for e in entries if e["kind"] == "dip" and e["class"] == "eclipsing_binary" and e.get("period_days")]
    if var:
        v = classify_variability(var, eb_periods)
        if v:
            entries.append({"id": entry_id(tic, sector, "var", var["period_days"]), "kind": "variability", **v,
                            "period_days": var["period_days"], "amplitude_ppm": var["amplitude_ppm"], "ls_power": var["power"],
                            "ls_fap": var["fap"], "ls_fap_method": var["fap_method"], "amplitude_ratio": var["amplitude_ratio"],
                            "period_range_days": var["period_range_days"], "halves_period_days": var["halves_period_days"],
                            "half_period_max_days": var["half_period_max_days"],
                            "binned_scatter_ppm": var["binned_scatter_ppm"], "marks": [], "words": [],
                            "note": "from the out-of-transit periodogram (variables.variability); no reviewer marks"})
    # Two events within 0.01 d of each other share a time in their id: the later ones get -2, -3 ... (so ids stay unique).
    seen: dict[str, int] = {}
    for e in entries:
        n = seen[e["id"]] = seen.get(e["id"], 0) + 1
        if n > 1:
            e["id"] = f"{e['id']}-{n}"
    for e in entries:
        e.update({k: v for k, v in base.items() if k not in e})
    counts = {c: sum(1 for e in entries if e["class"] == c) for c in CLASS_IDS}
    return {"entries": entries, "variability": var, "counts": counts, "n_dips": len(dips)}


def class_counts(entries) -> dict[str, int]:
    return {c: sum(1 for e in entries if e.get("class") == c) for c in CLASS_IDS}

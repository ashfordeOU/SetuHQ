# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Non-periodic brightenings in TESS light curves: detection, characterisation, class hints and false-alarm screens.

:func:`find_transients` takes one light curve (days, flux) and searches it on two time scales:

* **fast** (minutes to hours; normalised light curves of stars only, not difference-imaging ones, whose cadence-
  scale systematics would dominate): the residual from a 0.5-day running median at the native cadence, two or more
  consecutive points 3σ or more above it and a peak of 5σ (σ the point-to-point scatter; a single point only on a
  momentum dump, where it is kept to be screened);
* **medium** (hours to a day): 1-hour bins against a 3-day running median that masks brightenings, two or more bins
  above 3σ peaking at 5σ;
* **slow** (days to weeks): 6-hour bins against a baseline (the median of the faintest third of the bins, or zero
  for a difference-imaging light curve), runs of at least three bins above 3σ peaking at 5σ or more, bridged across
  gaps shorter than two days (the mid-sector downlink).

Each candidate gets its peak time and amplitude, a **rise time** (for slow events, from a fit of
f = A (t − t₀)² to the part below 40% of the peak, the fireball model whose index Fausnaugh et al. 2023 find near 2;
for fast events, from the start of the run), a **decay time** (peak to half the peak, or a lower limit when the
data end first), the full width at half maximum and the rise/decay asymmetry. **Class hints** follow stated rules:

* flare-like: rise ≤ 0.1 d, decay ≤ 0.5 d, a rise from half the peak of at most 0.03 d (43 minutes) and no longer
  than the decay to half;
* extragalactic-transient-like (a supernova or tidal disruption event): rise ≥ 2 d and a decay of 5 d or more, or
  still above half its peak when the data end (at least a day after the peak, or after a rise of 5 d or more);
  photometry alone cannot tell a supernova from a TDE, so the hint names both;
* asteroid-crossing-like: symmetric (rise/decay 0.5-2), FWHM 0.05-2 d, or a difference-image centroid that moves by
  more than a pixel during the event;
* momentum-dump-like: within two cadences (at least 0.02 d) of a reaction-wheel desaturation (TESS quality bit
  32) and shorter than 0.2 d;
* periodic-variability-like: a slow brightening on a star whose 6-hour light curve has a periodogram peak of
  normalised power 0.3 or more (rotation or pulsation, not a transient);
* scattered-light-like: shorter than 2 d and peaking within 0.25 d of a scattered-light flag (bits 2048 or 4096),
  or seen in every control aperture at half the target's amplitude or more.

The last four are **likely false alarms**. Everything is a *transient candidate*: SetuHQ never calls one new,
discovered or confirmed, and a class hint is not a classification (that needs a spectrum).
"""

from __future__ import annotations

import math

import numpy as np

from setuhq.preprocess import diff_sigma, mad_sigma

LABEL = ("A transient candidate is a brightening in this light curve, never a new, discovered or confirmed object; "
         "class hints come from the light curve's shape and timing alone, and a spectrum is needed to classify.")
DUMP_BIT, SCATTER_BITS = 32, (2048, 4096)
FALSE_ALARM = ("asteroid-crossing-like", "momentum-dump-like", "scattered-light-like", "periodic-variability-like")
TESS_ZERO_POINT = 20.44  # TESS magnitude of a source giving 1 e-/s (TESS Instrument Handbook)


def quality_times(time, quality) -> dict:
    """Times of momentum dumps (bit 32) and scattered-light flags (bits 2048, 4096) from a QUALITY column."""
    t = np.asarray(time, float)
    q = np.asarray(quality, int)
    ok = np.isfinite(t)
    return {"momentum_dump": t[ok & ((q & DUMP_BIT) > 0)].tolist(),
            "scattered_light": t[ok & ((q & (SCATTER_BITS[0] | SCATTER_BITS[1])) > 0)].tolist()}


def read_quality(path) -> dict:
    """The quality-flag times of a SPOC light-curve FITS file (the loaders drop flagged cadences, so they are read
    here from the file itself)."""
    from astropy.io import fits

    with fits.open(path) as h:
        d = h[1].data
        return quality_times(np.asarray(d["TIME"], float), np.asarray(d["QUALITY"], int))


def _runs(mask):
    """(start, stop) index pairs of the True runs of ``mask`` (stop exclusive)."""
    m = np.concatenate([[False], np.asarray(mask, bool), [False]])
    d = np.diff(m.astype(int))
    return list(zip(np.where(d == 1)[0], np.where(d == -1)[0]))


def _bin(t, y, width):
    idx = np.floor((t - t[0]) / width).astype(int)
    n = np.bincount(idx)
    s = np.bincount(idx, y)
    ts = np.bincount(idx, t)
    k = n > 0
    return ts[k] / n[k], s[k] / n[k], n[k]


def first_light(tb, yb, t_peak, peak, frac=0.4):
    """t₀ and A of f = A (t − t₀)² (zero before t₀) fitted to the bins before the peak below ``frac`` of it, by a grid
    over t₀ with A solved linearly; None when fewer than four such bins rise."""
    sel = (tb <= t_peak) & (yb <= frac * peak)
    # only the stretch of bins that ends where the curve passes frac of the peak
    if sel.sum() < 4:
        return None
    tt, yy = tb[sel], yb[sel]
    grid = np.linspace(tt[0] - 5.0, min(t_peak, tt[-1]), 400)
    best = None
    for t0 in grid:
        x = np.clip(tt - t0, 0, None) ** 2
        xx = float(np.dot(x, x))
        if xx <= 0:
            continue
        a = float(np.dot(x, yy) / xx)
        if a <= 0:
            continue
        chi = float(np.sum((yy - a * x) ** 2))
        if best is None or chi < best[0]:
            best = (chi, t0, a)
    return None if best is None else {"t0": float(best[1]), "amplitude": float(best[2]), "points": int(sel.sum())}


def _characterise(tb, yb, i0, i1, sigma, fast: bool) -> dict:
    """Peak, amplitude, rise, decay, FWHM and asymmetry of the run [i0, i1) of the series (tb, yb)."""
    seg = slice(i0, i1)
    k = i0 + int(np.argmax(yb[seg]))
    if not fast and i1 - i0 >= 5:
        # a running mean over five bins (1.25 days of 6-hour bins) finds a steadier peak for slow events
        sm = np.convolve(yb, np.ones(5) / 5, mode="same")
        k = i0 + int(np.argmax(sm[seg]))
        peak = float(sm[k])
    else:
        peak = float(yb[k])
    tp = float(tb[k])
    half = peak / 2
    # decay: first time after the peak below half the peak
    j = k
    while j < len(yb) - 1 and yb[j] > half:
        j += 1
    decay = float(tb[j] - tp) if yb[j] <= half else None
    decay_lower = None if decay is not None else float(tb[-1] - tp)
    j0 = k
    while j0 > 0 and yb[j0] > half:
        j0 -= 1
    rise_half = float(tp - tb[j0]) if yb[j0] <= half else None
    fwhm = (decay + rise_half) if (decay is not None and rise_half is not None) else None
    fl = None if fast else first_light(tb, yb, tp, peak)
    rise = (tp - fl["t0"]) if fl else (tp - float(tb[i0]))
    sym = (rise_half / decay) if (rise_half and decay) else None
    return {"t_peak": tp, "peak": peak, "peak_sigma": float(peak / sigma) if sigma > 0 else None,
            "t_start": float(tb[i0]), "t_end": float(tb[i1 - 1]), "duration": float(tb[i1 - 1] - tb[i0]),
            "rise_time": float(rise), "rise_half_time": rise_half, "decay_time": decay, "decay_time_lower_limit": decay_lower,
            "fwhm": fwhm, "rise_decay_ratio": sym, "first_light": fl, "n_points": int(i1 - i0)}


def classify(c: dict, *, cadence: float, quality: dict | None = None, control_peaks=None, centroid_shift=None,
             periodic: dict | None = None) -> dict:
    """The class hint of one candidate and the reasons, by the rules of the module docstring."""
    reasons, hints = [], []
    dumps = np.asarray((quality or {}).get("momentum_dump") or [], float)
    scat = np.asarray((quality or {}).get("scattered_light") or [], float)
    tp, dur = c["t_peak"], max(c["duration"], cadence)
    if dumps.size and np.min(np.abs(dumps - tp)) <= max(2 * cadence, 0.02) and dur < 0.2:
        hints.append("momentum-dump-like")
        reasons.append(f"within {max(2 * cadence, 0.02) * 24:.1f} h of a momentum dump and shorter than 0.2 d")
    if scat.size and dur < 2 and np.min(np.abs(scat - tp)) <= max(0.25, 2 * cadence):
        hints.append("scattered-light-like")
        reasons.append("peaks next to cadences flagged for scattered light, and lasts under 2 days")
    if control_peaks is not None and len(control_peaks) and min(control_peaks) >= 0.5 * c["peak"] > 0:
        if "scattered-light-like" not in hints:
            hints.append("scattered-light-like")
        reasons.append(f"every control aperture brightens by at least {min(control_peaks) / c['peak']:.0%} of the target's peak at the same time")
    r, d, fw = c["rise_time"], c["decay_time"], c["fwhm"]
    sym = c["rise_decay_ratio"]
    if centroid_shift is not None and centroid_shift > 1.0 and dur < 3:
        hints.append("asteroid-crossing-like")
        reasons.append(f"the difference-image centroid moves {centroid_shift:.1f} pixels during the event")
    elif sym is not None and 0.5 <= sym <= 2.0 and fw is not None and 0.05 <= fw <= 2.0 and r < 2:
        hints.append("asteroid-crossing-like")
        reasons.append(f"symmetric (rise/decay {sym:.2f}) with a FWHM of {fw:.2f} d")
    rh = c["rise_half_time"] or 0.0
    if r <= 0.1 and d is not None and d <= 0.5 and rh <= 0.03 and rh <= d:
        hints.append("flare-like")
        reasons.append(f"fast rise ({r * 24 * 60:.0f} min to the peak, {(c['rise_half_time'] or 0) * 24 * 60:.0f} min from half "
                       f"of it) and a decay to half of {d * 24 * 60:.0f} min")
    elif r >= 2 and ((d is not None and d >= 5) or (d is None and ((c["decay_time_lower_limit"] or 0) >= 1 or r >= 5))):
        hints.append("extragalactic-transient-like")
        reasons.append(f"slow rise ({r:.1f} d) and a {'decay of ' + format(d, '.1f') + ' d' if d is not None else 'decay longer than the data'}"
                       ", as a supernova or tidal disruption event (photometry alone cannot tell which)")
    if periodic is not None and c["scale"] == "slow":
        hints.append("periodic-variability-like")
        reasons.append(f"the star varies periodically ({periodic['period']:.2f} d, normalised power {periodic['power']:.2f}); "
                       "a slow brightening is likely part of that variation")
    false_alarm = any(h in FALSE_ALARM for h in hints)
    # a false-alarm screen outranks a shape hint: the class is the first screen that fired, else the shape
    order = [h for h in hints if h in FALSE_ALARM] + [h for h in hints if h not in FALSE_ALARM]
    return {"class_hint": order[0] if order else "unclassified", "hints": hints, "likely_false_alarm": false_alarm,
            "reasons": reasons or ["no rule matched"]}


def _masked_trend(t, y, window, step=10 / 1440, iterations=3, sigma=2.5):
    """A running median that ignores brightenings: points more than ``sigma`` robust deviations above it are masked
    and the median recomputed (so a bump of up to about half the window is not absorbed)."""
    from setuhq.binaries import trend
    from setuhq.preprocess import running_median

    keep = np.ones_like(y, bool)
    tr = np.zeros_like(y)
    for _ in range(iterations):
        tr_k = trend(t[keep], y[keep], window, step=step) if step else running_median(t[keep], y[keep], window)
        tr = np.interp(t, t[keep], tr_k)
        r = y - tr
        sd = mad_sigma(r[keep])
        new = r < sigma * sd
        if new.sum() < 0.5 * len(y) or np.array_equal(new, keep):
            break
        keep = new
    return tr


def _merge(runs, tb, max_gap):
    out = []
    for a, b in runs:
        if out and tb[a] - tb[out[-1][1] - 1] <= max_gap:
            out[-1] = (out[-1][0], b)
        else:
            out.append((a, b))
    return out


def find_transients(time, flux, flux_err=None, *, mode: str = "relative", quality: dict | None = None,
                    controls=None, centroid=None, slow_bin_days: float = 0.25, min_sigma: float = 3.0,
                    peak_sigma: float = 5.0, zero_point: float | None = None, aperture_correction: float = 1.0) -> dict:
    """Search one light curve for brightenings on both time scales and characterise each candidate.

    ``mode`` is "relative" (a normalised light curve, e.g. SPOC PDCSAP) or "difference" (difference-imaging flux in
    e-/s, zero before the event). ``controls`` are light curves of control apertures on the same time grid,
    ``centroid`` the difference-image centroid (x, y) per cadence; both are optional. With ``zero_point`` and a
    difference light curve, peaks are also given as TESS magnitudes (after ``aperture_correction``)."""
    t = np.asarray(time, float)
    y = np.asarray(flux, float)
    ok = np.isfinite(t) & np.isfinite(y)
    t, y = t[ok], y[ok]
    ctrl = [np.asarray(c, float)[ok] for c in (controls or [])]
    cen = None if centroid is None else np.asarray(centroid, float)[ok]
    if len(t) < 20:
        return {"label": LABEL, "candidates": [], "n_points": int(len(t)), "reasons": ["too few points"]}
    if mode == "relative":
        y = y / np.median(y) - 1
    cad = float(np.median(np.diff(t)))
    base = float(t[-1] - t[0])
    cands = []
    dumps = np.asarray((quality or {}).get("momentum_dump") or [], float)
    # ---- fast: residual from a 0.5-day running median at the native cadence; runs of two or more points (a single
    # point is an outlier unless it sits on a momentum dump, where it is kept to be screened)
    if mode == "relative" and cad < 0.05:
        r = y - _masked_trend(t, y, 0.5)
        s = diff_sigma(r)
        above = r > min_sigma * s
        wins = []
        for a, b in _runs(above):
            on_dump = bool(dumps.size and np.min(np.abs(dumps - t[a])) <= 2 * cad + 1e-9)
            if (b - a >= 2 or on_dump) and np.max(r[a:b]) >= peak_sigma * s:
                b2 = b
                while b2 < len(r) and r[b2] > 0.5 * s:
                    b2 += 1
                if wins and a <= wins[-1][1]:
                    wins[-1] = (wins[-1][0], max(b2, wins[-1][1]))  # overlapping windows are one event
                else:
                    wins.append((a, b2))
        for a, b2 in wins:
            cands.append({"scale": "fast", **_characterise(t, r, a, b2, s, True)})
    # ---- medium: 1-hour bins against a 3-day running median that masks brightenings (asteroid crossings, long
    # flares and other events of hours to a day)
    tm, ym, _ = _bin(t, y, 1 / 24)
    if len(tm) > 24:
        rm = ym - _masked_trend(tm, ym, 3.0, step=None)
        s_m = diff_sigma(rm)
        for a, b in _runs(rm > min_sigma * s_m):
            if b - a >= 2 and np.max(rm[a:b]) >= peak_sigma * s_m:
                c = {"scale": "medium", **_characterise(tm, rm, a, b, s_m, True)}
                if not any(o["t_start"] - 1 / 24 <= c["t_peak"] <= o["t_end"] + 1 / 24 for o in cands):
                    cands.append(c)
    # ---- slow: 6-hour bins against the baseline
    tb, yb, nb = _bin(t, y, slow_bin_days)
    s_b = diff_sigma(yb)
    if mode == "relative":
        base_level = float(np.median(np.sort(yb)[: max(3, len(yb) // 3)]))
    else:
        base_level = 0.0
    yb0 = yb - base_level
    above = yb0 > min_sigma * s_b
    runs = [(a, b) for a, b in _merge(_runs(above), tb, 2.0) if b - a >= 3 and np.max(yb0[a:b]) >= peak_sigma * s_b]
    for a, b in runs:
        c = {"scale": "slow", **_characterise(tb, yb0, a, b, s_b, False)}
        if c["duration"] < 0.75:
            continue  # shorter than three bins of real data: the faster searches cover it
        # a slow event replaces the medium candidates inside it (its own rise and peak, seen in shorter bins)
        cands = [o for o in cands if not (o["scale"] == "medium" and c["t_start"] <= o["t_peak"] <= c["t_end"])]
        cands.append(c)
    # a periodic star (normalised light curves only): its slow brightenings are marked as part of the variation
    periodic = None
    if mode == "relative" and len(tb) > 20 and base > 2:
        from astropy.timeseries import LombScargle

        fr, pw = LombScargle(tb, yb).autopower(minimum_frequency=2 / base, maximum_frequency=4.0, samples_per_peak=5)
        k = int(np.argmax(pw))
        if pw[k] >= 0.3:
            periodic = {"period": float(1 / fr[k]), "power": float(pw[k])}
    # characterise each candidate's context and class hint
    for c in cands:
        win = (t >= c["t_start"] - cad) & (t <= c["t_end"] + cad)
        cp = None
        if ctrl:
            cp = []
            for cy in ctrl:
                cy2 = cy / np.median(cy) - 1 if mode == "relative" else cy
                if c["scale"] != "slow":
                    cb = cy2 - _masked_trend(t, cy2, 0.5 if c["scale"] == "fast" else 3.0)
                    cp.append(float(np.max(cb[win])) if win.any() else 0.0)
                else:
                    tcb, ycb, _ = _bin(t, cy2, slow_bin_days)
                    m = (tcb >= c["t_peak"] - 1) & (tcb <= c["t_peak"] + 1)
                    cp.append(float(np.median(ycb[m])) if m.any() else 0.0)
            c["control_peaks"] = cp
        shift = None
        if cen is not None and win.sum() >= 3:
            w = cen[win]
            g = np.all(np.isfinite(w), axis=1)
            if g.sum() >= 3:
                shift = float(np.hypot(*(np.nanmax(w[g], axis=0) - np.nanmin(w[g], axis=0))))
            c["centroid_shift_px"] = shift
        c.update(classify(c, cadence=cad, quality=quality, control_peaks=cp, centroid_shift=shift, periodic=periodic))
        if mode == "difference" and zero_point is not None and c["peak"] > 0:
            c["peak_mag"] = float(zero_point - 2.5 * math.log10(c["peak"] / aperture_correction))
        c["label"] = "transient candidate"
    cands.sort(key=lambda c: c["t_peak"])
    return {"label": LABEL, "mode": mode, "cadence_days": cad, "baseline_days": base, "n_points": int(len(t)), "periodic": periodic,
            "noise": {"fast_point_sigma": float(diff_sigma(y)), "slow_bin_sigma": float(s_b), "slow_bin_days": slow_bin_days},
            "candidates": cands,
            "summary": {"n_candidates": len(cands), "n_likely_false_alarms": sum(c["likely_false_alarm"] for c in cands),
                        "by_class": {k: sum(c["class_hint"] == k for c in cands) for k in sorted({c["class_hint"] for c in cands})}}}


# ---------------------------------------------------------------- synthetic events (tests and injections)

def sn_model(t, t_first, t_rise, peak, decline_days=20.0):
    """A type Ia-like light curve: (t − t_first)² up to the peak, then an exponential decline."""
    t = np.asarray(t, float)
    tp = t_first + t_rise
    y = np.where(t < t_first, 0.0, peak * np.clip((t - t_first) / t_rise, 0, None) ** 2)
    return np.where(t > tp, peak * np.exp(-(t - tp) / decline_days * math.log(2) * 1.0), y)


def flare_model(t, t_peak, amp, rise_min=5.0, decay_min=30.0):
    """A flare: a linear rise over ``rise_min`` minutes and an exponential decay with an e-folding of ``decay_min``."""
    t = np.asarray(t, float)
    r, d = rise_min / 1440, decay_min / 1440
    y = np.where((t >= t_peak - r) & (t <= t_peak), amp * (t - (t_peak - r)) / r, 0.0)
    return np.where(t > t_peak, amp * np.exp(-(t - t_peak) / d), y)


def asteroid_model(t, t_peak, amp, fwhm):
    """An asteroid crossing the aperture: a symmetric Gaussian bump."""
    return amp * np.exp(-0.5 * ((np.asarray(t, float) - t_peak) / (fwhm / 2.3548)) ** 2)


def dump_spike(t, t_dump, amp, n_cadences=2):
    """A spike of ``n_cadences`` cadences starting at a momentum dump."""
    t = np.asarray(t, float)
    i = int(np.searchsorted(t, t_dump))
    y = np.zeros_like(t)
    y[i:i + n_cadences] = amp
    return y

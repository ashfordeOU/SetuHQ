# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Eclipsing binaries and ellipsoidal or reflection variables in TESS light curves.

:func:`analyse` takes one light curve (days, relative flux) and returns:

* **the orbital period**, from a box search (BLS) on a flattened copy and a Lomb-Scargle periodogram on the
  unflattened one; the shortest coherent period is doubled when the two halves of the fold at twice it differ (an
  odd/even difference: the true period) or when the fold has a single minimum per cycle (equal minima are assumed,
  and the record says the period is ambiguous);
* **the primary and secondary eclipses**: phase, depth (1 − minimum / out-of-eclipse level), width (full width at
  half depth, in phase units) and significance, on a binned phase curve;
* **the secondary phase**, and from it the hint e·cosω ≈ (π/2)(φ₂ − 0.5) (Sterne 1940; first order in e, so a
  hint, not a measurement);
* **a morphology class** (detached, semi-detached, contact, ellipsoidal or reflection-like) from the eclipse widths
  and the out-of-eclipse variation, a heuristic stated with its numbers;
* **an eclipsing-binary candidate flag** with its reasons. A candidate is never "new" or "confirmed": the record says
  what the light curve shows.

:func:`vetting_hints` gives the same evidence for a transit candidate's ephemeris (odd/even depths, a secondary at
any phase, ellipsoidal and reflection amplitudes). It is advisory: no vetting decision of :mod:`setuhq.vet` uses it,
the frozen benchmark is unchanged, and using it in vetting would need its own pre-registered evaluation.
"""

from __future__ import annotations

import math

import numpy as np

from setuhq.preprocess import diff_sigma, mad_sigma, running_median

LABEL = ("An eclipsing-binary candidate is what this light curve shows, never a confirmed or new binary; the "
         "morphology is a heuristic class, and e·cosω is a first-order hint from the secondary's phase.")
VETTING_NOTE = ("Advisory only: these hints are not used by SetuHQ's planet vetting (vet.py), whose results and frozen "
                "benchmark are unchanged; using them in vetting needs its own pre-registered evaluation.")
N_BINS = 200


def _clean(time, flux, flux_err=None):
    t = np.asarray(time, float)
    f = np.asarray(flux, float)
    e = np.full_like(f, np.nan) if flux_err is None else np.asarray(flux_err, float)
    ok = np.isfinite(t) & np.isfinite(f)
    t, f, e = t[ok], f[ok], e[ok]
    o = np.argsort(t)
    t, f, e = t[o], f[o], e[o]
    med = np.median(f)
    f, e = f / med, e / med
    if not np.isfinite(e).any():
        e = np.full_like(f, diff_sigma(f))
    e = np.where(np.isfinite(e) & (e > 0), e, np.nanmedian(e[e > 0]) if (e > 0).any() else diff_sigma(f))
    return t, f, e


def _bin(t, y, width):
    """Means of ``y`` in bins of ``width`` (days); returns centres, means, standard errors, counts."""
    if len(t) == 0:
        return (np.array([]),) * 4
    idx = np.floor((t - t[0]) / width).astype(int)
    n = np.bincount(idx)
    s = np.bincount(idx, y)
    s2 = np.bincount(idx, y * y)
    ts = np.bincount(idx, t)
    k = n > 0
    m = s[k] / n[k]
    v = np.maximum(s2[k] / n[k] - m * m, 0)
    return ts[k] / n[k], m, np.sqrt(v / np.maximum(n[k] - 1, 1)), n[k]


def trend(t, f, window, step=20 / 1440):
    """A running median of ``window`` days, computed on ``step``-day medians and interpolated (fast on 2-minute
    data; the step is far shorter than any window used here)."""
    t = np.asarray(t, float)
    f = np.asarray(f, float)
    if len(t) < 3:
        return np.full_like(f, np.median(f) if len(f) else 1.0)
    idx = np.floor((t - t[0]) / step).astype(int)
    order = np.argsort(idx, kind="stable")
    uniq, start = np.unique(idx[order], return_index=True)
    meds = np.array([np.median(x) for x in np.split(f[order], start[1:])])
    tb = np.array([np.mean(x) for x in np.split(t[order], start[1:])])
    rm = running_median(tb, meds, window)
    return np.interp(t, tb, rm)


def flatten(t, f, window=1.0, iterations=3, sigma=2.5):
    """Divide out a running median, masking low points (eclipses) before recomputing it."""
    keep = np.ones_like(f, bool)
    tr_all = np.ones_like(f)
    for _ in range(iterations):
        tt = t[keep]
        tr = trend(tt, f[keep], window)
        trend_ = np.interp(t, tt, tr)
        tr_all = trend_
        r = f / trend_ - 1
        s = mad_sigma(r[keep])
        new = r > -sigma * s
        if new.sum() < 0.3 * len(f) or np.array_equal(new, keep):
            break
        keep = new
    return f / tr_all, tr_all


def _cycle_detrend(t, f, period, base):
    """Divide out variability slower than the binary: a running median over a whole number of cycles (at least one
    day). A median over whole cycles of a periodic signal is nearly constant, so the binary's own eclipses and
    ellipsoidal variation stay while spots and drifts on longer time scales go."""
    w = period * max(1, math.ceil(1.0 / period))
    return f / trend(t, f, w) if w < base / 1.5 else f / np.median(f)


def fold_curve(t, f, period, t0, n_bins=N_BINS):
    """The binned phase curve: bin centres (phase 0-1, primary at 0), means, errors and counts per bin."""
    ph = np.mod((t - t0) / period, 1.0)
    idx = np.minimum((ph * n_bins).astype(int), n_bins - 1)
    n = np.bincount(idx, minlength=n_bins).astype(float)
    s = np.bincount(idx, f, minlength=n_bins)
    s2 = np.bincount(idx, f * f, minlength=n_bins)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / n
        v = np.maximum(s2 / n - m * m, 0)
        err = np.sqrt(v / np.maximum(n - 1, 1))
    centres = (np.arange(n_bins) + 0.5) / n_bins
    return centres, m, err, n


def _fill(m):
    """Fill empty bins of a periodic binned curve by circular interpolation."""
    m = np.array(m, float)
    ok = np.isfinite(m)
    if ok.all() or not ok.any():
        return m
    x = np.arange(len(m))
    xp = np.concatenate([x[ok] - len(m), x[ok], x[ok] + len(m)])
    fp = np.concatenate([m[ok]] * 3)
    m[~ok] = np.interp(x[~ok], xp, fp)
    return m


def _smooth(m, k=3):
    """Circular running mean over ``k`` bins (odd)."""
    if k <= 1:
        return m
    pad = k // 2
    x = np.concatenate([m[-pad:], m, m[:pad]])
    return np.convolve(x, np.ones(k) / k, mode="valid")


def explained(t, f, period, n_bins=N_BINS):
    """Fraction of the variance a binned phase curve at ``period`` explains (phase-dispersion statistic)."""
    _, m, _, n = fold_curve(t, f, period, t[0], n_bins)
    m = _fill(m)
    ph = np.mod((t - t[0]) / period, 1.0)
    model = m[np.minimum((ph * n_bins).astype(int), n_bins - 1)]
    v = np.var(f)
    return float(1 - np.var(f - model) / v) if v > 0 else 0.0


def _halves_differ(t, f, e, period, n_bins=100):
    """Fold at ``period`` and compare the two halves (phases 0-0.5 and 0.5-1) bin by bin: chi² per degree of freedom
    and its significance in sigma (a significant difference means the true period is ``period``, not half of it)."""
    ph = np.mod((t - t[0]) / period, 1.0)
    h = ph >= 0.5
    sub = np.mod(ph, 0.5) * 2
    idx = np.minimum((sub * n_bins).astype(int), n_bins - 1)
    out = []
    for part in (~h, h):
        n = np.bincount(idx[part], minlength=n_bins).astype(float)
        s = np.bincount(idx[part], f[part], minlength=n_bins)
        s2 = np.bincount(idx[part], f[part] ** 2, minlength=n_bins)
        with np.errstate(invalid="ignore", divide="ignore"):
            m = s / n
            v = np.maximum(s2 / n - m * m, 0)
            err2 = v / np.maximum(n - 1, 1)
        out.append((m, err2, n))
    (m1, e1, n1), (m2, e2, n2) = out
    ok = (n1 >= 3) & (n2 >= 3) & ((e1 + e2) > 0)
    if ok.sum() < 10:
        return {"chi2_dof": None, "sigma": 0.0, "bins": int(ok.sum())}
    chi2 = float(np.sum((m1[ok] - m2[ok]) ** 2 / (e1[ok] + e2[ok])))
    dof = int(ok.sum())
    return {"chi2_dof": chi2 / dof, "sigma": float((chi2 - dof) / math.sqrt(2 * dof)), "bins": dof}


def _persistent_difference(t, f, e, period, n_bins=50):
    """True when the halves of the fold at ``period`` differ significantly (5 sigma) and the difference has the same
    shape in the first and second half of the data (correlation above 0.5)."""
    if _halves_differ(t, f, e, period)["sigma"] < 5:
        return False
    mid = np.median(t)
    vecs = []
    for sel in (t < mid, t >= mid):
        ph = np.mod((t[sel] - t[0]) / period, 1.0)
        idx = np.minimum((np.mod(ph, 0.5) * 2 * n_bins).astype(int), n_bins - 1)
        a = np.bincount(idx[ph < 0.5], f[sel][ph < 0.5], minlength=n_bins) / np.maximum(np.bincount(idx[ph < 0.5], minlength=n_bins), 1)
        b = np.bincount(idx[ph >= 0.5], f[sel][ph >= 0.5], minlength=n_bins) / np.maximum(np.bincount(idx[ph >= 0.5], minlength=n_bins), 1)
        vecs.append(a - b)
    if np.std(vecs[0]) == 0 or np.std(vecs[1]) == 0:
        return False
    return bool(np.corrcoef(vecs[0], vecs[1])[0, 1] > 0.5)


def _min_near(c, m, centre, half):
    """Index of the minimum of the binned curve within ``half`` (phase) of ``centre`` (circular)."""
    d = np.abs((c - centre + 0.5) % 1.0 - 0.5)
    w = np.where(d <= half)[0]
    if w.size == 0:
        return None
    return int(w[np.nanargmin(m[w])])


def _refine_min(c, m, i):
    """Sub-bin phase of a minimum from a parabola through three bins."""
    n = len(m)
    y0, y1, y2 = m[(i - 1) % n], m[i], m[(i + 1) % n]
    den = y0 - 2 * y1 + y2
    dx = 0.5 * (y0 - y2) / den if den > 0 else 0.0
    return float((c[i] + np.clip(dx, -1, 1) / n) % 1.0)


def _width(c, m, i, level, depth):
    """Full width (phase) of the eclipse at bin ``i`` at half its depth below ``level``."""
    n = len(m)
    half = level - 0.5 * depth
    lo = hi = 0
    while lo < n // 2 and m[(i - lo - 1) % n] < half:
        lo += 1
    while hi < n // 2 and m[(i + hi + 1) % n] < half:
        hi += 1
    # linear interpolation of the half-depth crossing on each side
    def frac(a, b):
        ya, yb = m[a % n], m[b % n]
        return float(np.clip((half - ya) / (yb - ya), 0, 1)) if yb != ya else 0.0
    w = lo + hi + frac(i - lo, i - lo - 1) + frac(i + hi, i + hi + 1)
    return float(max(w, 1.0) / n)


def bls_period(t, f, e, pmin, pmax):
    """Box least squares on a flattened light curve: best period, epoch, duration, depth and its SDE."""
    from astropy.timeseries import BoxLeastSquares

    base = t[-1] - t[0]
    tb, fb, eb, _ = _bin(t, f, 10 / 1440)  # 10-minute bins for speed
    eb = np.where(eb > 0, eb, np.nanmedian(eb[eb > 0]) if (eb > 0).any() else 1e-3)
    durations = np.array([0.02, 0.04, 0.08, 0.12, 0.16, 0.24])
    durations = durations[durations < 0.5 * pmin * 2]
    if durations.size == 0:
        durations = np.array([0.4 * pmin])
    model = BoxLeastSquares(tb, fb, dy=eb)
    q = 3.0
    freqs = np.arange(1 / pmax, 1 / pmin, durations.min() / (q * base * base) if base > 0 else 1e-3)
    freqs = freqs[: 60_000]
    periods = np.sort(1 / freqs)
    res = model.power(periods, durations, objective="snr")
    p = np.asarray(res.power, float)
    k = int(np.nanargmax(p))
    sde = float((p[k] - np.nanmean(p)) / np.nanstd(p)) if np.nanstd(p) > 0 else 0.0
    return {"period": float(res.period[k]), "t0": float(res.transit_time[k]), "duration": float(res.duration[k]),
            "depth": float(res.depth[k]), "snr": float(p[k]), "sde": sde}


def ls_period(t, f, pmin, pmax):
    """Lomb-Scargle on 10-minute bins: the best period and its normalised power and false-alarm probability."""
    from astropy.timeseries import LombScargle

    tb, fb, _, _ = _bin(t, f, 10 / 1440)
    ls = LombScargle(tb, fb)
    freq, power = ls.autopower(minimum_frequency=1 / pmax, maximum_frequency=1 / pmin, samples_per_peak=10)
    k = int(np.argmax(power))
    return {"period": float(1 / freq[k]), "power": float(power[k]),
            "fap": float(ls.false_alarm_probability(power[k], minimum_frequency=1 / pmax, maximum_frequency=1 / pmin))}


def _refine_period(t, f, p, span=0.003, n=61):
    """The period near ``p`` whose phase curve explains most variance (a fine grid of ±``span``·p)."""
    grid = p * (1 + np.linspace(-span, span, n))
    ev = np.array([explained(t, f, g) for g in grid])
    k = int(np.argmax(ev))
    # a parabola through the best three points
    if 0 < k < n - 1:
        y0, y1, y2 = ev[k - 1], ev[k], ev[k + 1]
        den = y0 - 2 * y1 + y2
        dx = 0.5 * (y0 - y2) / den if den < 0 else 0.0
        best = grid[k] + np.clip(dx, -1, 1) * (grid[1] - grid[0])
    else:
        best = grid[k]
    return float(best), float(ev[k])


def analyse(time, flux, flux_err=None, *, pmin: float = 0.2, pmax: float | None = None, n_bins: int = N_BINS) -> dict:
    """Detect and characterise an eclipsing binary (or ellipsoidal or reflection variable) in one light curve.

    The strongest periodic signal is analysed first. When the box search on the flattened light curve found a
    different period, that period is analysed again on the flattened curve and kept if it is binary-like and its
    fold explains more of the flattened curve, so an eclipsing binary under a stronger spot modulation is not missed
    or given the spots' period; the record says which pass it came from."""
    t, f, e = _clean(time, flux, flux_err)
    base = float(t[-1] - t[0]) if len(t) > 1 else 0.0
    out = {"label": LABEL, "n_points": int(len(t)), "baseline_days": base}
    if len(t) < 200 or base < 2 * pmin:
        return {**out, "eb_candidate": False, "reasons": ["too few points or too short a baseline"], "period": None}
    pmax = float(min(pmax or 13.0, base / 2.0))
    flat, _ = flatten(t, f, window=1.0)
    bls = bls_period(t, flat, e, pmin, pmax)
    # the unflattened copy keeps ellipsoidal and contact variation for the periodogram
    ls = ls_period(t, f, pmin / 2, pmax)
    first = _analyse(t, f, e, base, pmin, pmax, n_bins, bls, ls, None)
    if not first.get("period") or bls["snr"] < 7:
        return {**out, **first, "pass": "strongest periodic signal"}
    near = any(abs(bls["period"] / (first["period"] * m) - 1) < 0.01 for m in (0.5, 1, 2))
    if near:
        return {**out, **first, "pass": "strongest periodic signal"}
    second = _analyse(t, flat, e, base, pmin, pmax, n_bins, bls, ls, [bls["period"], 2 * bls["period"]])
    # the box-search period wins when it is binary-like and, on the flattened curve, its fold explains more than the
    # first pass's period does (eclipses under spots, or a spot period mistaken for an orbit)
    # (and only with three or more cycles, so the halves of the data can be compared)
    better = second["eb_candidate"] and second.get("half_stability") is not None and (not first["eb_candidate"] or
                                         second["explained_variance"] > explained(t, flat, first["period"], n_bins))
    if better:
        second["reasons"] = second["reasons"] + [
            f"found by the box search on the flattened light curve, beside a stronger periodic signal at P = "
            f"{first['period']:.4f} d (" + "; ".join(first["reasons"]) + ")"]
        return {**out, **second, "pass": "box search on the flattened light curve", "first_pass": {
            k: first.get(k) for k in ("period", "reasons", "half_stability", "half_amplitude_ratio")}}
    return {**out, **first, "pass": "strongest periodic signal"}


def _analyse(t, f, e, base, pmin, pmax, n_bins, bls, ls, candidates) -> dict:
    noise = diff_sigma(f)
    cands = candidates or sorted({round(bls["period"], 6), round(ls["period"], 6), round(2 * ls["period"], 6)} - {0.0})
    cands = [p for p in cands if pmin <= p <= pmax]
    scored = []
    for p in cands:
        g = _cycle_detrend(t, f, p, base)
        scored.append((explained(t, g, p, n_bins), p))
    ev0, p_phot = max(scored)
    g = _cycle_detrend(t, f, p_phot, base)
    # the shortest coherent period: halve while half the period explains 90% as much (equal or similar minima)
    # unless the two halves of each cycle differ significantly and in the same way in both halves of the data (unequal
    # minima; evolving spots make differences that change)
    while p_phot / 2 >= pmin:
        if explained(t, g, p_phot / 2, n_bins) >= 0.9 * explained(t, g, p_phot, n_bins) and not _persistent_difference(t, g, e, p_phot):
            p_phot /= 2
        else:
            break
    # the orbital period: the photometric one when its fold holds two minima; twice it when the minima of the fold at
    # twice it differ in depth (odd/even); otherwise twice it only for a deep or continuous curve (equal minima assumed)
    doubled = 2 * p_phot <= max(pmax, base / 2)
    c1, m1, er1, n1 = fold_curve(t, g, p_phot, t[0], n_bins)
    m1s = _smooth(_fill(m1), 3)
    i1 = int(np.nanargmin(m1s))
    level1 = float(np.nanpercentile(m1s, 90))
    depth1 = level1 - float(m1s[i1])
    w1 = _width(c1, m1s, i1, level1, depth1)
    berr1 = float(np.nanmedian(er1[n1 > 2])) if (n1 > 2).any() else noise
    j = _min_near(c1, m1s, (c1[i1] + 0.5) % 1.0, 0.5 - max(1.5 * w1, 0.03))
    sec_at_phot = False
    if j is not None:
        d2 = level1 - float(m1s[j])
        sec_at_phot = bool(d2 > max(5 * berr1, 0.1 * depth1) and w1 < 0.3)
    oe = {"sigma": 0.0, "relative": 0.0}
    if doubled and not sec_at_phot:
        t1 = t[0] + c1[i1] * p_phot
        c2, m2, er2, n2 = fold_curve(t, g, 2 * p_phot, t1 - p_phot / 4, n_bins)
        m2s = _smooth(_fill(m2), 3)
        ka, kb = _min_near(c2, m2s, 0.25, 0.1), _min_near(c2, m2s, 0.75, 0.1)
        if ka is not None and kb is not None:
            e2 = float(np.nanmedian(er2[n2 > 2])) if (n2 > 2).any() else noise
            lv = float(np.nanpercentile(m2s, 90))
            da, db = lv - m2s[ka], lv - m2s[kb]
            oe = {"sigma": float(abs(da - db) / (math.sqrt(2) * e2)) if e2 > 0 else 0.0,
                  "relative": float(abs(da - db) / max(da, db, 1e-12))}
            # a binary's odd/even difference is the same all through the data; evolving spots make one that changes:
            # the difference in each half of the data must have the same sign and agree within a factor of two
            mid = np.median(t)
            parts = []
            for sel in (t < mid, t >= mid):
                ch, mh, _, _ = fold_curve(t[sel], g[sel], 2 * p_phot, t1 - p_phot / 4, n_bins)
                mh = _smooth(_fill(mh), 3)
                lh = float(np.nanpercentile(mh, 90))
                parts.append((lh - mh[ka]) - (lh - mh[kb]))
            oe["halves"] = [float(x) for x in parts]
            oe["consistent"] = bool(parts[0] * parts[1] > 0 and 0.5 <= parts[0] / parts[1] <= 2.0)
    odd_even = oe["sigma"] >= 5 and oe["relative"] >= 0.1 and oe.get("consistent", False)
    continuous1 = w1 >= 0.3  # one broad minimum per photometric cycle: a sinusoid-like curve
    equal_minima = False
    if sec_at_phot:
        period, ambiguous, why = p_phot, False, "two minima per photometric cycle"
    elif doubled and odd_even:
        period, ambiguous, why = 2 * p_phot, False, (f"alternate minima differ by {oe['relative']:.0%} "
                                                     f"({oe['sigma']:.0f} sigma): odd/even")
    elif doubled and (depth1 / max(level1, 1e-12) >= 0.05 or continuous1):
        period, ambiguous, why = 2 * p_phot, True, ("one minimum per photometric cycle, deep or continuous: equal minima "
                                                    "assumed (the period may be half this)")
        equal_minima = True
    else:
        period, ambiguous, why = p_phot, True, ("one shallow, narrow minimum per cycle (transit-like): the period is "
                                                "the photometric one (it may be twice this if the minima are equal)")
    hd2 = {"sigma": oe["sigma"], "relative": oe["relative"], "consistent_in_halves": oe.get("consistent")}
    g = _cycle_detrend(t, f, period, base)
    period, ev = _refine_period(t, g, period)
    # the final fold, primary at phase 0, with bins of about three cadences (200 to 1000 per cycle)
    cad = float(np.median(np.diff(t)))
    n_bins = int(np.clip(period / (3 * cad), n_bins, 1000))
    c, m, err, n = fold_curve(t, g, period, t[0], n_bins)
    ms = _smooth(_fill(m), 3)
    i = int(np.nanargmin(ms))
    ph_p = _refine_min(c, ms, i)
    t0 = float(t[0] + ph_p * period)
    t0 += period * np.round((np.median(t) - t0) / period)
    c, m, err, n = fold_curve(t, g, period, t0, n_bins)
    ms = _smooth(_fill(m), 3)
    i = _min_near(c, ms, 0.0, 0.03)
    i = int(np.nanargmin(ms)) if i is None else i
    level = float(np.nanpercentile(ms, 90))
    depth_p = 1 - float(ms[i]) / level
    width_p = _width(c, ms, i, level, level - float(ms[i]))
    berr = float(np.nanmedian(err[n > 2])) if (n > 2).any() else noise
    berr = berr if np.isfinite(berr) and berr > 0 else noise / max(1, math.sqrt(len(t) / n_bins))
    snr_p = (level - float(ms[i])) / berr
    # secondary: the deepest minimum away from the primary
    j = _min_near(c, ms, 0.5, 0.5 - max(1.5 * width_p, 0.03))
    sec = None
    if j is not None:
        d = level - float(ms[j])
        snr_s = d / berr
        phs = _refine_min(c, ms, j)
        if snr_s >= 5 and d > 0:
            ws = _width(c, ms, j, level, d)
            sec = {"phase": phs, "depth": 1 - float(ms[j]) / level, "width_phase": ws, "snr": float(snr_s),
                   "e_cos_omega_hint": float(math.pi / 2 * (phs - 0.5))}
    # out-of-eclipse variation: the 10-90 range of the curve outside both eclipses, relative to the primary depth
    d_p = np.abs((c + 0.5) % 1.0 - 0.5)
    mask = d_p > max(width_p, 0.02)
    if sec:
        d_s = np.abs((c - sec["phase"] + 0.5) % 1.0 - 0.5)
        mask &= d_s > max(sec["width_phase"], 0.02)
    oot = ms[mask] if mask.sum() > 10 else ms
    oot_var = float((np.nanpercentile(oot, 90) - np.nanpercentile(oot, 10)) / max(level - float(ms[i]), 1e-12))
    # stability: the phase curve of each half of the data, compared (spots evolve, a binary's curve does not)
    half = t < np.median(t)
    stab = amp_ratio = None
    if period < base / 3:
        a = _fill(fold_curve(t[half], g[half], period, t0, 50)[1])
        b = _fill(fold_curve(t[~half], g[~half], period, t0, 50)[1])
        if np.isfinite(a).all() and np.isfinite(b).all() and np.std(a) > 0 and np.std(b) > 0:
            stab = float(np.corrcoef(a, b)[0, 1])
            amp_ratio = float(np.std(a) / np.std(b))
    morph = morphology(width_p, sec, oot_var, depth_p)
    reasons = []
    eb = False
    signal = snr_p >= 10 and ev >= 0.2
    # a binary's curve keeps its shape and amplitude; spots change them. Every piece of evidence needs the two
    # halves of the data to agree (correlation 0.9, amplitude within 20%), a continuous variation more (0.95, 15%)
    settled = stab is None or (stab >= 0.9 and amp_ratio is not None and abs(amp_ratio - 1) <= 0.2)
    steady = stab is not None and stab >= 0.95 and amp_ratio is not None and abs(amp_ratio - 1) <= 0.15
    if signal and settled:
        if odd_even and period == 2 * p_phot and not ambiguous and (steady or stab is None):
            reasons.append(f"odd and even minima differ by {hd2['relative']:.0%} ({hd2['sigma']:.0f} sigma)")
        if sec and not equal_minima:
            reasons.append(f"secondary minimum at phase {sec['phase']:.3f} ({sec['snr']:.0f} sigma, depth {sec['depth']:.4f})")
        if depth_p >= 0.05:
            reasons.append(f"primary depth {depth_p:.3f}, deeper than a planet's transit is likely to be")
        if (morph["class"] in ("contact", "ellipsoidal") or equal_minima) and depth_p >= 0.002 and steady and not reasons:
            reasons.append(f"continuous variation ({morph['class']}) with a steady shape and amplitude")
        eb = bool(reasons)
    if equal_minima and sec:
        sec = {**sec, "equal_minima_assumed": True,
               "note": "the period was doubled on the equal-minima assumption, so this minimum is not independent evidence"}
    if not signal:
        reasons.append(f"no coherent periodic signal (primary S/N {snr_p:.1f}, explained variance {ev:.2f})")
    elif not settled:
        reasons.append(f"the phase curve changes between the halves of the data (correlation {stab:.2f}, amplitude "
                       f"ratio {amp_ratio if amp_ratio is None else round(amp_ratio, 2)}); spots, not a binary, are likely")
    elif not eb and equal_minima:
        reasons.append("a continuous variation whose shape or amplitude changes between the halves of the data "
                       f"(correlation {stab if stab is None else round(stab, 2)}, amplitude ratio "
                       f"{amp_ratio if amp_ratio is None else round(amp_ratio, 2)}): spot modulation is as likely as a binary; not flagged")
    elif not eb:
        reasons.append("one eclipse-like dip per cycle, no secondary, shallower than 5%: transit-like, not flagged")
    sigma_p = period * max(width_p, 1 / n_bins) / max(base / period, 1) / max(math.sqrt(max(snr_p, 1)), 1)
    return {"eb_candidate": eb, "reasons": reasons, "period": period, "period_err": float(sigma_p),
            "period_ambiguous": ambiguous, "period_rule": why, "t0_btjd": t0,
            "searches": {"bls": bls, "ls": ls, "photometric_period": p_phot, "odd_even_sigma": hd2["sigma"],
                         "odd_even_relative": hd2["relative"]},
            "explained_variance": ev, "half_stability": stab, "half_amplitude_ratio": amp_ratio,
            "primary": {"phase": 0.0, "depth": depth_p, "width_phase": width_p, "snr": float(snr_p)},
            "secondary": sec, "out_of_eclipse_variation": oot_var, "morphology": morph,
            "phase_curve": {"phase": c.tolist(), "flux": [None if not np.isfinite(x) else float(x) for x in m]}}


def morphology(width_p: float, sec: dict | None, oot_var: float, depth_p: float) -> dict:
    """A heuristic class from the eclipse widths (full width at half depth, phase units) and the out-of-eclipse
    variation (relative to the primary depth): detached eclipses are narrow on a flat curve; a contact or ellipsoidal
    curve varies all the time."""
    ws = sec["width_phase"] if sec else 0.0
    total = width_p + ws
    if width_p >= 0.18 and (sec is None or sec["depth"] >= 0.6 * depth_p) and depth_p < 0.1:
        cls = "ellipsoidal"
    elif width_p >= 0.18:
        cls = "contact"
    elif width_p <= 0.08 and oot_var < 0.15:
        cls = "detached"
    elif sec is None and width_p >= 0.3:
        cls = "reflection-like"
    else:
        cls = "semi-detached"
    return {"class": cls, "primary_width_phase": width_p, "secondary_width_phase": ws, "total_width_phase": total,
            "out_of_eclipse_variation": oot_var,
            "rule": "detached: primary FWHM <= 0.08 in phase on a flat curve (out-of-eclipse range < 0.15 of the depth); "
                    "contact or ellipsoidal: FWHM >= 0.18 (ellipsoidal when the minima are similar and shallower than 10%); "
                    "semi-detached otherwise"}


def vetting_hints(time, flux, period: float, epoch: float, duration_days: float, flux_err=None) -> dict:
    """Binary-star evidence at a transit candidate's ephemeris: odd/even depths, a secondary eclipse at any phase,
    and the ellipsoidal (P/2) and reflection (P) amplitudes. Advisory only; see :data:`VETTING_NOTE`."""
    t, f, e = _clean(time, flux, flux_err)
    flat, _ = flatten(t, f, window=max(1.0, 3 * duration_days))
    ph = np.mod((t - epoch) / period + 0.5, 1.0) - 0.5
    cyc = np.round((t - epoch) / period).astype(int)
    intr = np.abs(ph * period) < duration_days / 2
    noise = diff_sigma(flat)
    def depth(sel):
        k = int(sel.sum())
        return (float(1 - np.mean(flat[sel])), float(noise / math.sqrt(k))) if k else (None, None)
    d_odd, e_odd = depth(intr & (cyc % 2 == 1))
    d_even, e_even = depth(intr & (cyc % 2 == 0))
    oe = abs(d_odd - d_even) / math.hypot(e_odd, e_even) if d_odd is not None and d_even is not None else None
    # secondary at any phase away from the transit, in steps of a tenth of the duration
    best = None
    w = duration_days / period
    for p0 in np.arange(w * 1.5, 1 - w * 1.5, max(w / 10, 0.002)):
        sel = np.abs(((np.mod((t - epoch) / period, 1.0) - p0 + 0.5) % 1.0 - 0.5) * period) < duration_days / 2
        k = int(sel.sum())
        if k < 5:
            continue
        d = float(1 - np.mean(flat[sel]))
        s = d / (noise / math.sqrt(k))
        if best is None or s > best["sigma"]:
            best = {"phase": float(p0), "depth": d, "sigma": float(s)}
    # ellipsoidal (cos 4πφ) and reflection (cos 2πφ) amplitudes on the unflattened curve, transits masked
    out = ~intr
    phi = 2 * np.pi * np.mod((t[out] - epoch) / period, 1.0)
    A = np.vstack([np.ones(out.sum()), np.cos(phi), np.sin(phi), np.cos(2 * phi), np.sin(2 * phi)]).T
    coef, *_ = np.linalg.lstsq(A, f[out], rcond=None)
    resid = f[out] - A @ coef
    s = np.std(resid) / math.sqrt(max(out.sum(), 1)) * math.sqrt(2)
    return {"odd_depth": d_odd, "even_depth": d_even, "odd_even_sigma": oe, "secondary": best,
            "reflection_amplitude": float(-coef[1]), "ellipsoidal_amplitude": float(-coef[3]),
            "amplitude_err": float(s), "note": VETTING_NOTE}


def synthetic_eb(time, period, t0, depth_p, depth_s=0.0, phase_s=0.5, width_phase=0.04, ellipsoidal=0.0):
    """A simple binary model for tests and injections: Gaussian-shaped eclipses of the given depths and full width at
    half depth (phase units), and an optional ellipsoidal term (semi-amplitude at P/2). Relative flux, mean about 1."""
    ph = np.mod((np.asarray(time, float) - t0) / period, 1.0)
    sig = width_phase / 2.3548
    def ecl(centre, d):
        x = (ph - centre + 0.5) % 1.0 - 0.5
        return d * np.exp(-0.5 * (x / sig) ** 2)
    model = 1 - ecl(0.0, depth_p) - ecl(phase_s, depth_s)
    if ellipsoidal:
        model = model - ellipsoidal * np.cos(4 * np.pi * ph)
    return model

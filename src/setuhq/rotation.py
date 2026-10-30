# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Stellar rotation from spot modulation: a Lomb-Scargle periodogram and the autocorrelation function.

:func:`measure` takes one light curve (days, relative flux) and returns:

* **the Lomb-Scargle period** on 30-minute bins, flares and outliers clipped first, with the peak's half width at
  half maximum as its uncertainty;
* **the autocorrelation period** (McQuillan, Aigrain & Mazeh 2013): the ACF of the gap-filled, binned light curve,
  smoothed with a Gaussian, its first peak and that peak's local height, with the period from a line through the
  positions of the peaks when several are seen;
* **half and double handling**: two spot groups on opposite hemispheres put the strongest periodogram peak at half
  the period, and the ACF then shows a lower peak there than at twice it; the period is doubled when the ACF's peak
  near twice the periodogram period is more than 10% higher than its peak near the period, and
  the alias is kept beside it;
* **a detected flag** only when the ACF has a peak within 15% of the period kept (the periodogram's, or twice it by
  the rule above),
  the semi-amplitude (half the 5-95% range) is at least 0.5 ppt and three times the noise of a 30-minute bin, the
  periodogram peak's normalised power is at least 0.1, and, for periods up to a
  quarter of the baseline, each half of the light curve gives the same period within 20%.

**The limit.** One TESS sector is about 27 days with a gap in the middle, and SPOC's PDC can attenuate slow
variability, so periods longer than about 13 days are not measured from one sector: they are reported as beyond
the limit, never as a period. Stitching sectors needs care with sector-to-sector offsets and is not done here.
"""

from __future__ import annotations

import math

import numpy as np

from setuhq.preprocess import diff_sigma, mad_sigma

LIMIT_DAYS = 13.0
LABEL = ("A rotation period is measured from spot modulation in the light curve given; one TESS sector cannot measure "
         "periods longer than about 13 days, and a detected period can be half or double the true one.")
BIN_DAYS = 30 / 1440


def _clean(time, flux):
    t = np.asarray(time, float)
    f = np.asarray(flux, float)
    ok = np.isfinite(t) & np.isfinite(f)
    t, f = t[ok], f[ok]
    o = np.argsort(t)
    t, f = t[o], f[o] / np.median(f[o])
    return t, f


def _binned(t, f, width=BIN_DAYS):
    idx = np.floor((t - t[0]) / width).astype(int)
    n = np.bincount(idx)
    s = np.bincount(idx, f)
    ts = np.bincount(idx, t)
    k = n > 0
    return ts[k] / n[k], s[k] / n[k], n[k]


def clip_flares(t, f, sigma=4.0, window=0.3):
    """Drop upward outliers (flares) and isolated downward ones: points beyond ``sigma`` robust deviations from a
    running median of ``window`` days, and the points right after an upward one."""
    from setuhq.binaries import trend

    r = f - trend(t, f, window, step=10 / 1440)
    s = mad_sigma(r)
    up = r > sigma * s
    after = np.zeros_like(up)
    after[1:] = up[:-1]
    after[2:] |= up[:-2]
    keep = ~(up | after | (r < -2 * sigma * s))
    return t[keep], f[keep]


def lomb_scargle(t, f, pmin, pmax, samples_per_peak=20):
    """The normalised periodogram over periods ``pmin``-``pmax`` days, its best period, half width at half maximum
    (in period), semi-amplitude and the periodogram itself."""
    from astropy.timeseries import LombScargle

    ls = LombScargle(t, f)
    freq, power = ls.autopower(minimum_frequency=1 / pmax, maximum_frequency=1 / pmin, samples_per_peak=samples_per_peak)
    k = int(np.argmax(power))
    half = power[k] / 2
    lo = k
    while lo > 0 and power[lo] > half:
        lo -= 1
    hi = k
    while hi < len(power) - 1 and power[hi] > half:
        hi += 1
    f0 = freq[k]
    hwhm_f = (freq[hi] - freq[lo]) / 2
    amp = float(np.sqrt(np.sum(ls.model_parameters(f0)[1:] ** 2)))
    return {"period": float(1 / f0), "power": float(power[k]), "hwhm": float(hwhm_f / f0 ** 2), "semi_amplitude": amp,
            "edge": bool(k == 0), "freq": freq, "pow": power}


def acf(t, f, max_lag_days, width=BIN_DAYS, smooth_days=None):
    """The autocorrelation function of the binned light curve on a uniform grid (gaps filled with the mean, so they
    add no correlation), smoothed with a Gaussian of ``smooth_days`` (default: 2.5% of the lag range, as McQuillan et
    al. smooth with a kernel tied to the range)."""
    tb, fb, _ = _binned(t, f, width)
    grid = np.arange(tb[0], tb[-1] + width / 2, width)
    idx = np.round((tb - tb[0]) / width).astype(int)
    y = np.zeros(grid.size)
    w = np.zeros(grid.size)
    y[idx] = fb - fb.mean()
    w[idx] = 1.0
    n = grid.size
    nfft = 1 << (2 * n - 1).bit_length()
    fy = np.fft.rfft(y, nfft)
    fw = np.fft.rfft(w, nfft)
    num = np.fft.irfft(fy * np.conj(fy), nfft)[:n]
    den = np.fft.irfft(fw * np.conj(fw), nfft)[:n]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.where(den > 0.25 * den[0], num / den, 0.0)
    r = r / r[0] if r[0] > 0 else r
    m = int(min(n - 1, max_lag_days / width))
    lags = np.arange(m + 1) * width
    r = r[: m + 1]
    sd = smooth_days or max(0.025 * max_lag_days, 2 * width)
    k = np.arange(-int(3 * sd / width), int(3 * sd / width) + 1) * width
    g = np.exp(-0.5 * (k / sd) ** 2)
    g /= g.sum()
    rs = np.convolve(np.concatenate([r[::-1][:-1], r]), g, mode="same")[len(r) - 1:]
    return lags, rs


def acf_period(lags, r):
    """The ACF's peaks and their local heights (the mean height above the two neighbouring minima); the period from the
    first peak, doubled when the second peak is higher than the first (McQuillan et al. 2013)."""
    peaks = [i for i in range(1, len(r) - 1) if r[i] > r[i - 1] and r[i] >= r[i + 1] and r[i] > 0]
    mins = [i for i in range(1, len(r) - 1) if r[i] < r[i - 1] and r[i] <= r[i + 1]]
    rows = []
    for p in peaks:
        left = max([m for m in mins if m < p], default=0)
        right = min([m for m in mins if m > p], default=len(r) - 1)
        lph = r[p] - (r[left] + r[right]) / 2
        rows.append({"lag": float(lags[p]), "height": float(r[p]), "local_height": float(lph)})
    rows = [x for x in rows if x["local_height"] > 0.05]
    if not rows:
        return {"period": None, "peaks": [], "local_height": None}
    first = rows[0]
    period, doubled = first["lag"], False
    if len(rows) > 1 and rows[1]["local_height"] > first["local_height"] and abs(rows[1]["lag"] / first["lag"] - 2) < 0.2:
        period, doubled = rows[1]["lag"], True
    # a line through the peaks at multiples of the period refines it and gives its scatter
    mult = [(round(x["lag"] / period), x["lag"]) for x in rows if abs(x["lag"] / period - round(x["lag"] / period)) < 0.15
            and round(x["lag"] / period) >= 1]
    err = None
    if len(mult) >= 2:
        n, lag = np.array(mult, float).T
        slope = float(np.sum(n * lag) / np.sum(n * n))
        if abs(slope / period - 1) < 0.1:
            period = slope
            err = float(np.std(lag - slope * n) / math.sqrt(len(n)) + 1e-9)
    return {"period": float(period), "peaks": rows[:8], "local_height": float(first["local_height"] if not doubled else rows[1]["local_height"]),
            "doubled": doubled, "err": err}


def _near(a, b, tol=0.1):
    return a is not None and b is not None and abs(a / b - 1) <= tol


def measure(time, flux, *, pmin: float = 0.2, limit: float = LIMIT_DAYS, half_check: bool = True) -> dict:
    """Measure a rotation period (see the module docstring for the rules)."""
    t0, f0 = _clean(time, flux)
    base = float(t0[-1] - t0[0]) if len(t0) > 1 else 0.0
    out = {"label": LABEL, "limit_days": limit, "baseline_days": base, "n_points": int(len(t0))}
    if len(t0) < 100 or base < 4 * pmin:
        return {**out, "detected": False, "period": None, "reasons": ["too few points or too short a baseline"]}
    t, f = clip_flares(t0, f0)
    pmax = float(min(limit, base / 2))
    # the periodogram searches a little past the limit, so a longer period shows as a peak at the edge
    search_max = float(min(base, 2 * limit))
    tb, fb, nb = _binned(t, f)
    ls = lomb_scargle(tb, fb, pmin, search_max)
    # the ACF's smoothing kernel scales with the periodogram's period, so a short period is not smoothed away
    lags, r = acf(t, f, max_lag_days=min(base / 2, search_max),
                  smooth_days=float(np.clip(0.05 * ls["period"], 2 * BIN_DAYS, 0.025 * min(base / 2, search_max))))
    ac = acf_period(lags, r)
    noise_bin = diff_sigma(fb)
    # semi-amplitude: half the 5-95 percentile range of the 30-minute bins smoothed over two hours (cf. McQuillan et
    # al.'s range R_per); the sinusoid's amplitude at the periodogram peak is reported beside it
    k = max(1, int(round(2 / 24 / BIN_DAYS)))
    sm = np.convolve(fb, np.ones(k) / k, mode="valid") if len(fb) > k else fb
    amp = float((np.percentile(sm, 95) - np.percentile(sm, 5)) / 2)
    p_ls, p_ac = ls["period"], ac["period"]
    reasons, alias, rule = [], None, None
    period = None
    # any ACF peak (not only the first) near the periodogram's period, or near twice it
    def peak_near(x):
        c = [q for q in ac["peaks"] if abs(q["lag"] / x - 1) <= 0.15]
        return max(c, key=lambda q: q["height"]) if c else None
    near1, near2 = peak_near(p_ls), peak_near(2 * p_ls)
    if near2 and 2 * p_ls <= search_max and (near1 is None or near2["height"] > 1.1 * near1["height"]):
        period, alias, rule = 2 * p_ls, p_ls, ("the ACF peaks higher at twice the periodogram period than at it (two spot "
                                              "groups): doubled")
        if _near(p_ac, period):
            period = p_ac
    elif near1:
        period, rule = p_ls, "an ACF peak lies within 15% of the periodogram period"
        if near2:
            alias = 2 * p_ls
    sig = None
    if period is not None:
        # the periodogram peak's half width (scaled to the period kept), half the difference between the methods
        # when they agree, and the ACF peaks' scatter
        hw = ls["hwhm"] * (period / p_ls) ** 2
        sig = math.hypot(hw, abs(period - p_ac) / 2 if _near(period, p_ac) else 0.0)
        if ac.get("err"):
            sig = math.hypot(sig, ac["err"])
    detected = True
    if period is None:
        detected = False
        reasons.append(f"the periodogram ({p_ls:.3f} d) and the ACF ({'none' if p_ac is None else f'{p_ac:.3f} d'}) disagree")
    if amp < 5e-4:
        detected = False
        reasons.append(f"semi-amplitude {amp * 1e3:.2f} ppt is below 0.5 ppt")
    if noise_bin and amp < 3 * noise_bin:
        detected = False
        reasons.append(f"semi-amplitude is below three times the 30-minute noise ({noise_bin * 1e3:.2f} ppt)")
    if ls["power"] < 0.1:
        detected = False
        reasons.append(f"the periodogram peak's normalised power {ls['power']:.2f} is below 0.1")
    beyond = (period is not None and period > pmax) or (p_ls > pmax and (p_ac is None or p_ac > pmax * 0.8))
    if beyond:
        detected = False
        reasons.append(f"the signal's period is longer than this light curve can measure (about {pmax:.1f} d here; "
                       f"periods beyond about {limit:g} d are not measured from one TESS sector)")
    halves = None
    if detected and half_check and period is not None and period <= base / 4:
        mid = np.median(t)
        hp = []
        for sel in (t < mid, t >= mid):
            if sel.sum() > 50:
                tb2, fb2, _ = _binned(t[sel], f[sel])
                hp.append(lomb_scargle(tb2, fb2, pmin, min(search_max, (t[sel][-1] - t[sel][0])))["period"])
        halves = hp
        ok = len(hp) == 2 and any(_near(h * m, period, 0.2) for h in hp[:1] for m in (1, 2)) and \
            any(_near(h * m, period, 0.2) for h in hp[1:] for m in (1, 2))
        if not ok:
            detected = False
            reasons.append("the two halves of the light curve do not give the same period within 20%")
    if detected:
        reasons.append(rule)
    return {**out, "detected": bool(detected), "beyond_limit": bool(beyond),
            "period": float(period) if (detected and period) else None,
            "period_err": float(sig) if (detected and sig) else None,
            "candidate_period": float(period) if period else None, "alias": alias, "rule": rule, "reasons": reasons,
            "lomb_scargle": {k: v for k, v in ls.items() if k not in ("freq", "pow")},
            "acf": ac, "semi_amplitude": float(amp), "noise_30min": float(noise_bin), "halves": halves,
            "periodogram": {"period": (1 / ls["freq"][::-1]).tolist()[::max(1, len(ls["freq"]) // 400)],
                            "power": ls["pow"][::-1].tolist()[::max(1, len(ls["freq"]) // 400)]}}


def spot_model(time, period, semi_amplitude, rng, n_spots=None, lifetime_periods=(2.0, 6.0)):
    """Evolving spot modulation for tests and injections: two to four spots, each a cosine-squared bump in the
    rotational phase (visible half the time) whose depth grows and decays as a Gaussian over its lifetime, at
    random longitudes, scaled to the requested semi-amplitude (relative flux, mean about 1)."""
    t = np.asarray(time, float)
    n = int(n_spots or rng.integers(2, 5))
    sig = np.zeros_like(t)
    span = t[-1] - t[0]
    for _ in range(n):
        lon = rng.uniform(0, 2 * np.pi)
        life = rng.uniform(*lifetime_periods) * period
        tc = rng.uniform(t[0] - 0.25 * span, t[-1] + 0.25 * span)
        a = rng.uniform(0.5, 1.0) * np.exp(-0.5 * ((t - tc) / life) ** 2) + 0.3
        ph = 2 * np.pi * (t - t[0]) / period + lon
        sig += a * np.clip(np.cos(ph), 0, None) ** 2
    sig -= sig.mean()
    rng_amp = (np.percentile(sig, 95) - np.percentile(sig, 5)) / 2
    return 1 - sig / max(rng_amp, 1e-12) * semi_amplitude

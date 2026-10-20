"""Cleaning, detrending and binning.

Detrending uses a running median and masks dips before recomputing the trend,
so a transit is not partly absorbed into the baseline. The window must be
several times longer than the longest transit the survey is meant to find.
"""

from __future__ import annotations

import numpy as np

from setuhq.lightcurve import LightCurve


def mad_sigma(values) -> float:
    """Robust standard deviation from the median absolute deviation."""
    values = np.asarray(values, dtype=float)
    if values.size == 0:
        return float("nan")
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def diff_sigma(values) -> float:
    """Point-to-point white-noise estimate, insensitive to any smooth trend.

    A running median is itself a data point on a steep trend, so residuals
    from it can have zero MAD. Differences between neighbours do not have that problem.
    """
    values = np.asarray(values, dtype=float)
    if values.size < 3:
        return float("nan")
    return float(1.4826 * np.median(np.abs(np.diff(values))) / np.sqrt(2.0))


def running_median(time, values, window: float) -> np.ndarray:
    """Median of ``values`` within ``window`` (same units as ``time``) centred on each point."""
    time = np.asarray(time, dtype=float)
    values = np.asarray(values, dtype=float)
    lo = np.searchsorted(time, time - window / 2.0, side="left")
    hi = np.searchsorted(time, time + window / 2.0, side="right")
    return np.array([np.median(values[a:b]) for a, b in zip(lo, hi)])


def low_runs(mask, min_run: int) -> np.ndarray:
    """True where ``mask`` is part of a run of at least ``min_run`` consecutive True values."""
    mask = np.asarray(mask, bool)
    out = np.zeros_like(mask)
    i = 0
    while i < mask.size:
        if mask[i]:
            j = i
            while j < mask.size and mask[j]:
                j += 1
            if j - i >= min_run:
                out[i:j] = True
            i = j
        else:
            i += 1
    return out


def clean(lc: LightCurve, *, high_sigma: float = 5.0, low_sigma: float = 10.0, window_days: float = 0.5,
          dip_sigma: float = 3.0, min_dip_minutes: float = 20.0) -> LightCurve:
    """Drop invalid points and isolated spikes.

    Upward outliers (cosmic rays, momentum dumps) are removed beyond ``high_sigma``.
    Downward outliers beyond ``low_sigma`` are removed only when they are isolated. With hysteresis: such a point is
    kept when it lies in a run of at least L consecutive cadences that are all more than ``dip_sigma`` below the
    running median, with L = max(3, ceil(``min_dip_minutes`` / cadence)): a real transit or eclipse lasts that long,
    and its ingress and egress points below ``low_sigma`` join the run through the lower threshold. Before this guard
    every point of an eclipse deeper than ``low_sigma`` times the point-to-point scatter was removed, so deep
    eclipsing binaries and hot Jupiters on quiet stars never reached the panel.

    The trade-off: a real event deeper than ``low_sigma`` that lasts less than ``min_dip_minutes`` (for example an
    18-minute eclipse at 2-minute cadence, 9 cadences against the 10 required) is still removed as a spike.
    """
    valid = np.isfinite(lc.time) & np.isfinite(lc.flux) & np.isfinite(lc.flux_err) & (lc.flux_err > 0)
    lc = lc.masked(valid, cleaning_window_days=window_days)
    if len(lc) < 3:
        return lc
    residual = lc.flux - running_median(lc.time, lc.flux, window_days)
    scatter = diff_sigma(lc.flux)
    if not np.isfinite(scatter) or scatter <= 0:
        return lc
    cadence_min = float(np.median(np.diff(lc.time))) * 1440.0 if len(lc) > 1 else min_dip_minutes
    min_run = max(3, int(np.ceil(min_dip_minutes / cadence_min - 1e-6))) if cadence_min > 0 else 3
    low = residual < -low_sigma * scatter
    dip = residual < -dip_sigma * scatter
    spikes = (residual > high_sigma * scatter) | (low & ~low_runs(dip, min_run))
    return lc.masked(~spikes, spike_clip_high_sigma=high_sigma, spike_clip_low_sigma=low_sigma,
                     spike_clip_low_min_run=min_run, spike_clip_dip_sigma=dip_sigma)


def local_quadratic(time, flux, keep, window: float, min_points: int = 10) -> tuple[np.ndarray, np.ndarray]:
    """Local quadratic least-squares fit to the kept points, evaluated at every time.

    A running median is biased on curved trends by about window**2 / 24 times the
    second derivative. A local quadratic removes that bias. Sums are cumulative,
    so the cost is linear in the number of points. Returns (fit, ok), where ``ok``
    marks times with enough kept points in their window.
    """
    time = np.asarray(time, dtype=float)
    span = max(time[-1] - time[0], 1e-9)
    x = 2.0 * (time - time[0]) / span - 1.0
    weight = keep.astype(float)
    cumulative = [np.concatenate([[0.0], np.cumsum(weight * x**k)]) for k in range(5)]
    cumulative_flux = [np.concatenate([[0.0], np.cumsum(weight * x**k * flux)]) for k in range(3)]
    lo = np.searchsorted(time, time - window / 2.0, side="left")
    hi = np.searchsorted(time, time + window / 2.0, side="right")
    s = [c[hi] - c[lo] for c in cumulative]
    r = [c[hi] - c[lo] for c in cumulative_flux]
    matrix = np.stack(
        [
            np.stack([s[0], s[1], s[2]], axis=-1),
            np.stack([s[1], s[2], s[3]], axis=-1),
            np.stack([s[2], s[3], s[4]], axis=-1),
        ],
        axis=-2,
    )
    rhs = np.stack(r, axis=-1)
    ok = s[0] >= min_points
    matrix = np.where(ok[:, None, None], matrix, np.eye(3))
    rhs = np.where(ok[:, None], rhs, 0.0)
    coefficients = np.linalg.solve(matrix, rhs[..., None])[..., 0]
    fit = coefficients[:, 0] + coefficients[:, 1] * x + coefficients[:, 2] * x**2
    return fit, ok


def detrend(lc: LightCurve, *, window_days: float = 1.0, mask_sigma: float = 3.0, exclude=None) -> LightCurve:
    """Divide out a smooth trend estimated without the dips.

    A running median finds the first trend and identifies points more than
    ``mask_sigma`` below it. A local quadratic fit to the remaining points then
    gives the final trend, so a transit is not absorbed into the baseline.

    ``exclude`` (a boolean array) leaves further points out of the quadratic fit, and the trend across those points is
    interpolated from the fit on either side: the extended vetting passes the fitted ephemeris's transits, as DV
    does. Without it, the shallow ingress and egress points that are not
    ``mask_sigma`` below the trend pull the fit down near each transit and leave positive shoulders beside it
    (+30 to +60 ppm on pi Men c).
    """
    trend = running_median(lc.time, lc.flux, window_days)
    relative = lc.flux / trend - 1.0
    scatter = diff_sigma(lc.flux / trend)
    keep = relative > -mask_sigma * scatter if np.isfinite(scatter) and scatter > 0 else np.ones(len(lc), bool)
    if exclude is not None:
        keep = keep & ~np.asarray(exclude, bool)
    if keep.sum() >= 10:
        fit, ok = local_quadratic(lc.time, lc.flux, keep, window_days)
        trend = np.where(ok, fit, trend)
    if exclude is not None:
        # Inside an excluded span the quadratic has no support of its own: with a long transit masked (3 T14 of a
        # 1-day window) it extrapolates wildly. The trend there is interpolated linearly between the fitted trend
        # at the nearest kept points on each side (held flat beyond the data's ends).
        ex = np.asarray(exclude, bool)
        support = ~ex & np.isfinite(trend)
        if ex.any() and support.sum() >= 2:
            trend = trend.copy()
            trend[ex] = np.interp(lc.time[ex], lc.time[support], trend[support])
    return lc.with_data(
        lc.time,
        lc.flux / trend,
        lc.flux_err / trend,
        detrend_window_days=window_days,
        detrend_mask_sigma=mask_sigma,
    )


def bin_lightcurve(lc: LightCurve, minutes: float) -> LightCurve:
    """Average points into bins of ``minutes`` width. Errors add in quadrature."""
    if minutes <= 0 or len(lc) == 0:
        return lc
    width = minutes / 1440.0
    index = np.floor((lc.time - lc.time[0]) / width).astype(int)
    counts = np.bincount(index)
    filled = counts > 0
    n = counts[filled]
    time = np.bincount(index, weights=lc.time)[filled] / n
    flux = np.bincount(index, weights=lc.flux)[filled] / n
    flux_err = np.sqrt(np.bincount(index, weights=lc.flux_err**2)[filled]) / n
    return lc.with_data(time, flux, flux_err, bin_minutes=minutes)

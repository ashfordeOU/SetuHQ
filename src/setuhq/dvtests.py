# SPDX-License-Identifier: AGPL-3.0-only
# SPDX-FileCopyrightText: 2026 Ashforde OÜ
"""Extended light-curve vetting after the Kepler and TESS SPOC Data Validation (DV) tests (Twicken et al. 2018,
doi:10.1088/1538-3873/aab694; Jenkins et al. 2016 for SPOC). These tests only add flags by default; the run
config's ``[vetting] decide = true`` turns the disqualifying ones into pass/fail (see :data:`DISQUALIFYING`).

* ``crowded``: the SPOC aperture's CROWDSAP (the fraction of the aperture flux that comes from the target) is below
  0.8, where the HEASARC "Understanding Crowding" page says reliability drops (ATLAS C9). CROWDSAP and FLFRCSAP
  (the fraction of the target's flux inside the aperture) are recorded either way.
* ``secondary_any_phase``: the DV weak-secondary test (ATLAS E3). A box with the transit's duration is slid over
  every phase of the folded light curve, away from the primary, and the most significant dip is reported with its
  phase, depth and significance. The box statistic's nominal σ assumes white noise, and its maximum over the
  phase is a look-elsewhere statistic, so the threshold is calibrated by simulation: the dip is flagged when its
  statistic exceeds q × the robust spread (MAD) of the statistic over all box positions, where q is the 99.9%
  quantile of (largest dip)/(robust spread) on white noise for that number of positions (:data:`SECONDARY_TABLE`,
  from ``scripts/calibrate_secondary.py``; q = 5.16 for 187 positions), and also exceeds the largest brightening at
  any phase (in the spirit of the Robovetter's model-shift uniqueness test, Coughlin et al. 2016,
  doi:10.3847/0067-0049/224/1/12). Measured false-flag rate on clean simulated planets: 2 of 3000 (0.07%, 95% CI
  0.01–0.24%), against 87 of 3000 for the earlier look-elsewhere rule. It must also be
  periodic: covered by two or more epochs, with no single epoch carrying 70% or more of the statistic, so one lone
  dip is never a secondary. When the scan has too few positions for a robust spread (under 20), a fixed 7.1σ is
  used instead, a conventional fallback. The light curve should be detrended with the transits masked
  (:func:`setuhq.pipeline.vetting_lightcurve`): an unmasked trend overshoots beside each transit, and those
  shoulders read as brightenings that veto real secondaries. This replaces the phase-0.5-only check for eccentric
  binaries, whose secondary is not at phase 0.5. The phase-0.5 value is reported beside it.
* ``odd_even_depth``: the DV odd/even depth test (ATLAS E2): every epoch is fitted with the transit shape and a
  local baseline (as DV fits odd and even transits separately), and the depths of odd and of even epochs are
  compared, each with its error, as a difference in σ. The errors are inflated by the
  epochs' own scatter about their parity means and carry a 2% systematic floor. Both parities must show a
  significant dip, as in :func:`setuhq.vet.vet_event`.
* ``odd_even_timing``: the DV odd/even epoch test. Each epoch's mid-time is measured with the fitted transit shape;
  a linear ephemeris with a separate offset for odd epochs is fitted, and the offset is flagged when it is
  significant. A slightly eccentric binary at twice the period shows it. It needs four or more epochs (one spare
  degree of freedom), and its error is inflated by √χ²ᵣ of that fit when it exceeds 1. (Inflating by the plain
  linear fit's χ²ᵣ instead would absorb the very offset being tested: a 15-minute odd/even offset over ten epochs
  was then detected in 0 of 20 simulations, against 20 of 20 with this rule, which flagged 1 of 200 clean
  four-epoch planets.)
* ``timing_inconsistent``: the epochs' mid-times are inconsistent with a linear ephemeris (χ² p-value < 10⁻³).
  Real TTVs do this too, so it is evidence to look at, never a disqualifier.

Noise model. Depth errors use the subject's robust scatter divided by √n, the same model as the SNR check in
:mod:`setuhq.vet`; mid-time errors come from the χ² profile of each epoch, scaled up by √χ²ᵣ when the scatter
exceeds the stated errors. Red noise is not modelled beyond that, so significances on real data are optimistic
for long, shallow events.

DV parity (each SetuHQ test and its DV counterpart, Twicken et al. 2018 §III):

=========================  ===========================================  ==========================================
SetuHQ                     DV test                                       status
=========================  ===========================================  ==========================================
secondary_any_phase        weak secondary test (any phase)               implemented (albedo reported, not a flag)
odd_even_depth             odd/even transit depth comparison              implemented
odd_even_timing            odd/even epoch comparison                      implemented
timing_inconsistent        (no DV test; per-epoch timing)                 implemented, informational
crowded                    PDC crowding (CROWDSAP)                        recorded from the SPOC header
centroid_offset            difference-image centroid offsets              :mod:`setuhq.pixel`
centroid motion            centroid motion test (χ²₂)                     :mod:`setuhq.pixel`
ghost_suspect              optical ghost diagnostic (core vs halo)        :mod:`setuhq.pixel`
FAP (search.py)            statistical bootstrap                          implemented earlier (bounded by trials)
(none)                     rolling-band diagnostic                        not applicable (Kepler detector)
(none)                     shorter/longer period comparison               not implemented (one signal per subject)
=========================  ===========================================  ==========================================
"""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.stats import chi2 as chi2_dist

from setuhq.preprocess import mad_sigma

CROWDING_MIN = 0.8        # CROWDSAP below this: "reliability drops" (HEASARC Understanding Crowding, ATLAS C9)
SECONDARY_SIGMA = 7.1     # fallback weak-secondary threshold (a conventional value) when the scan is too small
# White-noise calibration of the all-phase secondary scan (scripts/calibrate_secondary.py, 20,000 scans per row at
# 2- and 10-minute cadence, the larger kept): (coarse positions, 99.9% quantile of largest dip / robust spread,
# 99.9% quantile of largest |excursion| / robust spread, effective number of independent positions).
SECONDARY_TABLE = (
    (25, 6.73, 6.91, 42),
    (41, 6.24, 6.34, 73),
    (73, 5.63, 5.80, 142),
    (121, 5.53, 5.53, 279),
    (193, 5.13, 5.32, 486),
    (313, 5.04, 5.13, 782),
    (409, 5.06, 5.09, 1048),
)


CALIBRATION_FILE = Path(__file__).resolve().parents[2] / "docs" / "results" / "secondary_calibration.json"


@lru_cache(maxsize=1)
def _null_tables():
    data = json.loads(CALIBRATION_FILE.read_text())
    z = np.array(data["z_grid"], float)
    rows = sorted((r["positions"], np.array(r["null_cdf"], float), r["null_tail"]) for r in data["table"])
    return z, np.array([r[0] for r in rows], float), np.array([r[1] for r in rows]), [r[2] for r in rows]


def _row_cdf(z: float, grid, cdf, tail: dict) -> tuple[float, float]:
    """(CDF, density) of one row: empirical up to the tail threshold u, the fitted generalized Pareto tail beyond."""
    u, pu, xi, sg = tail["u"], tail["p_u"], tail["xi"], tail["sigma"]
    if z >= u:
        base = 1.0 + xi * (z - u) / sg
        if base <= 0:      # beyond a bounded tail's end (ξ < 0)
            return 1.0, 0.0
        surv = pu * base ** (-1.0 / xi) if abs(xi) > 1e-9 else pu * math.exp(-(z - u) / sg)
        dens = pu / sg * base ** (-1.0 / xi - 1.0) if abs(xi) > 1e-9 else surv / sg
        return 1.0 - surv, dens
    # Below u: the empirical CDF, rescaled so it meets the tail at u exactly (the stored CDF is rounded and
    # tabulated at a 0.05 step), and its density as a centred difference over ±0.1 that does not cross u.
    at_u = float(np.interp(u, grid, cdf))
    scale = (1.0 - pu) / at_u if at_u > 0 else 1.0
    f = lambda x: float(np.interp(x, grid, cdf, left=0.0)) * scale  # noqa: E731
    lo, hi = z - 0.1, min(z + 0.1, u)
    return f(z), (f(hi) - f(lo)) / (hi - lo)


def _null(z: float, positions: int) -> tuple[float, float]:
    grid, pos, cdfs, tails = _null_tables()
    rows = [_row_cdf(z, grid, c, t) for c, t in zip(cdfs, tails)]
    x = math.log(max(positions, 2))
    cdf = float(np.interp(x, np.log(pos), [r[0] for r in rows]))
    pdf = float(np.interp(x, np.log(pos), [r[1] for r in rows]))
    return min(max(cdf, 0.0), 1.0), pdf


def null_cdf(z: float, positions: int) -> float:
    """The simulated white-noise CDF of (largest dip)/(robust spread) for a scan with ``positions`` coarse positions
    (``null_cdf`` in docs/results/secondary_calibration.json, 40,000 scans per row): empirical up to the row's 99th
    percentile, and above it the peaks-over-threshold tail fitted there (``null_tail``: a generalized Pareto with
    ξ = 0, i.e. exponential), so the far tail, where fewer than 40 simulated scans lie beyond z = 5.1, is smooth. Interpolated in log(positions), clamped at the ends."""
    return _null(z, positions)[0]


def null_pdf(z: float, positions: int) -> float:
    """The matching density: the fitted tail's own density above the 99th percentile (smooth and decreasing), a
    centred difference of the empirical CDF below it; floored at 1e-300."""
    return max(_null(z, positions)[1], 1e-300)


def white_quantiles(positions: int) -> dict:
    """The white-noise 99.9% quantiles (``q_dip``, ``q_abs``) and N_eff for a scan with ``positions`` coarse box
    positions, interpolated in log(positions) in :data:`SECONDARY_TABLE` and extended linearly beyond its ends."""
    n = np.array([r[0] for r in SECONDARY_TABLE], float)
    x = math.log(max(positions, 2))
    out = {}
    for key, col in (("q_dip", 1), ("q_abs", 2)):
        y = np.array([r[col] for r in SECONDARY_TABLE], float)
        if x <= math.log(n[0]):
            i = 0
        elif x >= math.log(n[-1]):
            i = len(n) - 2
        else:
            i = int(np.searchsorted(np.log(n), x)) - 1
        x0, x1 = math.log(n[i]), math.log(n[i + 1])
        out[key] = float(y[i] + (y[i + 1] - y[i]) * (x - x0) / (x1 - x0))
    ratio = np.array([r[3] / r[0] for r in SECONDARY_TABLE], float)
    out["n_eff"] = float(positions * np.interp(x, np.log(n), ratio))
    return out
SECONDARY_MAX_EPOCH_SHARE = 0.7  # no single epoch may carry this share of the secondary's statistic
MIN_SCAN_POSITIONS = 20   # fewer box positions than this: no robust spread, use SECONDARY_SIGMA
SIGMA_THRESHOLD = 3.0     # odd/even depth and timing; ~3σ is common practice (ATLAS E2 FLAG: no universal value)
TIMING_P = 1e-3           # p-value below which the epochs are called inconsistent with a linear ephemeris
MIN_PARITY_SNR = 5.0      # each parity must show a dip this significant, as in vet.vet_event
# Flags that become disqualifying with ``[vetting] decide = true``. Crowding and timing are informational.
DISQUALIFYING = frozenset({"secondary_any_phase", "odd_even_depth", "odd_even_timing"})


def _num(value) -> float | None:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def crowding(provenance: dict | None, *, minimum: float = CROWDING_MIN) -> dict:
    """CROWDSAP and FLFRCSAP from a light curve's provenance (:func:`setuhq.loaders.load_tess` records them from the
    SPOC header), and whether the aperture is crowded. ``crowded`` is None when CROWDSAP is not known."""
    provenance = provenance or {}
    crowdsap = _num(provenance.get("crowdsap"))
    flfrcsap = _num(provenance.get("flfrcsap"))
    return {"crowdsap": crowdsap, "flfrcsap": flfrcsap, "crowding_min": minimum,
            "crowded": None if crowdsap is None else bool(crowdsap < minimum)}


def _phase(time, period: float, t0: float) -> np.ndarray:
    """Orbital phase in [0, 1), with the primary transit at 0."""
    return np.mod((np.asarray(time, float) - t0) / period, 1.0)


def _box_sums(phase_sorted, flux_cum, centres, half_phase):
    """Count and flux sum of the points within ``half_phase`` (circular) of each centre, by prefix sums over the
    phase-sorted data tripled to [−1, 2) so a box can wrap."""
    lo = np.searchsorted(phase_sorted, centres - half_phase, side="left")
    hi = np.searchsorted(phase_sorted, centres + half_phase, side="right")
    return hi - lo, flux_cum[hi] - flux_cum[lo]


def secondary_search(time, flux, *, period: float, t0: float, duration: float, step: float | None = None,
                     noise: float | None = None, min_points: int = 3, exclude: float | None = None) -> dict | None:
    """The most significant box dip of width ``duration`` at any phase away from the primary transit.

    Box centres run over the phase with a step of a quarter duration (``step``, days), then the peak is refined in
    steps of a fortieth of a duration. A centre is excluded when it lies within ``exclude`` days of phase 0 (default:
    one duration, so the box clears the primary). The baseline is the median flux outside the excluded zone; the
    depth at a centre is the baseline minus the mean flux in the box, and its σ is the robust scatter over √n.
    Returns the peak's phase, depth (ppm), σ (ppm) and significance; the largest brightening's significance (the same
    statistic with the sign reversed); the scan statistic's median, robust spread (MAD) and plain standard
    deviation over the coarse positions; the value at phase 0.5; and the number of coarse positions.
    None when the period or the data cannot support the search.
    """
    time = np.asarray(time, float)
    flux = np.asarray(flux, float)
    good = np.isfinite(time) & np.isfinite(flux)
    time, flux = time[good], flux[good]
    exclude = duration if exclude is None else max(exclude, duration)
    if period is None or period <= 0 or duration <= 0 or exclude >= 0.5 * period or time.size < 10:
        return None
    phase = _phase(time, period, t0)
    dist0 = np.minimum(phase, 1.0 - phase) * period          # days from the nearest primary mid-time
    outside = dist0 > exclude
    if outside.sum() < 10:
        return None
    noise = mad_sigma(flux[outside] - 1.0) if noise is None else noise
    if not np.isfinite(noise) or noise <= 0:
        return None
    baseline = float(np.median(flux[outside]))
    order = np.argsort(phase)
    ph = phase[order]
    fl = flux[order]
    ph3 = np.concatenate([ph - 1.0, ph, ph + 1.0])
    cum = np.concatenate([[0.0], np.cumsum(np.concatenate([fl, fl, fl]))])
    step = 0.25 * duration if step is None else step
    half = 0.5 * duration / period
    centres = np.arange(exclude / period, 1.0 - exclude / period + 1e-12, step / period)
    n, s = _box_sums(ph3, cum, centres, half)
    ok = n >= min_points
    if not ok.any():
        return None
    centres, n, s = centres[ok], n[ok], s[ok]
    depth = baseline - s / n
    sigma = noise / np.sqrt(n)
    snr = depth / sigma
    i = int(np.argmax(snr))
    j = int(np.argmin(snr))
    c, d_best, sg_best, n_best = float(centres[i]), float(depth[i]), float(sigma[i]), int(n[i])
    # The grid can miss the true centre by up to half a step, which biases the depth low: refine around the peak
    fine = np.arange(c - step / period, c + step / period + 1e-12, duration / 40.0 / period) % 1.0
    fine = fine[np.minimum(fine, 1.0 - fine) * period >= exclude]
    if fine.size:
        fn, fs = _box_sums(ph3, cum, fine, half)
        keep = fn >= min_points
        if keep.any():
            fd = baseline - fs[keep] / fn[keep]
            fsg = noise / np.sqrt(fn[keep])
            k = int(np.argmax(fd / fsg))
            if fd[k] / fsg[k] > d_best / sg_best:
                c, d_best, sg_best, n_best = float(fine[keep][k]), float(fd[k]), float(fsg[k]), int(fn[keep][k])
    near = int(np.argmin(np.abs(centres - 0.5)))
    # How the peak's statistic is spread over epochs: each epoch's share of Σ (baseline − flux) in the box
    dd = np.abs(phase - c)
    inside = np.minimum(dd, 1.0 - dd) * period <= 0.5 * duration
    cycle = np.round((time[inside] - t0) / period - c).astype(int)
    drop = baseline - flux[inside]
    total = float(drop.sum())
    shares = {int(k): (float(drop[cycle == k].sum() / total) if total > 0 else 0.0) for k in np.unique(cycle)}
    robust = mad_sigma(snr) if snr.size >= MIN_SCAN_POSITIONS else None
    # The plain std of the scan (a noise model of the reduced FPP, and the white-noise gate's std/robust) leaves out
    # the positions within one duration of the strongest dip: a real secondary inflated it (std/robust 1.3-1.7 on
    # simulated binaries), so the "std" noise model diluted the very dip it was judging and refused the FPP of
    # obvious binaries as unstable. On white noise this changes the std by about 1%.
    gap = np.abs(centres - c)
    away = np.minimum(gap, 1.0 - gap) * period > duration
    std_snr = float(np.std(snr[away])) if away.sum() >= MIN_SCAN_POSITIONS else float(np.std(snr))
    return {
        "phase": c, "depth_ppm": d_best * 1e6, "sigma_ppm": sg_best * 1e6, "snr": d_best / sg_best, "n_points": n_best,
        "max_brightening_snr": float(-snr[j]), "n_trials": int(snr.size), "duration_days": duration,
        "excluded_days": exclude,
        "scan_median_snr": float(np.median(snr)), "scan_robust_sigma": robust, "scan_std_snr": std_snr,
        "n_epochs": len(shares), "max_epoch_share": max(shares.values()) if shares else None,
        "phase_05": {"phase": float(centres[near]), "depth_ppm": float(depth[near]) * 1e6,
                     "sigma_ppm": float(sigma[near]) * 1e6, "snr": float(snr[near])},
    }


def assess_secondary(sec: dict, *, secondary_sigma: float = SECONDARY_SIGMA) -> dict:
    """Decide whether a :func:`secondary_search` result is a significant secondary (adds ``threshold_sigma``,
    ``threshold_rule``, ``periodic`` and ``significant`` to it). The threshold is the white-noise 99.9% quantile
    of (largest dip)/(robust spread) for the scan's number of positions (:func:`white_quantiles`), times its robust
    spread; the dip must also exceed the largest brightening and be periodic (two or more epochs, none carrying
    70% or more). ``secondary_sigma`` is the fixed fallback for scans too short for a robust spread."""
    if sec["scan_robust_sigma"] is not None:
        z = white_quantiles(sec["n_trials"])["q_dip"]
        # The spread can only raise the threshold: a spread below white noise (detrending suppresses noise on the
        # box's time-scale) never lowers it under the white-noise calibration.
        threshold = z * max(sec["scan_robust_sigma"], 1.0)
        sec["threshold_rule"] = (f"{z:.2f} × max(1, the scan's robust spread) (white-noise 99.9% quantile for "
                                 f"{sec['n_trials']} positions)")
    else:
        threshold = secondary_sigma
        sec["threshold_rule"] = f"fixed {secondary_sigma:g}σ fallback (fewer than {MIN_SCAN_POSITIONS} positions)"
    sec["threshold_sigma"] = threshold
    sec["periodic"] = bool(sec["n_epochs"] >= 2 and (sec["max_epoch_share"] or 1.0) < SECONDARY_MAX_EPOCH_SHARE)
    sec["significant"] = bool(sec["snr"] > max(threshold, sec["max_brightening_snr"]) and sec["periodic"])
    return sec


def implied_albedo(secondary_depth: float, k: float | None, a_rs: float | None) -> float | None:
    """Geometric albedo a secondary of fractional depth ``secondary_depth`` implies if it is reflected light:
    δ_sec = A_g (k / (a/R★))², so A_g = δ_sec (a/R★)² / k² (ATLAS C5). Above 1 it cannot be reflection alone
    (thermal emission adds to it, so this is evidence, not proof)."""
    if not k or not a_rs or k <= 0 or not math.isfinite(a_rs):
        return None
    return float(secondary_depth * a_rs ** 2 / k ** 2)


def epoch_depths(time, flux, *, period: float, t0: float, duration: float, noise: float | None = None,
                 min_points: int = 2) -> list[dict]:
    """Box depth (fractional) and σ at every epoch ``t0 + n P`` covered by the data, with n and its parity."""
    time = np.asarray(time, float)
    flux = np.asarray(flux, float)
    if period is None or period <= 0 or time.size == 0:
        return []
    noise = mad_sigma(flux - 1.0) if noise is None else noise
    half = 0.5 * duration
    out = []
    for n in range(int(np.ceil((time.min() - t0) / period)), int(np.floor((time.max() - t0) / period)) + 1):
        mid = t0 + n * period
        inside = np.abs(time - mid) <= half
        k = int(inside.sum())
        if k < min_points:
            continue
        out.append({"epoch": n, "parity": "odd" if n % 2 else "even", "t_mid": float(mid), "n_points": k,
                    "depth": float(1.0 - np.mean(flux[inside])), "sigma": float(noise / math.sqrt(k))})
    return out


ODD_EVEN_FLOOR = 0.02      # systematic floor on each parity's depth error, as a fraction of its depth


def parity_scatter_scale(depths, sigmas, parities) -> tuple[float, float, int]:
    """√χ²ᵣ (at least 1) of per-epoch depths about their own parity's weighted mean, with χ² and its degrees of
    freedom. Box depths over a fixed window scatter more than their white-noise errors (where the bins fall on
    ingress and egress changes from epoch to epoch, and a small period error shifts the window), so the parity
    errors are inflated by it."""
    d = np.asarray(depths, float)
    s = np.asarray(sigmas, float)
    par = np.asarray(parities)
    chi, used = 0.0, 0
    for p in np.unique(par):
        m = par == p
        w = 1.0 / s[m] ** 2
        mean = np.sum(w * d[m]) / np.sum(w)
        chi += float(np.sum(w * (d[m] - mean) ** 2))
        used += 1
    dof = int(d.size - used)
    return (math.sqrt(max(1.0, chi / dof)) if dof > 0 else 1.0), chi, dof


def odd_even_depth_test(epochs: list[dict], *, sigma_threshold: float = SIGMA_THRESHOLD,
                        min_parity_snr: float = MIN_PARITY_SNR, floor: float = ODD_EVEN_FLOOR) -> dict | None:
    """Inverse-variance mean depth of odd and of even epochs with errors, and their difference in σ.

    Each parity's error is inflated by √χ²ᵣ of the per-epoch depths about their parity means
    (:func:`parity_scatter_scale`) and given a systematic floor of ``floor`` × its depth (2%): on a clean 1% hot
    Jupiter the white-noise errors alone made the box depths of odd and even epochs differ by many σ.
    ``significant`` needs both parities to show a dip of at least ``min_parity_snr`` (one lone transit cannot fake
    a mismatch) and |δ_odd − δ_even| > ``sigma_threshold`` × √(σ_odd² + σ_even²). None without both parities.
    """
    rows = [e for e in epochs if e["sigma"] > 0]
    groups = {}
    for parity in ("odd", "even"):
        mine = [e for e in rows if e["parity"] == parity]
        if not mine:
            return None
        w = np.array([1.0 / e["sigma"] ** 2 for e in mine])
        d = np.array([e["depth"] for e in mine])
        groups[parity] = (float(np.sum(w * d) / np.sum(w)), float(1.0 / math.sqrt(np.sum(w))), len(mine))
    scale, chi, dof = parity_scatter_scale([e["depth"] for e in rows], [e["sigma"] for e in rows],
                                           [e["parity"] for e in rows])
    (do, so, no), (de, se, ne) = groups["odd"], groups["even"]
    snr_odd, snr_even = do / so, de / se                       # detection of each parity, before inflation
    so = math.hypot(so * scale, floor * abs(do))
    se = math.hypot(se * scale, floor * abs(de))
    combined = math.hypot(so, se)
    delta_sigma = abs(do - de) / combined if combined > 0 else 0.0
    both = min(snr_odd, snr_even) >= min_parity_snr
    return {"odd_depth_ppm": do * 1e6, "odd_err_ppm": so * 1e6, "n_odd": no,
            "even_depth_ppm": de * 1e6, "even_err_ppm": se * 1e6, "n_even": ne,
            "error_scale": scale, "epoch_chi2": chi, "epoch_dof": dof, "floor_fraction": floor,
            "delta_sigma": delta_sigma, "both_parities_detected": bool(both),
            "significant": bool(both and delta_sigma > sigma_threshold)}


def trapezoid(dt, duration: float, ingress_fraction: float = 0.1) -> np.ndarray:
    """A unit-depth trapezoid profile (1 at the bottom, 0 outside) of total duration ``duration``."""
    dt = np.abs(np.asarray(dt, float))
    half = 0.5 * duration
    tau = max(ingress_fraction * duration, 1e-9)
    return np.clip((half - dt) / tau, 0.0, 1.0)


def shape_template(fit: dict | None, duration: float):
    """The unit-depth transit profile used to time each epoch: the fitted limb-darkened model when the fit is
    given (its k, b, T14, period and limb darkening), otherwise a trapezoid with a tenth of the duration in
    ingress. Returns a function of time from mid-transit."""
    if fit and fit.get("k") and fit.get("t14_hours") and fit.get("period_days"):
        from setuhq.transitfit import transit_model

        k, b, t14, p = float(fit["k"]), float(fit.get("b") or 0.0), float(fit["t14_hours"]) / 24.0, float(fit["period_days"])
        u1, u2 = float(fit.get("u1") or 0.4), float(fit.get("u2") or 0.25)
        centre = 1.0 - float(transit_model(np.array([0.0]), 0.0, k, t14, b, p, u1, u2)[0])
        if centre > 0:
            return lambda dt: (1.0 - transit_model(np.asarray(dt, float), 0.0, k, t14, b, p, u1, u2)) / centre
    return lambda dt: trapezoid(dt, duration)


def epoch_times(time, flux, flux_err, *, period: float, t0: float, duration: float, template=None,
                window: float = 1.5, min_side: int = 2) -> list[dict]:
    """Mid-time and 1σ error of every covered epoch, from a χ² scan of the shape template's shift.

    At each trial shift the template's depth and a constant baseline are fitted linearly (weighted least
    squares); the χ² minimum is refined with a parabola, and σ is where χ² rises by 1, scaled by √χ²ᵣ when
    χ²ᵣ > 1. An epoch needs ``min_side`` points before ingress, inside, and after egress within ``window``
    durations of the predicted mid-time; one whose best depth is not positive is skipped.
    """
    time = np.asarray(time, float)
    flux = np.asarray(flux, float)
    flux_err = np.asarray(flux_err, float)
    if period is None or period <= 0 or time.size == 0:
        return []
    template = template or (lambda dt: trapezoid(dt, duration))
    half = 0.5 * duration
    cadence = float(np.median(np.diff(np.sort(time)))) if time.size > 1 else duration / 20
    step = min(cadence / 4.0, duration / 200.0)
    shifts = np.arange(-half, half + 0.5 * step, step)
    out = []
    for n in range(int(np.ceil((time.min() - t0) / period)), int(np.floor((time.max() - t0) / period)) + 1):
        mid = t0 + n * period
        sel = np.abs(time - mid) <= window * duration
        t, f, e = time[sel], flux[sel], flux_err[sel]
        ok = np.isfinite(f) & np.isfinite(e) & (e > 0)
        t, f, e = t[ok], f[ok], e[ok]
        if (np.sum(t < mid - half) < min_side or np.sum(t > mid + half) < min_side
                or np.sum(np.abs(t - mid) <= half) < min_side):
            continue
        w = 1.0 / e ** 2
        chi = np.empty(shifts.size)
        amp = np.empty(shifts.size)
        for i, s in enumerate(shifts):
            m = template(t - mid - s)
            # flux = c - a m : weighted normal equations for (c, a)
            sw, sm, smm = w.sum(), (w * m).sum(), (w * m * m).sum()
            sf, sfm = (w * f).sum(), (w * f * m).sum()
            det = sw * smm - sm * sm
            if det <= 0:
                chi[i], amp[i] = np.inf, 0.0
                continue
            c = (sf * smm - sfm * sm) / det
            a = (sf * sm - sfm * sw) / det
            chi[i] = float((w * (f - c + a * m) ** 2).sum())
            amp[i] = a
        i = int(np.argmin(chi))
        if not np.isfinite(chi[i]) or amp[i] <= 0:
            continue
        best = shifts[i]
        if 0 < i < shifts.size - 1 and np.all(np.isfinite(chi[i - 1:i + 2])):
            y0, y1, y2 = chi[i - 1], chi[i], chi[i + 1]
            curv = (y0 - 2 * y1 + y2) / step ** 2
            if curv > 0:
                best = shifts[i] + 0.5 * step * (y0 - y2) / (y0 - 2 * y1 + y2)
        # σ from the χ² profile: the mean half-width where χ² first rises by 1 on each side of the minimum,
        # interpolated linearly between scan points
        level = chi[i] + 1.0

        def crossing(idx):
            for a, b in zip(idx, idx[1:]):
                if chi[b] > level >= chi[a]:
                    return shifts[a] + (shifts[b] - shifts[a]) * (level - chi[a]) / (chi[b] - chi[a])
            return None

        left, right = crossing(list(range(i, -1, -1))), crossing(list(range(i, shifts.size)))
        edge = left is None or right is None
        sig = 0.5 * ((best - (left if left is not None else shifts[0])) + ((right if right is not None else shifts[-1]) - best))
        sig = max(sig, 0.5 * step)
        dof = max(t.size - 3, 1)
        scale = math.sqrt(max(1.0, chi[i] / dof))
        # the amplitude's error at the best shift, from the 2 x 2 normal equations of (baseline, amplitude)
        m = template(t - mid - shifts[i])
        sw, sm, smm = w.sum(), (w * m).sum(), (w * m * m).sum()
        det = sw * smm - sm * sm
        amp_err = math.sqrt(sw / det) * scale if det > 0 else float("nan")
        out.append({"epoch": n, "parity": "odd" if n % 2 else "even", "t_predicted": float(mid),
                    "t_mid": float(mid + best), "sigma": float(sig * scale), "depth": float(amp[i]),
                    "depth_err": float(amp_err), "chi2_red": float(chi[i] / dof), "n_points": int(t.size),
                    "at_scan_edge": bool(edge)})
    return out


def _wls(design: np.ndarray, y: np.ndarray, sigma: np.ndarray):
    w = 1.0 / sigma ** 2
    a = design.T @ (design * w[:, None])
    cov = np.linalg.inv(a)
    beta = cov @ (design.T @ (w * y))
    chi = float(np.sum(w * (y - design @ beta) ** 2))
    return beta, cov, chi


MIN_EPOCH_SNR = 3.0   # an epoch's fitted depth must reach this many σ for its mid-time to enter the timing tests


def _epoch_snr(e: dict) -> float | None:
    err = e.get("depth_err")
    if err is None or not math.isfinite(err) or err <= 0:
        return None
    return float(e["depth"] / err)


def timing_test(epochs: list[dict], *, sigma_threshold: float = SIGMA_THRESHOLD, timing_p: float = TIMING_P) -> dict:
    """Linear-ephemeris consistency and the odd/even epoch offset from per-epoch mid-times (:func:`epoch_times`).

    * Linear: T_n = T0 + n P by weighted least squares, χ² with N − 2 degrees of freedom and its p-value
      (needs 3 or more epochs). ``inconsistent`` when p < ``timing_p``.
    * Odd/even: T_n = T0 + n P + Δ·[n odd]; Δ and σ_Δ from the fit's covariance, inflated by √χ²ᵣ of that fit
      when it exceeds 1 (needs 4 or more epochs with both parities, so the fit has a spare degree of freedom).
      ``significant`` when |Δ|/σ_Δ > ``sigma_threshold``.

    Epochs whose fitted depth is below :data:`MIN_EPOCH_SNR` σ are left out (``skipped_epochs``); when they are all
    of one parity and every kept epoch is of the other, ``period_alias_note`` says the period may be half the true one.
    """
    usable = [e for e in epochs if e["sigma"] > 0 and not e.get("at_scan_edge")]
    # An epoch without a significant dip has no mid-time to measure: the fit wanders to the deepest noise dip in the
    # window (on a P/2 alias, every other epoch is empty; O−C of 67 minutes on a 50 ppm "dip" flagged a clean
    # 600 ppm planet timing_inconsistent). Such epochs are left out, and when they are all of one parity while the
    # other parity has dips, that is reported as a possible period alias instead.
    rows = [e for e in usable if _epoch_snr(e) is None or _epoch_snr(e) >= MIN_EPOCH_SNR]
    skipped = [e for e in epochs if _epoch_snr(e) is not None and _epoch_snr(e) < MIN_EPOCH_SNR]
    out: dict = {"n_epochs": len(rows), "o_minus_c_minutes": None, "linear": None, "odd_even": None,
                 "skipped_epochs": [{"epoch": e["epoch"], "depth_snr": _epoch_snr(e)} for e in skipped]}
    if skipped and rows and len({e["parity"] for e in skipped}) == 1 and \
            all(e["parity"] != skipped[0]["parity"] for e in rows):
        out["period_alias_note"] = (f"every {skipped[0]['parity']} epoch ({len(skipped)}) shows no dip of "
                                    f"{MIN_EPOCH_SNR:g}σ or more: the period may be half the true one")
    if len(rows) < 2:
        return out
    n = np.array([e["epoch"] for e in rows], float)
    t = np.array([e["t_mid"] for e in rows], float)
    s = np.array([e["sigma"] for e in rows], float)
    if len(rows) >= 3:
        beta, cov, chi = _wls(np.column_stack([np.ones_like(n), n]), t, s)
        dof = len(rows) - 2
        p = float(chi2_dist.sf(chi, dof))
        out["o_minus_c_minutes"] = [float(x) for x in (t - (beta[0] + beta[1] * n)) * 1440.0]
        out["linear"] = {"t0": float(beta[0]), "period": float(beta[1]), "period_err": float(math.sqrt(cov[1, 1])),
                         "chi2": chi, "dof": dof, "p_value": p, "inconsistent": bool(p < timing_p)}
        odd = (n % 2 == 1).astype(float)
        # Δ needs a spare degree of freedom beyond (T0, P, Δ): four or more epochs, with both parities
        if len(rows) >= 4 and 0 < odd.sum() < len(rows):
            beta, cov, chi = _wls(np.column_stack([np.ones_like(n), n, odd]), t, s)
            scale = math.sqrt(max(1.0, chi / (len(rows) - 3)))
            delta, err = float(beta[2]), float(math.sqrt(cov[2, 2]) * scale)
            out["odd_even"] = {"offset_minutes": delta * 1440.0, "offset_err_minutes": err * 1440.0,
                               "delta_sigma": abs(delta) / err if err > 0 else 0.0,
                               "significant": bool(err > 0 and abs(delta) / err > sigma_threshold)}
    return out


def extended_vet(time, flux, flux_err, *, period: float | None, t0: float | None, duration: float | None,
                 fit: dict | None = None, provenance: dict | None = None, crowding_min: float = CROWDING_MIN,
                 secondary_sigma: float = SECONDARY_SIGMA, sigma_threshold: float = SIGMA_THRESHOLD,
                 timing_p: float = TIMING_P) -> tuple[tuple[str, ...], dict]:
    """All the light-curve DV tests for one signal. Returns (flags, metrics).

    ``period``, ``t0`` and ``duration`` (days) are the fitted ephemeris and T14 when a fit is available, otherwise
    the search's; the caller says which in ``metrics["ephemeris_source"]``. Without a period, only crowding is
    tested. Never changes a pass/fail decision itself.
    """
    flags: list[str] = []
    metrics: dict = {"crowding": crowding(provenance, minimum=crowding_min)}
    if metrics["crowding"]["crowded"]:
        flags.append("crowded")
    if not period or not duration or t0 is None:
        return tuple(flags), metrics
    time = np.asarray(time, float)
    flux = np.asarray(flux, float)
    flux_err = np.asarray(flux_err, float)
    noise = mad_sigma(flux - 1.0)
    sec = secondary_search(time, flux, period=period, t0=t0, duration=duration, noise=noise)
    if sec is not None:
        fit = fit or {}
        a_rs = fit.get("a_rs")
        sec["albedo"] = implied_albedo(max(sec["depth_ppm"], 0.0) * 1e-6, fit.get("k"), a_rs)
        assess_secondary(sec, secondary_sigma=secondary_sigma)
        if sec["significant"]:
            flags.append("secondary_any_phase")
    metrics["secondary"] = sec
    times = epoch_times(time, flux, flux_err, period=period, t0=t0, duration=duration,
                        template=shape_template(fit, duration))
    # Odd/even depths from each epoch's own fit (the transit shape plus a local baseline), as DV fits odd and even
    # transits separately; box depths over a fixed window against a global baseline of 1 pick up detrending offsets
    # near gaps and sector edges. Box depths are the fallback when fewer than one fitted epoch per parity exists.
    fitted = [{"epoch": e["epoch"], "parity": e["parity"], "depth": e["depth"], "sigma": e["depth_err"]}
              for e in times if math.isfinite(e.get("depth_err", float("nan"))) and e["depth_err"] > 0]
    oe = odd_even_depth_test(fitted, sigma_threshold=sigma_threshold)
    if oe is not None:
        oe["source"] = "per-epoch fits (transit shape plus a local baseline)"
    else:
        oe = odd_even_depth_test(epoch_depths(time, flux, period=period, t0=t0, duration=duration, noise=noise),
                                 sigma_threshold=sigma_threshold)
        if oe is not None:
            oe["source"] = "box depths over T14 (fallback)"
    metrics["odd_even_depth"] = oe
    if oe and oe["significant"]:
        flags.append("odd_even_depth")
    timing = timing_test(times, sigma_threshold=sigma_threshold, timing_p=timing_p)
    timing["epochs"] = [{k: e[k] for k in ("epoch", "t_mid", "sigma", "depth", "at_scan_edge")} for e in times]
    metrics["timing"] = timing
    if timing["odd_even"] and timing["odd_even"]["significant"]:
        flags.append("odd_even_timing")
    if timing["linear"] and timing["linear"]["inconsistent"]:
        flags.append("timing_inconsistent")
    metrics.update(period=period, t0=t0, duration_days=duration)
    return tuple(flags), metrics


def decide(flags, *, base_disqualifying=frozenset(), extra=DISQUALIFYING) -> bool:
    """Pass/fail when the extended tests decide (``[vetting] decide = true``): the base decision's flags except the
    phase-0.5 ``secondary_eclipse`` (the all-phase search replaces it), plus :data:`DISQUALIFYING`."""
    flags = set(flags)
    base = set(base_disqualifying) - {"secondary_eclipse"}
    return not (flags & (base | set(extra)))

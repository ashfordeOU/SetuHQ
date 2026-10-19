"""Extended light-curve vetting after the Kepler and TESS SPOC Data Validation (DV) tests (Twicken et al. 2018,
doi:10.1088/1538-3873/aab694; Jenkins et al. 2016 for SPOC). These tests only add flags by default; the run
config's ``[vetting] decide = true`` turns the disqualifying ones into pass/fail (see :data:`DISQUALIFYING`).

* ``crowded``: the SPOC aperture's CROWDSAP (the fraction of the aperture flux that comes from the target) is below
  0.8, where the HEASARC "Understanding Crowding" page says reliability drops (ATLAS C9). CROWDSAP and FLFRCSAP
  (the fraction of the target's flux inside the aperture) are recorded either way.
* ``secondary_any_phase``: the DV weak-secondary test (ATLAS E3). A box with the transit's duration is slid over
  every phase of the folded light curve, away from the primary, and the most significant dip is reported with its
  phase, depth and significance. It is flagged when its significance reaches 7.1σ (the DV/TPS detection threshold)
  and is larger than the largest brightening found at any phase. That second condition is in the spirit of the
  Robovetter's model-shift uniqueness test (Coughlin et al. 2016, doi:10.3847/0067-0049/224/1/12): a dip no deeper
  than the noise's own excursions is not a secondary eclipse. This replaces the phase-0.5-only check for eccentric
  binaries, whose secondary is not at phase 0.5. The phase-0.5 value is reported beside it.
* ``odd_even_depth``: the DV odd/even depth test (ATLAS E2), measured here at every epoch with the fitted duration:
  the depth of odd and of even epochs, each with its error, and the difference in σ. Both parities must show a
  significant dip, as in :func:`exoplan.vet.vet_event`.
* ``odd_even_timing``: the DV odd/even epoch test. Each epoch's mid-time is measured with the fitted transit shape;
  a linear ephemeris with a separate offset for odd epochs is fitted, and the offset is flagged when it is
  significant. A slightly eccentric binary at twice the period shows it.
* ``timing_inconsistent``: the epochs' mid-times are inconsistent with a linear ephemeris (χ² p-value < 10⁻³).
  Real TTVs do this too, so it is evidence to look at, never a disqualifier.

Noise model. Depth errors use the subject's robust scatter divided by √n, the same model as the SNR check in
:mod:`exoplan.vet`; mid-time errors come from the χ² profile of each epoch, scaled up by √χ²ᵣ when the scatter
exceeds the stated errors. Red noise is not modelled beyond that, so significances on real data are optimistic
for long, shallow events.

DV parity (each exoplan test and its DV counterpart, Twicken et al. 2018 §III):

=========================  ===========================================  ==========================================
exoplan                    DV test                                       status
=========================  ===========================================  ==========================================
secondary_any_phase        weak secondary test (any phase)               implemented (albedo reported, not a flag)
odd_even_depth             odd/even transit depth comparison              implemented
odd_even_timing            odd/even epoch comparison                      implemented
timing_inconsistent        (no DV test; per-epoch timing)                 implemented, informational
crowded                    PDC crowding (CROWDSAP)                        recorded from the SPOC header
centroid_offset            difference-image centroid offsets              :mod:`exoplan.pixel`
centroid motion            centroid motion test (χ²₂)                     :mod:`exoplan.pixel`
ghost_suspect              optical ghost diagnostic (core vs halo)        :mod:`exoplan.pixel`
FAP (search.py)            statistical bootstrap                          implemented earlier (bounded by trials)
(none)                     rolling-band diagnostic                        not applicable (Kepler detector)
(none)                     shorter/longer period comparison               not implemented (one signal per subject)
=========================  ===========================================  ==========================================
"""

from __future__ import annotations

import math

import numpy as np
from scipy.stats import chi2 as chi2_dist

from exoplan.preprocess import mad_sigma

CROWDING_MIN = 0.8        # CROWDSAP below this: "reliability drops" (HEASARC Understanding Crowding, ATLAS C9)
SECONDARY_SIGMA = 7.1     # DV/TPS detection threshold, used for the weak-secondary test (Twicken et al. 2018)
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
    """CROWDSAP and FLFRCSAP from a light curve's provenance (:func:`exoplan.loaders.load_tess` records them from the
    SPOC header), and whether the aperture is crowded. ``crowded`` is None when CROWDSAP is not known."""
    provenance = provenance or {}
    crowdsap = _num(provenance.get("crowdsap"))
    flfrcsap = _num(provenance.get("flfrcsap"))
    return {"crowdsap": crowdsap, "flfrcsap": flfrcsap, "crowding_min": minimum,
            "crowded": None if crowdsap is None else bool(crowdsap < minimum)}


def _phase(time, period: float, t0: float) -> np.ndarray:
    """Orbital phase in [0, 1), with the primary transit at 0."""
    return np.mod((np.asarray(time, float) - t0) / period, 1.0)


def secondary_search(time, flux, *, period: float, t0: float, duration: float, step: float | None = None,
                     noise: float | None = None, min_points: int = 3) -> dict | None:
    """The most significant box dip of width ``duration`` at any phase away from the primary transit.

    Box centres run over the phase with a step of a quarter duration (``step``, days). A centre is excluded when its
    box would overlap the primary's box (within one duration of phase 0). The baseline is the median flux outside
    the primary; the depth at a centre is the baseline minus the mean flux in the box, and its σ is the robust
    scatter over √n. Returns the peak's phase, depth (ppm), σ (ppm) and significance, the largest brightening's
    significance (the same statistic with the sign reversed), the value at phase 0.5, and the number of box centres
    tried. None when the period or the data cannot support the search.
    """
    time = np.asarray(time, float)
    flux = np.asarray(flux, float)
    good = np.isfinite(time) & np.isfinite(flux)
    time, flux = time[good], flux[good]
    if period is None or period <= 0 or duration <= 0 or duration >= 0.5 * period or time.size < 10:
        return None
    phase = _phase(time, period, t0)
    dist0 = np.minimum(phase, 1.0 - phase) * period          # days from the nearest primary mid-time
    outside = dist0 > duration                               # clear of the primary box and its wings
    if outside.sum() < 10:
        return None
    noise = mad_sigma(flux[outside] - 1.0) if noise is None else noise
    if not np.isfinite(noise) or noise <= 0:
        return None
    baseline = float(np.median(flux[outside]))
    step = 0.25 * duration if step is None else step
    half = 0.5 * duration
    centres = np.arange(duration / period, 1.0 - duration / period + 1e-12, step / period)
    rows = []
    for c in centres:
        d = np.abs(phase - c)
        inside = np.minimum(d, 1.0 - d) * period <= half
        n = int(inside.sum())
        if n < min_points:
            continue
        depth = baseline - float(np.mean(flux[inside]))
        sigma = noise / math.sqrt(n)
        rows.append((float(c), depth, sigma, n))
    if not rows:
        return None
    snr = np.array([r[1] / r[2] for r in rows])
    i = int(np.argmax(snr))
    j = int(np.argmin(snr))
    c, depth, sigma, n = rows[i]
    # The grid can miss the true centre by up to half a step, which biases the depth low: refine around the peak
    # in steps of a fortieth of a duration (the trial count reported stays the coarse grid's).
    for cc in np.arange(c - step / period, c + step / period + 1e-12, duration / 40.0 / period):
        d = np.abs(phase - (cc % 1.0))
        inside = np.minimum(d, 1.0 - d) * period <= half
        k = int(inside.sum())
        if k < min_points or min(cc % 1.0, 1.0 - cc % 1.0) * period < duration:
            continue
        dd = baseline - float(np.mean(flux[inside]))
        if dd / (noise / math.sqrt(k)) > depth / sigma:
            c, depth, sigma, n = float(cc % 1.0), dd, noise / math.sqrt(k), k
    near_half = min(rows, key=lambda r: abs(r[0] - 0.5))
    return {
        "phase": c, "depth_ppm": depth * 1e6, "sigma_ppm": sigma * 1e6, "snr": depth / sigma, "n_points": n,
        "max_brightening_snr": float(-snr[j]), "n_trials": len(rows), "duration_days": duration,
        "phase_05": {"phase": near_half[0], "depth_ppm": near_half[1] * 1e6, "sigma_ppm": near_half[2] * 1e6,
                     "snr": near_half[1] / near_half[2]},
    }


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


def odd_even_depth_test(epochs: list[dict], *, sigma_threshold: float = SIGMA_THRESHOLD,
                        min_parity_snr: float = MIN_PARITY_SNR) -> dict | None:
    """Inverse-variance mean depth of odd and of even epochs with errors, and their difference in σ.

    ``significant`` needs both parities to show a dip of at least ``min_parity_snr`` (one lone transit cannot fake
    a mismatch) and |δ_odd − δ_even| > ``sigma_threshold`` × √(σ_odd² + σ_even²). None without both parities.
    """
    groups = {}
    for parity in ("odd", "even"):
        rows = [e for e in epochs if e["parity"] == parity and e["sigma"] > 0]
        if not rows:
            return None
        w = np.array([1.0 / e["sigma"] ** 2 for e in rows])
        d = np.array([e["depth"] for e in rows])
        groups[parity] = (float(np.sum(w * d) / np.sum(w)), float(1.0 / math.sqrt(np.sum(w))), len(rows))
    (do, so, no), (de, se, ne) = groups["odd"], groups["even"]
    combined = math.hypot(so, se)
    delta_sigma = abs(do - de) / combined if combined > 0 else 0.0
    both = min(do / so, de / se) >= min_parity_snr
    return {"odd_depth_ppm": do * 1e6, "odd_err_ppm": so * 1e6, "n_odd": no,
            "even_depth_ppm": de * 1e6, "even_err_ppm": se * 1e6, "n_even": ne,
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
        from exoplan.transitfit import transit_model

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
        out.append({"epoch": n, "parity": "odd" if n % 2 else "even", "t_predicted": float(mid),
                    "t_mid": float(mid + best), "sigma": float(sig * scale), "depth": float(amp[i]),
                    "chi2_red": float(chi[i] / dof), "n_points": int(t.size), "at_scan_edge": bool(edge)})
    return out


def _wls(design: np.ndarray, y: np.ndarray, sigma: np.ndarray):
    w = 1.0 / sigma ** 2
    a = design.T @ (design * w[:, None])
    cov = np.linalg.inv(a)
    beta = cov @ (design.T @ (w * y))
    chi = float(np.sum(w * (y - design @ beta) ** 2))
    return beta, cov, chi


def timing_test(epochs: list[dict], *, sigma_threshold: float = SIGMA_THRESHOLD, timing_p: float = TIMING_P) -> dict:
    """Linear-ephemeris consistency and the odd/even epoch offset from per-epoch mid-times (:func:`epoch_times`).

    * Linear: T_n = T0 + n P by weighted least squares, χ² with N − 2 degrees of freedom and its p-value
      (needs 3 or more epochs). ``inconsistent`` when p < ``timing_p``.
    * Odd/even: T_n = T0 + n P + Δ·[n odd]; Δ and σ_Δ from the fit's covariance, scaled by √χ²ᵣ when the fit has
      spare degrees of freedom and χ²ᵣ > 1 (needs 3 or more epochs with both parities). ``significant`` when
      |Δ|/σ_Δ > ``sigma_threshold``.
    """
    rows = [e for e in epochs if e["sigma"] > 0 and not e.get("at_scan_edge")]
    out: dict = {"n_epochs": len(rows), "o_minus_c_minutes": None, "linear": None, "odd_even": None}
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
        if 0 < odd.sum() < len(rows):
            beta, cov, chi = _wls(np.column_stack([np.ones_like(n), n, odd]), t, s)
            dof = len(rows) - 3
            scale = math.sqrt(max(1.0, chi / dof)) if dof > 0 else 1.0
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
        sec["threshold_sigma"] = secondary_sigma
        sec["significant"] = bool(sec["snr"] >= secondary_sigma and sec["snr"] > sec["max_brightening_snr"])
        if sec["significant"]:
            flags.append("secondary_any_phase")
    metrics["secondary"] = sec
    depths = epoch_depths(time, flux, period=period, t0=t0, duration=duration, noise=noise)
    oe = odd_even_depth_test(depths, sigma_threshold=sigma_threshold)
    metrics["odd_even_depth"] = oe
    if oe and oe["significant"]:
        flags.append("odd_even_depth")
    times = epoch_times(time, flux, flux_err, period=period, t0=t0, duration=duration,
                        template=shape_template(fit, duration))
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
